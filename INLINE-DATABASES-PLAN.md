# Inline databases, synced blocks and Notion-import fields - design note

Draft 2026-10-28 for Drew's OK. Branch `inline-databases`, worktree `C:\repos\OpenCRaM-inline-databases\`.
Builds on design B1 (`NOTION-PARITY-PLAN.md`): the card is the page, and step 6 is "linked views".

## What exists today (so we reuse it)
- Card body = rich-text editor (`plane-community\packages\editor\src\core\extensions\`). It already has toggles, columns, and a `work-item-embed` block (one card shown inside a page).
- Custom fields (`apps\api\plane\db\models\custom_field.py`), relations and rollups (`apps\api\plane\relations\`), saved views, sharing rules (`apps\api\plane\sharing\`).
- Card body is saved by a live editing server (`apps\live\`), so the body is a shared document.

## 1. Inline databases

**Option A - Notion copy.** A "database block" owns its own table of rows inside the page.
- Familiar. But it is the rigid thing Drew does not like: the rows live in one place, one shape, and you cannot reuse them elsewhere.

**Option B - Live view block (recommended).** A block in the page body that *looks at* cards. It stores no cards.
- Each block remembers only its settings: source, layout (table, board, list, gallery, calendar), filter, sort, group-by, which fields to show.
- Source can be: a whole board, a saved view, the sub-cards of this page, or the cards linked to this page.
- One page can hold any number of blocks. Each has its own layout and filter.
- Change the source, layout or filter any time. The same board can show on 10 pages in 10 shapes.
- Edits write to the real cards, so every other screen updates. Changes made elsewhere show up in the block.
- "+ New" in a block makes a real card in the source board. It fills in the block's filter values (for a "this page's sub-cards" block, it makes a sub-card).
- Sharing rules: the block asks the server for cards the same way every card list does. Cards the viewer may not see are not sent, not counted, not greyed out.
- Why "more fluid": a page does not need its own little database. It points at the real ones. Same data, many lenses.
- Cost: new block in the editor (attrs only, so no change to how the body is stored), a small API that runs a view's filter and returns cards, and reuse of the existing table, board, list and gallery screens inside the block.

**Recommendation: B.** It is Notion's inline database without the lock-in, and it is what step 6 of the plan already meant.

## 2. Synced blocks (one block, many pages, edit once)

**Option A - Own table (recommended).** New table `synced_blocks` (id, content, who made it, home card, version). A "synced block" in a page body holds only the id and shows a small editor for that row.
- Edit in any copy: it saves (about 1 second after typing stops) and the other copies refresh within a few seconds.
- Last save wins if two people type at the exact same time in the same block.
- Visibility follows the home card (the page where it was made). Someone who cannot see the home card sees "You do not have access to this block", not the text. So a restricted block cannot leak onto an open page.
- "Unsync" turns a copy into plain text. Delete on the home page asks first.

**Option B - Hidden card.** Store the block as a hidden card and embed its body. You get true letter-by-letter live typing.
- But hidden cards leak into lists, search and counts unless every screen is taught to skip them. That is a sharing-rules risk. Slower to build.

**Recommendation: A.** Simple, safe, fast. We lose live co-typing inside one block, which is rare.

## 3. The other Notion-import features (separate commits, after inline databases)
| Feature | How |
|---|---|
| Created time, last edited time | Read-only field types, worked out from the card. "Last edited" must also move when a custom field or the body changes. |
| Created by, last edited by | Same, show the person. |
| Percent number | New field type `percent`. Stored as a number, shown with a % and a small bar. |
| Phone, email | New field types. Checked on save. Show as tap-to-call and tap-to-email links. |
| Second status | A "status" field type with grouped options (To do / In progress / Done) that can be a board column. Plane has one built-in state, so this is a custom field, as many as you want. |
| Date mention + reminder | `@date` in the body, with an optional reminder time. A scheduled job sends a notification to the person who set it. Cards the person can no longer see send nothing. |

Each custom-field type adds one choice to the field list plus a small migration. No secrets or shop data in any of it (the fork is public).

## Build and test plan
- Build order: inline databases, then synced blocks, then the field types, then date mentions. One commit each.
- Done for inline databases: a page shows 2+ live board views with their own layout and filter, edits flow both ways, a restricted card stays hidden, tests added.
- Build and test on the VPS only, under `flock /var/lock/notes-dev-heavy.lock`. Not started until VPS load is under 4 and https://notes.redeemersauto.com/auth/firebase/health/ answers. No release to production. No merge into `notes-app` without Drew.
