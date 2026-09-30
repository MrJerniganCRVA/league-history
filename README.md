# league-history

All-time records and head-to-head history for **Ardi's Bad Trade Bazaar and Emporium**.
The site is plain HTML/CSS/JS in `/docs`, served by GitHub Pages. It makes no API calls:
it only reads the JSON in `docs/data/`, which the Python scripts in `/scripts` generate.

- **Sleeper (2021 onward):** live. Refreshed weekly by a GitHub Action.
- **Yahoo (2016–2020):** deferred. The Yahoo API refuses our requests (see [Yahoo](#yahoo-deferred)).
  As soon as `data_raw/yahoo/<season>.json` files exist, the build includes them automatically.

## Pages

| Page | What's on it |
|---|---|
| `index.html` | Champion, Sacko and regular-season last place by year, 3 random "did you know" facts |
| `records.html` | Highest/lowest scores (all-time, by season, by manager), blowouts, closest games, highest score in a loss, lowest in a win, weekly-low counts, season points for/against |
| `h2h.html` | Everyone's record against everyone; tap a cell for the rivalry |
| `rivalry.html?a=<id>&b=<id>` | Series record, playoff record, points, average margin, biggest wins, streak, full game log |

Every page shares the same filters (season range, platform, game type), which are kept in the URL,
so a filtered view can be shared in the group chat. The default is all seasons, regular + playoff games
(consolation excluded).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate    # required on Raspberry Pi OS / Debian
pip install -r requirements.txt
```

League IDs, the site title and any manual result corrections are in `config.json`.

Each season shows three results:
- **Champion:** winner of the championship game.
- **Sacko:** loser of the loser-bracket (toilet bowl) final. Sleeper marks the team that *advances* in
  the loser bracket, which there is the team that lost. So the build compares the actual scores in the
  final and picks the lower one. For Yahoo seasons it's the last team in the final standings.
- **Last (reg. season):** worst regular-season record, with fewest points breaking ties.

To correct any of them, add `{"2023": "manager_id"}` to `champion_overrides`, `sacko_overrides` or
`last_place_overrides`.

## Update the data and site

```bash
python scripts/sleeper_fetch.py     # cache Sleeper responses in data_raw/sleeper/ (only the current season is re-fetched)
python scripts/build_games.py       # write docs/data/{games,seasons,managers}.json and print the sanity report
```

The report lists games and managers per season, unmapped identities, missing weeks and missing champions.
Unmapped people's games are kept, never dropped.

**Automatic refresh:** `.github/workflows/refresh.yml` runs every Tuesday from September to January
(and on demand from the Actions tab). It fetches the current Sleeper season, rebuilds, and commits only if
the data changed.

## Preview locally

```bash
python -m http.server -d docs 8000   # then open http://localhost:8000
```

## Publish on GitHub Pages (one time)

1. Merge to `main`.
2. Repo **Settings → Pages → Build and deployment**: Source **Deploy from a branch**, Branch **main**, Folder **/docs**, then Save.
3. The site appears at `https://<your-user>.github.io/league-history/` within a minute or two.
4. **Settings → Actions → General → Workflow permissions**: make sure **Read and write** is selected so the weekly refresh can commit.

## Managers (identity map)

`manager_map.csv` has one row per person. The first column is their Sleeper username, and each year column
is their Yahoo team name for that season. Leave a cell blank if they weren't in the league that year.
- An optional `DisplayName` column overrides the name shown on the site.
- For someone who never played on Sleeper, leave the first column blank and fill in `DisplayName`.

```bash
python scripts/import_manager_map.py      # regenerates managers.json and keeps any hand edits
```

Each row is exactly one person, even if a newcomer took over someone's old team slot or team name.

## Yahoo (deferred)

`scripts/yahoo_export.py` is written and tested, but Yahoo refuses every request, including
"who am I" (`This application is not authorized to perform this action`), with two different apps.
Options to revisit:

- `python scripts/yahoo_export.py --diagnose` with a fresh Yahoo app. It prints OK/FAIL per request.
- A browser-console script that reads the weekly matchup pages while you're logged in to Yahoo.
- A hand-filled CSV of matchups (about 400 rows).

Each one just needs to produce `data_raw/yahoo/<season>.json`. After that, `build_games.py` includes the
seasons and `manager_map.csv` already maps the team names. The five league IDs are in `config.json`.

Export setup, if you try the API again: create an app at https://developer.yahoo.com/apps/
(**Fantasy Sports → Read**, Confidential client, redirect URI `oob`). Put the keys in `.env`
(`YAHOO_CONSUMER_KEY=...`, `YAHOO_CONSUMER_SECRET=...`, no quotes needed), then run
`python scripts/yahoo_export.py`. `.env` and `yahoo_token.json` are gitignored.

## Tests

```bash
python -m unittest discover tests     # data pipeline
node --test tests/*.test.mjs          # record calculations in docs/js/stats.js
```
