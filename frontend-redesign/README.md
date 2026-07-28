# CareSync redesign

An isolated React 19 + TypeScript + styled-components rebuild. The original application remains available on port `5173`; this workspace uses strict port `5174` and its own cloned FastAPI service on `3002`.

## Run

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:5174`.

The cloned PostgreSQL database is an authorized write sandbox. Features remain read-only only until their write contracts, validation, recovery behavior, and tests are migrated into this interface.

## Migration rule

The legacy frontend is a behavioral specification, not a component library. A route moves only when its API contract, safety rules, checkpoint behavior, accessibility, and tests move with it.
