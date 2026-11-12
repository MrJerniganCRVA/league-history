"""Score trades and pickups by what they did to a team's best possible lineup afterwards.

For every week after a move that the team played (regular season or playoffs, not consolation):
    gain = best lineup from the real roster - best lineup from the roster without the move
"Without the move" means: take out the players it brought in (while they are on the roster) and
put back the players it sent away or dropped. Players brought in count only for their first unbroken
stint on the roster. For a trade, players sent away come back for the
rest of the season, even if the other team later cut them. For a pickup, the dropped player comes
back only for the weeks the picked-up player stayed on the roster.

Wins gained: each week, compare the real result with the result if the team (and, in a trade with
this week's opponent, the opponent too) had scored its gain less. A loss flipped to a win is +1,
a tie counts half. Regular-season and playoff flips are kept apart.

Player points come from Sleeper's matchup data (players_points) for anyone rostered that week, and
otherwise from the weekly stats times the league's scoring settings (players on waivers).
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from common import Resolver, read_json
from lineup import best_lineup, lineup_slots
from sleeper_normalize import normalize_sleeper_season, roster_manager

SCORED_GAMES = ("regular", "playoff")


def _result(a: float, b: float) -> float:
    a, b = round(a, 2), round(b, 2)
    return 1.0 if a > b else 0.5 if a == b else 0.0


class SeasonScorer:
    def __init__(self, season_dir: Path, resolver: Resolver, players: dict[str, dict]):
        league = read_json(season_dir / "league.json")
        users = read_json(season_dir / "users.json", []) or []
        rosters = read_json(season_dir / "rosters.json", []) or []
        who = roster_manager(users, rosters, resolver, [])
        self.roster_of = {who(r["roster_id"]): int(r["roster_id"]) for r in rosters}
        self.slots = lineup_slots(league.get("roster_positions") or [])
        self.scoring = {k: float(v) for k, v in (league.get("scoring_settings") or {}).items() if v}
        self.positions = {pid: set(p.get("fantasy_positions") or [p.get("position")])
                          for pid, p in players.items()}
        self.rosters: dict[int, dict[int, set[str]]] = defaultdict(dict)  # week -> roster_id -> players
        self.starters: dict[int, dict[int, set[str]]] = defaultdict(dict)
        self.points: dict[int, dict[str, float]] = defaultdict(dict)  # week -> player -> points
        for path in sorted((season_dir / "matchups").glob("*.json")):
            week = int(path.stem)
            for e in read_json(path, []) or []:
                rid = int(e["roster_id"])
                self.rosters[week][rid] = {str(p) for p in e.get("players") or []}
                self.starters[week][rid] = {str(p) for p in e.get("starters") or []}
                for pid, pts in (e.get("players_points") or {}).items():
                    self.points[week][str(pid)] = float(pts or 0)
        self.stats = {int(p.stem): read_json(p, {}) or {} for p in (season_dir / "stats").glob("*.json")}
        # (week, manager) -> (opponent, score, opp_score, game_type), from the same games the site shows
        games, _, _ = normalize_sleeper_season(season_dir, resolver)
        self.games: dict[tuple[int, str], tuple] = {}
        for g in games:
            if g["game_type"] not in SCORED_GAMES:
                continue
            self.games[(g["week"], g["team_a"])] = (g["team_b"], g["score_a"], g["score_b"], g["game_type"])
            self.games[(g["week"], g["team_b"])] = (g["team_a"], g["score_b"], g["score_a"], g["game_type"])
        self._cache: dict[tuple[int, frozenset], float] = {}

    # ------------------------------------------------------------------ points
    def player_points(self, week: int, pid: str) -> float:
        if pid in self.points[week]:
            return self.points[week][pid]
        st = (self.stats.get(week) or {}).get(pid)
        if not st:
            return 0.0
        pts = round(sum(self.scoring.get(k, 0.0) * v for k, v in st.items()), 2)
        self.points[week][pid] = pts
        return pts

    def best(self, week: int, roster: set[str]) -> float:
        key = (week, frozenset(roster))
        if key not in self._cache:
            pts = {p: self.player_points(week, p) for p in roster}
            self._cache[key] = best_lineup(roster, pts, self.positions, self.slots)[0]
        return self._cache[key]

    # ------------------------------------------------------------------ moves
    def _start_week(self, week: int, rid: int, adds: set[str], drops: set[str]) -> int:
        """The move's own week counts only if that week's roster already reflects it."""
        roster = self.rosters.get(week, {}).get(rid)
        if roster is None:
            return week + 1
        if adds and adds & roster:
            return week
        if not adds and drops and not drops & roster:
            return week
        return week + 1

    def side_gains(self, tx: dict, side: dict, stop: dict[str, int] | None = None) -> dict[int, float] | None:
        """week -> gain for one team's side of a trade or pickup; None if the move isn't scored."""
        kind = "trade" if tx["type"] == "trade" else "pickup" if side["adds"] else None
        if kind is None or tx["type"] == "commissioner":
            return None
        rid = self.roster_of.get(side["manager"])
        if rid is None:
            return None
        adds, drops = set(side["adds"]), set(side["drops"])
        start = self._start_week(tx["week"], rid, adds, drops)
        gains: dict[int, float] = {}
        gone: set[str] = set()  # added players count for one unbroken stint, so a later re-add isn't double-counted
        stop = stop or {}
        for week in sorted(w for w in self.rosters if w >= start):
            actual = self.rosters[week].get(rid)
            if actual is None:
                continue
            gone |= adds - actual
            gone |= {p for p in adds if week > stop.get(p, 99)}
            if (week, side["manager"]) not in self.games:
                continue  # bye, eliminated, consolation, or not played yet
            held = (actual & adds) - gone
            if kind == "pickup" and not held:
                continue  # the picked-up player was gone by then
            without = (actual - held) | drops
            gains[week] = round(self.best(week, actual) - self.best(week, without), 2)
        return gains

    def started_points(self, side: dict, weeks) -> float:
        rid = self.roster_of.get(side["manager"])
        adds = set(side["adds"])
        return round(sum(self.player_points(w, p) for w in weeks
                         for p in adds & self.starters[w].get(rid, set())), 2)

    def score(self, tx: dict, stops: dict[str, dict[str, int]] | None = None) -> None:
        """Adds pts / n (weeks scored) / wins / po_wins / started (and weeks, for trades) to each scored side.
        stops: manager -> player -> last week that added player may count (see score_transactions)."""
        stops = stops or {}
        gains = {i: self.side_gains(tx, s, stops.get(s["manager"])) for i, s in enumerate(tx["sides"])}
        by_manager = {s["manager"]: gains[i] for i, s in enumerate(tx["sides"]) if gains[i] is not None}
        for i, side in enumerate(tx["sides"]):
            g = gains[i]
            if g is None:
                continue
            wins = {"regular": 0.0, "playoff": 0.0}
            for week, gain in g.items():
                opp, score, opp_score, gtype = self.games[(week, side["manager"])]
                opp_gain = (by_manager.get(opp) or {}).get(week, 0.0)
                wins[gtype] += _result(score, opp_score) - _result(score - gain, opp_score - opp_gain)
            side["pts"] = round(sum(g.values()), 2)
            side["n"] = len(g)  # weeks scored, for points per week
            side["wins"] = wins["regular"]
            side["po_wins"] = wins["playoff"]
            side["started"] = self.started_points(side, g.keys())
            if tx["type"] == "trade":
                side["weeks"] = [[w, v] for w, v in sorted(g.items())]


def score_transactions(season_dir: Path, txs: list[dict], resolver: Resolver,
                       players: dict[str, dict]) -> None:
    """If a team acquires the same player again later (e.g. a claim redone after a commissioner
    reversal), that player stops counting for the earlier move the week before the later one."""
    scorer = SeasonScorer(season_dir, resolver, players)
    later: dict[tuple[str, str], int] = {}  # (manager, player) -> week of the next acquisition
    stops: dict[str, dict[str, dict[str, int]]] = {}
    for tx in sorted(txs, key=lambda t: t["ts"], reverse=True):
        per = {}
        for side in tx["sides"]:
            m = side["manager"]
            per[m] = {p: later[(m, p)] - 1 for p in side["adds"] if (m, p) in later}
            for p in side["adds"]:
                later[(m, p)] = tx["week"]
        stops[tx["id"]] = per
    for tx in txs:
        scorer.score(tx, stops[tx["id"]])
