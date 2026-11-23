# Wine Journal

A private wine journal: log bottles, add tasting notes and scores, attach label photos, and export everything to CSV. Mobile-first, available in French (default) and English.

Stack: Flask + Gunicorn, MariaDB, Docker Compose. Accounts are invite-only: an admin creates every user.

## Quick start

Copy the project to your server, edit `.env` (see below), then build and start.

```bash
docker compose up -d --build
```

The app listens on port `5000` at `http://<server-ip>:5000`.

## Configuration

Everything is set in `.env`, next to `docker-compose.yaml`. Replace every placeholder before the first start.

| Variable | Purpose |
| --- | --- |
| `DB_PASSWORD` | Password of the app's database user |
| `DB_ROOT_PASSWORD` | MariaDB root password |
| `SECRET_KEY` | Signs session cookies. Use a long random value |
| `ADMIN_EMAIL` | Email of the admin account |
| `ADMIN_USERNAME` | Username used if the admin has to be created (default `admin`) |
| `ADMIN_PASSWORD` | Password for that new admin, 12+ characters |

Generate strong values with:

```bash
openssl rand -hex 32
```

`DB_PASSWORD` is only applied the first time the database volume is created. Changing it later won't update the existing database.

## Users and admins

There is no public sign-up. On start, the app makes `ADMIN_EMAIL` an admin: it promotes the account if it exists, or creates it from `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Once `ADMIN_EMAIL` is set, that account is promoted again on every restart.

Admins manage everyone else from the **Utilisateurs / Users** page (`/admin/users`): create users, choose their language, and grant or remove admin rights. You can't change your own role, so at least one admin always remains.

If you're locked out, or want to reset the admin password, run:

```bash
docker compose exec web flask --app run create-admin you@example.com --username yourname
```

It prompts for a password (12+ characters). It creates the account, or resets the password and grants admin if it already exists.

## Language

French is the default. Each user's language is saved on their account, and the EN / FR links in the menu switch it at any time.

## Data and backups

Two named volumes hold everything: `wine_db_data` (database) and `wine_uploads` (label photos).

```bash
# database dump
docker compose exec db sh -c 'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" winejournal' > backup.sql

# photos
docker compose cp web:/app/static/uploads ./uploads-backup
```

Users can also download their own wines from the **CSV** link in the menu.

## Updating

After changing code or `.env`, rebuild and recreate the containers. A plain `restart` won't pick up either.

```bash
docker compose up -d --build
```

## HTTPS

The app serves plain HTTP on port 5000. For anything beyond your LAN, put it behind a reverse proxy (Traefik, Caddy, nginx) that handles TLS, and stop publishing port 5000 to the host.

## Troubleshooting

Check the app logs first.

```bash
docker compose logs web --tail 50
```

- **Can't log in as admin:** run the `create-admin` command above.
- **Web container can't reach the database:** the database volume was created with a different `DB_PASSWORD` than the one in `.env` now. Restore the old value, or wipe the volume (this deletes all data): `docker compose down -v`.
- **Log says `ADMIN_EMAIL is not set`:** nobody can create users until it's set. Add it to `.env` and rebuild.
