# AI Hackathon 2026 - Unhoused Matchmaker
### Kōkua · AI-powered social worker matchmaker for Hawaiʻi · Team hawaii-nc

---

# **🌐 LIVE DEMO → http://kokua-frontend-prod.s3-website.us-east-2.amazonaws.com

---

Kōkua is an AI-powered web application that connects social workers with the most relevant community health resources for their unhoused clients in Hawaiʻi. Named after the Hawaiian value of helping others, Kōkua reduces the manual coordination burden on case workers by analyzing handwritten or typed intake notes and recommending ranked shelter matches with a geographic map view.

---

## The Problem

Social workers in Hawaiʻi currently use the VI-SPDAT (Vulnerability Index) as a manual Google Form and rely on HUD's Coordinated Entry System for resource matching — a slow, paper-heavy process. Over 90% of social workers take handwritten notes in the field. Finding the right shelter for a client requires knowing dozens of organizations, their current capacity, eligibility requirements, and service specialties.

Kōkua automates this.

---

## What It Does

1. **Intake notes input** — Social worker types or photographs handwritten notes about a client
2. **AI tag extraction** — Notes are processed into structured attributes (needs, urgency, veteran status, languages, children)
3. **Shelter matching** — Client attributes are matched against Hawaii shelter database using semantic similarity
4. **Map view** — Matched shelters appear as pins on an interactive Leaflet map with match scores
5. **Referral generation** — One-click draft referral letter addressed to the matched organization

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML/CSS/JS (Kōkua DC framework), Leaflet.js |
| Backend | FastAPI (Python 3.11) |
| Database | Supabase (PostgreSQL) |
| AI | Google Gemini API (gemini-2.0-flash) |
| Hosting | AWS S3 + Elastic Beanstalk |

---

## Project Structure

```
AI-Hackathon_2026/
├── frontend-ui/
│   ├── index.html          # Landing page
│   ├── console.html        # Main app with map and matching
│   └── support.js          # DC framework runtime
│
└── backend/
    ├── Procfile            # AWS Elastic Beanstalk startup
    ├── requirements.txt
    └── app/
        ├── main.py
        ├── api/routes.py
        ├── core/config.py
        └── services/
            ├── matching.py
            ├── supabase_client.py
            ├── document_ai.py
            └── referral.py
```

---

## Local Development

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Mac/Linux
pip install -r requirements.txt
```

Create `backend/.env`:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
GEMINI_API_KEY=your_gemini_key
```

```bash
uvicorn app.main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`

### Frontend

Open `frontend-ui/index.html` with Live Server in VS Code.

---

## AWS Deployment

### Frontend → S3
1. Create bucket `kokua-frontend-prod`
2. Enable static website hosting, index document `index.html`
3. Set public read bucket policy
4. Upload `index.html`, `console.html`, `support.js`

### Backend → Elastic Beanstalk
1. Zip contents of `backend/` folder
2. Create EB app → Python 3.11
3. Upload zip, set environment variables in Configuration → Environment properties

---

## Environment Variables

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase public anon key |
| `GEMINI_API_KEY` | Google Gemini API key |

Never commit `.env` to GitHub.

---

## Inspiration

Built at the AI Hackathon 2026 by team **hawaii-nc** from the University of Hawaiʻi. Inspired by the work of Hawaii Pacific Health, Hope Services Hawaii, and the Hawaii Community Health Workers Association.
