# RAG Formulation Platform — Web App

Frontend for the RAG Formulation Platform: generate formulation reports, submit in-house experiment results, and download previous outputs.

## Run locally

1. **Install dependencies**

   ```bash
   cd webapp
   npm install
   ```

2. **Environment**

   Copy the example env and fill in your values:

   ```bash
   cp .env.local.example .env.local
   ```

   - **Clerk**: Create an app at [dashboard.clerk.com](https://dashboard.clerk.com), add Sign-in (e.g. Email). Set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY`.
   - **Single account**: Set `NEXT_PUBLIC_ALLOWED_CLERK_EMAIL` to the one allowed email (or leave empty to allow any signed-in user for dev).
   - **Backend**: Set `NEXT_PUBLIC_API_URL` to your FastAPI base URL (e.g. `http://localhost:8000` when running the backend locally).

3. **Start dev server**

   ```bash
   npm run dev
   ```

   Open [http://localhost:3000](http://localhost:3000). Sign in with your Clerk account (must match `NEXT_PUBLIC_ALLOWED_CLERK_EMAIL` if set).

## Features

- **Dashboard**: Backend status, saved report count, quick links.
- **RAG Report**: Enter API properties (BCS class, molecular weight, etc.), generate report, view markdown and download PDF. Report ID is shown for use in in-house experiments.
- **Account**: List and download previously generated reports (stored in browser).
- **In-house experiments**: Submit in-house experiment results by Report ID; optional lookup of entries per report.

## Deploy (e.g. Vercel)

- Set the same env vars in your hosting dashboard.
- Point `NEXT_PUBLIC_API_URL` to your FastAPI backend (e.g. GCP VM URL).
- Ensure the backend allows CORS from your frontend origin.
