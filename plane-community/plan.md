# Plane Community Integration Plan

Status: **Revision 3 — repo-reconciled, batched, implementation pending approval**

Upstream: `makeplane/plane` Community Edition **v1.4.2**, AGPL-3.0, vendored as ordinary source files under `/plane-community`.

This is the authoritative implementation plan for integrating Plane Community Edition into The Garden. It is based on direct inspection of the current Church monorepo, the vendored Plane 1.4.2 source, both authentication systems, both UI systems, CI, Firebase Hosting, and Plane's self-host stack.

## 1. Non-negotiable requirements

- Plane must run fully self-hosted on infrastructure controlled by The Garden.
- No Plane Cloud runtime dependency.
- No Plane Pro/Business subscription dependency.
- No paid OIDC/SSO dependency.
- Firebase Authentication remains the identity authority for Garden staff.
- Garden Firebase custom claims and `users/{uid}` records remain authoritative for Garden identity and access eligibility.
- Plane keeps PostgreSQL for project-management state. Firestore will not replace Plane's relational database.
- The Plane experience must visually read as part of the Garden staff operating system.
- Existing Garden member, admin, kiosk, giving, people, ministry, communications, and Firebase behavior must remain unaffected.
- Plane API credentials, database credentials, Firebase Admin credentials, and service secrets remain server-side only.

## 2. Verified current architecture

### Garden

The Garden repo is a pnpm/Turborepo TypeScript monorepo with root workspaces:

```text
apps/web
apps/admin
apps/kiosk
packages/*
functions
scripts/*
```

The staff application already owns:

- Firebase Auth state
- role-based route guards
- capability-based authorization through Firebase custom claims
- `users/{uid}` profile/access mirroring
- Garden audit logging
- the Garden `AdminShell`
- responsive navigation
- Garden theme tokens
- Firebase Functions integration

Garden currently builds under Node 20 and pnpm 9.15.4.

### Plane

Plane 1.4.2 is a separate application ecosystem. Its web client uses React Router, Tailwind, MobX, SWR, `next-themes`, and Plane's own packages. Its API is Django/Python.

Plane requires Node >=22.18 and pnpm 11.3.

Therefore `/plane-community` must remain a separately installed, built, tested, and deployed subtree. It must **not** be added to the root Garden pnpm workspace.

Plane's self-host stack contains:

```text
web
admin
space
api
worker
beat-worker
migrator
live
PostgreSQL 15
Valkey 7
RabbitMQ
MinIO
proxy
```

This stack can operate without Plane Cloud.

## 3. Target architecture

```text
                         THE GARDEN

        Existing Firebase-hosted Garden staff application
                         |
                         | /work launch route
                         | fresh Firebase ID token
                         v
                 Firebase session exchange
                         |
                         v
              Self-hosted Garden Plane fork
              work.thegarden.church
                         |
             +-----------+-----------+
             |           |           |
          Django      Plane web    workers/live
             |
       +-----+-----+---------+
       |           |         |
   PostgreSQL    Valkey   RabbitMQ
       |
     MinIO
```

Firebase answers **who the user is and whether the user may enter Work**.

Plane answers **which projects, work items, comments, cycles, modules, views, and Plane workspace permissions the user has**.

The first deployment target is `https://work.thegarden.church` unless final infrastructure establishes an equivalent Garden-controlled hostname.

Do not iframe Plane into Firebase Hosting. Garden Hosting sends `X-Frame-Options: DENY`, and iframe integration would create unnecessary cookie, navigation, accessibility, sizing, and styling problems.

## 4. Source and maintenance boundary

All Plane source remains under `/plane-community`.

Keep `/plane-community` outside the root `pnpm-workspace.yaml` and normal Garden Turborepo graph.

The current one-time vendoring mechanism successfully copied Plane into the repo, but its destructive `rsync --delete` behavior must not be used for future upgrades once Garden modifications begin.

Future upstream updates must:

