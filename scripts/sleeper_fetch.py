"""Walk the Sleeper league history and cache raw API responses.

Usage: python scripts/sleeper_fetch.py [--force]

Completed seasons are written to data_raw/sleeper/<season>/ with a `_complete`
marker and never fetched again; only the in-progress season is re-fetched.

Also cached, for the Transactions page:
- <season>/transactions/NN.json  completed trades/waiver/free-agent moves only (failed claims dropped)
- <season>/stats/NN.json         weekly raw stats, trimmed to the league's scoring keys, so players who
                                 sat on waivers can still be scored (undocumented Sleeper endpoint)
- players.json                   id -> name/position/team for players that appear in the league
A cached season missing transactions/ or stats/ gets just those back-filled, once.
"""
from __future__ import annotations

import argparse
import math
import sys

from common import SLEEPER_RAW, HttpClient, load_config, read_json, write_json

API = "https://api.sleeper.app/v1"
MAX_WEEK = 18
INDEX_PATH = SLEEPER_RAW / "index.json"  # league_id -> season, so cached seasons need no call
PLAYERS_PATH = SLEEPER_RAW / "players.json"
PLAYER_FIELDS = ("full_name", "first_name", "last_name", "position", "fantasy_positions", "team")


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


def keep_transaction(tx: dict) -> bool:
    """Only moves that actually happened. A failed or pending waiver claim never added anyone."""
    return tx.get("status") == "complete"


def scoring_keys(league: dict) -> set[str]:
    return {k for k, v in (league.get("scoring_settings") or {}).items() if v}


def trim_stats(raw, keys: set[str]) -> dict[str, dict[str, float]]:
    """player_id -> {stat: value} for the league's scoring stats only, dropping all-zero players.

    The endpoint has returned both {player_id: stats} and [{player_id, stats}] shapes; accept either.
    """
    if isinstance(raw, list):
        items = ((str(r.get("player_id")), r.get("stats") or {}) for r in raw if isinstance(r, dict))
    elif isinstance(raw, dict):
        items = ((str(pid), st or {}) for pid, st in raw.items())
    else:
        return {}
    out: dict[str, dict[str, float]] = {}
    for pid, stats in items:
        kept = {k: v for k, v in stats.items() if k in keys and isinstance(v, (int, float)) and v}
        if kept:
            out[pid] = dict(sorted(kept.items()))
    return dict(sorted(out.items()))


def fetch_transactions(client: HttpClient, league_id: str, out, weeks: int) -> int:
    kept = 0
    for week in range(1, weeks + 1):
        txs = client.get_json(f"{API}/league/{league_id}/transactions/{week}") or []
        txs = sorted((t for t in txs if keep_transaction(t)),
                     key=lambda t: (t.get("status_updated") or t.get("created") or 0,
                                    str(t.get("transaction_id"))))
        write_json(out / "transactions" / f"{week:02d}.json", txs)
        kept += len(txs)
    return kept


def fetch_stats(client: HttpClient, league: dict, out, weeks: int) -> bool:
    """Best effort: the stats endpoint isn't in Sleeper's official docs, so a failure only warns."""
    season = str(league["season"])
    keys = scoring_keys(league)
    try:
        for week in range(1, weeks + 1):
            raw = client.get_json(f"{API}/stats/nfl/regular/{season}/{week}")
            write_json(out / "stats" / f"{week:02d}.json", trim_stats(raw, keys), indent=None)
    except Exception as e:  # noqa: BLE001 - keep the rest of the refresh working
        print(f"  {season}: stats unavailable ({e}); waiver-wire weeks will score 0", file=sys.stderr)
        return False
    return True


def scored_weeks(league: dict, n: int) -> int:
    """Weeks whose games are final. In-season, the week in progress has no final stats yet."""
    if league.get("status") == "complete":
        return n
    return min(n, int(league.get("settings", {}).get("last_scored_leg") or 0))


def backfill_season(client: HttpClient, league_id: str, league: dict, skip_stats: bool) -> None:
    """A cached (complete) season from before transactions were fetched: add just the new folders."""
    season = str(league["season"])
    out = SLEEPER_RAW / season
    n = last_week(league, read_json(out / "winners_bracket.json"))
    if not (out / "transactions").exists():
        kept = fetch_transactions(client, league_id, out, n)
        print(f"  {season}: back-filled transactions ({kept} completed)")
    if not skip_stats and not (out / "stats").exists():
        if fetch_stats(client, league, out, n):
            print(f"  {season}: back-filled stats weeks 1-{n}")


