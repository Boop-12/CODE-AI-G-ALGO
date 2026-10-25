# Deployment Runbook

## Local development
1. Confirm Docker Desktop is running.
2. Ensure `.env` exists by copying `.env.example` if needed.
3. Start the services with Docker Compose.
4. Validate the backend health endpoint and frontend loads.
5. Run the project tests before release signoff.

## Production preparation
1. Set a strong random secret key.
2. Enable HTTPS origins and secure cookies.
3. Configure SMTP and email verification delivery.
4. Confirm the database is PostgreSQL and migration-safe.
5. Validate admin MFA setup and user access privileges.
6. Run final smoke tests against the deployed instance.

## Rollback
- use the project Docker and backup tooling from `deploy/*`
- keep database backups before any migration
- revert to the last known-good image or compose state if validation fails

## Safety rules
- never configure live broker credentials in the local or staging app
- never expose real secrets in committed files
- keep local testing isolated from production data