1. fetch a selected Plane tag into a temporary/upstream branch or staging directory;
2. compare it against the currently pinned Plane version;
3. deliberately merge/reapply Garden changes;
4. run Plane-specific CI;
5. update `.garden-upstream` only after the merged version passes;
6. never automatically overwrite the Garden-modified Plane tree.

Maintain `/plane-community/GARDEN_CHANGES.md` listing each Garden-specific Plane modification by subsystem and file path.

## 5. Authorization contract

Add explicit Garden work-management capabilities:

```text
work.read
work.manage
work.admin
```

Initial role policy:

```text
superadmin -> work.read + work.manage + work.admin
admin      -> work.read + work.manage + work.admin
staff      -> work.read + work.manage
```

Specialized roles do not automatically gain Work access unless the Garden role/capability policy explicitly grants it.

Plane workspace roles are:

```text
20 = Admin
15 = Member
 5 = Guest
```

Initial mapping:

```text
work.admin            -> Plane Admin (20)
work.manage/work.read -> Plane Member (15)
no work.read          -> no active Plane workspace membership
```

Do not use Plane Guest as a fallback for Garden users without access.

If Work permission is removed, deactivate the Plane workspace membership rather than deleting the Plane user or historical work records.

## 6. Firebase-to-Plane authentication design

Plane's authentication source ultimately creates sessions through:

```python
user_login(request=request, user=user, is_app=True)
```

which uses Django's normal session login machinery.

Therefore Firebase can be added directly as a server-verified Garden authentication path. Do not emulate OIDC and do not repurpose Plane's Google OAuth provider.

Create an isolated Garden Django integration module:

```text
plane-community/apps/api/plane/garden/
  apps.py
  models.py
  services/
    firebase_identity.py
    provisioning.py
  views/
    firebase_session.py
  migrations/
  tests/
```

Add `plane.garden` to Django `INSTALLED_APPS`.

Add:

```text
POST /auth/firebase/session/
```

The endpoint will:

1. accept a Firebase ID token in the Authorization bearer header;
2. verify signature, issuer, project/audience, expiration, revocation, and disabled-user state with Firebase Admin;
3. read Garden `roles` and `capabilities` from verified custom claims;
4. require `work.read`;
5. use Firebase UID as the immutable external identity key;
6. optionally read `users/{uid}` from Firestore for canonical display metadata;
7. find or create the corresponding Plane user;
8. create/reactivate membership in the managed `The Garden` workspace;
9. synchronize the Plane role from Garden capabilities;
10. invoke Plane post-auth behavior where appropriate;
11. call Plane's existing `user_login(...)` to create the Plane session;
12. return a minimal success payload and safe destination.

### External identity table

Do not permanently join systems by email.

Use a Garden-specific table such as:

```text
GardenExternalIdentity
  id
  provider = "firebase"
  external_id = <Firebase UID>   UNIQUE
  user_id = <Plane User FK>
  last_synced_at
```

Never store Firebase ID tokens in PostgreSQL.

### Firebase Admin configuration

Add a pinned `firebase-admin` dependency to Plane's Python requirements.

Credentials must be injected/mounted at deployment time, never committed.

Expected environment shape:

```text
GARDEN_FIREBASE_PROJECT_ID
GOOGLE_APPLICATION_CREDENTIALS
GARDEN_WORKSPACE_SLUG=the-garden
GARDEN_AUTH_ENABLED=1
GARDEN_AUTH_ALLOWED_ORIGIN=<production Garden admin origin>
```

## 7. Garden-to-Plane launch flow

Add a native Garden admin route:

```text
/work
```

with a small `WorkLaunchPage.tsx` under `apps/admin/src/site/pages/`.

Flow:

```text
User clicks Work
   |
   v
Garden verifies work.read
   |
   v
Firebase user.getIdToken(true)
   |
   v
POST https://work.thegarden.church/auth/firebase/session/
Authorization: Bearer <Firebase ID token>
credentials: include
   |
   v
Plane verifies token and provisions identity/membership
   |
   v
Plane sets normal Secure + HttpOnly session cookie
   |
   v
Browser navigates to https://work.thegarden.church/
```

Add validated client config:

