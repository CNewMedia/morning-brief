"""
Morning Brief — Dagelijks dagplan op basis van Calendar + ClickUp + Claude
"""

import os
import json
import datetime
import requests
import base64
from email import message_from_bytes
from dotenv import load_dotenv
import anthropic
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

load_dotenv()

CLICKUP_API_KEY = os.getenv("CLICKUP_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID")  # workspace ID
GMAIL_USER = os.getenv("GMAIL_USER", "christophe@cnip.be")

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
]


# ── Google Calendar ──────────────────────────────────────────────────────────

def get_calendar_events():
    """Haal events op van vandaag uit Google Calendar."""
    creds = None

    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    service = build("calendar", "v3", credentials=creds)

    now = datetime.datetime.utcnow()
    start_of_day = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    end_of_day = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    formatted = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        title = event.get("summary", "Geen titel")

        # Converteer naar leesbaar formaat
        if "T" in start:
            start_dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))
            time_str = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
        else:
            time_str = "Hele dag"

        formatted.append(f"- {time_str}: {title}")

    return formatted


# ── ClickUp ──────────────────────────────────────────────────────────────────

def get_clickup_tasks():
    """Haal alle open taken op die aan jou zijn toegewezen."""
    headers = {"Authorization": CLICKUP_API_KEY}

    # Haal teams/workspaces op
    if not CLICKUP_TEAM_ID:
        teams_resp = requests.get("https://api.clickup.com/api/v2/team", headers=headers)
        teams = teams_resp.json().get("teams", [])
        if not teams:
            print("❌ Geen ClickUp teams gevonden. Check je API key.")
            return []
        team_id = teams[0]["id"]
    else:
        team_id = CLICKUP_TEAM_ID

    # Haal taken op via /team/{id}/task
    params = {
        "assignees[]": "me",  # alleen jouw taken
        "statuses[]": ["Open", "in progress", "to do"],
        "include_closed": False,
        "subtasks": True,
    }

    resp = requests.get(
        f"https://api.clickup.com/api/v2/team/{team_id}/task",
        headers=headers,
        params=params,
    )

    if resp.status_code != 200:
        print(f"⚠️  ClickUp fout: {resp.status_code} — {resp.text[:200]}")
        return []

    tasks = resp.json().get("tasks", [])
    formatted = []

    for task in tasks[:30]:  # max 30 taken
        name = task.get("name", "Geen naam")
        priority = task.get("priority")
        prio_label = priority["priority"] if priority else "geen"
        due = task.get("due_date")
        due_str = ""
        if due:
            due_dt = datetime.datetime.fromtimestamp(int(due) / 1000)
            due_str = f" [deadline: {due_dt.strftime('%d/%m')}]"

        list_name = task.get("list", {}).get("name", "")
        formatted.append(f"- [{prio_label}] {name}{due_str} ({list_name})")

    return formatted



# ── Gmail ────────────────────────────────────────────────────────────────────

