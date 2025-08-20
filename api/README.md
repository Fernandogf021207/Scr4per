# Scr4per DB API and Scraper Orchestrator

This service exposes:
- Database endpoints: /profiles, /relationships, /posts, /comments, /reactions
- Scraper endpoint: /scrape to trigger scraping directly from platform scrapers

## Install

Create/activate your environment, then install API deps (includes Playwright):

```
pip install -r api/requirements.txt
python -m playwright install chromium
```

Apply DB schema and migration:

```
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/migrations/2025-08-20_add_friend_and_reactions.sql
```

## Run

```
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

## Scrape

POST /scrape

Body:
```
{
  "url": "https://www.facebook.com/some.user",
  "platform": "facebook",
  "max_photos": 5
}
```

Response (3 fields only):
```
{
  "Perfil objetivo": {"platform":"facebook","username":"some.user", ...},
  "Perfiles relacionados": [{"username":"u1","tipo de relacion":"seguidor"}, ...],
  "Tipo de relacion": ["seguidor","seguido","comentó"]
}
```

Notes:
- The API writes to platform-specific schemas (red_x, red_instagram, red_facebook).
- Facebook supports 'friend' in relationships and reactions persisted to {schema}.reactions.
