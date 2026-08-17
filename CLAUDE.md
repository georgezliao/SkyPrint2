@AGENTS.md

# SkyPrint Project

Climate-tech platform for clean aviation intelligence.

## Structure

- `src/` — Next.js App Router frontend + API routes
- `services/contrail_engine/` — Python FastAPI microservice (PyContrails CoCiP)
- `src/lib/types/` — Shared TypeScript type definitions
- `src/lib/clients/` — External API clients
- `src/lib/ai/` — Aero AI system (Gemini, tools, prompts)
- `src/lib/photon/` — Lifecycle notification system (spectrum-ts)
- `src/lib/pipeline/` — Core orchestration logic
- `src/lib/db/` — Drizzle ORM schema + queries (Supabase Postgres)

## Commands

- `npm run dev` — Start Next.js dev server
- `npm run build` — Production build
- `npm run lint` — ESLint
- `cd services/contrail_engine && uvicorn app.main:app --reload` — Start Python service

## Conventions

- Next.js 16 App Router with `src/` directory
- Tailwind CSS v4 + shadcn/ui for components
- AI SDK v6 for Gemini integration
- Zod for validation
- Drizzle ORM for database
- Use `@/*` import alias
