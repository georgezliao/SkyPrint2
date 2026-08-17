# SkyPrint

**Clean aviation intelligence. Carbon transparency at every altitude.**

SkyPrint is a climate-tech platform that reveals the hidden climate impact of aviation — especially contrails, which account for up to 57% of aviation's warming effect but remain invisible to travelers. It combines scientific modeling, AI-driven decision intelligence, and real-time behavioral nudges to help travelers, airlines, and advocates make cleaner choices.

## Why It Matters

- **Contrails cause up to 57%** of aviation's total warming effect — often 2-4x more than CO2 alone
- **Small altitude changes** (1,000-2,000 ft) can avoid most contrail-forming regions with <1% fuel penalty
- **91% of airlines** don't use contrail avoidance software — SkyPrint bridges this gap with consumer transparency

## Core Systems

### 1. Contrail Engine (Python/PyContrails)
Scientific contrail modeling using the CoCiP (Contrail Cirrus Prediction) model. Predicts contrail formation probability, radiative forcing, and optimal altitudes along flight trajectories using NOAA GFS weather data. Falls back to Schmidt-Appleman Criterion when full CoCiP isn't available.

### 2. Decision Intelligence (Next.js)
Flight comparison and airline scoring that ranks options by **total climate impact** — a weighted formula of CO2 emissions (40%) and contrail radiative forcing (60%). Integrates Aviationstack for flight data, OpenSky for real-time trajectories, and SerpApi for route-level CO2 benchmarks across 28 airlines.

### 3. Airline Report Card
Environmental grading system (A through F, with plus/minus granularity) scoring airlines across five weighted categories:

| Category | Weight | What It Measures |
|----------|--------|-----------------|
| Contrail Avoidance | 30% | Active contrail avoidance programs |
| Fleet Efficiency | 25% | Fuel efficiency (L/100pax-km) adjusted for fleet age |
| SAF Adoption | 20% | Sustainable aviation fuel usage % |
| Route Optimization | 15% | Operational efficiency and dispatch modernization |
| Emissions Trajectory | 10% | Year-over-year improvement signals |

Airlines are ranked into tiers: **Sky Saints** (A-), **Clean Cruisers** (B-), **Middle of the Pack** (C), **Greenwash Gold Medalists** (D), and **Contrail Criminals** (F).

### 4. Human Interface Layer

- **Aero** — Context-aware AI guide powered by Gemini 2.5 Flash. Not a chatbot — a proactive system that explains contrail science, flight impact, and nudges users toward cleaner choices. Supports voice interaction via ElevenLabs (speech-to-text with Scribe v1, text-to-speech with Rachel voice).

- **Photon** — Lifecycle notification system that delivers real iMessage notifications to users via spectrum-ts. When a user books a flight:
  1. **Booking confirmation** — immediate iMessage with CO2 estimate and contrail risk
  2. **Greener alternative nudge** — if a lower-impact flight exists on the same route (>10% better), Photon texts the user 15 seconds after booking with the comparison and savings
  3. **Pre-flight contrail forecast** — 24h before departure with atmospheric conditions
  4. **Post-flight impact summary** — after landing with CO2 savings, tree equivalents, and car mile equivalents

### 5. K2 Climate Intelligence (K2 Think V2)
AI-generated environmental analysis via the MBZUAI K2 Think V2 reasoning model:
- **Airline reports** — Executive summaries, contrail analysis, fleet assessments, SAF outlooks, and grade justifications
- **Scoring narratives** — Contextual explanations for each airline's environmental grade
- **Government reports** — Compliance-ready environmental improvement reports for tax deductions and stipends
- **Non-profit reports** — Advocacy targeting based on contrail mitigation gaps

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), React 19, Tailwind CSS v4, shadcn/ui, Framer Motion |
| AI | AI SDK v6, Gemini 2.5 Flash (via Vercel AI Gateway), K2 Think V2 (MBZUAI), ElevenLabs |
| Backend | Next.js API Routes, Zod v4 |
| Contrail Engine | Python 3.12, FastAPI, PyContrails (CoCiP), NOAA GFS, Open-Meteo |
| Notifications | Photon — spectrum-ts iMessage delivery |
| Deploy | Vercel (frontend + API), DigitalOcean (contrail engine) |

