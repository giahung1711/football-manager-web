# FOOTBALL MANAGER WEB

Flask + Flask-Login + Flask-SQLAlchemy, PostgreSQL via `DATABASE_URL`.

## Features
- Account registration/login; one saved career per account.
- Five clubs with original starting XI and five substitutes.
- Squad view and same-position substitutions.
- Transfer market: buy players and sell substitutes/extra players.
- Player packs: Bronze, Silver, Gold and GOAT.
- Player card upgrades from +0 to +5 with original success rates/cost scaling.
- Match simulation, results, rewards, points and weekly progression.
- Formation selection and finance overview.
- Game state persists in the user's `GameSave` JSON row in PostgreSQL.

## Deploy
Keep `DATABASE_URL` configured to the existing PostgreSQL database. Do not delete/reset the database. Keep a stable random `SECRET_KEY` environment variable. Install from `requirements.txt`; start command is in `Procfile`.

Existing saves using the earlier `players` JSON format are normalized on first game page load: the existing 11 players and budget/progress are retained, and the five default substitutes are added. No user or save rows are deleted.
