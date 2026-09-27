#!/usr/bin/env python3
"""
nfl_standings.py — Alfred keyword: nfls
Division standings for all 8 NFL divisions.
"""
from __future__ import annotations

import os
import sys

from utils import (
    alfred_error, alfred_output,
    api_get, cache_get, cache_get_stale, cache_set,
    team_logo_path, WORKFLOW_DIR,
)

CACHE_TTL = 300  # 5 minutes
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3"

DIVISION_ORDER = [
    "AFC East", "AFC North", "AFC South", "AFC West",
    "NFC East", "NFC North", "NFC South", "NFC West",
]


def header(division_name: str) -> dict:
    return {
        "title": f"── {division_name} ──",
        "subtitle": "",
        "valid": False,
        "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")},
    }


def stat_map(stats_list: list[dict]) -> dict[str, str]:
    res = {}
    for s in stats_list:
        name = s.get("name")
        val = s.get("displayValue")
        if name and val is not None:
            res[name] = val
    return res


def team_item(rank: int, entry: dict) -> dict:
    team = entry.get("team", {})
    tid = str(team.get("id"))
    abbr = team.get("abbreviation", "")
    name = team.get("displayName", "Unknown")
    stats = stat_map(entry.get("stats", []))

    record = stats.get("overall", f"{stats.get('wins', 0)}-{stats.get('losses', 0)}")
    ties = stats.get("ties")
    if ties and ties != "0" and record.count("-") == 1:
        record += f"-{ties}"

    diff = stats.get("pointDifferential") or stats.get("differential", "0")
    if diff and not str(diff).startswith("+") and not str(diff).startswith("-"):
        diff = f"+{diff}"

    streak = stats.get("streak", "—")
    pf = stats.get("pointsFor", "0")
    pa = stats.get("pointsAgainst", "0")
    div_rec = stats.get("divisionRecord", "—")

    # Links
    links = team.get("links", [])
    clubhouse = f"https://www.espn.com/nfl/team/_/name/{abbr.lower()}"
    for l in links:
        if "clubhouse" in l.get("rel", []):
            clubhouse = l.get("href", clubhouse)
            break

    subtitle = f"{record}  Diff: {diff}  Streak: {streak}  PF: {pf}  PA: {pa}  Div: {div_rec}"

    return {
        "title": f"{rank}. {name}",
        "subtitle": subtitle,
        "arg": clubhouse,
        "icon": {"path": team_logo_path(abbr)},
        "mods": {
            "cmd": {
                "subtitle": f"⌘ Open {name} Schedule",
                "arg": f"https://www.espn.com/nfl/team/schedule/_/name/{abbr.lower()}"
            },
            "alt": {
                "subtitle": f"⌥ Open {name} Roster",
                "arg": f"https://www.espn.com/nfl/team/roster/_/name/{abbr.lower()}"
            }
        }
    }


def fetch_standings_data():
    key = "nfl_standings_level3"
    data = cache_get(key, CACHE_TTL)
    if data:
        return data

    stale = cache_get_stale(key)
    try:
        data = api_get(STANDINGS_URL)
        cache_set(key, data)
        return data
    except Exception:
        if stale:
            return stale
        raise


def main():
    try:
        data = fetch_standings_data()
    except Exception as e:
        alfred_error("Could not fetch NFL standings", str(e))
        return

    # Map division name -> entries
    divisions_dict: dict[str, list] = {}
    for conf in data.get("children", []):
        for div in conf.get("children", []):
            dname = div.get("name")
            entries = div.get("standings", {}).get("entries", [])
            divisions_dict[dname] = entries

    items = []
    for div_name in DIVISION_ORDER:
        entries = divisions_dict.get(div_name, [])
        if not entries:
            continue
        items.append(header(div_name))
        for rank, entry in enumerate(entries, 1):
            items.append(team_item(rank, entry))

    alfred_output(items)


if __name__ == "__main__":
    main()
