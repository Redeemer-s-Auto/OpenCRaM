# Garden Work Access Projection

Garden Work is self-hosted Plane Community Edition with Garden-specific federation and authorization hardening.

## Authority

Firebase/Firestore are authoritative for Garden identity and organizational access. Plane/PostgreSQL remain authoritative only for project/work-item state.

Plane must never become a second Garden role database.

## Projection flow

```text
accessProfiles/{uid}
+ departmentMemberships
+ workProjectMappings
        |
        v
workAccessProjections/{uid}
        |
        v
/api/v1/garden/access-projections/{uid}/sync/
        |
        v
Plane WorkspaceMember + ProjectMember
```

The projection is versioned by Garden `accessVersion` and a deterministic projection hash.

## Roles

Plane workspace/project roles used by the projection:

- `20`: Plane Admin, only for Garden global Work administration / mapped project-management authority.
- `15`: Plane Member, for users who need normal Work editing in mapped projects.
- `null`: no Plane membership for that project. Garden may still expose a read-only project summary when `readable: true`.

## Managed project rules

- Every Garden-managed Plane project has one `workProjectMappings` record.
- Managed projects remain `ProjectNetwork.SECRET`.
- Integration/recurring automation may target only active managed mappings.
- Garden authorization controls managed project membership.
- Manual membership changes are not a durable workaround; Garden reconciliation remains authoritative.

## Revocation

When Garden access changes, the projection is recomputed and pushed to Plane.

If Plane is unavailable, Garden records the failure and retries. The Garden access change is still authoritative; a failed external sync does not restore Garden authority.

Statuses:

```text
pending
succeeded
failed_retryable
failed_terminal
```

## Federation

Firebase ID-token federation is the interactive identity path. Native Plane auth is locked down when Garden auth mode is enabled.

Garden projection sync uses the Garden integration API key and is restricted to the configured integration principal.

## Verification

Run before production rollout:

```bash
bash scripts/plane-garden/verify.sh
```

The script runs Garden monorepo checks, builds the vendored Plane images, creates disposable PostgreSQL/Redis infrastructure, and runs the Garden-specific Django test suite.