def get_unanswered_emails():
    """Haal mails op waar jij direct op moet reageren (To:, niet CC, nog niet geantwoord)."""
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    gmail = build("gmail", "v1", credentials=creds)

    # Zoek: direct aan jou gericht, niet van automatische senders, afgelopen 7 dagen
    query = (
        f"to:{GMAIL_USER} is:unread -from:noreply -from:no-reply "
        "-from:notifications@ -from:alerts@ -from:mailer@ "
        "-from:facebookmail.com -from:linkedin.com -from:twitter.com "
        "-category:promotions newer_than:7d"
    )

    result = gmail.users().messages().list(
        userId="me", q=query, maxResults=20
    ).execute()

    messages = result.get("messages", [])
    formatted = []

    # Sla kalender-accepts over (geen echte actie nodig)
    skip_subjects = ["geaccepteerd:", "accepted:", "voorlopig:", "tentative:"]

    for msg in messages[:15]:
        detail = gmail.users().messages().get(
            userId="me", messageId=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "To", "Cc", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        cc = headers.get("Cc", "")
        to = headers.get("To", "")
        date = headers.get("Date", "")

        # Sla over als jij in CC staat maar niet primair geadresseerde
        if GMAIL_USER not in to.lower() and GMAIL_USER in cc.lower():
            continue

        # Sla kalender-responses over
        if any(subject.lower().startswith(s) for s in skip_subjects):
            continue

        formatted.append(f"- Van: {sender} | {subject}")

    return formatted

# ── Claude prioritering ──────────────────────────────────────────────────────

def generate_morning_brief(events, tasks, emails):
    """Stuur alles naar Claude en krijg een dagplan + top 3 JSON terug."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    today = datetime.date.today().strftime("%A %d %B %Y")
    events_text = "\n".join(events) if events else "Geen meetings vandaag."
    tasks_text = "\n".join(tasks) if tasks else "Geen open taken gevonden."
    emails_text = "\n".join(emails) if emails else "Geen openstaande mails."

    prompt = (
        "Je bent een persoonlijke chief of staff voor een drukke marketingondernemer.\n"
        "Hij wil elke ochtend in 5 minuten weten wat hij die dag moet doen, in welke volgorde, en wanneer.\n\n"
        f"Vandaag is het {today}.\n\n"
        f"AGENDA VANDAAG:\n{events_text}\n\n"
        f"OPEN TAKEN IN CLICKUP:\n{tasks_text}\n\n"
        f"MAILS DIE ACTIE VEREISEN:\n{emails_text}\n\n"
        "Maak een helder dagplan met:\n"
        "1. **Top 3 prioriteiten voor vandaag** met korte uitleg waarom dit eerst\n"
        "2. **Voorgesteld dagschema** ingepland tussen de meetings, realistisch\n"
        "3. **Wat kan wachten** taken die bewust naar morgen/later verschoven worden\n"
        "4. **Mails die vandaag beantwoord moeten worden** met korte context per mail\n"
        "5. **Één ding om te delegeren** aan zijn junior marketeer (als relevant)\n\n"
        "Schrijf kort, direct, geen fluff. Max 350 woorden. Gebruik emoji spaarzaam.\n\n"
        "---\n"
        "BELANGRIJK: Sluit je antwoord ALTIJD af met dit blok (na de tekst, exact dit formaat):\n\n"
        "TOP3_JSON:\n"
        "[\n"
        '  {"title": "Taaknaam 1", "start": "HH:MM", "end": "HH:MM", "reden": "Korte reden"},\n'
        '  {"title": "Taaknaam 2", "start": "HH:MM", "end": "HH:MM", "reden": "Korte reden"},\n'
        '  {"title": "Taaknaam 3", "start": "HH:MM", "end": "HH:MM", "reden": "Korte reden"}\n'
        "]\n\n"
        "Gebruik realistische tijden die NIET overlappen met de agenda. Begin niet voor 08:30."
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    return message.content[0].text


# ── Calendar Blocking ────────────────────────────────────────────────────────

def parse_top3(brief_text):
    """Haal de TOP3_JSON uit de Claude response."""
    if "TOP3_JSON:" not in brief_text:
        return []
    try:
        json_part = brief_text.split("TOP3_JSON:")[1].strip()
        # Neem alleen het JSON array gedeelte
        start = json_part.index("[")
        end = json_part.rindex("]") + 1
        return json.loads(json_part[start:end])
    except Exception as e:
        print(f"   ⚠️  Kon TOP3_JSON niet parsen: {e}")
        return []


def block_tasks_in_calendar(top3_tasks):
    """Maak calendar events aan voor de top 3 taken."""
    if not top3_tasks:
        print("   ℹ️  Geen taken om te blokkeren.")
        return

    # Hergebruik credentials (token.pickle bestaat al na get_calendar_events)
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

    service = build("calendar", "v3", credentials=creds)
    today_str = datetime.date.today().isoformat()

    for i, task in enumerate(top3_tasks, 1):
        try:
            start_time = task["start"]  # "HH:MM"
            end_time = task["end"]
            title = task["title"]
            reden = task.get("reden", "")

            event = {
                "summary": f"🎯 {title}",
                "description": f"Morning Brief prioriteit #{i}\n\n{reden}",
                "start": {
                    "dateTime": f"{today_str}T{start_time}:00",
                    "timeZone": "Europe/Brussels",
                },
                "end": {
                    "dateTime": f"{today_str}T{end_time}:00",
                    "timeZone": "Europe/Brussels",
                },
                "colorId": "11",  # tomato rood = focus tijd
            }

            result = service.events().insert(calendarId="primary", body=event).execute()
            print(f"   ✅ Geblokkeerd: {start_time}-{end_time} → {title}")
        except Exception as e:
            print(f"   ⚠️  Fout bij aanmaken event '{task.get('title', '?')}': {e}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n🌅 Morning Brief wordt opgebouwd...\n")
    print("📅 Google Calendar ophalen...")

    try:
        events = get_calendar_events()
        print(f"   {len(events)} events gevonden")
    except FileNotFoundError:
        print("   ⚠️  credentials.json niet gevonden — zie README voor setup")
        events = []
    except Exception as e:
        print(f"   ⚠️  Calendar fout: {e}")
        events = []

    print("📬 Gmail ophalen...")
    try:
        emails = get_unanswered_emails()
        print(f"   {len(emails)} openstaande mails gevonden")
    except Exception as e:
        print(f"   ⚠️  Gmail fout: {e}")
        emails = []

    print("✅ ClickUp taken ophalen...")
    try:
        tasks = get_clickup_tasks()
        print(f"   {len(tasks)} taken gevonden")
    except Exception as e:
        print(f"   ⚠️  ClickUp fout: {e}")
        tasks = []

    print("🤖 Claude genereert je dagplan...\n")
    brief = generate_morning_brief(events, tasks, emails)

    # Splits brief tekst en JSON
    if "TOP3_JSON:" in brief:
        display_brief = brief.split("TOP3_JSON:")[0].strip()
    else:
        display_brief = brief

    print("=" * 60)
    print(display_brief)
    print("=" * 60)

    # Sla op als bestand
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"brief_{today_str}.txt"
    with open(filename, "w") as f:
        f.write(display_brief)
    print(f"\n💾 Opgeslagen als {filename}")

    # Calendar blocking
    print("\n📅 Top 3 taken blokkeren in Google Calendar...")
    top3 = parse_top3(brief)
    block_tasks_in_calendar(top3)
    print()


if __name__ == "__main__":
    main()
