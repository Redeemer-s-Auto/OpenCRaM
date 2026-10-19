# Notion import

Copies Notion databases and pages into Notes boards and cards. Python 3.10+, standard library only.

- A Notion database becomes a board; each row becomes a card (the card is the page).
- Plain pages become cards on a "Docs" board; sub-pages become sub-cards.
- Properties become custom fields; status becomes the card state; formulas, relations and
  rollups are rebuilt when Notes can do the same thing, otherwise a frozen copy is kept.
- Images and files stored in Notion are downloaded and re-uploaded (Notion's links expire).
- Anything with no Notes equivalent becomes a visible placeholder line and is counted in the report.
- Re-runnable: everything carries `external_source="notion"` and the Notion id, so a second run
  updates what the first one made.
- New boards are private (only the person running the import is a member), because the Notion
  API does not say who a page was shared with.

## Credentials

- Notion: an internal integration token with read content (and, for comments, read comments)
  capabilities, shared with the pages to import. The tool only reads Notion; any write is refused
  before it is sent.
- Notes: an API key of a workspace admin. Pass both as files (`--token-file`, `--api-key-file`) or
  environment variables (`NOTION_TOKEN`, `NOTES_API_KEY`), never on the command line.

## Use

Run from this folder (`scripts/notion-import`). Keep the token files, snapshot folders and
reports **outside the repository**: a snapshot holds full page contents and downloaded files.
Run a re-import with the same Notes API key as the first run (the snapshot folder remembers which
boards it made, and the importer stops rather than make a second copy of a board it cannot see).

    # 1. what can the token see?
    python -m notion_import inventory --token-file token.txt --out inventory.json

    # 2. read what you chose into a snapshot folder (files are downloaded now)
    python -m notion_import export --token-file token.txt --root ds:<data source id> \
        --root page:<page id> --exclude <id> --out snap/

    # 3. dry run: print and write what would be created, changed and left out
    python -m notion_import plan --snapshot snap/

    # 4. import (re-run safely at any time)
    python -m notion_import apply --snapshot snap/ --notes-url https://notes.example.org \
        --workspace <slug> --api-key-file notes-key.txt

`run --dry-run` does steps 2 and 3 without downloading files (sizes are still checked).
Reports land in the snapshot folder: `dry-run-report.md` and `import-report.md` (plus JSON).

Rate limits: Notion 3 requests/second, Notes about 1 request/second (the v1 default is 60 a minute
per key); both retry on HTTP 429 after the wait the server asks for.

## Tests

    python -m unittest discover -s tests

Fixtures are hand-written Notion JSON with fake data; `tests/fake_notes.py` stands in for the Notes API.
