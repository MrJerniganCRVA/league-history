import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from build_games import write_transactions  # noqa: E402
from common import Resolver, write_json  # noqa: E402
from sleeper_transactions import normalize_sleeper_transactions, player_table  # noqa: E402

MANAGERS = [
    {"manager_id": "alice", "display_name": "Alice", "sleeper_user_ids": ["u1"]},
    {"manager_id": "bob", "display_name": "Bob", "sleeper_user_ids": ["u2"]},
    {"manager_id": "carl", "display_name": "Carl", "sleeper_user_ids": ["u3"]},
]

WEEK1 = [
    {"transaction_id": "w1", "type": "waiver", "status": "complete", "leg": 1, "created": 50,
     "status_updated": 100, "roster_ids": [1], "adds": {"p3": 1}, "drops": {"p4": 1},
     "settings": {"waiver_bid": 12}, "waiver_budget": [], "draft_picks": []},
    {"transaction_id": "t1", "type": "trade", "status": "complete", "leg": 1, "created": 150,
     "status_updated": 200, "roster_ids": [1, 3], "adds": {"p1": 3, "p2": 1, "p5": 1},
     "drops": {"p1": 1, "p2": 3, "p5": 3, "p6": 1},
     "waiver_budget": [{"sender": 3, "receiver": 1, "amount": 5}],
     "draft_picks": [{"season": "2024", "round": 2, "roster_id": 3, "previous_owner_id": 3, "owner_id": 1}]},
    {"transaction_id": "f1", "type": "free_agent", "status": "complete", "leg": 1, "created": 300,
     "status_updated": 300, "roster_ids": [2], "adds": None, "drops": {"p7": 2},
     "settings": None, "waiver_budget": [], "draft_picks": []},
    {"transaction_id": "x1", "type": "waiver", "status": "failed", "leg": 1, "created": 90,
     "status_updated": 100, "roster_ids": [2], "adds": {"p3": 2}, "drops": None,
     "settings": {"waiver_bid": 5}, "waiver_budget": [], "draft_picks": []},
    {"transaction_id": "c1", "type": "commissioner", "status": "complete", "leg": 1, "created": 400,
     "status_updated": 400, "roster_ids": None, "adds": {"p8": 4}, "drops": None,
     "settings": None, "waiver_budget": [], "draft_picks": []},
]


class NormalizeTransactionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "2023"
        shutil.copytree(HERE / "fixtures" / "sleeper" / "2023", self.dir)
        write_json(self.dir / "transactions" / "01.json", WEEK1)
        self.txs, self.issues = normalize_sleeper_transactions(self.dir, Resolver(MANAGERS))
        self.by_id = {t["id"]: t for t in self.txs}

    def test_failed_claim_never_shows(self):
        self.assertNotIn("x1", self.by_id)
        self.assertEqual([t["id"] for t in self.txs], ["w1", "t1", "f1", "c1"])

    def test_waiver_side(self):
        side = self.by_id["w1"]["sides"][0]
        self.assertEqual(side, {"manager": "alice", "adds": ["p3"], "drops": ["p4"], "bid": 12})

    def test_trade_sides_with_co_owner_faab_and_picks(self):
        alice, carl = self.by_id["t1"]["sides"]
        self.assertEqual((alice["manager"], carl["manager"]), ("alice", "carl"))
        self.assertEqual(alice["adds"], ["p2", "p5"])
        self.assertEqual(alice["drops"], ["p1", "p6"])  # p6 released for roster room
        self.assertEqual(alice["faab_in"], 5)
        self.assertEqual(carl["faab_out"], 5)
        self.assertEqual(alice["picks_in"], [{"season": 2024, "round": 2, "original": "carl"}])
        self.assertEqual(carl["picks_out"], alice["picks_in"])
        self.assertNotIn("picks_in", carl)  # empty extras are left out

    def test_plain_drop_and_commissioner_without_roster_ids(self):
        self.assertEqual(self.by_id["f1"]["sides"], [{"manager": "bob", "adds": [], "drops": ["p7"]}])
        self.assertEqual(self.by_id["c1"]["sides"][0]["manager"], "unmapped:sleeper:u4")
        self.assertEqual(self.by_id["c1"]["type"], "commissioner")

    def test_player_table_falls_back_for_unknown(self):
        players = self.dir / "players.json"
        write_json(players, {"players": {"p3": {"full_name": "Pat Three", "position": "WR", "team": "KC"}}})
        table = player_table(self.txs, players)
        self.assertEqual(table["p3"], {"name": "Pat Three", "pos": "WR", "team": "KC"})
        self.assertEqual(table["p7"], {"name": "Player p7", "pos": "?", "team": None})

    def test_written_file_is_valid_json(self):
        out = self.dir.parent / "site" / "transactions.json"
        n = write_transactions(Resolver(MANAGERS), self.dir.parent, out)
        self.assertEqual(n, 4)
        doc = json.loads(out.read_text())
        self.assertEqual(len(doc["transactions"]), 4)
        self.assertIn("p8", doc["players"])


if __name__ == "__main__":
    unittest.main()
