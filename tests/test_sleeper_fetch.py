import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import sleeper_fetch  # noqa: E402
from common import read_json, write_json  # noqa: E402

LEAGUE = {
    "season": "2023", "status": "complete",
    "settings": {"playoff_week_start": 2, "playoff_teams": 2, "last_scored_leg": 2},
    "scoring_settings": {"rush_yd": 0.1, "rec_td": 6.0, "rec": 0.0, "fgm_50p": 5.0},
}

TRADE = {"transaction_id": "t1", "type": "trade", "status": "complete", "created": 200, "leg": 1,
         "roster_ids": [1, 2], "adds": {"p1": 2, "p2": 1}, "drops": {"p1": 1, "p2": 2},
         "draft_picks": [{"season": "2024", "round": 3, "roster_id": 1, "previous_owner_id": 1,
                          "owner_id": 2}], "waiver_budget": []}
CLAIM = {"transaction_id": "w1", "type": "waiver", "status": "complete", "created": 100, "leg": 1,
         "roster_ids": [1], "adds": {"p3": 1}, "drops": {"p4": 1}, "settings": {"waiver_bid": 12}}
FAILED = {"transaction_id": "w2", "type": "waiver", "status": "failed", "created": 100, "leg": 1,
          "roster_ids": [2], "adds": {"p3": 2}, "drops": None, "settings": {"waiver_bid": 5}}


class FakeClient:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        for suffix, value in self.routes.items():
            if url.endswith(suffix):
                if isinstance(value, Exception):
                    raise value
                return value
        return []


class TransactionsTest(unittest.TestCase):
    def test_failed_claims_dropped_and_sorted_by_time(self):
        out = Path(tempfile.mkdtemp())
        client = FakeClient({"/transactions/1": [TRADE, FAILED, CLAIM]})
        kept = sleeper_fetch.fetch_transactions(client, "L", out, 2)
        self.assertEqual(kept, 2)
        week1 = read_json(out / "transactions" / "01.json")
        self.assertEqual([t["transaction_id"] for t in week1], ["w1", "t1"])
        self.assertEqual(read_json(out / "transactions" / "02.json"), [])

    def test_trade_keeps_picks(self):
        out = Path(tempfile.mkdtemp())
        sleeper_fetch.fetch_transactions(FakeClient({"/transactions/1": [TRADE]}), "L", out, 1)
        self.assertEqual(read_json(out / "transactions" / "01.json")[0]["draft_picks"][0]["round"], 3)


class StatsTest(unittest.TestCase):
    def test_trim_keeps_scoring_keys_only(self):
        keys = sleeper_fetch.scoring_keys(LEAGUE)
        self.assertEqual(keys, {"rush_yd", "rec_td", "fgm_50p"})  # rec is 0 in this league
        raw = {"p1": {"rush_yd": 54, "rec": 3, "gp": 1}, "p2": {"gp": 1, "rush_yd": 0}}
        self.assertEqual(sleeper_fetch.trim_stats(raw, keys), {"p1": {"rush_yd": 54}})

    def test_trim_accepts_list_shape(self):
        raw = [{"player_id": "p9", "stats": {"rec_td": 1}}]
        self.assertEqual(sleeper_fetch.trim_stats(raw, {"rec_td"}), {"p9": {"rec_td": 1}})

    def test_failure_only_warns(self):
        out = Path(tempfile.mkdtemp())
        client = FakeClient({"/stats/nfl/regular/2023/1": RuntimeError("404")})
        with mock.patch("sys.stderr"):
            self.assertFalse(sleeper_fetch.fetch_stats(client, LEAGUE, out, 2))

    def test_in_season_skips_unfinished_week(self):
        lg = dict(LEAGUE, status="in_season", settings=dict(LEAGUE["settings"], last_scored_leg=9))
        self.assertEqual(sleeper_fetch.scored_weeks(lg, 10), 9)
        self.assertEqual(sleeper_fetch.scored_weeks(LEAGUE, 17), 17)


class BackfillTest(unittest.TestCase):
    def test_only_missing_folders_fetched(self):
        root = Path(tempfile.mkdtemp())
        season = root / "2023"
        write_json(season / "league.json", LEAGUE)
        write_json(season / "winners_bracket.json", [{"r": 1, "m": 1, "t1": 1, "t2": 2, "w": 1, "p": 1}])
        write_json(season / "stats" / "01.json", {})
        client = FakeClient({"/transactions/1": [CLAIM]})
        with mock.patch.object(sleeper_fetch, "SLEEPER_RAW", root):
            sleeper_fetch.backfill_season(client, "L", LEAGUE, skip_stats=False)
            self.assertTrue(all("/transactions/" in u for u in client.urls))
            self.assertEqual(len(client.urls), 2)  # weeks 1-2; stats/ already there
            client.urls.clear()
            sleeper_fetch.backfill_season(client, "L", LEAGUE, skip_stats=False)
            self.assertEqual(client.urls, [])  # second run is a no-op


class PlayersTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        write_json(self.root / "2023" / "matchups" / "01.json", [{"players": ["p1", "HOU"]}])
        write_json(self.root / "2023" / "transactions" / "01.json", [CLAIM])
        self.raw = {
            "p1": {"full_name": "Pat One", "position": "RB", "fantasy_positions": ["RB"], "team": "KC",
                   "college": "x", "height": "70"},
            "p3": {"full_name": "Pat Three", "position": "WR", "fantasy_positions": ["WR"]},
            "HOU": {"first_name": "Houston", "last_name": "Texans", "position": "DEF",
                    "fantasy_positions": ["DEF"], "team": "HOU"},
            "p99": {"full_name": "Not In League", "position": "QB"},
        }

    def run_refresh(self, client, force=False):
        with mock.patch.object(sleeper_fetch, "SLEEPER_RAW", self.root), \
             mock.patch.object(sleeper_fetch, "PLAYERS_PATH", self.root / "players.json"):
            sleeper_fetch.refresh_players(client, force=force)
        return read_json(self.root / "players.json")

    def test_trimmed_to_league_players(self):
        data = self.run_refresh(FakeClient({"/players/nfl": self.raw}))
        self.assertEqual(sorted(data["players"]), ["HOU", "p1", "p3"])
        self.assertEqual(data["players"]["p1"], {"full_name": "Pat One", "position": "RB",
                                                 "fantasy_positions": ["RB"], "team": "KC"})
        self.assertEqual(data["players"]["HOU"]["full_name"], "Houston Texans")
        self.assertEqual(data["missing"], ["p4"])

    def test_no_download_when_nothing_new(self):
        self.run_refresh(FakeClient({"/players/nfl": self.raw}))
        client = FakeClient({"/players/nfl": self.raw})
        with mock.patch("builtins.print"):
            self.run_refresh(client)
        self.assertEqual(client.urls, [])


if __name__ == "__main__":
    unittest.main()
