"""Best possible lineup for a roster, given each player's points that week."""
from __future__ import annotations

# Which positions can fill each Sleeper roster slot. Single-position slots are filled first,
# then the flex slots from whoever is left; that is optimal whenever each flex slot accepts a
# superset of positions (true for every standard Sleeper layout, including this league's).
SLOT_POSITIONS = {
    "FLEX": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "IDP_FLEX": {"DL", "LB", "DB"},
}
BENCH = {"BN", "IR", "TAXI"}


def lineup_slots(roster_positions: list[str]) -> list[set[str]]:
    slots = [SLOT_POSITIONS.get(s, {s}) for s in roster_positions if s not in BENCH]
    return sorted(slots, key=len)  # most restrictive first


def best_lineup(players, points: dict[str, float], positions: dict[str, set[str]],
                slots: list[set[str]]) -> tuple[float, list[str]]:
    """(total, starters) for the highest-scoring legal lineup from `players`."""
    pool = sorted(set(players), key=lambda p: (-points.get(p, 0.0), p))
    used: set[str] = set()
    total, starters = 0.0, []
    for slot in slots:
        for p in pool:
            if p not in used and positions.get(p, set()) & slot:
                used.add(p)
                starters.append(p)
                total += points.get(p, 0.0)
                break
    return round(total, 2), starters