```text
VITE_WORK_URL
```

This is a public URL only, never a secret.

Use explicit CORS/CSRF origin allowlists, HTTPS-only cookies, and Plane's existing cookie/session controls. Do not enable wildcard production CORS.

Plane sign-out ends the Plane session and returns to Garden. It does not automatically sign the user out of Firebase.

## 8. Plane-native auth lockdown

Firebase must be the only ordinary Garden-facing identity entry path.

Disable Garden-facing access to:

- Plane email/password sign-in
- Plane sign-up
- magic link sign-in/sign-up
- Plane Google OAuth
- GitHub OAuth
- GitLab OAuth
- Gitea OAuth
- ordinary Plane password reset/set-password flows

Do not merely hide buttons. Prevent unintended account creation/authentication at the server/routing level in Garden mode.

Unauthenticated access to `work.thegarden.church` should return through the Garden login/Work launch path rather than show Plane's native login UI.

Restrict Plane's separate god-mode/admin surface to trusted infrastructure/admins. It must not become a second public identity system.

## 9. Managed Plane workspace

First milestone workspace:

```text
Name: The Garden
Slug: the-garden
Timezone: America/Chicago
```

Garden users are provisioned automatically from Firebase claims.

Ordinary staff should not have to accept email invitations or complete redundant Plane onboarding.

Workspace bootstrapping may occur automatically only under an explicit deployment/bootstrap flag. Production then treats the workspace as persistent state.

## 10. Visual integration

Garden source-of-truth theme values:

```text
background   #F7F2E6
surface      #FFFDF7
text         #102A1C
muted text   #466050
primary      #2F7D4A
primary text #FFFDF7
border       #E5DDCF
danger       #B91C1C
radii        8 / 12 / 16 px
```

Garden's existing UI language also includes:

- translucent cream surfaces
- blur/saturation glass treatment
- subtle inset white highlights
- restrained green-tinted shadows
- 44px minimum form/control height
- visible focus rings
- 333ms ease transitions
- small hover lift where appropriate
- reduced-motion support

Do not import `@yadasa/church-ui` directly into Plane initially. That would couple two different workspace/build ecosystems.

Instead adapt Plane at its semantic Tailwind theme layer.

Create an override such as:

```text
plane-community/packages/tailwind-config/garden.css
```

imported after Plane's base variables.

Map Plane semantic tokens for:

- canvas/background
- layer/surface levels
- primary/secondary/placeholder text
- weak/default/strong borders
- brand/accent states
- selected/hover/focus states
- inputs/buttons
- success/warning/danger
- scrollbars
- overlays/modals

Preserve Plane's existing semantic class names so thousands of components do not need individual rewrites.

Match the current Garden admin shell's visual rhythm, including the 1440px desktop reference width, ~228px sidebar reference, ~58px sticky topbar reference, 900px mobile-navigation changeover, and 520px small-screen refinement.

Replace Garden-facing Plane branding in title/meta/PWA information, app icons/favicons/OG assets, visible wordmarks, loading branding, onboarding copy, and third-party-feeling empty states where appropriate.

Preserve AGPL notices and required upstream legal/license text.

First milestone uses a canonical Garden light theme. A future dark mode should be a Garden-designed dark palette, not stock Plane dark mode.

## 11. Data boundaries

### Firebase / Firestore remains authoritative for

- Garden identity/users
- roles and capabilities
- people and households
- giving/finance
- groups
- events/registrations
- schedules/services
- check-in
- communications
- content
- Garden audit records

### Plane PostgreSQL remains authoritative for

- local Plane user principals
- workspace membership
- projects
- work items
- comments
- cycles
- modules
- labels
- views
- Plane activity/project state

Only copy minimum Garden profile metadata needed to render Plane members/assignees.

Do not copy giving, financial, household, sensitive pastoral/profile, or unrelated member information into Plane.

## 12. Self-host deployment boundary

Firebase continues to deploy:

```text
member site
/admin
/kiosk
Firebase Functions
```

Plane does not enter the Firebase Hosting build bundle.

Create a Garden deployment overlay, for example:

