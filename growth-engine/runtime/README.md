# Growth Runtime

Cloudflare Agents runtime for Zuhause am Bach and Die Wilden Wachauer Windis.

## What it does

- persists runtime state in the Agent/Durable Object
- ensures one daily cron callback (`0 7 * * *`, UTC)
- fetches the public Zuhause-am-Bach Booking worker JSON
- loads Windis JSON from `WINDIS_DATA_URL`, or falls back to the reviewed repository seed
- runs the existing Daily Planner
- stores pending approvals persistently
- exposes protected manual status/run/approve/reject endpoints
- never publishes content, sends external partner messages, or spends ad budget

## Setup

1. `cd growth-engine/runtime`
2. `npm install`
3. copy `.dev.vars.example` to `.dev.vars` for local development
4. configure `BOOKING_WORKER_URL`
5. configure a strong `ADMIN_TOKEN` as a Cloudflare secret for deployment
6. optionally configure `WINDIS_DATA_URL`
7. `npm run dev` or `npm run deploy`

The Agent is addressed through `/agents/growth-runtime/main/...` after deployment. Hitting an Agent route initializes the instance and `onStart()` ensures the daily schedule exists.

## Protected routes

Send `Authorization: Bearer <ADMIN_TOKEN>`.

- `GET /agents/growth-runtime/main/status`
- `POST /agents/growth-runtime/main/run-now`
- `POST /agents/growth-runtime/main/approve` with `{ "id": "...", "note": "..." }`
- `POST /agents/growth-runtime/main/reject` with `{ "id": "...", "note": "..." }`

`GET /health` is public and contains no business data.

## Safety

Approval only changes approval state. There is deliberately no executor for protected actions yet. Publishing, outbound messages and paid-media changes remain impossible from this runtime until separate connectors and explicit execution policies are added.
