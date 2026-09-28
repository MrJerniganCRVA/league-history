# league-history

All-time records and head-to-head history for **Ardi's Bad Trade Bazaar and Emporium**:
Yahoo seasons (2016–2020) plus Sleeper seasons (2021 onward). The site is a static page in `/docs`,
served by GitHub Pages, and it only reads JSON that the Python scripts in `/scripts` generate.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

League IDs and the site title are in `config.json`.

## Sleeper (Phase 1)

```bash
python scripts/sleeper_fetch.py     # walk previous_league_id and cache raw responses in data_raw/sleeper/
python scripts/sanity_report.py     # games/managers per season, unmapped users, missing weeks, champions
```

- Completed seasons get a `_complete` marker and are never fetched again. Only the in-progress season is re-fetched. Use `--force` to re-fetch everything.
- Any Sleeper user who isn't in `managers.json` is listed as **unmapped** in the report. Their games are kept, never dropped.

## Tests

```bash
python -m unittest discover tests
```