```text
plane-community/docker-compose.garden.yml
plane-community/.env.garden.example
```

Production stack remains fully self-hosted:

```text
Plane web/admin/space/api/live
worker + beat worker + migrator
PostgreSQL 15
Valkey 7
RabbitMQ
MinIO
reverse proxy
```

The overlay must:

- inject Firebase project configuration into Plane API;
- mount Firebase credentials read-only;
- use explicit CORS/CSRF origins;
- configure `WEB_URL` / `APP_BASE_URL` for the Garden Work hostname;
- retain persistent database/object-storage volumes;
- provide health/restart behavior;
- keep PostgreSQL, Valkey, RabbitMQ, and MinIO private;
- expose only required proxy/web ports behind HTTPS;
- use non-default production passwords and a stable Django `SECRET_KEY`.

Back up PostgreSQL and MinIO at minimum and perform an actual restore test.

## 13. CI/CD separation

Existing Garden CI stays on the current Garden toolchain and scope.

Add dedicated Plane workflows triggered by `plane-community/**`, for example:

```text
.github/workflows/plane-ci.yml
.github/workflows/plane-deploy.yml
```

Plane CI uses:

```text
Node >=22.18
pnpm 11.3
Python/Django dependencies matching Plane 1.4.2
```

Plane auth tests must include:

- valid Firebase token
- expired token
- malformed token
- revoked/disabled Firebase user
- wrong project/audience
- missing `work.read`
- first-login provisioning
- repeat-login idempotency
- display metadata changes
- role promotion/demotion
- removed access

Browser/session tests must include:

- exact CORS behavior
- Secure/HttpOnly session cookie
- CSRF behavior
- Garden `/work` handoff
- unauthenticated redirects
- disabled Plane-native auth paths
- sign-out behavior

Visual smoke tests must include:

- dashboard/home
- project list/detail
- board/list work views
- work-item detail/modal
- create/edit work item
- mobile navigation
- loading/empty/error states

Garden root CI, Firebase rules tests, and deployment behavior must remain unchanged.

# 14. Implementation batches after approval

Implementation will be executed one batch at a time. Each batch must leave the repo coherent and testable. Do not begin the next batch until the current batch passes its exit criteria.

## Batch 0 — Fork safety, build isolation, and baseline

**Goal:** make the vendored Plane tree safe to modify and prove independent buildability before touching Garden identity.

**Primary systems/files:**

```text
.github/workflows/vendor-plane-community.yml
.github/workflows/plane-ci.yml
plane-community/.garden-upstream
plane-community/GARDEN_CHANGES.md
plane-community/package.json
plane-community/apps/api/
```

**Work:**

1. Replace destructive future re-vendoring with a deliberate merge-safe update workflow.
2. Add `GARDEN_CHANGES.md`.
3. Confirm Plane v1.4.2 frontend install/type/build under Node >=22.18 and pnpm 11.3.
4. Confirm Django dependencies install and the Plane API can boot against disposable local/self-host services.
5. Add Plane-only CI triggered by `plane-community/**`.
6. Keep Plane outside Garden root pnpm/Turbo/Firebase build scopes.
7. Capture pre-integration Plane and Garden build baselines.

**Exit gate:**

- Plane frontend builds independently.
- Plane API migrations run against disposable PostgreSQL.
- Existing Garden CI still behaves as before.
- Future Plane refresh cannot silently erase Garden modifications.
- No Garden authentication behavior has changed.

**Rollback:** infrastructure-only. No production identity or Plane user data exists yet.

---

## Batch 1 — Garden authorization and Work access contract

**Goal:** decide and enforce who may use Work before connecting anyone to Plane.

**Primary systems/files:**

```text
packages/config/src/capabilities.ts
packages/config/src/index.ts
functions/src/modules/auth/
apps/admin/src/site/auth/
apps/admin/src/site/adminNavigation.ts
claims backfill tooling
```

**Work:**

