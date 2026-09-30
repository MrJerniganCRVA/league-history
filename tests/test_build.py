import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from build_games import BuildError, apply_results, build, normalize_yahoo_season, regular_season_last  # noqa: E402
from common import Resolver, make_game  # noqa: E402

MANAGERS = [
    {"manager_id": "alice", "display_name": "Alice", "sleeper_user_ids": ["u1"],
     "yahoo_team_names_by_season": {"2020": "Alpha"}},
    {"manager_id": "bob", "display_name": "Bob", "sleeper_user_ids": ["u2"],
     "yahoo_team_names_by_season": {"2020": "Bravo"}},
    {"manager_id": "carl", "display_name": "Carl", "sleeper_user_ids": ["u3"]},
]


def g(week, a, sa, b, sb, t="regular", season=2023):
    return make_game(season, week, "sleeper", t, a, sa, b, sb)


class LastPlaceTest(unittest.TestCase):
    def test_worst_record_then_fewest_points(self):
        games = [g(1, "a", 100, "b", 90), g(1, "c", 80, "d", 85),
                 g(2, "a", 70, "c", 60), g(2, "b", 95, "d", 60),
                 g(3, "c", 200, "d", 10, t="consolation")]  # consolation ignored
        # b: 1-1, c: 0-2 (140 pts), d: 1-1 -> c is last
        self.assertEqual(regular_season_last(games, 2023), "c")
        games.append(g(3, "d", 50, "b", 51))  # d now 1-2 (195), c 0-2 still worst
        self.assertEqual(regular_season_last(games, 2023), "c")

    def test_tie_counts_half_and_points_break_ties(self):
        games = [g(1, "a", 90, "b", 90), g(1, "c", 70, "d", 80)]
        # a,b: 0.5 wins; c: 0 -> c last
        self.assertEqual(regular_season_last(games, 2023), "c")
        games = [g(1, "a", 90, "b", 100), g(1, "c", 70, "d", 80)]
        # a and c both 0-1: c has fewer points
        self.assertEqual(regular_season_last(games, 2023), "c")

    def test_overrides_and_in_progress(self):
        games = [g(1, "a", 100, "b", 90)]
        seasons = [{"season": 2023, "status": "complete", "champion": "a", "last_place": None},
                   {"season": 2024, "status": "in_season", "champion": None, "last_place": None}]
        apply_results(games, seasons, {"champion_overrides": {"2023": "b"}})
        self.assertEqual((seasons[0]["champion"], seasons[0]["last_place"], seasons[0]["last_place_source"]),
                         ("b", "b", "regular_season_record"))
        self.assertIsNone(seasons[1]["last_place"])
        apply_results(games, seasons, {"last_place_overrides": {2023: "a"}})
        self.assertEqual((seasons[0]["last_place"], seasons[0]["last_place_source"]), ("a", "override"))


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.yahoo = self.tmp / "yahoo"

    def test_sleeper_only_build(self):
        games, seasons, _ = build({}, Resolver(MANAGERS), HERE / "fixtures" / "sleeper", self.yahoo)
        self.assertEqual(len(games), 6)
        self.assertEqual([s["season"] for s in seasons], [2023])
        self.assertEqual(seasons[0]["champion"], "alice")
        self.assertEqual(seasons[0]["last_place_source"], "regular_season_record")

    def test_yahoo_file_is_picked_up(self):
        self.yahoo.mkdir()
        (self.yahoo / "2020.json").write_text(json.dumps({
            "season": 2020, "settings": {"playoff_start_week": 2},
            "teams": [{"team_key": "t1", "name": "Alpha", "guids": [], "nicknames": ["al"]},
                      {"team_key": "t2", "name": "Bravo", "guids": [], "nicknames": ["bo"]},
                      {"team_key": "t3", "name": "Ghost Team", "guids": [], "nicknames": ["x"]}],
            "games": [{"week": 1, "team_a_key": "t1", "score_a": 90.5, "team_b_key": "t2", "score_b": 80,
                       "game_type": "regular"},
                      {"week": 2, "team_a_key": "t1", "score_a": 0, "team_b_key": "t3", "score_b": 0,
                       "game_type": "playoff"}],
            "champion_team_key": "t1", "last_team_key": "t3"}))
        r = Resolver(MANAGERS)
        games, seasons, _ = build({}, r, HERE / "fixtures" / "sleeper", self.yahoo)
        y = [x for x in games if x["platform"] == "yahoo"]
        self.assertEqual(len(y), 1)  # 0-0 game skipped
        self.assertEqual((y[0]["team_a"], y[0]["winner"]), ("alice", "alice"))
        s2020 = seasons[0]
        self.assertEqual((s2020["champion"], s2020["last_place_source"]), ("alice", "final_rank"))
        self.assertTrue(s2020["last_place"].startswith("unmapped:yahoo:2020:Ghost Team"))

    def test_bad_yahoo_file_is_an_error(self):
        self.yahoo.mkdir()
        (self.yahoo / "2020.json").write_text("{}")
        with self.assertRaises(BuildError):
            normalize_yahoo_season(self.yahoo / "2020.json", Resolver(MANAGERS))


if __name__ == "__main__":
    unittest.main()
