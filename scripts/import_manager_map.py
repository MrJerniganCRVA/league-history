"""Build/update managers.json from the hand-maintained manager_map.csv.

CSV format (one row per person, blank cell = not in the league that season):
    SleeperID,2016,2017,2018,2019,2020[,DisplayName]
    OviSnipes,JernyFootball,JernyFootball,...,CeeDee's TDs

- First column: Sleeper username (header `SleeperID` or `sleeper_name`). Blank for someone who
  never played on Sleeper; then DisplayName is required.
- Year columns: `2016` or `yahoo_2016` -> that season's Yahoo team name.
- Optional DisplayName overrides the name shown on the site.

Usage: python scripts/import_manager_map.py [--csv PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import difflib
import re
import sys
from pathlib import Path

from common import (MANAGER_MAP_CSV, MANAGERS_PATH, SLEEPER_RAW, YAHOO_RAW, norm_name,
                    read_json, slugify, write_json)

SLEEPER_HEADERS = {"sleeperid", "sleeper_id", "sleeper_name", "sleeper"}
DISPLAY_HEADERS = {"displayname", "display_name", "manager"}
YEAR_RE = re.compile(r"^(?:yahoo_)?(\d{4})$", re.I)


class MapError(ValueError):
    pass


def parse_csv(path: Path) -> list[dict]:
    """Return [{sleeper_name, display_name, yahoo: {season: team}}] with validation."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [h.strip() for h in next(reader)]
        rows = [[c.strip() for c in r] for r in reader]

    sleeper_col = display_col = None
    year_cols: dict[int, str] = {}
    for i, h in enumerate(header):
        key = h.lower().replace(" ", "")
        if key in SLEEPER_HEADERS:
            sleeper_col = i
        elif key in DISPLAY_HEADERS:
            display_col = i
        elif (m := YEAR_RE.match(h)):
            year_cols[i] = m.group(1)
    if sleeper_col is None:
        raise MapError(f"{path.name}: no SleeperID/sleeper_name column in header {header}")

    people, seen_sleeper, seen_team = [], {}, {}
    for line_no, row in enumerate(rows, start=2):
        if not any(row):
            continue
        row += [""] * (len(header) - len(row))
        sleeper = row[sleeper_col]
        display = row[display_col] if display_col is not None else ""
        if not sleeper and not display:
            raise MapError(f"line {line_no}: needs a Sleeper name or a DisplayName")
        if sleeper:
            k = norm_name(sleeper)
            if k in seen_sleeper:
                raise MapError(f"line {line_no}: Sleeper name {sleeper!r} repeats line {seen_sleeper[k]}")
            seen_sleeper[k] = line_no
        yahoo = {}
        for i, season in year_cols.items():
            team = row[i]
            if not team:
                continue
            k = (season, norm_name(team))
            if k in seen_team:
                raise MapError(f"line {line_no}: {season} team {team!r} already used on line {seen_team[k]}")
            seen_team[k] = line_no
            yahoo[season] = team
        people.append({"sleeper_name": sleeper, "display_name": display or sleeper, "yahoo": yahoo})
    return people


def _sleeper_users() -> dict[str, str]:
    """norm(display_name) -> user_id from any cached Sleeper users.json."""
    out = {}
    for p in sorted(SLEEPER_RAW.glob("*/users.json")) if SLEEPER_RAW.exists() else []:
        for u in read_json(p, []) or []:
            for name in (u.get("display_name"), u.get("username")):
                if name:
                    out[norm_name(name)] = str(u["user_id"])
    return out


def _yahoo_teams() -> dict[str, list[str]]:
    """season -> team names from any cached Yahoo export."""
    out = {}
    for p in sorted(YAHOO_RAW.glob("*.json")) if YAHOO_RAW.exists() else []:
        data = read_json(p, {}) or {}
        out[str(data.get("season", p.stem))] = [t["name"] for t in data.get("teams", [])]
    return out


def merge(people: list[dict], existing: list[dict], sleeper_users: dict[str, str]) -> list[dict]:
    by_id = {m["manager_id"]: m for m in existing}
    result = []
    for p in people:
        mid = slugify(p["sleeper_name"] or p["display_name"])
        m = dict(by_id.pop(mid, {"manager_id": mid}))
        m["display_name"] = p["display_name"]
        if p["sleeper_name"]:
            m["sleeper_names"] = sorted(set(m.get("sleeper_names", [])) | {p["sleeper_name"]})
            uid = sleeper_users.get(norm_name(p["sleeper_name"]))
            if uid:
                m["sleeper_user_ids"] = sorted(set(m.get("sleeper_user_ids", [])) | {uid})
        m.setdefault("sleeper_user_ids", [])
        m["yahoo_team_names_by_season"] = dict(sorted(p["yahoo"].items()))
        m.setdefault("yahoo_manager_guids", [])
        m.setdefault("yahoo_team_names_fallback", [])
        result.append(m)
    # keep hand-added managers that aren't in the CSV
    result.extend(by_id.values())
    return result


def report(people: list[dict], sleeper_users: dict[str, str], yahoo_teams: dict[str, list[str]]) -> None:
    print(f"{len(people)} managers in CSV.")
    seasons = sorted({s for p in people for s in p["yahoo"]})
    for s in seasons:
        print(f"  Yahoo {s}: {sum(s in p['yahoo'] for p in people)} teams mapped")
    if sleeper_users:
        for p in people:
            if p["sleeper_name"] and norm_name(p["sleeper_name"]) not in sleeper_users:
                close = difflib.get_close_matches(norm_name(p["sleeper_name"]), sleeper_users, n=3)
                print(f"  ! Sleeper name {p['sleeper_name']!r} not in cached users; close: {close}")
    else:
        print("  (no cached Sleeper users yet; names are matched at build time)")
    for season, teams in yahoo_teams.items():
        known = {norm_name(t): t for t in teams}
        mapped = {norm_name(p["yahoo"][season]) for p in people if season in p["yahoo"]}
        for p in people:
            team = p["yahoo"].get(season)
            if team and norm_name(team) not in known:
                close = difflib.get_close_matches(team, teams, n=3)
                print(f"  ! {season}: CSV team {team!r} not in Yahoo export; close: {close}")
        for k, t in known.items():
            if k not in mapped:
                print(f"  ? {season}: Yahoo team {t!r} is not in the CSV (unmapped)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, default=MANAGER_MAP_CSV)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        people = parse_csv(args.csv)
    except MapError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    sleeper_users = _sleeper_users()
    managers = merge(people, read_json(MANAGERS_PATH, []) or [], sleeper_users)
    report(people, sleeper_users, _yahoo_teams())
    if not args.dry_run:
        write_json(MANAGERS_PATH, managers)
        print(f"Wrote {MANAGERS_PATH.name} ({len(managers)} managers).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
