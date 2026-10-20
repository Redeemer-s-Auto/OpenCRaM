# Custom fields - plan (draft for Drew's OK)

Branch: `custom-fields`, worktree `C:\repos\OpenCRaM-custom-fields\`.

## What the free Plane code already has
- `IssueType` and `ProjectIssueType` tables (`apps\api\plane\db\models\issue_type.py`) and the flag `Project.is_issue_type_enabled`.
- No field definitions, no field values, no screens. The paid feature is not in the free code.
- So we build new. All new code is ours, under the same AGPL-3.0 license as Plane.

## Data model (2 new tables)
1. `custom_fields` - one row per field on a board.
   - project, name, type, options (dropdown choices: id, name, color), sort_order, archived_at.
   - Types: text, long_text, number, money, date, checkbox, select, multi_select, person, url.
2. `custom_field_values` - one row per card per field.
   - issue, field, and one typed column per kind: `value_text`, `value_number`, `value_date`, `value_bool`, `value_json` (multi-select choices, person ids).
   - Money goes in `value_number` as whole cents. The screen shows dollars.
   - One row per card and field (unique).
   - Typed columns let the database sort and filter fast.

## API
- App API: `/api/workspaces/<slug>/projects/<project_id>/custom-fields/` - list, create, edit, reorder, archive, restore, delete.
- Card values: send `custom_fields: {"<field_id>": value}` on the card update. Card reads return the same shape.
- Public API `/api/v1/`: same field endpoints, and cards carry `custom_fields` on read and write.
- Webhooks: the card payload carries `custom_fields`.
- Each value is checked against its type (number, date, URL, choice exists, person is a workspace member).

## Filters and sort
- Saved-view filters use keys like `custom_field__<field_id>` with operators: is, is not, contains, greater than, less than, between, is empty.
- Table view sorts on any field column.

## Sharing rules fit
- Values are never read on their own. They are always joined to cards that already passed the "who can see this card" filter.
- No endpoint lists values without its card. So table, filters, API, webhooks and exports follow the card rule.

## Delete
- "Delete" archives the field. Values stay. An admin can restore it.
- A real delete is admin only, and the admin must type the field name to confirm. It removes every value in it.

## Screens
- Board settings > **Fields**: add, rename, change order (drag), edit choices, archive.
- Card side panel: fields show under the built-in properties.
- Table view: one column per field, with sort. Show/hide in Display.
- Filter menu: a "Fields" group.

## Mockup - card side panel
```
State       In Progress
Priority    High
Assignee    (person)
Labels      Brakes
-- Fields ---------------------------
RO number   10432
Vehicle     2019 Toyota Camry
Amount      $1,214.00
Call-back   Oct 22, 2026
Tech role   [ A-Tech v ]
Approved    [x]
Link        https://...
+ Add field  (admins only)
```

## Mockup - table view
```
| Title            | State   | RO number | Amount    | Call-back  | Tech role |
|------------------|---------|-----------|-----------|------------|-----------|
| Brake job quote  | Todo    | 10432     | $1,214.00 | Oct 22     | A-Tech    |
| Follow up on AC  | Waiting | 10455     | $640.00   | Oct 24     | GS Tech   |
```

## Build order
1. Server: models, migration, API, validation, filters, sort, webhooks. Tests in a small container with the code mounted.
2. Screens: settings page, side panel, table columns, filters.
3. Demo board for Drew.

## Migration number
- Ours is `0123`. The sharing-rules session may also make `0123`. Before merge: rebase, renumber, re-run tests.
