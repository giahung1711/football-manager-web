# FOOTBALL MANAGER — Web Edition (starter)

A multi-user Flask starter for the Football Manager project.

## Included
- Account registration and login (passwords are hashed).
- One independent save per account.
- Club selection and a dashboard.
- Squad page.
- SQLite for local development; PostgreSQL can be configured for deployment.

## Run locally
1. Install Python 3.10+.
2. Create and activate a virtual environment.
3. Install packages:
   `pip install -r requirements.txt`
4. Start:
   `python app.py`
5. Open `http://127.0.0.1:5000`.

## Before public deployment
- Set a long random `SECRET_KEY` environment variable.
- Set `DATABASE_URL` to a managed PostgreSQL database.
- Run with Gunicorn (the Procfile is included).
- Turn off Flask debug mode in production.
- Add CSRF protection, rate limiting, email verification, password reset, backups,
  and database migrations before opening registration to the public.

## Project structure
- `app.py`: routes, login and save loading.
- `models.py`: user and save database models.
- `game_engine.py`: independent game rules and starter squad data.
- `templates/`: HTML screens.
- `static/style.css`: visual theme.

This is the foundation, not the finished full game. Transfer market, player cards,
packs, tactics, fixtures, leagues and multiplayer competition are planned next.
