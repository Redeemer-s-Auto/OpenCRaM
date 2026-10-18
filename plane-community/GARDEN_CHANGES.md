# Garden Plane Fork Changes

This file records The Garden-specific changes made to the vendored Plane Community Edition source.

Upstream pin: `makeplane/plane` `v1.4.2`

## Maintenance rules

1. Do not run the legacy `Vendor Plane Community Edition` workflow after Garden modifications have begun. That workflow intentionally replaces the entire `plane-community/` directory from upstream and would erase this fork's changes.
2. Do not edit or repurpose existing GitHub Actions workflows as part of the Garden Plane integration. Other agents may be using them.
3. Use `scripts/plane-garden/update-upstream.sh` for future upstream refreshes. It stages an upstream copy separately and never overwrites `plane-community/` automatically.
4. Keep Plane outside the root Church pnpm workspace. Church and Plane intentionally use different Node/pnpm toolchains.
5. Record every Garden-specific Plane subsystem change below.

## Change log

### Batch 0 - fork safety and build isolation

- Added this change log.
- Added workflow-independent upstream update tooling under `scripts/plane-garden/`.
- Added repository-boundary verification under `scripts/plane-garden/verify-boundary.mjs`.
- Existing `.github/workflows/*` files were intentionally left untouched.

### Batch 1 - Garden authorization

Pending implementation.

### Batch 2 - Firebase identity bridge

Pending implementation.

### Batch 3 - seamless launch and auth lockdown

Pending implementation.

### Batch 4 - Garden visual system

Pending implementation.

### Batch 5 - self-hosted production

Pending implementation.

### Batch 6 - security, regression, backup and release gate

Pending implementation.

### Batch 7 - Garden domain integrations

Pending implementation.


### September 2026 - mobile Work and department boards

- Added a department-first board directory and scoped board-creation surface to Garden Admin.
- Changed department-owned project creation to require `work.create` for the selected department; organization-owned project creation still requires global `work.admin`.
- Added server-computed department visibility and creation capability to the scoped Work dashboard.
- Added a dismissible mobile navigation scrim, bounded drawer width, safe-area handling, 16px form controls, and full-viewport mobile framing.
- Added regression coverage under `packages/config/work-department-boards.test.cjs`.

### September 2026 - Garden glass Work refinement

- Added Garden-specific SVG navigation icons, workspace branding and structural frosted surfaces while retaining upstream navigation, issue controls and AGPL notices.
- Scoped backdrop filters to navigation surfaces instead of every card; added reduced-transparency fallbacks and retained reduced-motion/mobile drawer behavior.
- Garden Admin retains the authenticated Plane iframe/standalone integration and existing roles; its separate demo board now shares the Garden visual language.
