# Security policy

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting for this repository:
`Security` → `Advisories` → `Report a vulnerability`.

Do not include live credentials, session cookies, personal data, or destructive proof-of-concept
payloads. Include the affected route/version, impact, and the smallest safe reproduction.

## Deployment boundary

The default Compose file is a localhost development stack. Internet deployment must use
`docker-compose.production.yml`, externally managed TLS, rotated secrets, database migrations,
and a production Keycloak database/configuration. The API, database, broker, and Keycloak admin
ports must remain private; only the web reverse proxy is public.
