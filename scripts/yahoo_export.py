"""ONE-TIME Yahoo export (run locally, e.g. on the Pi). The site and the GitHub Action never call Yahoo.

Setup:
  1. Create an app at https://developer.yahoo.com/apps/  (API permissions: Fantasy Sports -> Read,
     redirect URI: oob). Put its keys in .env at the repo root:
         YAHOO_CONSUMER_KEY=...
         YAHOO_CONSUMER_SECRET=...
  2. pip install -r requirements.txt
  3. python scripts/yahoo_export.py            (all seasons in config.json)
     python scripts/yahoo_export.py 2018 2019  (just these)

First run prints an AUTHORIZATION URL: open it on any device, approve, paste the code back.
The token is saved to yahoo_token.json (gitignored) so later runs don't ask again.

Writes data_raw/yahoo/<season>.json and fills missing league IDs (found via the `renew` chain)
into config.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import CONFIG_PATH, MANAGER_MAP_CSV, ROOT, YAHOO_RAW, load_config, write_json

TOKEN_PATH = ROOT / "yahoo_token.json"

# Yahoo NFL game keys are fixed per season. Using these avoids the /games lookup, which Yahoo
# rejects ("not authorized") for some older seasons.
NFL_GAME_KEYS = {2014: "331", 2015: "348", 2016: "359", 2017: "371", 2018: "380",
                 2019: "390", 2020: "399", 2021: "406", 2022: "414", 2023: "423"}


# ---------------------------------------------------------------- pure helpers (unit tested)

def txt(v) -> str:
    """YFPY returns some strings as bytes."""
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return "" if v is None else str(v)


def parse_renew(renew: str | None) -> tuple[str, str] | None:
    """League.renew / renewed look like '390_123456' (game_id, league_id)."""
    if not renew or "_" not in str(renew):
        return None
    game_id, league_id = str(renew).split("_", 1)
    return game_id, league_id


def tag_game_types(games: list[dict], playoff_start: int, seeds: dict[str, int],
                   num_playoff_teams: int, multiweek_final_week: int | None = None) -> None:
    """Set game['game_type'] in place.

    regular: week < playoff_start. playoff: both teams still alive on the championship path.
    Alive starts as the top `num_playoff_teams` seeds; each playoff-week loser is eliminated
    (except after the first week of a two-week championship). Yahoo's is_consolation flag
    always wins. Everything else in the playoff weeks (3rd place, consolation bracket) is consolation.
    """
    alive = {k for k, s in seeds.items() if s and s <= num_playoff_teams}
    for week in sorted({g["week"] for g in games}):
        week_games = [g for g in games if g["week"] == week]
        losers = set()
        for g in week_games:
            a, b = g["team_a_key"], g["team_b_key"]
            if week < playoff_start:
                g["game_type"] = "regular"
            elif not g.get("is_consolation") and a in alive and b in alive:
                g["game_type"] = "playoff"
                if g["score_a"] != g["score_b"]:
                    losers.add(b if g["score_a"] > g["score_b"] else a)
            else:
                g["game_type"] = "consolation"
        if week >= playoff_start and week != multiweek_final_week:
            alive -= losers


# ---------------------------------------------------------------- yahoo access

NOT_AUTHORIZED_HELP = """
Yahoo refused the request: "This application is not authorized to perform this action."
The saved token has been deleted. Fix the app, then re-run (you'll get a fresh sign-in link):
  1. https://developer.yahoo.com/apps/ -> your app -> API Permissions: tick Fantasy Sports, choose Read.
     Client type: Confidential. If permissions can't be edited, create a new app and put its
     key/secret in .env.
  2. Make sure .env has the key/secret of THAT app (YAHOO_CONSUMER_KEY / YAHOO_CONSUMER_SECRET).
"""


def _load_token(consumer_key: str | None) -> dict | None:
    """Reuse the saved token only if it belongs to the app currently in .env.

    YFPY prefers the key stored in the token over .env, so a token from an old app would
    silently keep being used after you switch apps.
    """
    if not TOKEN_PATH.exists():
        return None
    token = json.loads(TOKEN_PATH.read_text())
    if consumer_key and token.get("consumer_key") != consumer_key:
        print("Saved Yahoo token is for a different app than .env; signing in again.")
        TOKEN_PATH.unlink()
        return None
    return token


def make_query():
    import os

    from dotenv import load_dotenv
    from yfpy.query import YahooFantasySportsQuery

    load_dotenv(ROOT / ".env", override=True)
    key = os.environ.get("YAHOO_CONSUMER_KEY")
    if not key or not os.environ.get("YAHOO_CONSUMER_SECRET"):
        raise SystemExit("Missing YAHOO_CONSUMER_KEY / YAHOO_CONSUMER_SECRET in .env")
    q = YahooFantasySportsQuery(
        league_id="0", game_code="nfl",
        yahoo_access_token_json=_load_token(key),
        browser_callback=False,  # print the auth URL instead of opening a browser (headless Pi)
    )
    print(f"Using Yahoo app key ...{key[-6:]} "
          f"({'saved sign-in' if TOKEN_PATH.exists() else 'new sign-in'})")
    return q


def save_token(q) -> None:
    """Called only after a request succeeds, so a token that can't read fantasy data is never kept."""
    TOKEN_PATH.write_text(json.dumps(q._yahoo_access_token_dict, indent=2))


def check_access(q) -> None:
    try:
        q.get_game_key_by_season(2018)  # a request that needs Fantasy Sports read access
    except Exception as e:  # yfpy raises YahooFantasySportsDataNotFound with Yahoo's message
        if "not authorized" in str(e).lower():
            TOKEN_PATH.unlink(missing_ok=True)
            raise SystemExit(NOT_AUTHORIZED_HELP)
        raise
    save_token(q)


def game_key_for(q, season: int) -> str:
    return NFL_GAME_KEYS.get(season) or q.get_game_key_by_season(season)


def use_league(q, game_key: str, league_id: str) -> None:
    q.game_id = int(game_key)
    q.league_id = str(league_id)
    q.league_key = f"{game_key}.l.{league_id}"


def discover_league_ids(q, cfg: dict) -> dict[str, str]:
    """Fill null seasons in cfg['yahoo_leagues'] by walking `renew` back from known leagues."""
    leagues = {s: (str(l) if l else None) for s, l in cfg["yahoo_leagues"].items()}
    first = int(cfg.get("yahoo_first_season") or min(map(int, leagues)))
    known = sorted((int(s) for s, l in leagues.items() if l), reverse=True)
    if not known:
        raise SystemExit("config.json: need at least one Yahoo league ID to start the renew chain")
    season, league_id = known[-1], leagues[str(known[-1])]  # earliest known, walk backwards
    while season > first:
        use_league(q, game_key_for(q, season), league_id)
        prev = parse_renew(txt(q.get_league_metadata().renew))
        if not prev:
            print(f"  renew chain ends at {season}; no link to {season - 1}")
            break
        season -= 1
        league_id = prev[1]
        if not leagues.get(str(season)):
            print(f"  found {season} league id {league_id} via renew")
            leagues[str(season)] = league_id
    return leagues


def export_season(q, season: int, league_id: str) -> dict:
    game_key = game_key_for(q, season)
    use_league(q, game_key, league_id)
    meta = q.get_league_metadata()
    settings = q.get_league_settings()
    teams_raw = q.get_league_teams()
    standings = q.get_league_standings()

    teams = []
    for t in teams_raw:
        mgrs = getattr(t, "managers", None) or ([t.manager] if getattr(t, "manager", None) else [])
        teams.append({
            "team_key": txt(t.team_key),
            "name": txt(t.name),
            "guids": [txt(m.guid) for m in mgrs if txt(m.guid) and txt(m.guid) != "--"],
            "nicknames": [txt(m.nickname) for m in mgrs],
        })

    ranks, seeds = {}, {}
    for t in standings.teams:
        key = txt(t.team_key)
        ts = getattr(t, "team_standings", None)
        ranks[key] = int(getattr(ts, "rank", None) or getattr(t, "rank", None) or 0)
        seeds[key] = int(getattr(ts, "playoff_seed", None) or getattr(t, "playoff_seed", None) or 0)

    end_week = int(meta.end_week)
    playoff_start = int(settings.playoff_start_week or end_week + 1)
    num_playoff = int(settings.num_playoff_teams or 0)
    if not any(seeds.values()):  # older seasons may lack playoff_seed; fall back to final rank
        seeds = dict(ranks)

    games = []
    for week in range(1, end_week + 1):
        for m in q.get_league_scoreboard_by_week(week).matchups:
            if len(m.teams) != 2:
                continue
            a, b = sorted(m.teams, key=lambda t: txt(t.team_key))
            pts = lambda t: float(getattr(getattr(t, "team_points", None), "total", None)  # noqa: E731
                                  or getattr(t, "points", 0) or 0)
            games.append({
                "week": week,
                "team_a_key": txt(a.team_key), "score_a": round(pts(a), 2),
                "team_b_key": txt(b.team_key), "score_b": round(pts(b), 2),
                "is_playoffs": bool(int(m.is_playoffs or 0)),
                "is_consolation": bool(int(m.is_consolation or 0)),
            })
        print(f"    week {week}: {sum(g['week'] == week for g in games)} games")

    multiweek = bool(int(getattr(settings, "has_multiweek_championship", 0) or 0))
    # two-week final: don't eliminate anyone after its first week
    tag_game_types(games, playoff_start, seeds, num_playoff,
                   multiweek_final_week=(end_week - 1) if multiweek else None)

    by_rank = sorted((r, k) for k, r in ranks.items() if r)
    return {
        "season": season,
        "league_key": q.league_key,
        "league_name": txt(meta.name),
        "settings": {
            "start_week": int(meta.start_week or 1),
            "end_week": end_week,
            "playoff_start_week": playoff_start,
            "num_playoff_teams": num_playoff,
            "uses_playoff_reseeding": bool(int(getattr(settings, "uses_playoff_reseeding", 0) or 0)),
            "has_multiweek_championship": multiweek,
        },
        "teams": teams,
        "final_rank": ranks,
        "playoff_seed": seeds,
        "games": games,
        "champion_team_key": by_rank[0][1] if by_rank else None,
        "last_team_key": by_rank[-1][1] if by_rank else None,
    }


def _probe(label: str, fn):
    try:
        result = fn()
    except Exception as e:  # report every failure instead of stopping at the first
        msg = str(e).split("failed with error:")[-1].strip()
        print(f"  FAIL  {label}: {msg[:160]}")
        return None
    print(f"  OK    {label}")
    return result


def diagnose(q, cfg: dict) -> None:
    """Try each Yahoo request separately and print OK/FAIL; only the sign-in token is saved."""
    print("\nDiagnosis (no league data is written):")
    user = _probe("current user", q.get_current_user)
    if user is not None:
        save_token(q)
        print(f"        signed in as Yahoo guid {txt(getattr(user, 'guid', '?'))}")
    for season_str, lid in sorted(cfg["yahoo_leagues"].items()):
        season = int(season_str)
        key = NFL_GAME_KEYS.get(season)
        print(f"\n  {season} (game key {key}, league id in config: {lid or 'unknown'})")
        _probe(f"{season} season-info lookup", lambda: q.get_game_key_by_season(season))
        mine = _probe(f"{season} leagues this account was in", lambda: q.get_user_leagues_by_game_key(key))
        for lg in mine or []:
            print(f"        - {txt(getattr(lg, 'name', ''))}  (league id {txt(getattr(lg, 'league_id', ''))})")
        if mine is not None and not mine:
            print("        (none: this Yahoo account wasn't in a league that season)")
        if lid:
            use_league(q, key, lid)
            _probe(f"{season} league {lid} metadata", q.get_league_metadata)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seasons", nargs="*", type=int)
    ap.add_argument("--diagnose", action="store_true",
                    help="test each Yahoo request and print OK/FAIL; writes no league data")
    args = ap.parse_args()

    cfg = load_config()
    q = make_query()
    if args.diagnose:
        diagnose(q, cfg)
        return 0
    check_access(q)

    print("Resolving league IDs...")
    leagues = discover_league_ids(q, cfg)
    if leagues != cfg["yahoo_leagues"]:
        cfg["yahoo_leagues"] = leagues
        write_json(CONFIG_PATH, cfg)
        print("  updated config.json")

    seasons = args.seasons or sorted(int(s) for s in leagues)
    failed: list[int] = []
    for season in seasons:
        lid = leagues.get(str(season))
        if not lid:
            print(f"! {season}: no league id. Add it to config.json yahoo_leagues "
                  f"(it's the number in the Yahoo league URL) and re-run.")
            continue
        print(f"Exporting {season} (league {lid})...")
        try:
            data = export_season(q, season, lid)
        except Exception as e:  # keep going so one bad season doesn't block the rest
            print(f"! {season} failed: {e}")
            failed.append(season)
            continue
        write_json(YAHOO_RAW / f"{season}.json", data)
        n = {t: sum(g["game_type"] == t for g in data["games"]) for t in ("regular", "playoff", "consolation")}
        champ = next((t["name"] for t in data["teams"] if t["team_key"] == data["champion_team_key"]), "?")
        print(f"  {season}: {len(data['teams'])} teams, {n}, champion: {champ}")

    if failed:
        print(f"\nFailed seasons: {failed} (paste the messages above to Claude)")
    print("\nChecking manager_map.csv against the export:")
    from import_manager_map import _sleeper_users, _yahoo_teams, parse_csv, report
    report(parse_csv(MANAGER_MAP_CSV), _sleeper_users(), _yahoo_teams())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
