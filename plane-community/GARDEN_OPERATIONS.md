# The Garden Work Operations Runbook

This runbook covers the Garden-specific self-hosted Plane Community deployment in this repository. It intentionally does not use or modify GitHub Actions.

## Runtime boundary

Garden Work is deployed separately from Firebase Hosting.

- Garden member/admin/kiosk applications remain in the existing Firebase deployment.
- Garden Work runs at `https://work.thegarden.church` on Garden-controlled infrastructure.
- Human identity remains Firebase Authentication.
- Plane keeps its application state in PostgreSQL and object storage.
- PostgreSQL, Valkey, RabbitMQ, and the object-storage service are private Docker-network services. Only the reverse proxy publishes ports 80/443.
- Plane god-mode is not exposed through the public Garden Work proxy.

## Server prerequisites

Install:

- Linux with Docker Engine
- Docker Compose v2
- Node/Corepack only if running the root Church regression checks directly on this server
- enough persistent disk for PostgreSQL, object storage, Docker images, and backups

DNS must point `work.thegarden.church` at the server before public TLS validation can complete. The firewall should permit inbound TCP 80 and 443 only unless separate infrastructure requirements justify something else.

## Production secrets

Copy:

```bash
cp plane-community/.env.garden.example plane-community/.env.garden
```

Populate every required blank value. In particular:

- `SECRET_KEY`
- `LIVE_SERVER_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `RABBITMQ_PASSWORD`
- `AWS_SECRET_ACCESS_KEY`
- `MINIO_IMAGE` with a deliberately pinned, supported S3-compatible image
- `CERT_EMAIL` if desired for ACME account notices

Keep `.env.garden` outside version control. The root `.gitignore` ignores `.env.*`.

Mount a Firebase service-account credential at the path configured by `GARDEN_FIREBASE_CREDENTIALS_PATH`. The file must remain server-only and read-only inside the Plane backend containers.

The canonical Garden production values are:

```text
GARDEN_WORK_URL=https://work.thegarden.church
GARDEN_ADMIN_URL=https://thegarden.church/admin
CORS_ALLOWED_ORIGINS=https://thegarden.church
GARDEN_AUTH_ALLOWED_ORIGINS=https://thegarden.church
GARDEN_FIREBASE_PROJECT_ID=church-2612f
GARDEN_WORKSPACE_SLUG=the-garden
GARDEN_WORKSPACE_TIMEZONE=America/Chicago
```

## Preflight and verification

Before deploying:

```bash
bash scripts/plane-garden/preflight.sh plane-community/.env.garden
```

For the full local release gate:

```bash
bash scripts/plane-garden/verify.sh plane-community/.env.garden
```

`verify.sh` runs the existing Church typechecks/tests, builds the Garden Plane images from the vendored source, starts disposable PostgreSQL/Valkey infrastructure, and runs the Garden-specific Plane API test suite.

## Initial workspace bootstrap

The managed Plane workspace is persistent state. Bootstrap it only once.

1. Set `GARDEN_WORKSPACE_BOOTSTRAP=1`.
2. Run the deploy script.
3. Sign in to the existing Garden admin as a user with `work.admin` and open `/admin/work`.
4. Confirm the `The Garden` / `the-garden` workspace exists.
5. Set `GARDEN_WORKSPACE_BOOTSTRAP=0` immediately.
6. Run the deploy script again so automatic workspace creation is disabled.

A non-admin cannot bootstrap the workspace.

## Deploy

```bash
bash scripts/plane-garden/deploy.sh plane-community/.env.garden
```

The deploy script:

1. runs preflight;
2. builds Garden application images from `/plane-community` source;
3. starts private state services;
4. waits for object storage;
5. runs Django migrations;
6. starts API/workers/live/web/space/proxy;
7. waits for the Garden readiness endpoint;
8. verifies object storage and proxy health.

No `makeplane/plane-*` application image is required by the Garden production compose file.

## Status and stop

```bash
bash scripts/plane-garden/status.sh plane-community/.env.garden
bash scripts/plane-garden/stop.sh plane-community/.env.garden
```

`stop.sh` does not delete named persistent volumes.

## Backups

Create a consistent PostgreSQL + object-storage backup:

```bash
bash scripts/plane-garden/backup.sh plane-community/.env.garden /var/backups/garden-work
```

The backup script pauses write-capable Garden Work application services while capturing both stores, creates SHA-256 checksums and a manifest, then restarts only the services that had been running.

The backup does not contain `.env.garden` or Firebase credentials. Back up those secrets separately through the church's approved secrets-management process.

## Mandatory restore verification

Every backup intended for disaster recovery should be proven against disposable state:

```bash
bash scripts/plane-garden/verify-restore.sh /var/backups/garden-work/<timestamp>
```

This restores the PostgreSQL dump into a disposable PostgreSQL container and restores the object archive into a disposable Docker volume. It fails if checksums are invalid, database restoration fails, or the restored database has no public tables.

## Live restore

Live restore is deliberately destructive and requires an explicit flag:

```bash
bash scripts/plane-garden/restore.sh \
  plane-community/.env.garden \
  /var/backups/garden-work/<timestamp> \
  --confirm-destructive
