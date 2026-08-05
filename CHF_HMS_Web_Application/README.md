# CHF Hospital Management System — Web Application

A deployable Flask web application for Community Health Foundation Hospital.

## Included modules

- Secure staff login and role permissions
- Patient registration and automatic CHF patient numbers
- Patient search and medical history
- Clinical visits and vital signs
- Pharmacy inventory and low-stock alerts
- Billing, payments and outstanding balances
- Dashboard, user management and audit logs
- SQLite for local testing and PostgreSQL for online hosting
- Docker, Gunicorn and Render deployment files

## Run locally on Windows

1. Extract the project and open PowerShell in the project folder.
2. Run:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:SECRET_KEY="replace-this-with-a-long-random-value"
$env:ADMIN_PASSWORD="replace-this-with-a-strong-password"
python app.py
```

Open `http://127.0.0.1:5000`.

Default username is `admin`. The password is the value assigned to `ADMIN_PASSWORD`. If the variable is omitted on a brand-new database, the temporary password is `ChangeMe123!`.

## Put it online with Render

1. Create a GitHub repository and upload all project files.
2. In Render, select **New > Blueprint** and connect the repository.
3. Render reads `render.yaml` and creates the web service and PostgreSQL database.
4. When prompted, enter a strong value for `ADMIN_PASSWORD`.
5. Deploy and open the web address supplied by Render.

The health check is available at `/health`.

## Docker

```bash
docker build -t chf-hms .
docker run --rm -p 5000:5000 \
  -e SECRET_KEY="replace-this" \
  -e ADMIN_PASSWORD="replace-this" \
  chf-hms
```

## Production requirements

Before entering real patient information:

- Use PostgreSQL rather than an ephemeral SQLite database.
- Use HTTPS and set `COOKIE_SECURE=1`.
- Replace the initial administrator password immediately.
- Configure automated encrypted database backups.
- Restrict access by staff role and deactivate departed staff accounts.
- Complete privacy, consent, retention, downtime and breach-response policies.
- Have a qualified developer conduct security testing and database migrations.

This build is an operational MVP, not yet a certified electronic medical record system.
