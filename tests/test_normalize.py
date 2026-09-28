import io
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from common import Resolver, make_game  # noqa: E402
from sanity_report import print_report  # noqa: E402
from sleeper_fetch import last_week, round_weeks  # noqa: E402
from sleeper_normalize import normalize_sleeper_season  # noqa: E402

MANAGERS = [
    {"manager_id": "alice", "display_name": "Alice", "sleeper_user_ids": ["u1"]},
    {"manager_id": "bob", "display_name": "Bob", "sleeper_user_ids": ["u2"]},
    {"manager_id": "carl", "display_name": "Carl", "sleeper_user_ids": ["u3"]},
]


class MakeGameTest(unittest.TestCase):
    def test_winner_and_tie(self):
        self.assertEqual(make_game(2023, 1, "sleeper", "regular", "a", 1.01, "b", 1)["winner"], "a")
        self.assertEqual(make_game(2023, 1, "sleeper", "regular", "a", 99.1, "b", 99.10)["winner"], "tie")
        self.assertEqual(make_game(2023, 1, "yahoo", "playoff", "a", 80, "b", 81)["winner"], "b")

    def test_bad_type(self):
        with self.assertRaises(ValueError):
            make_game(2023, 1, "sleeper", "exhibition", "a", 1, "b", 2)


class SleeperNormalizeTest(unittest.TestCase):
    def setUp(self):
        self.resolver = Resolver(MANAGERS)
        self.games, self.meta, self.issues = normalize_sleeper_season(
            HERE / "fixtures" / "sleeper" / "2023", self.resolver)

    def game(self, week, team):
        return next(g for g in self.games if g["week"] == week and team in (g["team_a"], g["team_b"]))

    def test_counts_and_unplayed_week_skipped(self):
        # weeks 1-3 x 2 games; week 4 is all zeros; null matchup_id skipped
        self.assertEqual(len(self.games), 6)
        self.assertFalse(any(g["week"] == 4 for g in self.games))

    def test_co_owner_maps_to_primary(self):
        self.assertIn("carl", self.meta["managers"])

    def test_tie(self):
        g = self.game(2, "alice")
        self.assertEqual((g["team_b"], g["winner"]), ("carl", "tie"))

    def test_custom_points_override(self):
        g = self.game(2, "bob")
        self.assertEqual(g["score_a"], 120.0)
        self.assertEqual(g["winner"], "bob")

    def test_game_types(self):
        self.assertEqual(self.game(1, "alice")["game_type"], "regular")
        self.assertEqual(self.game(3, "alice")["game_type"], "playoff")
        self.assertEqual(self.game(3, "carl")["game_type"], "consolation")

    def test_champion(self):
        self.assertEqual(self.meta["champion"], "alice")

    def test_unmapped_reported_not_dropped(self):
        key = "unmapped:sleeper:u4"
        self.assertIn(key, self.resolver.unmapped)
        self.assertIn("Dana", self.resolver.unmapped[key])
        self.assertEqual(sum(key in (g["team_a"], g["team_b"]) for g in self.games), 3)

    def test_report_runs(self):
        buf = io.StringIO()
        print_report(self.games, [self.meta], {2023: self.issues}, self.resolver.unmapped, out=buf)
        self.assertIn("Dana", buf.getvalue())


class PlayoffWeeksTest(unittest.TestCase):
    def test_round_types(self):
        lg = {"settings": {"playoff_week_start": 15, "playoff_round_type": 0}}
        self.assertEqual(round_weeks(lg, 3), {1: [15], 2: [16], 3: [17]})
        lg["settings"]["playoff_round_type"] = 1
        self.assertEqual(round_weeks(lg, 3), {1: [15], 2: [16], 3: [17, 18]})
        lg["settings"]["playoff_round_type"] = 2
        self.assertEqual(round_weeks(lg, 2), {1: [15, 16], 2: [17, 18]})

    def test_last_week_from_playoff_teams(self):
        lg = {"settings": {"playoff_week_start": 15, "playoff_teams": 6, "playoff_round_type": 0}}
        self.assertEqual(last_week(lg, None), 17)


if __name__ == "__main__":
    unittest.main()
