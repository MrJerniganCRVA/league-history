"""Sanity report over normalized data. Run directly after sleeper_fetch.py, or via build_games.py."""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

from common import SLEEPER_RAW, Resolver


def _champ(season: dict) -> str:
    if season.get("champion"):
        return season["champion"]
    return "(in progress)" if season.get("status", "complete") != "complete" else "??"


def print_report(games: list[dict], seasons: list[dict], issues: dict[int, list[str]],
                 unmapped: dict[str, str], out=sys.stdout) -> None:
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("=" * 64)
    p("SANITY REPORT")
    p("=" * 64)
    per_season: dict[int, Counter] = defaultdict(Counter)
    for g in games:
        per_season[g["season"]][g["game_type"]] += 1
    p(f"{'season':<8}{'platform':<9}{'reg':>5}{'po':>5}{'cons':>6}{'mgrs':>6}  champion")
    for s in sorted(seasons, key=lambda s: s["season"]):
        c = per_season[s["season"]]
        p(f"{s['season']:<8}{s['platform']:<9}{c['regular']:>5}{c['playoff']:>5}"
          f"{c['consolation']:>6}{len(s['managers']):>6}  {_champ(s)}")
    p(f"TOTAL games: {len(games)}")

    p("\nManagers per season:")
    for s in sorted(seasons, key=lambda s: s["season"]):
        p(f"  {s['season']}: {', '.join(s['managers'])}")

    p("\nUnmapped identities (add to manager_map.csv / managers.json):")
    if unmapped:
        for key, desc in sorted(unmapped.items()):
            n = sum(1 for g in games if key in (g["team_a"], g["team_b"]))
            p(f"  - {desc}  [{n} games]")
    else:
        p("  none")

    p("\nWeeks with missing scores (regular season, no games found):")
    missing = [(s["season"], s.get("missing_weeks") or []) for s in seasons]
    missing = [(season, wks) for season, wks in missing if wks]
    p("".join(f"  {season}: weeks {wks}\n" for season, wks in missing).rstrip() or "  none")

    p("\nSeasons without a determinable champion:")
    no_champ = [s["season"] for s in seasons
                if not s.get("champion") and s.get("status", "complete") == "complete"]
    p(f"  {no_champ or 'none'}")

    p("\nSeasons without a Sacko (loser-bracket loser):")
    no_sacko = [s["season"] for s in seasons
                if not s.get("sacko") and s.get("status", "complete") == "complete"]
    p(f"  {no_sacko or 'none'}")

    p("\nOther issues:")
    any_issue = False
    for season in sorted(issues):
        for msg in issues[season]:
            any_issue = True
            p(f"  {season}: {msg}")
    if not any_issue:
        p("  none")
    p("=" * 64)


def main() -> int:
    from sleeper_normalize import normalize_sleeper_season
    resolver = Resolver()
    games, seasons, issues = [], [], {}
    for d in sorted(p for p in SLEEPER_RAW.iterdir() if p.is_dir()) if SLEEPER_RAW.exists() else []:
        if not (d / "league.json").exists():
            continue
        g, meta, iss = normalize_sleeper_season(d, resolver)
        games += g
        seasons.append(meta)
        issues[meta["season"]] = iss
    if not seasons:
        print("No cached Sleeper seasons. Run scripts/sleeper_fetch.py first.")
        return 1
    print_report(games, seasons, issues, resolver.unmapped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