1. Add `work.read`, `work.manage`, and `work.admin`.
2. Map superadmin/admin/staff according to the authorization contract above.
3. Preserve existing custom claims rather than overwriting unrelated claims.
4. Add capability-aware protection suitable for the future `/work` route.
5. Add validated `VITE_WORK_URL` client config.
6. Build an audited dry-run-first claims backfill for existing eligible users.
7. Make the backfill idempotent and safe to rerun.

**Exit gate:**

- Eligible roles resolve correct Work capabilities.
- Users without `work.read` are denied before a Plane request occurs.
- Specialized roles do not accidentally gain access.
- Existing role/capability behavior remains intact.
- Backfill supports dry-run, apply, rerun, and audit output.
- No Plane user has been provisioned yet.

**Rollback:** remove new capabilities/config before Plane is connected.

---

## Batch 2 — Firebase identity bridge inside Plane

**Goal:** make Plane trust Garden Firebase identity without Plane Cloud, OIDC, paid SSO, or a second credential.

**Primary systems/files:**

```text
plane-community/apps/api/requirements/
plane-community/apps/api/plane/settings/common.py
plane-community/apps/api/plane/urls.py
plane-community/apps/api/plane/garden/
```

**Work:**

1. Add pinned `firebase-admin` dependency.
2. Create isolated `plane.garden` Django app.
3. Add `GardenExternalIdentity` keyed by Firebase UID.
4. Add server-side Firebase token verification.
5. Require `work.read` from verified claims.
6. Read Firestore profile metadata only when needed for safe display information.
7. Provision/update Plane user idempotently.
8. Create/reactivate managed workspace membership.
9. Synchronize Garden capabilities to Plane Admin/Member role.
10. Add `POST /auth/firebase/session/`.
11. Create the normal Plane session with existing `user_login(...)` machinery.
12. Add auth/provisioning tests.

**Exit gate:**

- Valid eligible Firebase user receives a Plane session.
- First login creates exactly one external identity/user association.
- Repeat login does not duplicate users.
- Email/display-name change does not break identity.
- Invalid/expired/revoked/disabled/wrong-project tokens fail closed.
- Missing `work.read` fails closed.
- Promotion/demotion works.
- Removed Work access deactivates membership without deleting historical work.

**Rollback:** isolated Garden integration app/table can be disabled without altering core Plane data models.

---

## Batch 3 — Seamless Garden launch and Plane auth lockdown

**Goal:** create a single-login Garden experience and remove redundant Plane public auth entry points.

**Primary systems/files:**

```text
apps/admin/src/site/pages/WorkLaunchPage.tsx
apps/admin routing
apps/admin/src/site/adminNavigation.ts
packages/config/src/index.ts
Plane Garden auth routes/middleware
Plane CORS/CSRF/session config
```

**Work:**

1. Add Garden `/work` route and navigation item.
2. Require `work.read`.
3. Fetch a fresh Firebase ID token.
4. Exchange it with Plane using credentials enabled.
5. Navigate into Work after Plane sets its Secure/HttpOnly session.
6. Configure exact CORS/CSRF/cookie/trusted-host behavior.
7. Redirect unauthenticated Plane users through Garden auth/Work launch.
8. Disable Garden-facing Plane email/password, signup, magic-link, Google, GitHub, GitLab, Gitea, and password-reset entry paths at the routing/server level.
9. Skip redundant Plane onboarding for provisioned Garden staff.
10. Make Plane sign-out return to Garden without automatically signing out Firebase.

**Exit gate:**

- Eligible staff clicks Work and enters without another credential.
- Direct unauthenticated Work entry returns through Garden auth.
- Users without `work.read` cannot bypass Garden by calling Plane directly.
- Plane-native public login/signup paths are inaccessible in Garden mode.
- CORS/CSRF/session/sign-out browser tests pass.
- Existing Garden login/profile/admin behavior remains unchanged.

**Rollback:** disable/remove Garden `/work` entry while retaining Plane data.

---

## Batch 4 — Garden visual system and product shell

**Goal:** make Work visually feel like The Garden instead of a separately branded Plane install.

**Primary systems/files:**

