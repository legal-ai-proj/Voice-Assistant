# AI Receptionist SaaS -- Voice Assistant

Multi-tenant AI receptionist platform for appointment-based local
businesses. First vertical: barbershops, with **Barber Shop On Main**
(San Antonio, TX) as the reference tenant. The voice agent (Vapi +
Twilio) is a first-class client of the same Booking Service the website
and admin dashboard use -- no client, including the AI, touches the
database directly.

## Architecture

```
Website / Admin Dashboard / Voice Agent (Vapi)
              |
      Booking Service (FastAPI)
              |
          Supabase (Postgres, Auth, Storage, RLS)
```

Every booking action -- check availability, create/reschedule/cancel an
appointment -- goes through the Booking Service exactly once. The Vapi
voice agent calls it via tool endpoints under `/api/v1/voice-tools/`;
the website will call the same underlying service functions through its
own API routes.

## Stack

- **Frontend**: React 19 + TypeScript, Vite, Tailwind v4, Framer Motion, TanStack Query, shadcn/ui
- **Backend**: FastAPI (Python 3.13), SQLAlchemy 2 (async), Pydantic v2
- **Database**: Supabase Postgres, with RLS scoped through a `chain_users` membership table
- **Voice**: Twilio (telephony) + Vapi (STT/TTS orchestration) + Claude (reasoning)
- **Deployment**: Railway (backend), Vercel (frontend)

## Data model

Every tenant is modeled as a **chain** with one or more **branches** --
a single-location shop is just a chain with one branch, so multi-location
growth never requires a schema migration. See `backend/app/models/` for
the SQLAlchemy models and the Supabase migration history for the full
schema (23 tables: chains, branches, staff, services, appointments,
customers, transactions, call logs, and supporting operational tables).

## Current status

- [x] Milestone 1 -- Architecture scaffold
- [x] Milestone 2 -- Database schema (live in Supabase, seeded with Barber Shop On Main)
- [ ] Milestone 3 -- Booking Service API (`check_availability` implemented; `create_appointment`, `reschedule_appointment`, `cancel_appointment` in progress)
- [ ] Milestone 4 -- Frontend (website, admin dashboard)
- [ ] Milestone 5 -- Voice agent integration (Vapi tool wiring, webhook ingestion)
- [ ] Milestone 6 -- Notifications (SMS/email reminders)
- [ ] Milestone 7 -- Polish, deployment, demo

## Local setup

### Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values
uvicorn app.main:app --reload
```
Docs at `http://localhost:8000/docs`.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env   # fill in real values
npm run dev
```

## Repo layout

```
backend/
  app/
    api/v1/        # FastAPI routes (thin -- delegate to services)
    services/       # Business logic (the Booking Service lives here)
    repositories/    # Raw data access, no business logic
    models/         # SQLAlchemy ORM models
    schemas/        # Pydantic request/response contracts
    core/           # Config, database engine, auth
  vapi-tools/       # Vapi tool JSON configs, one per voice tool
frontend/
  src/
    features/       # booking, customer, admin, voice, products, reviews, authentication
    shared/         # components, hooks, services, types, utils
```
