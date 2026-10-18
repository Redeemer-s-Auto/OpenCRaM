# OpenCram

The customized Plane Community Edition application extracted from [yadasa/church](https://github.com/yadasa/church). This copy preserves the Garden Work UI, Firebase identity bridge, authorization integration, and self-hosting configuration.

## Source

- Church commit: `c9e4eef890127f5fadff04d94ae42f346907c831` (October 18, 2026).
- `plane-community/`: complete tracked Plane application, packages, lockfile, Docker configuration, and upstream notices, copied without modification.
- `scripts/plane-garden/`: deployment, backup, restore, and maintenance tools. Verification is adapted to check Plane without the Church root workspace.
- Original license and copyright notices remain at the root and within `plane-community/`.

The original Church repository is unchanged. This is a source snapshot with a fresh Git history. Church frontend apps, Cloud Functions, credentials, databases, local environment files, dependencies, and build output are outside this extraction. Nested upstream workflow files remain under `plane-community/.github/`; they are not active repository-root Actions workflows.

## Development

Use Node.js 22.18 or newer and the pnpm version pinned in `plane-community/package.json`.

```bash
cd plane-community
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

For API and infrastructure setup, follow [CONTRIBUTING](plane-community/CONTRIBUTING.md) and the checked-in Compose configuration. Check the extraction boundary from this repository's root:

```bash
node scripts/plane-garden/verify-boundary.mjs
```

## Garden integration and self-hosting

The copied Garden configuration still depends on the existing Firebase project, access projections, Garden admin application, and optional Church webhook functions. Copying the source does not create those services or replace authentication with an independent OpenCram account system. Existing domains, branding, project IDs, and integration defaults are retained from the source.

Before starting a separate instance, choose its domains, Firebase integration, storage, secrets, and database volumes. The checked-in `.env.garden.example` contains the original deployment's public defaults, including its bind address. Review those values before use.

```bash
cp plane-community/.env.garden.example plane-community/.env.garden
# Populate and review environment values and provide Firebase credentials.
bash scripts/plane-garden/preflight.sh plane-community/.env.garden
bash scripts/plane-garden/verify.sh plane-community/.env.garden
bash scripts/plane-garden/deploy.sh plane-community/.env.garden
```

Install Plane dependencies before running `verify.sh`. It checks Plane types and lint, builds application images, and runs the Garden API suite in disposable Docker infrastructure. Church-wide checks remain in the original repository.

The [original operations runbook](plane-community/GARDEN_OPERATIONS.md) describes the retained Garden deployment. Its references to Church-wide regression checks and Church deployment history describe the original repository; use the commands above for this extraction. See also [Garden changes](plane-community/GARDEN_CHANGES.md) and [access projection](plane-community/GARDEN_ACCESS_PROJECTION.md).

## Notices

Plane-covered material retains its [AGPL license](plane-community/LICENSE.txt) and [copyright notices](plane-community/COPYRIGHT.txt). Original first-party material remains subject to the preserved [root license](LICENSE.md) and [third-party notices](THIRD_PARTY_NOTICES.md). The OpenCram repository name does not change those terms.
