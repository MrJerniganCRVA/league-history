"""Turn cached Sleeper transactions into docs/data/transactions.json for the Transactions page.

Each transaction becomes one entry with a `sides` list, one per team involved:
  {"id", "season", "week", "ts", "type", "sides": [{"manager", "adds", "drops", ...}]}
`type` is Sleeper's: trade, waiver, free_agent or commissioner. Only completed moves are cached
(sleeper_fetch drops failed claims), so everything here actually happened.
"""
from __future__ import annotations

from pathlib import Path

from common import SLEEPER_RAW, Resolver, read_json
from sleeper_normalize import roster_manager


def _side(tx: dict, roster_id: int, who) -> dict:
    adds = sorted(str(p) for p, r in (tx.get("adds") or {}).items() if int(r) == roster_id)
    drops = sorted(str(p) for p, r in (tx.get("drops") or {}).items() if int(r) == roster_id)
    side: dict = {"manager": who(roster_id), "adds": adds, "drops": drops}
    bid = (tx.get("settings") or {}).get("waiver_bid")
    if tx.get("type") == "waiver" and bid is not None:
        side["bid"] = int(bid)
    if tx.get("type") == "trade":
        budget = tx.get("waiver_budget") or []
        faab_in = sum(int(b.get("amount") or 0) for b in budget if int(b.get("receiver", -1)) == roster_id)
        faab_out = sum(int(b.get("amount") or 0) for b in budget if int(b.get("sender", -1)) == roster_id)

        def pick(d: dict) -> dict:
            return {"season": int(d["season"]), "round": int(d["round"]), "original": who(d["roster_id"])}
        picks = tx.get("draft_picks") or []
        picks_in = [pick(d) for d in picks if int(d.get("owner_id", -1)) == roster_id]
        picks_out = [pick(d) for d in picks if int(d.get("previous_owner_id", -1)) == roster_id]
        # only non-empty extras, to keep the file small
        for k, v in (("faab_in", faab_in), ("faab_out", faab_out),
                     ("picks_in", picks_in), ("picks_out", picks_out)):
            if v:
                side[k] = v
    return side


def normalize_sleeper_transactions(season_dir: Path, resolver: Resolver) -> tuple[list[dict], list[str]]:
    league = read_json(season_dir / "league.json")
    users = read_json(season_dir / "users.json", []) or []
    rosters = read_json(season_dir / "rosters.json", []) or []
    issues: list[str] = []
    who = roster_manager(users, rosters, resolver, issues)
    season = int(league["season"])
    out = []
    for path in sorted((season_dir / "transactions").glob("*.json")):
        for tx in read_json(path, []) or []:
            if tx.get("status") != "complete":
                continue
            roster_ids = [int(r) for r in tx.get("roster_ids") or []]
            # some commissioner moves leave roster_ids empty; fall back to who was touched
            if not roster_ids:
                roster_ids = sorted({int(r) for r in list((tx.get("adds") or {}).values())
                                     + list((tx.get("drops") or {}).values())})
            sides = [_side(tx, r, who) for r in roster_ids]
            sides = [s for s in sides if s["adds"] or s["drops"] or s.get("picks_in") or s.get("faab_in")
                     or s.get("picks_out") or s.get("faab_out")]
            if not sides:
                continue
            out.append({
                "id": str(tx["transaction_id"]),
                "season": season,
                "week": int(tx.get("leg") or path.stem),
                "ts": int(tx.get("status_updated") or tx.get("created") or 0),
                "type": tx.get("type"),
                "sides": sides,
            })
    out.sort(key=lambda t: (t["season"], t["ts"], t["id"]))
    return out, issues


def player_table(transactions: list[dict], players_path: Path = SLEEPER_RAW / "players.json") -> dict:
    """id -> {name, pos, team} for every player referenced, so the page needs no other lookup."""
    known = (read_json(players_path, {}) or {}).get("players") or {}
    ids = sorted({p for t in transactions for s in t["sides"] for p in s["adds"] + s["drops"]})
    out = {}
    for pid in ids:
        p = known.get(pid) or {}
        out[pid] = {"name": p.get("full_name") or f"Player {pid}",
                    "pos": p.get("position") or "?",
                    "team": p.get("team")}
    return out
