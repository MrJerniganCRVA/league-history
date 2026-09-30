"""Merge Sleeper + Yahoo raw data into docs/data/{games,seasons,managers}.json.

Usage: python scripts/build_games.py

Yahoo is optional: any data_raw/yahoo/<season>.json present is included automatically.
"""
from __future__ import annotations

import sys
from collections import defaultdict
import json
from pathlib import Path

from common import (SITE_DATA, SLEEPER_RAW, UNMAPPED_PREFIX, YAHOO_RAW, Resolver, load_config,
                    make_game, read_json, write_json)
from sanity_report import print_report
from sleeper_normalize import normalize_sleeper_season


class BuildError(RuntimeError):
    pass


def normalize_yahoo_season(path: Path, resolver: Resolver) -> tuple[list[dict], dict, list[str]]:
    data = read_json(path)
    if not data or "games" not in data or "teams" not in data:
        raise BuildError(f"{path}: not a yahoo_export.py file")
    season = int(data["season"])
    teams = {t["team_key"]: t for t in data["teams"]}

    def who(team_key: str) -> str:
        t = teams.get(team_key)
        if not t:
            return resolver.yahoo_team(season, team_key)
        return resolver.yahoo_team(season, t["name"], t.get("guids"), ", ".join(t.get("nicknames", [])))

    games, issues = [], []
    for g in data["games"]:
        if g["score_a"] == 0 and g["score_b"] == 0:
            continue
        games.append(make_game(season, g["week"], "yahoo", g["game_type"],
                               who(g["team_a_key"]), g["score_a"], who(g["team_b_key"]), g["score_b"]))
    settings = data.get("settings", {})
    playoff_start = settings.get("playoff_start_week")
    champ = data.get("champion_team_key")
    last = data.get("last_team_key")
    meta = {
        "season": season,
        "platform": "yahoo",
        "status": "complete",
        "managers": sorted({who(k) for k in teams}),
        "regular_weeks": (playoff_start - 1) if playoff_start else None,
        "playoff_start_week": playoff_start,
        "champion": who(champ) if champ else None,
        # Yahoo's final standings already account for the consolation/loser bracket
        "sacko": who(last) if last else None,
        "last_place_regular": None,  # computed from regular-season games in apply_results
        "missing_weeks": [],
    }
    if not champ:
        issues.append("no champion in export")
    return games, meta, issues


def regular_season_last(games: list[dict], season: int) -> str | None:
    """Worst regular-season record (ties count half); fewest points for breaks ties."""
    wins: dict[str, float] = defaultdict(float)
    pts: dict[str, float] = defaultdict(float)
    for g in games:
        if g["season"] != season or g["game_type"] != "regular":
            continue
        for side, other in (("a", "b"), ("b", "a")):
            team = g[f"team_{side}"]
            pts[team] += g[f"score_{side}"]
            wins[team] += 1 if g["winner"] == team else 0.5 if g["winner"] == "tie" else 0
            wins.setdefault(g[f"team_{other}"], 0)
    if not wins:
        return None
    return min(wins, key=lambda t: (wins[t], pts[t], t))


def apply_results(games: list[dict], seasons: list[dict], cfg: dict) -> None:
    """Champion, Sacko and regular-season last place, with config.json overrides winning."""
    def overrides(key: str) -> dict[str, str]:
        return {str(k): v for k, v in (cfg.get(key) or {}).items()}

    champ_over = overrides("champion_overrides")
    sacko_over = overrides("sacko_overrides")
    last_over = overrides("last_place_overrides")
    for s in seasons:
        key = str(s["season"])
        s.setdefault("sacko", None)
        if key in champ_over:
            s["champion"] = champ_over[key]
        if key in sacko_over:
            s["sacko"] = sacko_over[key]
        if key in last_over:
            s["last_place_regular"], s["last_place_regular_source"] = last_over[key], "override"
        elif not s.get("last_place_regular") and s.get("status") == "complete":
            s["last_place_regular"] = regular_season_last(games, s["season"])
            s["last_place_regular_source"] = "regular_season_record" if s["last_place_regular"] else None
        s.setdefault("last_place_regular", None)
        s.setdefault("last_place_regular_source", None)


def build_managers(games: list[dict], resolver: Resolver, latest_season: int | None) -> list[dict]:
    seasons_by: dict[str, set[int]] = defaultdict(set)
    for g in games:
        seasons_by[g["team_a"]].add(g["season"])
        seasons_by[g["team_b"]].add(g["season"])
    out = []
    for mid, seasons in seasons_by.items():
        if mid.startswith(UNMAPPED_PREFIX):
            name = resolver.unmapped.get(mid, mid)
        else:
            name = resolver.display.get(mid, mid)
        out.append({
            "manager_id": mid,
            "display_name": name,
            "first_season": min(seasons),
            "last_season": max(seasons),
            "active": latest_season in seasons,
        })
    return sorted(out, key=lambda m: m["display_name"].casefold())


def build(cfg: dict, resolver: Resolver, sleeper_dir: Path = SLEEPER_RAW,
          yahoo_dir: Path = YAHOO_RAW) -> tuple[list[dict], list[dict], dict[int, list[str]]]:
    games, seasons, issues = [], [], {}
    for d in sorted(p for p in sleeper_dir.glob("*") if p.is_dir() and (p / "league.json").exists()):
        g, meta, iss = normalize_sleeper_season(d, resolver)
        games += g
        seasons.append(meta)
        issues[meta["season"]] = iss
    yahoo_files = sorted(yahoo_dir.glob("*.json")) if yahoo_dir.exists() else []
    if not yahoo_files:
        print("Yahoo: no data yet (data_raw/yahoo/ is empty); building from Sleeper only.")
    for path in yahoo_files:
        g, meta, iss = normalize_yahoo_season(path, resolver)
        if any(s["season"] == meta["season"] for s in seasons):
            raise BuildError(f"season {meta['season']} exists on both platforms")
        games += g
        seasons.append(meta)
        issues[meta["season"]] = iss
    if not seasons:
        raise BuildError("no raw data found; run scripts/sleeper_fetch.py first")
    games.sort(key=lambda g: (g["season"], g["week"], g["team_a"], g["team_b"]))
    seasons.sort(key=lambda s: s["season"])
    apply_results(games, seasons, cfg)
    return games, seasons, issues


def main() -> int:
    cfg = load_config()
    resolver = Resolver()
    try:
        games, seasons, issues = build(cfg, resolver)
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    latest = max(s["season"] for s in seasons)
    managers = build_managers(games, resolver, latest)
    public_seasons = [{k: v for k, v in s.items() if k not in ("missing_weeks", "league_id")}
                      for s in seasons]
    # one game per line: small, readable diffs when the weekly refresh adds games
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "games.json").write_text(
        "[\n" + ",\n".join(json.dumps(g, ensure_ascii=False) for g in games) + "\n]\n",
        encoding="utf-8")
    last = games[-1] if games else None
    write_json(SITE_DATA / "seasons.json", {
        "meta": {
            "site_title": cfg.get("site_title", "League History"),
            # deterministic (no timestamp) so an unchanged refresh produces no commit
            "data_through": {"season": last["season"], "week": last["week"]} if last else None,
            "platforms": sorted({s["platform"] for s in seasons}),
        },
        "seasons": public_seasons,
    })
    write_json(SITE_DATA / "managers.json", managers)
    print_report(games, seasons, issues, resolver.unmapped)
    print(f"Wrote {len(games)} games, {len(seasons)} seasons, {len(managers)} managers to docs/data/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
