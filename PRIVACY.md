# Privacy Policy for FLC Fat Loss Coach

Effective date: 2026-06-12

FLC Fat Loss Coach is a Custom GPT action backend that helps manage meal planning, food inventory, body-weight logs, meal logs, and ingredient usage through a Google Sheets database controlled by the user.

## Information processed

When you use this GPT action, the following information may be sent to the backend and written to the connected Google Sheet:

- Food inventory items, quantities, units, storage location, purchase dates, use-by dates, and nutrition estimates.
- Morning body weight and related daily signals such as sleep, hunger, training, calories, protein, fast food, alcohol, night snacks, and notes.
- Planned or actual meal logs, macro estimates, ingredient usage, and shopping suggestions.
- Settings needed to generate daily coaching context.

The backend does not intentionally collect payment information, government identifiers, or unrelated personal data.

## How information is used

Information is used only to:

- Read current inventory and coaching context.
- Log weight, meals, grocery additions, and ingredient usage.
- Generate meal-planning context and suggested shopping lists.
- Maintain the user's Google Sheets database as the source of truth.

## Storage and access

Data is stored in the Google Sheet configured by the user. The backend accesses that spreadsheet through a Google service account whose credentials are configured in the hosting environment.

The backend is deployed on Render and uses environment variables for secrets such as the API key, spreadsheet ID, and Google service account credentials. Secrets should not be committed to GitHub or pasted into GPT instructions.

## Sharing

FLC Fat Loss Coach does not sell personal information. Data is shared only with the services required to operate the action:

- OpenAI ChatGPT, to invoke the Custom GPT action.
- Render, to host the backend.
- Google Sheets / Google APIs, to read and write the user's spreadsheet.

## Retention and deletion

Because the Google Sheet is the source of truth, the user controls most stored records directly in their spreadsheet. To delete logged inventory, weight, meal, or usage records, delete the corresponding rows from the Google Sheet.

To disable backend access, remove or rotate the Render environment variables, revoke the Google service account key, remove spreadsheet sharing for the service account, or delete the deployed service.

## Security

The API requires an `X-API-Key` header for authenticated operations. Keep the API key and Google service account credentials private. If a secret is exposed, rotate it immediately.

## Health and nutrition note

This project is a personal tracking and meal-planning tool. It is not medical advice and should not replace guidance from a licensed medical or nutrition professional.

## Contact

For questions about this policy or the FLC Fat Loss Coach project, use the GitHub repository owner contact path for this project:

https://github.com/ShijieL-FDA/flc
