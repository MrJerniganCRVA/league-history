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

## Yahoo (Phase 2): one-time export, run locally

1. Create an app at https://developer.yahoo.com/apps/ with the API permission **Fantasy Sports → Read** and the redirect URI `oob`.
2. Create a `.env` file in the repo root. It's gitignored, so it never gets committed:
   ```
   YAHOO_CONSUMER_KEY=your_key
   YAHOO_CONSUMER_SECRET=your_secret
   ```
3. Run the export:
   ```bash
   python scripts/yahoo_export.py          # every season in config.json (2016-2020)
   python scripts/yahoo_export.py 2018     # or specific seasons
   ```
   - The first run prints an **AUTHORIZATION URL**. Open it on any device, approve access, then paste the code back into the terminal.
   - The token is saved to `yahoo_token.json` (gitignored), so later runs don't ask again.
   - The 2016 and 2017 league IDs are found automatically by following Yahoo's `renew` links and written to `config.json`.
4. Commit `data_raw/yahoo/*.json` and `config.json`. The script ends by listing any Yahoo team that isn't in `manager_map.csv`.

## Managers (identity map)

`manager_map.csv` has one row per person. The first column is their Sleeper username, and each year column
is their Yahoo team name for that season. Leave a cell blank if they weren't in the league that year.
Two optional extras:
- A `DisplayName` column overrides the name shown on the site.
- For someone who never played on Sleeper, leave the first column blank and fill in `DisplayName`.

```bash
python scripts/import_manager_map.py      # regenerates managers.json and keeps any hand edits
```

Each row is exactly one person, even if a newcomer took over someone's old team slot or team name.
Any team that isn't in the CSV is reported as unmapped and kept in the data, never guessed.

## Tests

```bash
python -m unittest discover tests
```
