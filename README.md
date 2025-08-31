# Gradio + PostgreSQL on Render (Free)

This repo contains a minimal Gradio app that stores audio clips (≤10 MB) in a PostgreSQL database on Render.

## Quick Deploy (Blueprint)

1. Fork this repo to your GitHub.
2. In Render, click **New → Blueprint** and select your fork.
3. Keep everything default. The provided `render.yaml` will:
   - Provision a free **PostgreSQL** database
   - Deploy a **Web Service** (Python) for the Gradio app
   - Wire `DATABASE_URL` automatically

When live, click your Render service URL to open the Gradio UI.

## Manual Deploy (if you don't use the Blueprint)

1. Create a **PostgreSQL** (Free) in Render. Copy the **Internal Database URL**.
2. Create a **Web Service** from this repo.
   - Environment: **Python 3**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`
   - Add Env Var `DATABASE_URL` = the Internal Database URL from step 1
3. Deploy. When Live, open the public URL.

## Verify data

In Render's Postgres **psql** or Data tab:
```sql
SELECT id, title, octet_length(audio_data) AS bytes, sample_rate, date
FROM audio_text
ORDER BY id DESC
LIMIT 10;
```

## Notes

- Audio is converted to WAV (PCM_16) before storing in `BYTEA` (Postgres).
- Free Postgres is 1 GB — ~100 recordings at 10 MB each (actual number depends on metadata and storage overhead).
- For larger scale or cheaper storage, move audio to object storage (S3, B2, Firebase Storage) and store only URLs in the DB.