def collect_player_ids(root=None) -> set[str]:
    """Every player id that was ever on a roster or in a transaction in this league."""
    root = root or SLEEPER_RAW
    ids: set[str] = set()
    for f in root.glob("*/matchups/*.json"):
        for e in read_json(f, []) or []:
            ids.update(str(p) for p in (e.get("players") or []))
    for f in root.glob("*/transactions/*.json"):
        for t in read_json(f, []) or []:
            ids.update(str(p) for p in (t.get("adds") or {}))
            ids.update(str(p) for p in (t.get("drops") or {}))
    return ids


def trim_players(raw: dict, ids: set[str]) -> dict[str, dict]:
    out = {}
    for pid in sorted(ids):
        p = raw.get(pid)
        if not p:
            continue
        rec = {k: p.get(k) for k in PLAYER_FIELDS if p.get(k) is not None}
        if "full_name" not in rec:  # team defenses have only first/last name ("Houston", "Texans")
            name = " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
            if name:
                rec["full_name"] = name
        out[pid] = rec
    return out


def refresh_players(client: HttpClient, force: bool = False) -> None:
    """Re-download /players/nfl only when a new player id shows up (or --force), so the file
    doesn't change on every weekly run. Ids Sleeper doesn't list are remembered under `missing`
    so they don't trigger a download every time either."""
    cached = read_json(PLAYERS_PATH, {}) or {}
    known = set((cached.get("players") or {}).keys()) | set(cached.get("missing") or [])
    ids = collect_player_ids()
    if not force and ids <= known:
        print("  players: cached")
        return
    raw = client.get_json(f"{API}/players/nfl") or {}
    players = trim_players(raw, ids)
    for pid, rec in (cached.get("players") or {}).items():  # keep anyone Sleeper dropped from the list
        players.setdefault(pid, rec)
    missing = sorted(ids - set(players))
    write_json(PLAYERS_PATH, {"players": dict(sorted(players.items())), "missing": missing})
    print(f"  players: {len(players)} saved, {len(missing)} not listed by Sleeper")


def fetch_season(client: HttpClient, league_id: str, league: dict, skip_stats: bool = False) -> None:
    season = str(league["season"])
    out = SLEEPER_RAW / season
    write_json(out / "league.json", league)
    for name in ("users", "rosters", "winners_bracket", "losers_bracket"):
        write_json(out / f"{name}.json", client.get_json(f"{API}/league/{league_id}/{name}"))
    wb = read_json(out / "winners_bracket.json")
    n = last_week(league, wb)
    if league.get("status") != "complete":
        # current season: nothing past the week in progress exists yet
        n = min(n, int(league.get("settings", {}).get("last_scored_leg") or 0) + 1)
    for week in range(1, n + 1):
        data = client.get_json(f"{API}/league/{league_id}/matchups/{week}")
        write_json(out / "matchups" / f"{week:02d}.json", data)
    kept = fetch_transactions(client, league_id, out, n)
    if not skip_stats:
        fetch_stats(client, league, out, scored_weeks(league, n))
    marker = out / "_complete"
    if league.get("status") == "complete":
        marker.write_text(league_id + "\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()
    print(f"  {season}: fetched weeks 1-{n}, {kept} transactions (status={league.get('status')})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch completed seasons too")
    ap.add_argument("--skip-stats", action="store_true", help="don't fetch weekly player stats")
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
            backfill_season(client, league_id, league, args.skip_stats)
        else:
            league = client.get_json(f"{API}/league/{league_id}")
            if not league:
                print(f"  league {league_id} not found; stopping", file=sys.stderr)
                break
            index[league_id] = str(league["season"])
            fetch_season(client, league_id, league, args.skip_stats)
        league_id = str(league.get("previous_league_id") or "")
    write_json(INDEX_PATH, dict(sorted(index.items(), key=lambda kv: kv[1])))
    refresh_players(client, force=args.force)
    print(f"Done. {client.calls} API calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
