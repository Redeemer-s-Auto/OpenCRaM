# Notes app: closer to Notion - plan for Drew

Updated 2026-10-19. Drew's goal: "make this app as close to Notion as possible."
Code: `C:\repos\OpenCRaM\plane-community\` (Plane CE v1.4.2 + Kei's changes).

## The design Drew chose: B1, one unit
- **The work item (card) is the one Notion-style page.** It has properties (custom fields), a full page body, sub-cards (pages inside pages), and shows in table, board, calendar and timeline views.
- **Plane's separate Pages feature is retired.** Plain documents become cards in a project shown as a page list.
- **History stays:** each card keeps old versions of its body (who saved each one, and restore), plus an activity log of every field change with who and when.
- **Private projects:** a project only its members can see, other workspace admins included. First use: Drew's Personal Dashboard.
- Sharing-rules session told on 2026-10-19: build for cards only, and respect private projects.

## Already done
- Custom fields (Notion "properties"), branch `custom-fields`, with an "+ Add field" button in the table and card panel. Demo on the VPS (`/opt/dev-custom-fields`, private on port 8095).

## Build order

| # | Step | What it means | Clashes with sharing rules? |
|---|---|---|---|
| 1 | **Private projects** | Project setting: only members see it, admins included. | Coordinated (told the session the flag). |
| 2 | **Toggle blocks and columns** | Click-to-open toggles and side-by-side columns in card bodies. | No |
| 3 | **Formulas** | A field that works out its value from other fields. | No |
| 4 | **One-unit screens** | Card opens as a full page by default; sidebar tree of projects and cards (cards inside cards); "page list" project layout for documents; hide Plane Pages. Allow a child card in another project. | Yes: wait for sharing rules to merge. |
| 5 | **Relations and rollups** | Link cards across projects; sum, count or show values from linked cards. | Yes: after sharing rules. |
| 6 | **Linked views** | A live table or board inside a card's page. | Yes: after sharing rules. |
| 7 | **Templates** | Ready-made cards with fields and checklists filled in. | No |
| 8 | **Gallery view** | Cards as tiles with a cover image. | No |
| 9 | **Notion look** | Fonts, spacing, quieter menus; rename "project" if Drew wants a Notion word. | Last. |
| 10 | **Notion import** | Move Notion databases and pages in. Drew names what to exclude (databases the hub replaces). Test one small database first, side by side. | After 2-6. |

## Ongoing
- **Monthly security check:** a scheduled task reviews Plane's security notices, copies each fix into our code, runs the tests, and reports.
- **Kei:** read `docs/legal/CONTRIBUTOR-IP-POLICY.md` and give Drew the short version before offering any of this back.

## Open items
- Custom fields: filters for text and number fields; show fields on board and list cards.
- Merge `custom-fields` to `main` with Drew's OK, after checking the migration number against sharing rules (both may use `0123`).
