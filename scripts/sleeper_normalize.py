"""Turn one cached Sleeper season (data_raw/sleeper/<season>/) into games + season metadata."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from common import Resolver, make_game, read_json
from sleeper_fetch import playoff_rounds, round_weeks


def _roster_owners(rosters: list[dict], issues: list[str]) -> dict[int, str | None]:
    """roster_id -> owner user_id, for THIS season only. Co-owned rosters use the primary owner."""
    owners: dict[int, str | None] = {}
    for r in rosters:
        owner = r.get("owner_id") or (r.get("co_owners") or [None])[0]
        if not owner:
            issues.append(f"roster {r.get('roster_id')} has no owner_id or co_owners")
        owners[int(r["roster_id"])] = owner
    return owners


def _score(entry: dict) -> float:
    cp = entry.get("custom_points")
    return float(cp if cp is not None else (entry.get("points") or 0))


def _playoff_pairs(league: dict, winners_bracket: list[dict]) -> dict[int, set[frozenset]]:
    """week -> set of {roster, roster} pairs that are real (championship-path) playoff games."""
    rounds = playoff_rounds(league, winners_bracket)
    weeks_by_round = round_weeks(league, rounds)
    pairs: dict[int, set[frozenset]] = defaultdict(set)
    for m in winners_bracket or []:
        if m.get("p") not in (None, 1):
            continue  # 3rd/5th place games etc. are consolation
        t1, t2 = m.get("t1"), m.get("t2")
        if t1 is None or t2 is None:
            continue
        for week in weeks_by_round.get(m.get("r", 0), []):
            pairs[week].add(frozenset((int(t1), int(t2))))
    return pairs


def _sacko_roster(season_dir: Path, league: dict, losers_bracket: list[dict]) -> int | None:
    """Roster that lost the loser-bracket (toilet bowl) final.

    In a toilet bowl the loser advances, and Sleeper marks that team `w`. So instead of
    trusting the labels, compare the two teams' actual scores in the final's week; the bracket
    label only breaks an exact tie.
    """
    final = next((m for m in losers_bracket if m.get("p") == 1
                  and m.get("t1") is not None and m.get("t2") is not None), None)
    if not final:
        return None
    rounds = playoff_rounds(league, losers_bracket)
    weeks = round_weeks(league, rounds).get(final.get("r", rounds), [])
    t1, t2 = int(final["t1"]), int(final["t2"])
    totals = {t1: 0.0, t2: 0.0}
    for week in weeks:
        for e in read_json(season_dir / "matchups" / f"{week:02d}.json", []) or []:
            if e.get("roster_id") in totals:
                totals[e["roster_id"]] += _score(e)
    if totals[t1] != totals[t2]:
        return t1 if totals[t1] < totals[t2] else t2
    return int(final["w"]) if final.get("w") is not None else None


def normalize_sleeper_season(season_dir: Path, resolver: Resolver) -> tuple[list[dict], dict, list[str]]:
    league = read_json(season_dir / "league.json")
    users = read_json(season_dir / "users.json", []) or []
    rosters = read_json(season_dir / "rosters.json", []) or []
    wb = read_json(season_dir / "winners_bracket.json", []) or []
    lb = read_json(season_dir / "losers_bracket.json", []) or []
    season = int(league["season"])
    settings = league.get("settings", {})
    playoff_start = int(settings.get("playoff_week_start") or 99)
    complete = league.get("status") == "complete"
    # In-season, ignore weeks Sleeper hasn't finished scoring (e.g. only TNF played so far).
    scored_through = None if complete else int(settings.get("last_scored_leg") or 0)
    issues: list[str] = []

    names = {u["user_id"]: (u.get("display_name") or (u.get("metadata") or {}).get("team_name") or "")
             for u in users}
    owners = _roster_owners(rosters, issues)

    def who(roster_id: int) -> str:
        uid = owners.get(roster_id)
        return resolver.sleeper_user(uid, names.get(uid, ""))

    playoff_pairs = _playoff_pairs(league, wb)
    games: list[dict] = []
    missing_weeks: list[int] = []
    for path in sorted((season_dir / "matchups").glob("*.json")):
        week = int(path.stem)
        if scored_through is not None and week > scored_through:
            continue
        entries = read_json(path, []) or []
        by_matchup: dict[int, list[dict]] = defaultdict(list)
        for e in entries:
            if e.get("matchup_id") is None:
                continue  # bye / no game
            by_matchup[e["matchup_id"]].append(e)
        week_games = []
        for mid, pair in sorted(by_matchup.items()):
            if len(pair) != 2:
                issues.append(f"week {week} matchup {mid} has {len(pair)} teams")
                continue
            a, b = sorted(pair, key=lambda e: e["roster_id"])
            sa, sb = _score(a), _score(b)
            if sa == 0 and sb == 0:
                continue  # not played yet
            if week < playoff_start:
                gtype = "regular"
            elif frozenset((a["roster_id"], b["roster_id"])) in playoff_pairs.get(week, set()):
                gtype = "playoff"
            else:
                gtype = "consolation"
            week_games.append(make_game(season, week, "sleeper", gtype,
                                        who(a["roster_id"]), sa, who(b["roster_id"]), sb))
        if not week_games and week < playoff_start and complete:
            missing_weeks.append(week)
        games.extend(week_games)

    champion = None
    final = next((m for m in wb if m.get("p") == 1 and m.get("w") is not None), None)
    if final and complete:
        champion = who(int(final["w"]))
    elif complete:
        issues.append("no championship result in winners_bracket")

    sacko = None
    if complete:
        roster = _sacko_roster(season_dir, league, lb)
        if roster is None:
            issues.append("no finished loser-bracket final; Sacko unknown")
        else:
            sacko = who(roster)

    meta = {
        "season": season,
        "platform": "sleeper",
        "league_id": league.get("league_id"),
        "status": league.get("status"),
        "managers": sorted({who(int(r["roster_id"])) for r in rosters}),
        "regular_weeks": max(0, playoff_start - 1) if playoff_start != 99 else None,
        "playoff_start_week": playoff_start if playoff_start != 99 else None,
        "champion": champion,
        "sacko": sacko,
        "last_place_regular": None,  # derived from standings in build_games (with overrides)
        "missing_weeks": missing_weeks,
    }
    return games, meta, issues
