UniAttend UI Polish (CSS-only patch)

Purpose: Improve shared visual styling for Admin, Lecturer and Student without changing Python routes, database logic, or templates.

Apply:
1. Back up your current app/static/css/style.css.
2. Copy this ZIP's app/static/css/style.css to your project at app/static/css/style.css, replacing the existing file.
3. Rebuild the web container:
   docker compose up -d --build web
4. Hard refresh the browser with Ctrl+Shift+R.

This patch only replaces the shared stylesheet. It does not modify .env, config.py, database, routes, or data.