```text
plane-community/packages/tailwind-config/variables.css
plane-community/packages/tailwind-config/index.css
plane-community/packages/tailwind-config/garden.css
plane-community/apps/web/app/root.tsx
plane-community/apps/web/app/assets/
Plane shell/navigation components
```

**Work:**

1. Add Garden semantic theme overrides after Plane base tokens.
2. Map Plane surfaces/text/borders/brand/focus/selected/input/button/status/overlay tokens to Garden palette.
3. Apply Garden glass/surface/radius/focus/44px-touch-target/333ms-motion conventions where appropriate.
4. Align topbar/sidebar/density/selected states/responsive behavior with Garden `AdminShell`.
5. Preserve Plane's richer internal project navigation while making it read as Garden's Work section.
6. Replace Garden-facing Plane title/meta/PWA assets, icons, wordmarks, loading branding, onboarding copy, and third-party-feeling copy where appropriate.
7. Preserve AGPL/legal notices.
8. Use canonical Garden light theme for milestone one.
9. Run desktop/tablet/mobile visual QA across primary Work flows.

**Exit gate:**

- Work reads as the same product family as Garden admin.
- Primary routes consistently use Garden palette/surfaces/focus/motion.
- Mobile/tablet/desktop remain usable.
- No direct dependency on `@yadasa/church-ui` is required.
- Theme modifications remain concentrated in semantic/shell layers for maintainability.

**Rollback:** visual changes can revert without touching authentication or Plane project data.

---

## Batch 5 — Fully self-hosted production stack

**Goal:** run the integrated Work system entirely on Garden-controlled infrastructure.

**Primary systems/files:**

```text
plane-community/docker-compose.yml
plane-community/docker-compose.garden.yml
plane-community/.env.garden.example
Plane reverse proxy
work.thegarden.church DNS/TLS
Plane deployment workflow/scripts
```

**Work:**

1. Create Garden compose overlay instead of unnecessarily rewriting upstream compose.
2. Run required Plane web/API/workers/live services plus PostgreSQL, Valkey, RabbitMQ, MinIO, and proxy.
3. Configure final Garden Work hostname and HTTPS.
4. Configure secure cookies, origins, application URLs, trusted proxies/hosts.
5. Keep PostgreSQL/Valkey/RabbitMQ/MinIO private.
6. Mount Firebase Admin credentials read-only as deployment secrets.
7. Replace all example/default passwords/secrets.
8. Add/verify health checks, startup/migration order, restart behavior, and persistent volumes.
9. Add deterministic deployment commands and `plane-deploy.yml` when target server supports GitHub-driven deploys.
10. Keep Firebase Hosting deployment separate.

**Exit gate:**

- A clean host can reconstruct Work from repo configuration plus documented secrets.
- Work is reachable only through intended HTTPS entry point.
- Internal persistence/queue services are not public.
- Container restarts do not lose project/upload data.
- Firebase handoff works against production hostname.
- No Plane Cloud account/API/subscription is required.

**Rollback:** remove/redirect DNS/proxy while preserving Plane persistent volumes.

---

## Batch 6 — Security, regression, backup/restore, and release gate

**Goal:** prove the system is safe and recoverable before calling the first milestone complete.

**Primary systems:** Garden CI, Plane CI, Firebase claims, browser sessions, Plane services, PostgreSQL, MinIO, operations docs.

**Work:**

1. Run full Firebase auth failure/success matrix.
2. Run browser CORS/CSRF/cookie/redirect/sign-out/native-auth-lockdown tests.
3. Run Plane frontend/API tests and full existing Garden CI/Firebase rules tests.
4. Run production-like desktop/mobile Work QA.
5. Add PostgreSQL backup procedure.
6. Add MinIO backup procedure.
7. Restore backups into a clean/disposable environment and verify usable recovered data.
8. Document deployment, rollback, credential rotation, upstream updates, backup/restore, access sync, and common failure recovery.
9. Verify `GARDEN_CHANGES.md` covers every Garden modification from Batches 0-6.
10. Freeze the first stable integrated revision only when all milestone criteria pass.

**Exit gate:**

