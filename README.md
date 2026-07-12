# Transport Booking Website

Flask-based transport booking web application with:
- Customer booking form
- Admin dashboard and booking management
- Truck inventory tracking
- Quotation calculation

## Can we deploy this with Streamlit?

This project is **Flask**, not Streamlit.

- If you want to keep this code as-is: deploy on a Flask-friendly host (Render, Railway, Fly.io, etc.).
- If you want Streamlit Cloud specifically: the UI/routes would need to be rewritten in Streamlit.

## Run locally

1. Create and activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
pip install -r requirements.txt
```

3. Set environment variables (PowerShell example)

```powershell
$env:FLASK_SECRET_KEY = "change-this-to-a-random-secret"
$env:ADMIN_USER = "admin"
$env:ADMIN_PASS = "change-this-password"
$env:ORS_API_KEY = "your-openrouteservice-key"
```

3. Start app

```powershell
python app.py
```

Open: http://localhost:5000

## Make it public (Railway)

1. Push this repo to GitHub.
2. In Railway, create a new project from the GitHub repo.
3. Configure:
- Runtime: `Python`
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --bind 0.0.0.0:$PORT wsgi:application`
4. Add environment variables in Railway:
- `PYTHON_VERSION` = `3.11.11`
- `FLASK_SECRET_KEY` (required, strong random value)
- `ADMIN_USER` (required)
- `ADMIN_PASS` (required)
- `ORS_API_KEY` (optional but recommended)
5. Deploy.

Your public URL will look like: `https://your-service-name.up.railway.app`

## Important production notes

- Data persistence:
	- This app uses local SQLite file (`transport_booking.sqlite`).
		- On free tiers, ephemeral filesystem may reset on redeploy/restart.
		- For reliable production data, migrate to managed Postgres.
	- Security:
		- Never use default admin password in production.
		- Keep `FLASK_SECRET_KEY` private and strong.
	- Deployment:
		- Production servers should run `gunicorn --bind 0.0.0.0:$PORT wsgi:application`.
		- `wsgi.py` exposes the Flask app in a standard format for hosts like Railway and Fly.io.

## Files added for deployment

- `requirements.txt`: Python dependencies
- `Procfile`: process declaration (`gunicorn wsgi:application`)
- `.env.example`: environment variable template
- `.python-version`: pins the Python runtime for the host
