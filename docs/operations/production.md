# Production operations

- Start: `docker compose -f deploy/compose/docker-compose.yml -f deploy/compose/docker-compose.production.yml --profile production up --build`.
- Use both Compose files; the production override fails closed until every required secret and HTTPS/host value is supplied.
- Keep API, Postgres, RabbitMQ, and Keycloak admin ports private. Expose only the TLS-terminated web reverse proxy.
- Run Alembic migrations before starting the production API; production startup never creates tables.
- Keycloak runs in production mode with an external Postgres database. The confidential OIDC client
  is `purrden-web`, uses PKCE S256, and returns through `/v1/auth/callback`.
- Backup: `powershell -File deploy/backup.ps1`; restore only during a maintenance window with `deploy/restore.ps1 -Backup PATH`.
- Load smoke: `python tools/load_test.py http://127.0.0.1:8000`.
- RabbitMQ delivery is at-least-once; `visitor_inbox.schedule_id` makes worker retries idempotent.
- The scheduler claims due rows with `SKIP LOCKED` on Postgres and writes an outbox event in the same transaction.