- Existing Garden member/admin/kiosk/giving/people/ministry behavior passes regression testing.
- Plane CI passes.
- Eligible users receive correct Plane role without second credentials.
- Removed/revoked Garden access blocks future Plane entry.
- Plane project/upload data survives restart and tested restore.
- Work visual QA passes on desktop and mobile.
- Entire stack can be rebuilt without contacting Plane or buying a subscription.

**Rollback:** Work can be removed from routing/deployment while preserving PostgreSQL/MinIO state.

---

## Batch 7 — Cross-system operational integrations, post-MVP only

**Goal:** connect Plane Work to Garden operational domains only after Batches 0-6 are stable.

Batch 7 is **not part of the first milestone**. It will be split further when specific integrations are chosen.

Potential sub-batches:

```text
7A forms/workflows -> Plane work-item creation
7B events/groups/services -> linked operational work
7C Garden admin dashboard -> Plane project/task summaries
7D Plane state changes -> Garden workflow updates
7E recurring ministry/production/facilities work automation
```

Rules for every Batch 7 integration:

- use stable Garden entity IDs;
- keep Firebase/Firestore authoritative for Garden domain data;
- keep Plane authoritative for project/work-item state;
- copy only safe summary/link metadata;
- never duplicate giving, financial, sensitive profile, household, or unrelated pastoral data into Plane;
- use server-to-server authentication for cross-system writes;
- add audit logging and idempotency before enabling automation.

## 15. Batch dependency chain

```text
Batch 0  Fork safety + independent CI
   |
   v
Batch 1  Garden Work capabilities
   |
   v
Batch 2  Firebase -> Plane identity bridge
   |
   v
Batch 3  Seamless launch + Plane auth lockdown
   |
   v
Batch 4  Garden visual integration
   |
   v
Batch 5  Self-host production deployment
   |
   v
Batch 6  Security/regression/restore release gate
   |
   v
Batch 7  Optional operational integrations
```

### Stopping rule

When implementation starts, complete and test one batch before moving to the next.

If a batch exposes an architectural issue, resolve it inside that batch and revise this plan before continuing rather than carrying a known compromise forward.

For the first milestone, **Batches 0 through 6 are required. Batch 7 is deferred.**

## 16. Explicit non-goals for the first milestone

- Do not rewrite Plane to use Firestore instead of PostgreSQL.
- Do not merge Plane's package graph into the Garden pnpm workspace.
- Do not iframe Plane.
- Do not expose Plane API keys or Firebase Admin credentials in Garden browser code.
- Do not use Plane Cloud for auth, storage, telemetry-required functionality, or project data.
- Do not pay for/depend on Plane OIDC/Pro features.
- Do not duplicate sensitive Garden member/finance data into Plane.
- Do not begin Batch 7 integrations before Batches 0-6 pass.

## 17. First-milestone acceptance criteria

The integration is complete only when all of the following are true:

- An eligible existing Garden Firebase user clicks Work and enters self-hosted Work without a second credential.
- Firebase UID is the immutable Garden-to-Plane identity key.
- Garden admins receive Plane Admin access and permitted staff receive Plane Member access.
- Removing Garden Work permission prevents future Plane access without deleting historical work.
- No Plane Cloud account, Plane-hosted identity, paid OIDC, Pro/Business feature, or Plane subscription is required.
- PostgreSQL, Valkey, RabbitMQ, MinIO, and Plane applications all run on Garden-controlled infrastructure.
- Plane's native public signup/auth paths are unusable in Garden mode.
- Primary Work screens visually match Garden palette, surface treatment, interaction timing, and responsive quality closely enough to read as the same product family.
- Existing Garden Firebase/member/admin/kiosk functionality still passes CI and behaves as before.
- Plane has its own passing CI, deterministic deployment, persistent storage, and tested backup/restore path.
- The source tree remains maintainable against future Plane Community Edition updates.

---

**Implementation state:** not started. Awaiting explicit approval. On approval, implementation begins with Batch 0 and proceeds through Batch 6 only after each prior batch passes its exit gate.