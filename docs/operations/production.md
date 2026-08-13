# Production operations

- Start: `docker compose -f deploy/compose/docker-compose.yml --profile production up --build`.
- Replace every development password and set secure-cookie/public URL/Keycloak values before exposure.
- Keycloak client: confidential OIDC client `purrden-web`, PKCE S256, callback `/v1/auth/callback`.
- Backup: `powershell -File deploy/backup.ps1`; restore only during a maintenance window with `deploy/restore.ps1 -Backup PATH`.
- Load smoke: `python tools/load_test.py http://127.0.0.1:8000`.
- RabbitMQ delivery is at-least-once; `visitor_inbox.schedule_id` makes worker retries idempotent.
- The scheduler claims due rows with `SKIP LOCKED` on Postgres and writes an outbox event in the same transaction.
