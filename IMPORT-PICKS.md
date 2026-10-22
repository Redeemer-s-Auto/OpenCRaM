# Import picks - edit this file

HOW TO USE
- Every line that starts with `[ ]` is one pick.
- Change the space to `I` (import) or `L` (leave). Example: `[I]` or `[L]`.
- Want half of an item? Copy the line, mark one copy `I`, the other `L`, and cut the words down to each half.
- A line you do not touch stays `[ ]` = undecided.
- Save the file. Tell Claude "done".

SOURCE (both files live on the branch `origin/notes-app`)
- `CUSTOM-FIELDS-PLAN.md`
- `NOTION-PARITY-PLAN.md`
- Both files are not on `main` here. Claude read them with `git show origin/notes-app:<file>`.

---

## FILE 1: CUSTOM-FIELDS-PLAN.md

### Data model
[ ] Table `custom_fields`: one row per field on a board (project, name, type, options, sort_order, archived_at)
[ ] Table `custom_field_values`: one row per card per field (issue, field, typed value columns)
[ ] Field type: text
[ ] Field type: long text
[ ] Field type: number
[ ] Field type: money (stored as whole cents, shown as dollars)
[ ] Field type: date
[ ] Field type: checkbox
[ ] Field type: select (dropdown)
[ ] Field type: multi-select
[ ] Field type: person
[ ] Field type: URL

### API
[ ] App API: list, create, edit, reorder, archive, restore, delete fields (`/api/workspaces/<slug>/projects/<project_id>/custom-fields/`)
[ ] Card values: send and read `custom_fields` on card update and card read
[ ] Public API `/api/v1/`: field endpoints
[ ] Public API `/api/v1/`: `custom_fields` on card read and write
[ ] Webhooks: card payload carries `custom_fields`
[ ] Check each value against its type (number, date, URL, choice exists, person is a workspace member)

### Filters and sort
[ ] Saved-view filters with keys `custom_field__<field_id>`
[ ] Filter operators: is, is not, contains
[ ] Filter operators: greater than, less than, between, is empty
[ ] Table view sorts on any field column

### Sharing rules fit
[ ] Values are never read without their card (follows the "who can see this card" filter)
[ ] No endpoint lists values without its card (table, filters, API, webhooks, exports)

### Delete
[ ] "Delete" archives the field; values stay; an admin can restore it
[ ] Real delete is admin only and needs the field name typed to confirm

### Screens
[ ] Board settings > Fields page: add, rename, drag to reorder, edit choices, archive
[ ] Card side panel: fields under the built-in properties
[ ] Card side panel: "+ Add field" button (admins only)
[ ] Table view: one column per field, with sort
[ ] Table view: show/hide field columns in Display
[ ] Filter menu: a "Fields" group

### Build order and housekeeping
[ ] Step 1: server (models, migration, API, validation, filters, sort, webhooks, tests)
[ ] Step 2: screens (settings page, side panel, table columns, filters)
[ ] Step 3: demo board for Drew
[ ] Migration number `0123`: rebase, renumber and re-run tests before merge if sharing rules also made `0123`

---

## FILE 2: NOTION-PARITY-PLAN.md

### The design (B1, one unit)
[ ] The card is the one Notion-style page (properties, full body, sub-cards, all views)
[ ] Retire Plane's separate Pages feature; documents become cards shown as a page list
[ ] Keep old versions of a card body (who saved, restore)
[ ] Keep an activity log of every field change (who, when)
[ ] Private projects: only members see them, other workspace admins included

### Already done (decide if it comes over)
[ ] Custom fields with "+ Add field" in table and card panel (branch `custom-fields`)
[ ] Demo on the VPS (`/opt/dev-custom-fields`, port 8095)

### Build order
[ ] 1. Private projects
[ ] 2. Toggle blocks (click-to-open) in card bodies
[ ] 2. Columns (side by side) in card bodies
[ ] 3. Formulas (a field that works out its value from other fields)
[ ] 4. One-unit screens: card opens as a full page by default
[ ] 4. One-unit screens: sidebar tree of projects and cards (cards inside cards)
[ ] 4. One-unit screens: "page list" project layout for documents
[ ] 4. One-unit screens: hide Plane Pages
[ ] 4. One-unit screens: allow a child card in another project
[ ] 5. Relations: link cards across projects
[ ] 5. Rollups: sum, count or show values from linked cards
[ ] 6. Linked views: a live table or board inside a card's page
[ ] 7. Templates: ready-made cards with fields and checklists filled in
[ ] 8. Gallery view: cards as tiles with a cover image
[ ] 9. Notion look: fonts, spacing, quieter menus
[ ] 9. Rename "project" to a Notion word (only if Drew wants)
[ ] 10. Notion import: move Notion databases and pages in
[ ] 10. Notion import: test one small database first, side by side
[ ] 10. Notion import: Drew names databases to exclude (the ones the hub replaces)

### Ongoing
[ ] Monthly security check: a scheduled task reviews Plane's security notices
[ ] Monthly security check: copy each fix into our code and run the tests
[ ] Monthly security check: report the result
[ ] Kei reads `docs/legal/CONTRIBUTOR-IP-POLICY.md` before any of this is offered back

### Open items
[ ] Custom fields: filters for text and number fields
[ ] Custom fields: show fields on board and list cards
[ ] Merge `custom-fields` to `main` (after the `0123` migration check)