## Architecture

```
User → Flight Search    → Aviationstack / SerpApi
     → Trajectory       → Great-circle interpolation / OpenSky
     → Weather          → NOAA GFS (Open-Meteo)
     → Contrail Model   → PyContrails CoCiP / SAC fallback
     → Impact Score     → CO2 (40%) + Contrail RF (60%)
     → K2 Intelligence  → MBZUAI K2 Think V2 reasoning
     → Aero Explains    → Gemini streaming + ElevenLabs voice
     → User Books       → Knot booking flow
     → Photon Fires     → flight_booked (now) → greener_alternative (15s) → pre_flight_24h → post_flight
     → iMessage         → spectrum-ts → user's phone from Photon
```

### Demo Flow
1. User searches flights on `/compare` (e.g., JFK → Madrid)
2. Flights load ranked by total climate impact with contrail risk badges
3. **Aero** proactively explains the contrail impact difference between options
4. User selects a flight → booking modal with phone number field
5. **Photon** immediately sends iMessage booking confirmation with CO2 and contrail data
6. If a greener alternative exists → **Photon sends a nudge 15 seconds later** with the airline, price, and % impact reduction
7. 24h before flight → **pre-flight contrail forecast** via iMessage
8. After landing → **post-flight impact summary** with tree/car-mile equivalents
9. User can view full airline report cards on `/airlines` with K2-generated intelligence

## Getting Started

### Prerequisites
- Node.js 20+
- Python 3.11+ (for contrail engine)
- API keys (see `.env.local.example`)

### Setup

```bash
# Install dependencies
npm install

# Copy environment variables
cp .env.local.example .env.local
# Fill in your API keys in .env.local

# Start development server
npm run dev
```

### Contrail Engine (Python)

```bash
cd services/contrail_engine
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

## Pages

| Route | Description |
|-------|-------------|
| `/` | Landing page with platform overview and mission |
| `/compare` | Flight comparison with booking → Photon notifications → Aero guidance |
| `/compare/detail` | Side-by-side flight comparison with contrail gauges, carbon cost analysis, and booking |
| `/airlines` | Airline Report Card — rankings with plus/minus grades, category breakdowns, K2 narratives |
| `/airline/[code]` | Full airline environmental report with K2 Climate Intelligence |
| `/simulate` | Route altitude optimization — baseline vs contrail-optimized trajectory |
| `/dashboard` | User trip history and cumulative climate stats |
| `/daily` | Daily climate brief |
| `/mission` | About the mission |

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/api/compare-flights` | POST | Full flight comparison pipeline (search → contrail prediction → impact scoring) |
| `/api/simulate-route` | POST | Altitude optimization simulation |
| `/api/score-airline` | POST | Single airline scoring with K2 Think narrative and full report |
| `/api/rankings` | GET | All 28 airlines ranked by environmental score |
| `/api/reports` | POST | K2 Think report generation (government/nonprofit) |
| `/api/aero/chat` | POST | Gemini streaming chat with tool calls (Aero) |
| `/api/aero/voice` | POST | ElevenLabs text-to-speech |
| `/api/aero/transcribe` | POST | ElevenLabs speech-to-text (Scribe v1) |
| `/api/photon/trigger` | POST | Dispatch booking notifications + greener alternative nudge via iMessage |
| `/api/photon/cron` | GET | Cron handler for scheduled Photon events |

## Environment Variables

See `.env.local.example` for all required variables:
- `AVIATIONSTACK_API_KEY` — Flight search data
- `SERPAPI_KEY` — Google Flights CO2 scraping
- `GOOGLE_AI_API_KEY` — Gemini 2.5 Flash for Aero
- `K2_THINK_API_KEY` — K2 Think V2 for airline reports and narratives
- `ELEVENLABS_API_KEY` — Voice synthesis and transcription
- `PHOTON_PROJECT_ID` / `PHOTON_PROJECT_SECRET` — spectrum-ts iMessage delivery
- `CONTRAIL_ENGINE_URL` — PyContrails CoCiP microservice

## License

MIT
