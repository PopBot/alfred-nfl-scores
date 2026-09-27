#!/usr/bin/env python3
"""
utils.py — Shared utilities for the NFL Alfred workflow.
Bundled lib/ is loaded first so requests always works regardless of
which Python version Alfred uses on the Mac.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime

# ── Bundled dependencies ──────────────────────────────────────────────────────
_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
WORKFLOW_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR    = os.path.join(WORKFLOW_DIR, ".cache")
HEADSHOT_DIR = os.path.join(CACHE_DIR, "headshots")
LOGO_DIR     = os.path.join(WORKFLOW_DIR, "nfl_logos")
TEAMS_FILE   = os.path.join(WORKFLOW_DIR, "data", "teams.json")

os.makedirs(CACHE_DIR,    exist_ok=True)
os.makedirs(HEADSHOT_DIR, exist_ok=True)

# ── Teams ──────────────────────────────────────────────────────────────────────
with open(TEAMS_FILE) as f:
    TEAMS: list[dict] = json.load(f)

TEAM_BY_ID:   dict[str, dict] = {str(t["id"]): t for t in TEAMS}
TEAM_BY_ABBR: dict[str, dict] = {t["abbreviation"].upper(): t for t in TEAMS}


def team_logo_path(team_id_or_abbr: str | int) -> str:
    key = str(team_id_or_abbr).upper()
    team = TEAM_BY_ID.get(str(team_id_or_abbr)) or TEAM_BY_ABBR.get(key)
    if team:
        path = os.path.join(LOGO_DIR, f"{team['abbreviation']}.png")
        if os.path.exists(path):
            return path
    return os.path.join(WORKFLOW_DIR, "icon.png")


def team_name_from_id(team_id: str | int) -> str:
    t = TEAM_BY_ID.get(str(team_id))
    return t["name"] if t else "—"


def team_abbr_from_id(team_id: str | int) -> str:
    t = TEAM_BY_ID.get(str(team_id))
    return t["abbreviation"] if t else "—"


# ── File Cache ─────────────────────────────────────────────────────────────────
def cache_get(key: str, ttl: int):
    """Return cached data only if younger than ttl seconds, else None."""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < ttl:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def cache_get_stale(key: str):
    """Return cached data regardless of age (stale-while-revalidate). None if missing."""
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def cache_set(key: str, data) -> None:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    with open(path, "w") as f:
        json.dump(data, f)


# ── HTTP Session ───────────────────────────────────────────────────────────────
_session = requests.Session()
_session.headers.clear()
_session.headers.update({
    "User-Agent": "curl/8.7.1",
    "Accept": "*/*",
})


def api_get(url: str, params: dict | None = None, timeout: int = 5) -> dict:
    r = _session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def current_season() -> int:
    now = datetime.now()
    return now.year if now.month >= 6 else now.year - 1


# ── Timezone ───────────────────────────────────────────────────────────────────
def utc_to_local_datetime(utc_str: str) -> datetime:
    """Convert '2026-09-27T17:00Z' to local datetime."""
    dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
    return dt.astimezone()


def utc_to_local(utc_str: str) -> str:
    """Format local time like 'Sunday 1:00 PM' or 'Today 4:25 PM'."""
    local = utc_to_local_datetime(utc_str)
    now = datetime.now().astimezone()
    if local.date() == now.date():
        day_str = "Today"
    else:
        day_str = local.strftime("%a")
    return f"{day_str} {local.strftime('%-I:%M %p')}"


# ── Player Headshots ───────────────────────────────────────────────────────────
HEADSHOT_TTL = 7 * 24 * 3600

ESPN_HEADSHOT_TEMPLATE = "https://a.espncdn.com/i/headshots/nfl/players/full/{player_id}.png"


def player_headshot_path(player_id: str | int, direct_url: str | None = None) -> str:
    """Local path to cached player headshot. Downloads on first use."""
    path = os.path.join(HEADSHOT_DIR, f"{player_id}.png")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < HEADSHOT_TTL:
        return path
    url = direct_url or ESPN_HEADSHOT_TEMPLATE.format(player_id=player_id)
    try:
        r = _session.get(url, timeout=4)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            with open(path, "wb") as f:
                f.write(r.content)
            return path
    except Exception:
        pass
    return os.path.join(WORKFLOW_DIR, "icon.png")


# ── Alfred Output ──────────────────────────────────────────────────────────────
def alfred_error(message: str, detail: str = "") -> None:
    items = [{
        "title": f"⚠️ {message}",
        "subtitle": detail,
        "valid": False,
        "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")}
    }]
    print(json.dumps({"items": items}))
    sys.exit(0)


def alfred_output(items: list, rerun: float | None = None) -> None:
    out: dict = {"items": items}
    if rerun:
        out["rerun"] = rerun
    print(json.dumps(out))
