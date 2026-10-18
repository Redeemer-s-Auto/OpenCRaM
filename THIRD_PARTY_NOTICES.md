# Third-Party Notices

This repository contains both proprietary first-party software and third-party/open-source software.

Nothing in the root `LICENSE.md`, `COPYRIGHT.md`, `NOTICE.md`, or the policies under `docs/legal/` is intended to replace, narrow, override, or relicense rights granted by third-party copyright holders.

## Plane

The `plane-community/` directory contains software from Plane Software, Inc. and contributors.

The repository currently includes the following notices within that directory:

- `plane-community/COPYRIGHT.txt`
  - Copyright (c) 2023-present Plane Software, Inc. and contributors
  - SPDX-License-Identifier: AGPL-3.0-only
- `plane-community/LICENSE.txt`
  - GNU Affero General Public License, Version 3

Those notices and the corresponding license terms remain controlling for Plane-covered material.

Do not remove, replace, obscure, or overwrite Plane copyright, attribution, or AGPL notices with the proprietary Keith Azodeh license.

Do not add `LicenseRef-Keith-Azodeh-Proprietary` or a Keith Azodeh proprietary copyright header to files that are Plane-covered unless the file contains separately identifiable original material and counsel has confirmed the appropriate notice treatment.



## Other dependencies

The repository also uses third-party packages and services through package manifests, lockfiles, source imports, build tooling, SDKs, and related integrations.

Examples include libraries and SDKs distributed through npm and other ecosystems. Those components remain subject to their respective licenses and copyright notices even when they are used by, linked with, or bundled alongside proprietary first-party software.

The applicable package manifests and lockfiles should be treated as part of the dependency record. This file is not intended to be an exhaustive reproduction of every dependency license.

## Adding third-party code

Before introducing a new third-party dependency, copied source file, template, snippet, generated artifact, model output containing third-party code, or vendored package, a contributor must:

1. identify the source;
2. identify the applicable license;
3. confirm the contributor has the right to use it;
4. preserve required attribution and notices;
5. document material licensing obligations when necessary; and
6. avoid introducing terms that would unintentionally require proprietary first-party platform code to be relicensed or disclosed.

When a license is unclear, stop and obtain approval from Keith Azodeh before adding the material.

## Proprietary scope

The proprietary terms in the root of this repository apply only to material for which Keith Azodeh owns or controls the relevant rights.

See `LICENSE.md` and `COPYRIGHT.md`.

# Mobile App notification components

The mobile app includes MIT-licensed code from [rit3zh/expo-dynamic-notifications](https://github.com/rit3zh/expo-dynamic-notifications), pinned to `5de059a5cbefbe28c14efbe785166665a7c70bc5`. The original license is preserved at `apps/mobile/src/vendor/dynamic-notifications/LICENSE`; provenance and adaptations are documented alongside it.

