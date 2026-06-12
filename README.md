# Fat Loss Coach Action Package

This package turns your Custom GPT into a real inventory/weight-management agent:

**Custom GPT → GPT Action → FastAPI backend → Google Sheets database**

The Google Sheet is the source of truth for:
- inventory
- morning weight
- meal logs
- ingredient usage
- food catalog
- settings

## Files

- `app.py` — FastAPI backend that reads/writes Google Sheets.
- `requirements.txt` — Python dependencies.
- `.env.example` — required environment variables.
- `openapi.action-probe.json` — temporary no-auth schema to prove Custom GPT Actions can reach Render.
- `openapi.health-only.json` — temporary authenticated schema to prove `X-API-Key` is configured correctly.
- `openapi.render.json` — final schema for the deployed Render backend.
- `openapi.yaml` — YAML equivalent kept for reference; prefer the JSON schemas for GPT Actions.
- `gpt_instructions_action_patch.md` — add to your Custom GPT Instructions.
- `morning_task_prompt.md` — prompt for your daily morning ChatGPT Task.
- `evening_task_prompt.md` — optional evening prompt to keep inventory accurate.

## Google Sheet setup

1. Upload/import `fat_loss_agent_google_sheets_template.xlsx` into Google Sheets.
2. Rename it if desired, e.g. `Fat Loss Coach DB`.
3. Copy the spreadsheet ID from the URL:
   - `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit...`
4. Create a Google Cloud project.
5. Enable Google Sheets API.
6. Create a service account.
7. Create/download a JSON key for the service account.
8. Share the Google Sheet with the service account email as Editor.

## Backend deployment

Deploy this directory to any Python web host that supports FastAPI, for example Render, Railway, Fly.io, Google Cloud Run, or a small VPS.

Start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

Environment variables:

```bash
API_KEY=use_a_long_random_secret
SPREADSHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=base64_encoded_service_account_json
TIMEZONE=America/Los_Angeles
```

Generate `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64`:

```bash
base64 -i service-account.json | tr -d '\n'
```

## GPT Action setup and debug flow

1. Open your Custom GPT editor.
2. Go to Configure → Actions → Create new action.
3. First paste `openapi.action-probe.json`.
4. Set Authentication to None.
5. Use the Action editor Test button for `actionProbe`.
6. Confirm Render logs show `GET /action-probe 200`.
7. Replace the schema with `openapi.health-only.json`.
8. Authentication: choose API Key.
9. API key type: Custom header.
10. Header name: `X-API-Key`.
11. Secret: use the same raw value as your backend `API_KEY` env var.
12. Use the Action editor Test button for `health`.
13. Confirm Render logs show `GET /health 200`.
14. Replace the schema with `openapi.render.json`.
15. Test operations in this order: `health`, `getInventory`, `getTrendSummary`, `getCoachContext`, `logWeight`.

Do not use normal chat messages to diagnose initial Action connectivity. The Action editor Test button gives a cleaner signal, and Render logs should show the exact route being called.

## Operational rule

The GPT should **read inventory every morning** and use it for meal planning.

It should **not deduct inventory just because it created a plan**. Deduct inventory only after you confirm actual consumption, for example:

> I ate according to plan. Deduct the used ingredients.

or

> I changed dinner: I used 250g chicken instead of 300g and no rice. Update inventory.

This prevents the database from drifting away from reality.

## Recommended task setup

Use two tasks:

1. Morning task: asks for weight, training, and runs plan generation.
2. Evening task: asks what you actually ate, then updates inventory.

The evening task is optional, but inventory accuracy depends on actual-consumption confirmation.
