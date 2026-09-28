"""Walk the Sleeper league history and cache raw API responses.

Usage: python scripts/sleeper_fetch.py [--force]

Completed seasons are written to data_raw/sleeper/<season>/ with a `_complete`
marker and never fetched again; only the in-progress season is re-fetched.
"""
from __future__ import annotations

import argparse
import math
import sys

from common import SLEEPER_RAW, HttpClient, load_config, read_json, write_json

API = "https://api.sleeper.app/v1"
MAX_WEEK = 18
INDEX_PATH = SLEEPER_RAW / "index.json"  # league_id -> season, so cached seasons need no call


def playoff_rounds(league: dict, winners_bracket: list | None) -> int:
    if winners_bracket:
        return max(m.get("r", 1) for m in winners_bracket)
    teams = int(league.get("settings", {}).get("playoff_teams") or 0)
    return max(1, math.ceil(math.log2(teams))) if teams > 1 else 0


def round_weeks(league: dict, rounds: int) -> dict[int, list[int]]:
    """Map playoff round number -> the NFL weeks it spans.

    playoff_round_type: 0 = one week per round, 1 = two-week championship only,
    2 = two weeks per round.
    """
    settings = league.get("settings", {})
    start = int(settings.get("playoff_week_start") or 0)
    rtype = int(settings.get("playoff_round_type") or 0)
    out: dict[int, list[int]] = {}
    week = start
    for r in range(1, rounds + 1):
        span = 2 if rtype == 2 or (rtype == 1 and r == rounds) else 1
        out[r] = list(range(week, week + span))
        week += span
    return out


def last_week(league: dict, winners_bracket: list | None) -> int:
    settings = league.get("settings", {})
    start = int(settings.get("playoff_week_start") or 0)
    if not start:
        return min(MAX_WEEK, int(settings.get("last_scored_leg") or MAX_WEEK))
    rounds = playoff_rounds(league, winners_bracket)
    weeks = round_weeks(league, rounds)
    end = max((w for ws in weeks.values() for w in ws), default=start - 1)
    return min(MAX_WEEK, end)


def fetch_season(client: HttpClient, league_id: str, league: dict) -> None:
    season = str(league["season"])
    out = SLEEPER_RAW / season
    write_json(out / "league.json", league)
    for name in ("users", "rosters", "winners_bracket", "losers_bracket"):
        write_json(out / f"{name}.json", client.get_json(f"{API}/league/{league_id}/{name}"))
    wb = read_json(out / "winners_bracket.json")
    n = last_week(league, wb)
    for week in range(1, n + 1):
        data = client.get_json(f"{API}/league/{league_id}/matchups/{week}")
        write_json(out / "matchups" / f"{week:02d}.json", data)
    marker = out / "_complete"
    if league.get("status") == "complete":
        marker.write_text(league_id + "\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()
    print(f"  {season}: fetched weeks 1-{n} (status={league.get('status')})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch completed seasons too")
    args = ap.parse_args()

    cfg = load_config()
    league_id = str(cfg.get("sleeper_league_id") or "")
    if not league_id or league_id == "0":
        print("config.json: sleeper_league_id is not set", file=sys.stderr)
        return 2

    client = HttpClient()
    index: dict[str, str] = read_json(INDEX_PATH, {}) or {}
    seen = set()
    print("Walking Sleeper league history...")
    while league_id and league_id != "0" and league_id not in seen:
        seen.add(league_id)
        season = index.get(league_id)
        cached = season and (SLEEPER_RAW / season / "_complete").exists()
        if cached and not args.force:
            league = read_json(SLEEPER_RAW / season / "league.json")
            print(f"  {season}: cached (league {league_id})")
        else:
            league = client.get_json(f"{API}/league/{league_id}")
            if not league:
                print(f"  league {league_id} not found; stopping", file=sys.stderr)
                break
            index[league_id] = str(league["season"])
            fetch_season(client, league_id, league)
        league_id = str(league.get("previous_league_id") or "")
    write_json(INDEX_PATH, dict(sorted(index.items(), key=lambda kv: kv[1])))
    print(f"Done. {client.calls} API calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
