# 🌅 Morning Brief

Elke ochtend in 5 minuten een helder dagplan op basis van je Google Calendar en ClickUp taken.

---

## Setup (eenmalig, ~15 minuten)

### 1. Keys instellen

Kopieer `.env.example` naar `.env` en vul in:

```bash
cp .env.example .env
```

- **CLICKUP_API_KEY** → ClickUp → Settings (rechtsonder) → Apps → API Token
- **ANTHROPIC_API_KEY** → console.anthropic.com → API Keys

### 2. Google Calendar koppelen

Je hebt een `credentials.json` nodig van Google:

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Maak een nieuw project aan (bijv. "Morning Brief")
3. Ga naar **APIs & Services → Enable APIs** → zoek **Google Calendar API** → enable
4. Ga naar **APIs & Services → Credentials**
5. Klik **Create Credentials → OAuth client ID**
6. Kies **Desktop app** → geef een naam → Create
7. Download het JSON bestand → hernoem naar `credentials.json` → zet in deze map

De eerste keer dat je het script draait, opent er een browser om toegang te geven. Daarna wordt dit onthouden (`token.pickle`).

### 3. Dependencies installeren

```bash
pip install anthropic requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client python-dotenv
```

### 4. Draaien

```bash
python morning_brief.py
```

---

## Elke ochtend automatisch draaien

### Mac (via cron):
```bash
crontab -e
```
Voeg toe (draait elke dag om 08:00):
```
0 8 * * 1-5 cd /pad/naar/morning-brief && python morning_brief.py
```

### Windows (Task Scheduler):
Maak een taak aan die `python morning_brief.py` uitvoert om 08:00.

---

## Output voorbeeld

```
============================================================
🗓️ TOP 3 VOOR VANDAAG

1. 🔴 Client X campagne review afronden
   → Deadline vandaag, blokkeert je junior

2. 🟠 Offerte Y versturen
   → Al 2 dagen uitgesteld, klant wacht

3. 🟡 Weekly check-in junior voorbereiden
   → 15 min werk, geeft haar de rest van de week structuur

📅 DAGSCHEMA
09:00 - 09:30 → Taak 1 (campagne review)
09:30 - 10:30 → Meeting: Klant Z
10:30 - 11:00 → Taak 2 (offerte)
...

⏳ KAN WACHTEN
- Blog update → geen deadline, volgende week
- LinkedIn post → junior kan dit oppakken

👩‍💼 DELEGEER AAN JUNIOR
- Social media scheduling voor volgende week
============================================================
```

---

## Problemen?

- **ClickUp geeft geen taken terug** → controleer of je API key klopt en je taken ook echt aan jou zijn toegewezen in ClickUp
- **Google Calendar werkt niet** → verwijder `token.pickle` en draai opnieuw (nieuwe login)
- **Lege output** → voeg `CLICKUP_TEAM_ID` toe aan `.env` (te vinden in je ClickUp URL: app.clickup.com/**123456**/...)
