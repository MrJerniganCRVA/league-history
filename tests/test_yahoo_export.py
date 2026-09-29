import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from yahoo_export import parse_renew, tag_game_types, txt  # noqa: E402


def g(week, a, sa, b, sb, cons=False):
    return {"week": week, "team_a_key": a, "score_a": sa, "team_b_key": b, "score_b": sb,
            "is_consolation": cons}


class HelpersTest(unittest.TestCase):
    def test_txt_and_renew(self):
        self.assertEqual(txt(b"Danger Zone"), "Danger Zone")
        self.assertEqual(parse_renew("380_905683"), ("380", "905683"))
        self.assertIsNone(parse_renew(""))
        self.assertIsNone(parse_renew(None))


class TagTest(unittest.TestCase):
    # 6 teams, 4 make playoffs, playoffs start week 3 (semis), week 4 final + 3rd place
    seeds = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6}

    def test_bracket(self):
        games = [
            g(1, "A", 100, "B", 90), g(2, "C", 80, "D", 80),                     # regular (tie ok)
            g(3, "A", 110, "D", 90), g(3, "B", 95, "C", 99), g(3, "E", 70, "F", 60, cons=True),
            g(4, "A", 120, "C", 100),  # final
            g(4, "B", 100, "D", 90),   # 3rd place: both eliminated -> consolation
            g(4, "E", 50, "F", 55),    # consolation even without the flag
        ]
        tag_game_types(games, playoff_start=3, seeds=self.seeds, num_playoff_teams=4)
        types = [x["game_type"] for x in games]
        self.assertEqual(types, ["regular", "regular", "playoff", "playoff", "consolation",
                                 "playoff", "consolation", "consolation"])

    def test_byes_stay_alive(self):
        # 6-team playoff: seeds 1-2 on bye in week 3
        games = [g(3, "C", 90, "F", 80), g(3, "D", 70, "E", 75),
                 g(4, "A", 100, "E", 90), g(4, "B", 100, "C", 90)]
        tag_game_types(games, 3, self.seeds, 6)
        self.assertTrue(all(x["game_type"] == "playoff" for x in games))

    def test_multiweek_final(self):
        games = [g(3, "A", 100, "B", 90), g(4, "A", 80, "B", 120)]
        tag_game_types(games, 3, self.seeds, 2, multiweek_final_week=3)
        self.assertEqual([x["game_type"] for x in games], ["playoff", "playoff"])


if __name__ == "__main__":
    unittest.main()
