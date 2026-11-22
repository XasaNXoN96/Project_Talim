# Online demo on Vercel

The real Django site (fictitious demo data) as a Vercel deployment. **For viewing only**: uploaded files are temporary, the second factor is
skipped and the antivirus is off (`config/settings/vercel.py`). Keep the project behind Vercel's own sign-in.

1. Create a Vercel project and connect a Postgres database (Neon) to it.
2. Environment variables: `DJANGO_SECRET_KEY`, `OTP_ENCRYPTION_KEYS` (a Fernet key), `SETUP_TOKEN`, `DJANGO_SETTINGS_MODULE=config.settings.vercel`.
3. `python tools/vercel_demo/build.py <folder>` and deploy that folder.
4. Once: `GET /api/setup?step=migrate`, then `?step=load` with the header `X-Setup-Token: <SETUP_TOKEN>`.
