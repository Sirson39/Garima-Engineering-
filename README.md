# Garima Engineering Consultancy Management System

Production-ready Django foundation for Garima Engineering Consultancy.

## Stack

* Python 3.13
* Django 5.2
* PostgreSQL
* Django templates
* HTMX
* Bootstrap 5
* Docker

## Features In This MVP

* Custom user model and role groups
* Secure login with lockout tracking
* Client register
* Project register with automatic numbering
* Configurable Naya Naksa and Abhilekhikaran workflows
* Revisioned document uploads
* Stage history and automatic task creation
* Physical file register and QR code generation
* Site visits, government records, municipality notes, and payments
* Dashboard, reports, and audit logs

## Local Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run migrations:

```bash
python manage.py migrate
```

4. Seed demo data:

```bash
python manage.py seed_demo_data
```

5. Start the development server:

```bash
powershell -ExecutionPolicy Bypass -File scripts/start_server.ps1
```

The local development application uses PostgreSQL only. Copy `.env.example` to `.env`, enter the password for the `siru_app` PostgreSQL role, and use the startup script above. It verifies the PostgreSQL backend, applies pending migrations, and starts the single development server at `http://127.0.0.1:8000/`. SQLite is reserved for automated test databases and cannot be used by normal application commands.

## Organization workspaces

Platform administrators can provision Professional Service Management and Retail
Management from the organization creation wizard. Both use the existing login,
organization membership, role permissions and PostgreSQL database.

* Professional Services Phase 1: clients, services, engagements, billing defaults,
  assignment-aware access, dashboard, roles and audit activity.
  See [architecture and scope](docs/professional-services-phase-one.md).
* Retail: products, locations, suppliers, customers, inventory, purchase receipts,
  sales, payment recording, full-sale returns, reports, roles and audit activity.
  See [architecture and scope](docs/retail-management.md). Start by creating a store
  location and products, then receive a purchase or record an opening-stock
  adjustment before posting the first sale.

Apply migrations with `python manage.py migrate`; run checks with
`python manage.py check` and tests with `python manage.py test`.

## Environment Variables

Set these values in your environment for production:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key |
| `DJANGO_DEBUG` | `true` or `false` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_HOST` | PostgreSQL host |
| `POSTGRES_PORT` | PostgreSQL port |
| `SESSION_IDLE_TIMEOUT_MINUTES` | Automatic session timeout |

## Docker

Build and run the application with Docker Compose:

```bash
docker compose up --build
```

The app container uses PostgreSQL from the compose file and is ready for the seeded demo workflow once migrations and the seed command are run.

## Backup And Restore

See [`docs/architecture.md`](docs/architecture.md) for the PostgreSQL backup and restore commands.

## Notes

* Uploaded files are stored outside the static assets directory and are served through authenticated views.
* The QR code endpoint generates a printable PNG for each project file.
* Workflow stages, numbering schemes, and document checklists are editable from the workflow catalogue and Django admin.
