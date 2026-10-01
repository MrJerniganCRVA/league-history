import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import json  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

import yahoo_export as Y  # noqa: E402
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


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code, self.text = payload, status, json.dumps(payload)

    def json(self):
        return self.payload


class FakePost:
    """Records calls; returns queued payloads in order."""
    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = []

    def __call__(self, url, headers=None, data=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "data": data or {}})
        return FakeResp(self.payloads.pop(0))


GOOD = {"access_token": "AT", "refresh_token": "RT", "token_type": "bearer", "xoauth_yahoo_guid": "G1"}


class SignInTest(unittest.TestCase):
    def setUp(self):
        self._orig = Y.TOKEN_PATH
        Y.TOKEN_PATH = Path(tempfile.mkdtemp()) / "yahoo_token.json"

    def tearDown(self):
        Y.TOKEN_PATH = self._orig

    def test_auth_url_has_redirect_and_fantasy_scope(self):
        q = parse_qs(urlparse(Y.auth_url("dj0yKEY", "https://localhost:8080")).query)
        self.assertEqual(q["redirect_uri"], ["https://localhost:8080"])
        self.assertEqual(q["scope"], ["fspt-r"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["client_id"], ["dj0yKEY"])

    def test_extract_code(self):
        self.assertEqual(Y.extract_code("https://localhost:8080/?code=abc123xyz&state=1"), "abc123xyz")
        self.assertEqual(Y.extract_code("  abc123xyz \n"), "abc123xyz")
        self.assertEqual(Y.extract_code("localhost:8080/?code=q%2Bz"), "q+z")

    def test_sign_in_uses_same_redirect_and_saves_yfpy_shape(self):
        post = FakePost(GOOD)
        tok = Y.sign_in(post, "KEY", "SECRET", "https://localhost:8080",
                        ask=lambda _: "https://localhost:8080/?code=CODE1")
        sent = post.calls[0]
        self.assertEqual(sent["data"], {"grant_type": "authorization_code",
                                        "redirect_uri": "https://localhost:8080", "code": "CODE1"})
        self.assertTrue(sent["headers"]["Authorization"].startswith("Basic "))
        for k in ("access_token", "consumer_key", "consumer_secret", "guid", "refresh_token",
                  "token_time", "token_type"):  # YFPY rejects a token missing any of these
            self.assertIn(k, tok)
        self.assertEqual((tok["guid"], tok["consumer_key"]), ("G1", "KEY"))

    def test_falls_back_to_credentials_in_body(self):
        post = FakePost({"error": "INVALID_CLIENT_SECRET", "error_description": "invalid"}, GOOD)
        resp = Y.request_token(post, "KEY", "SECRET", {"grant_type": "authorization_code", "code": "C"})
        self.assertEqual(resp["access_token"], "AT")
        self.assertEqual(post.calls[1]["data"]["client_secret"], "SECRET")
        self.assertNotIn("Authorization", post.calls[1]["headers"])

    def test_both_methods_failing_explains(self):
        post = FakePost({"error": "invalid_grant"}, {"error": "invalid_grant"})
        with self.assertRaises(SystemExit) as cm:
            Y.request_token(post, "K", "S", {})
        self.assertIn("invalid_grant", str(cm.exception))

    def test_saved_fresh_token_is_reused_without_network(self):
        Y.TOKEN_PATH.write_text(json.dumps(Y.token_record(GOOD, "KEY", "S")))
        tok, how = Y.load_or_refresh_token(FakePost(), "KEY", "S", "https://localhost:8080",
                                           ask=lambda _: self.fail("should not ask"))
        self.assertEqual((tok["access_token"], how), ("AT", "saved sign-in"))

    def test_old_token_is_refreshed_with_same_redirect(self):
        Y.TOKEN_PATH.write_text(json.dumps(Y.token_record(GOOD, "KEY", "S", now=time.time() - 3600)))
        post = FakePost({"access_token": "AT2", "token_type": "bearer"})
        tok, how = Y.load_or_refresh_token(post, "KEY", "S", "https://localhost:8080")
        self.assertEqual(how, "refreshed sign-in")
        self.assertEqual(post.calls[0]["data"]["grant_type"], "refresh_token")
        self.assertEqual(post.calls[0]["data"]["redirect_uri"], "https://localhost:8080")
        self.assertEqual((tok["access_token"], tok["refresh_token"], tok["guid"]), ("AT2", "RT", "G1"))

    def test_token_from_other_app_triggers_new_sign_in(self):
        Y.TOKEN_PATH.write_text(json.dumps(Y.token_record(GOOD, "OLDKEY", "S")))
        post = FakePost(GOOD)
        _, how = Y.load_or_refresh_token(post, "NEWKEY", "S", "https://localhost:8080",
                                         ask=lambda _: "CODE")
        self.assertEqual(how, "new sign-in")
        self.assertFalse(Y.TOKEN_PATH.exists())


if __name__ == "__main__":
    unittest.main()
