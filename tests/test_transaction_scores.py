import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from common import Resolver, write_json  # noqa: E402
from lineup import best_lineup, lineup_slots  # noqa: E402
from transaction_scores import score_transactions  # noqa: E402

MANAGERS = [
    {"manager_id": "alice", "display_name": "Alice", "sleeper_user_ids": ["u1"]},
    {"manager_id": "bob", "display_name": "Bob", "sleeper_user_ids": ["u2"]},
]
POS = {"q1": "QB", "q2": "QB", "r1": "RB", "r2": "RB", "r3": "RB",
       "w1": "WR", "w2": "WR", "w3": "WR", "w4": "WR", "w5": "WR"}
PLAYERS = {p: {"position": pos, "fantasy_positions": [pos]} for p, pos in POS.items()}
PTS = {"q1": 10, "q2": 10, "r1": 9, "r2": 20, "r3": 6, "w1": 18, "w2": 15, "w3": 5, "w4": 12, "w5": 30}


def entry(rid, players, starters, points, matchup=1):
    return {"roster_id": rid, "matchup_id": matchup, "points": points, "custom_points": None,
            "players": players, "starters": starters,
            "players_points": {p: PTS[p] for p in players}}


class LineupTest(unittest.TestCase):
    def test_flex_takes_best_leftover(self):
        slots = lineup_slots(["QB", "RB", "WR", "FLEX", "BN", "BN"])
        pos = {p: {v} for p, v in POS.items()}
        total, starters = best_lineup(["q1", "r1", "r2", "w1", "w2"], PTS, pos, slots)
        self.assertEqual(total, 10 + 20 + 18 + 15)
        self.assertEqual(set(starters), {"q1", "r2", "w1", "w2"})

    def test_empty_slot_when_nobody_eligible(self):
        slots = lineup_slots(["QB", "K"])
        self.assertEqual(best_lineup(["q1"], PTS, {"q1": {"QB"}}, slots), (10, ["q1"]))


class ScoreTest(unittest.TestCase):
    """Alice trades WR w1 to Bob for RB r2 after week 1, then picks up WR w5 (dropping w4) in week 3."""

    def setUp(self):
        d = Path(tempfile.mkdtemp()) / "2023"
        write_json(d / "league.json", {
            "season": "2023", "status": "complete", "league_id": "L",
            "roster_positions": ["QB", "RB", "WR", "FLEX", "BN", "BN"],
            "settings": {"playoff_week_start": 10, "playoff_teams": 2},
            "scoring_settings": {"rec_td": 6}})
        write_json(d / "users.json", [{"user_id": "u1", "display_name": "A"}, {"user_id": "u2", "display_name": "B"}])
        write_json(d / "rosters.json", [{"roster_id": 1, "owner_id": "u1"}, {"roster_id": 2, "owner_id": "u2"}])
        write_json(d / "winners_bracket.json", [])
        write_json(d / "losers_bracket.json", [])
        a1 = ["q1", "r1", "w1", "w2", "w4"]
        a2 = ["q1", "r1", "r2", "w2", "w4"]
        a3 = ["q1", "r1", "r2", "w2", "w5"]
        b2 = ["q2", "w1", "w3", "r3"]
        write_json(d / "matchups" / "01.json", [entry(1, a1, a1[:4], 60), entry(2, ["q2", "r2", "w3", "r3"], [], 55)])
        write_json(d / "matchups" / "02.json", [entry(1, a2, ["q1", "r2", "w2", "w4"], 50), entry(2, b2, b2, 49)])
        write_json(d / "matchups" / "03.json", [entry(1, a3, ["q1", "r2", "w5", "w2"], 60), entry(2, b2, b2, 70)])
        # w4 is on waivers in week 3: scored from stats (2 rec TD x 6 = 12)
        write_json(d / "stats" / "03.json", {"w4": {"rec_td": 2}})
        self.trade = {"id": "t", "season": 2023, "week": 1, "ts": 1, "type": "trade", "sides": [
            {"manager": "alice", "adds": ["r2"], "drops": ["w1"]},
            {"manager": "bob", "adds": ["w1"], "drops": ["r2"]}]}
        self.pickup = {"id": "p", "season": 2023, "week": 3, "ts": 2, "type": "free_agent", "sides": [
            {"manager": "alice", "adds": ["w5"], "drops": ["w4"]}]}
        self.drop = {"id": "d", "season": 2023, "week": 3, "ts": 3, "type": "free_agent", "sides": [
            {"manager": "bob", "adds": [], "drops": ["w3"]}]}
        score_transactions(d, [self.trade, self.pickup, self.drop], Resolver(MANAGERS), PLAYERS)

    def test_trade_points_by_best_lineup(self):
        alice, bob = self.trade["sides"]
        # wk2: with 10+20+15+12=57, without 10+9+18+15=52 -> +5; wk3: 75 vs 67 -> +8
        self.assertEqual(alice["weeks"], [[2, 5.0], [3, 8.0]])
        self.assertEqual(alice["pts"], 13.0)
        self.assertEqual(alice["n"], 2)  # weeks scored, for points per week
        # Bob: 39 vs 41 both weeks
        self.assertEqual(bob["pts"], -4.0)

    def test_trade_wins_include_partner_swing(self):
        alice, bob = self.trade["sides"]
        # wk2 real 50-49 Alice; without: 45 vs 51 -> flips. wk3 lost either way.
        self.assertEqual((alice["wins"], bob["wins"]), (1.0, -1.0))
        self.assertEqual(alice["po_wins"], 0.0)

    def test_started_is_context(self):
        self.assertEqual(self.trade["sides"][0]["started"], 40.0)  # r2 started both weeks

    def test_pickup_restores_dropped_player(self):
        side = self.pickup["sides"][0]
        self.assertEqual(side["pts"], 18.0)  # 75 vs 57 in week 3 (w4's 12 from stats)
        self.assertEqual(side["wins"], 0.0)
        self.assertNotIn("weeks", side)

    def test_plain_drop_not_scored(self):
        self.assertNotIn("pts", self.drop["sides"][0])


if __name__ == "__main__":
    unittest.main()