```

Before altering production state, the script runs the disposable restore verification. It then restores PostgreSQL and object storage and redeploys the current vendored code through the normal health-gated deploy path.

## Offline / registry-independent image archive

After a successful source build:

```bash
bash scripts/plane-garden/export-images.sh plane-community/.env.garden /secure/path/garden-work-images.tar
```

On another Garden-controlled host:

```bash
bash scripts/plane-garden/load-images.sh /secure/path/garden-work-images.tar
```

This archive includes the locally built Garden application images and the pinned infrastructure images used by the deployment, allowing an operator to preserve the exact runnable image set independently of Plane's registry.

## Key rotation

### Firebase service account

1. Create/approve a replacement credential according to the Google/Firebase IAM process.
2. Replace the file at `GARDEN_FIREBASE_CREDENTIALS_PATH` atomically with restrictive file permissions.
3. Redeploy/restart the API and workers.
4. Verify `/admin/work` login.
5. Revoke the old credential after successful validation.

### Django `SECRET_KEY`

Changing `SECRET_KEY` invalidates existing Plane sessions and signed values. Schedule the rotation, update `.env.garden`, deploy, then have staff re-enter Work through `/admin/work`.

### PostgreSQL / RabbitMQ / object-storage passwords

Treat these as coordinated service rotations. Take and verify a backup first. Update the service credential and `.env.garden` together, restart the affected state service plus dependent app services, and run `status.sh` afterward.

## Rollback

Application-only rollback:

1. retain/identify the last known-good Church commit and Garden Work image archive;
2. take and verify a current backup before rollback if the system is still writable;
3. check whether the newer version introduced database migrations that are not backward-compatible;
4. if state is compatible, deploy the known-good source/images;
5. if state is not compatible, restore the backup taken under the known-good schema and then deploy the matching code;
6. run `status.sh` and manually test `/admin/work`, project navigation, work-item creation/editing, and sign-out.

Never solve an application regression by deleting the PostgreSQL or uploads volumes.

## Brand theme (web build)

The web app's look is chosen when the `web` image is built (`apps/web/core/lib/brand-config.ts`):

| Build arg             | Default  | Meaning                                                                                                                                                                     |
| --------------------- | -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VITE_BRAND_THEME`    | `garden` | `garden` keeps The Garden look. `hub` is a neutral look with a red accent, Inter, light and dark mode (`packages/tailwind-config/hub.css`). Any other value means `garden`. |
| `VITE_BRAND_NAME`     | empty    | Name beside the logo in the top bar. Hub theme only.                                                                                                                        |
| `VITE_BRAND_LOGO_URL` | empty    | Logo image (`https://...` or a same-site `/path`). Hub theme only. Logos are deployment assets: serve them from the deployment, do not commit them.                         |
| `VITE_BRAND_ICON_URL` | logo URL | Browser-tab icon. Hub theme only.                                                                                                                                           |

`docker-compose.notes.yml` passes them from `NOTES_BRAND_THEME`, `NOTES_BRAND_NAME`, `NOTES_BRAND_LOGO_URL` and `NOTES_BRAND_ICON_URL`. A Garden build ignores the name, logo and icon values. Change them, then rebuild `web`.

Use a single-colour dark logo on a transparent background: in dark mode the hub theme shows it inverted (white).

## Manual browser release QA

Before declaring a deployment production-ready, verify at minimum:

- Garden `/admin/work` with a `work.read` user
- promotion/demotion between member/admin behavior
- denied access after removing `work.read`
- unauthenticated Work entry returns to Garden rather than Plane-native login
- Plane-native sign-in/signup/password/OAuth URLs are unavailable
- sign-out leaves the Garden Firebase session intact
- Work home/project list/project detail
- board/list views
- create/edit/complete a work item
- comments/attachments if enabled
- desktop and mobile navigation
- loading/empty/error states
- browser cookie is Secure + HttpOnly on production HTTPS
- no `/god-mode` access through the public Work hostname
- normal member/admin/kiosk Church routes remain unaffected

## Upstream updates

Do not run the legacy destructive vendoring workflow after Garden modifications exist.

Stage an upstream release with:

```bash
bash scripts/plane-garden/update-upstream.sh <plane-tag>
```

Review and deliberately merge upstream changes into `/plane-community`, preserve the Garden patches listed in `GARDEN_CHANGES.md`, then run the full verification and backup/restore gate before deployment.
