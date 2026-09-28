import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from common import Resolver  # noqa: E402
from import_manager_map import MapError, merge, parse_csv  # noqa: E402


def write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    f.write(text)
    f.close()
    return Path(f.name)


CRLF = ("SleeperID,2016,2017,2018\r\n"
        "OviSnipes,JernyFootball,JernyFootball,CeeDee's TDs\r\n"
        "DrinkingUrBeers,Danger Zone,Danger Zone,Danger Zone\r\n"
        "ShoeTouch,,,Viagra Salesman \r\n")


class ParseTest(unittest.TestCase):
    def test_crlf_and_blanks(self):
        people = parse_csv(write_csv(CRLF))
        self.assertEqual(len(people), 3)
        self.assertEqual(people[2]["yahoo"], {"2018": "Viagra Salesman"})  # trailing space stripped
        self.assertEqual(people[0]["display_name"], "OviSnipes")

    def test_duplicate_team_in_season_rejected(self):
        with self.assertRaises(MapError):
            parse_csv(write_csv("SleeperID,2016\nA,Same Team\nB,same team\n"))

    def test_duplicate_sleeper_name_rejected(self):
        with self.assertRaises(MapError):
            parse_csv(write_csv("SleeperID,2016\nA,X\na,Y\n"))

    def test_yahoo_only_member_needs_display_name(self):
        with self.assertRaises(MapError):
            parse_csv(write_csv("SleeperID,2016\n,Old Team\n"))
        people = parse_csv(write_csv("SleeperID,2016,DisplayName\n,Old Team,Dave\n"))
        self.assertEqual(people[0]["display_name"], "Dave")


class ResolveTest(unittest.TestCase):
    def setUp(self):
        people = parse_csv(write_csv(CRLF))
        self.managers = merge(people, [{"manager_id": "ovisnipes", "yahoo_manager_guids": ["G1"]}],
                              {"drinkingurbeers": "999"})
        self.r = Resolver(self.managers)

    def test_merge_keeps_hand_edits_and_resolves_ids(self):
        ovi = next(m for m in self.managers if m["manager_id"] == "ovisnipes")
        self.assertEqual(ovi["yahoo_manager_guids"], ["G1"])
        beers = next(m for m in self.managers if m["manager_id"] == "drinkingurbeers")
        self.assertEqual(beers["sleeper_user_ids"], ["999"])

    def test_sleeper_by_id_then_username(self):
        self.assertEqual(self.r.sleeper_user("999"), "drinkingurbeers")
        self.assertEqual(self.r.sleeper_user("123", "ovisnipes "), "ovisnipes")
        self.assertTrue(self.r.sleeper_user("555", "Newbie").startswith("unmapped:"))

    def test_yahoo_by_season_and_name(self):
        self.assertEqual(self.r.yahoo_team(2016, "danger  zone"), "drinkingurbeers")
        self.assertEqual(self.r.yahoo_team(2018, "CeeDee's TDs"), "ovisnipes")
        # a team name only counts for the seasons listed for that person
        self.assertTrue(self.r.yahoo_team(2016, "Viagra Salesman").startswith("unmapped:"))


if __name__ == "__main__":
    unittest.main()
