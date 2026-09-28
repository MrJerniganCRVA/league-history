"""Shared schema helpers, paths, config/identity loading and a polite HTTP client."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
MANAGERS_PATH = ROOT / "managers.json"
MANAGER_MAP_CSV = ROOT / "manager_map.csv"
RAW_DIR = ROOT / "data_raw"
SLEEPER_RAW = RAW_DIR / "sleeper"
YAHOO_RAW = RAW_DIR / "yahoo"
SITE_DATA = ROOT / "docs" / "data"

GAME_TYPES = ("regular", "playoff", "consolation")
UNMAPPED_PREFIX = "unmapped:"


# ---------------------------------------------------------------- io helpers

def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: Any, indent: int | None = 2) -> None:
    """Write deterministic JSON so re-runs produce no diff when nothing changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=indent, ensure_ascii=False, sort_keys=False)
    path.write_text(text + "\n", encoding="utf-8")


def load_config() -> dict:
    cfg = read_json(CONFIG_PATH)
    if cfg is None:
        raise SystemExit(f"Missing {CONFIG_PATH}")
    return cfg


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "manager"


def norm_name(name: str | None) -> str:
    """Case/whitespace-insensitive key for matching names by hand-typed CSV values."""
    return re.sub(r"\s+", " ", (name or "").strip()).casefold()


# ---------------------------------------------------------------- identities

class Resolver:
    """Maps platform identities to stable manager_ids using managers.json.

    Anything that can't be resolved is returned as ``unmapped:<platform>:<id>``
    and recorded, so it is reported instead of silently dropped.
    """

    def __init__(self, managers: list[dict] | None = None):
        managers = managers if managers is not None else (read_json(MANAGERS_PATH, []) or [])
        self.managers = managers
        self.display = {m["manager_id"]: m.get("display_name", m["manager_id"]) for m in managers}
        self.sleeper: dict[str, str] = {}
        self.yahoo_guid: dict[str, str] = {}
        self.yahoo_season_name: dict[tuple[str, str], str] = {}
        self.yahoo_fallback: dict[str, str] = {}
        for m in managers:
            mid = m["manager_id"]
            for uid in m.get("sleeper_user_ids", []) or []:
                self.sleeper[str(uid)] = mid
            for guid in m.get("yahoo_manager_guids", []) or []:
                self.yahoo_guid[str(guid)] = mid
            for season, name in (m.get("yahoo_team_names_by_season") or {}).items():
                self.yahoo_season_name[(str(season), norm_name(name))] = mid
            for name in m.get("yahoo_team_names_fallback", []) or []:
                self.yahoo_fallback[norm_name(name)] = mid
        # unmapped key -> human description, for the report
        self.unmapped: dict[str, str] = {}

    def sleeper_user(self, user_id: str | None, label: str = "") -> str:
        uid = str(user_id) if user_id else "none"
        if uid in self.sleeper:
            return self.sleeper[uid]
        key = f"{UNMAPPED_PREFIX}sleeper:{uid}"
        self.unmapped.setdefault(key, f"Sleeper user_id={uid} name={label!r}")
        return key

    def yahoo_team(self, season: int | str, team_name: str, guids: list[str] | None = None,
                   label: str = "") -> str:
        season = str(season)
        hit = self.yahoo_season_name.get((season, norm_name(team_name)))
        if hit:
            return hit
        for g in guids or []:
            if g and g in self.yahoo_guid:
                return self.yahoo_guid[g]
        hit = self.yahoo_fallback.get(norm_name(team_name))
        if hit:
            return hit
        key = f"{UNMAPPED_PREFIX}yahoo:{season}:{team_name}"
        self.unmapped.setdefault(
            key, f"Yahoo {season} team={team_name!r} guids={guids or []} {label}".strip())
        return key


# ---------------------------------------------------------------- games

def make_game(season: int, week: int, platform: str, game_type: str,
              team_a: str, score_a: float, team_b: str, score_b: float) -> dict:
    if game_type not in GAME_TYPES:
        raise ValueError(f"bad game_type {game_type}")
    sa, sb = round(float(score_a), 2), round(float(score_b), 2)
    if sa > sb:
        winner = team_a
    elif sb > sa:
        winner = team_b
    else:
        winner = "tie"
    return {
        "season": int(season), "week": int(week), "platform": platform,
        "game_type": game_type,
        "team_a": team_a, "score_a": sa,
        "team_b": team_b, "score_b": sb,
        "winner": winner,
    }


# ---------------------------------------------------------------- http

class HttpClient:
    """requests.Session wrapper: throttled (well under Sleeper's 1000/min) with retries."""

    def __init__(self, min_interval: float = 0.2, retries: int = 4):
        import requests  # imported lazily so tests don't need it
        self._requests = requests
        self.session = requests.Session()
        self.min_interval = min_interval
        self.retries = retries
        self._last = 0.0
        self.calls = 0

    def get_json(self, url: str) -> Any:
        delay = 2.0
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.calls += 1
            try:
                resp = self.session.get(url, timeout=30)
            except self._requests.RequestException:
                if attempt == self.retries:
                    raise
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    resp.raise_for_status()
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("unreachable")
