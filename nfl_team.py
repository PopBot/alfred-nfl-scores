#!/usr/bin/env python3
"""
nfl_team.py — Alfred keyword: nflt {query}
Shows team season record by default.
  ⌘ (Cmd) → Team Offense stats (Pass YDS, Rush YDS, Total TDs, Points/Game)
  ⌥ (Alt) → Team Defense stats (Sacks, INTs, Forced Fumbles, Tackles)
No query → all 32 teams sorted alphabetically / by win %.
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import (
    alfred_error, alfred_output,
    api_get, cache_get, cache_get_stale, cache_set,
    team_logo_path, TEAMS, WORKFLOW_DIR,
)

CACHE_TTL = 300  # 5 minutes
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3"


def search_teams(query: str) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return list(TEAMS)
    words = q.split()
    return [
        t for t in TEAMS
        if all(
            w in (
                f"{t['name']} {t['city']} {t['nickname']} "
                f"{t['abbreviation']} {t['division']} {t['conference']} {t.get('conference_abbr', '')}"
            ).lower()
            for w in words
        )
    ]


def fetch_standings_map() -> dict[str, dict]:
    key = "nfl_standings_level3"
    data = cache_get(key, CACHE_TTL) or cache_get_stale(key)
    if not data:
        try:
            data = api_get(STANDINGS_URL)
            cache_set(key, data)
        except Exception:
            return {}

    teams_map = {}
    for conf in data.get("children", []):
        for div in conf.get("children", []):
            for entry in div.get("standings", {}).get("entries", []):
                t = entry.get("team", {})
                tid = str(t.get("id"))
                stats = {}
                for s in entry.get("stats", []):
                    name = s.get("name")
                    stype = s.get("type", "")
                    val = s.get("displayValue")
                    if val is None:
                        continue
                    if stype:
                        stats[stype] = val
                    if name and ("_" not in stype or name not in stats):
                        stats[name] = val
                win_pct_raw = stats.get("winPercent", "0")
                try:
                    win_pct = float(win_pct_raw)
                except ValueError:
                    win_pct = 0.0
                teams_map[tid] = {
                    "record": stats.get("overall", f"{stats.get('wins', 0)}-{stats.get('losses', 0)}"),
                    "diff": stats.get("pointDifferential") or stats.get("differential", "0"),
                    "streak": stats.get("streak", "—"),
                    "pf": stats.get("pointsFor", "0"),
                    "pa": stats.get("pointsAgainst", "0"),
                    "div_rec": stats.get("divisionRecord", "—"),
                    "seed": stats.get("playoffSeed", "—"),
                    "win_pct": win_pct,
                }
    return teams_map


def fetch_team_stats(team_id: str) -> dict:
    key = f"nfl_team_stats_{team_id}"
    data = cache_get(key, CACHE_TTL) or cache_get_stale(key)
    if not data:
        url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/statistics"
        try:
            data = api_get(url)
            cache_set(key, data)
        except Exception:
            return {}

    categories = data.get("results", {}).get("stats", {}).get("categories", [])
    cat_map = {}
    for cat in categories:
        cname = cat.get("name")
        stats_dict = {}
        for s in cat.get("stats", []):
            stats_dict[s.get("name")] = s.get("displayValue")
        cat_map[cname] = stats_dict
    return cat_map


def build_team_item(team: dict, standings_map: dict[str, dict]) -> dict:
    tid = str(team["id"])
    abbr = team["abbreviation"]
    name = team["name"]
    division = team["division"]
    std = standings_map.get(tid, {})

    rec = std.get("record", "0-0")
    diff = std.get("diff", "0")
    if diff and not str(diff).startswith("+") and not str(diff).startswith("-"):
        diff = f"+{diff}"
    streak = std.get("streak", "—")
    pf = std.get("pf", "0")
    pa = std.get("pa", "0")
    div_rec = std.get("div_rec", "—")

    subtitle = f"{rec} · Diff {diff} · Streak {streak} · PF {pf} · PA {pa} · {division}"
    clubhouse = f"https://www.espn.com/nfl/team/_/name/{abbr.lower()}"

    # Modifiers: fetch team offensive & defensive stats
    team_stats = fetch_team_stats(tid)
    passing = team_stats.get("passing", {})
    rushing = team_stats.get("rushing", {})
    defensive = team_stats.get("defensive", {})
    scoring = team_stats.get("scoring", {})
    interceptions = team_stats.get("defensiveInterceptions", {})
    general = team_stats.get("general", {})

    pass_yds = passing.get("passingYards", "—")
    pass_tds = passing.get("passingTouchdowns", "—")
    cmp_pct = passing.get("completionPct", "—")
    rush_yds = rushing.get("rushingYards", "—")
    rush_tds = rushing.get("rushingTouchdowns", "—")
    pts_per_game = scoring.get("totalPointsPerGame", "—")

    sacks = defensive.get("sacks", "—")
    ints = interceptions.get("interceptions", "—")
    forced_fumb = general.get("fumblesForced", "—")
    tot_tackles = defensive.get("totalTackles", "—")

    off_sub = f"⌘ Offense: {pts_per_game} PPG · Pass: {pass_yds} YDS ({pass_tds} TD, {cmp_pct}%) · Rush: {rush_yds} YDS ({rush_tds} TD)"
    def_sub = f"⌥ Defense: {sacks} Sacks · {ints} INTs · {forced_fumb} Forced Fum · {tot_tackles} Tackles"

    return {
        "title": name,
        "subtitle": subtitle,
        "arg": clubhouse,
        "icon": {"path": team_logo_path(abbr)},
        "mods": {
            "cmd": {
                "subtitle": off_sub,
                "arg": f"https://www.espn.com/nfl/team/stats/_/name/{abbr.lower()}"
            },
            "alt": {
                "subtitle": def_sub,
                "arg": f"https://www.espn.com/nfl/team/stats/_/name/{abbr.lower()}"
            }
        }
    }


def main():
    query = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    matched_teams = search_teams(query)

    if not matched_teams:
        alfred_output([{
            "title": f"No NFL teams matching '{query}'",
            "subtitle": "Try searching by city, nickname, or abbreviation (e.g. KC, Chiefs, Dallas)",
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")}
        }])
        return

    standings_map = fetch_standings_map()

    # Sort by win percentage descending, then point differential descending
    def team_sort_key(t: dict):
        std = standings_map.get(str(t["id"]), {})
        win_pct = std.get("win_pct", 0.0)
        try:
            diff = int(str(std.get("diff", "0")).replace("+", ""))
        except ValueError:
            diff = 0
        return (-win_pct, -diff, t["name"])

    matched_teams.sort(key=team_sort_key)

    # Fetch team stats concurrently for all matched teams (up to 32)
    results_by_id: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        future_map = {
            pool.submit(build_team_item, t, standings_map): str(t["id"])
            for t in matched_teams
        }
        for future in as_completed(future_map):
            tid = future_map[future]
            try:
                results_by_id[tid] = future.result()
            except Exception:
                pass

    items = [results_by_id[str(t["id"])] for t in matched_teams if str(t["id"]) in results_by_id]
    alfred_output(items)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import json as _json, traceback
        print(_json.dumps({"items": [{
            "title": "⚠️ NFL Team script error",
            "subtitle": str(exc),
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")},
            "text": {"copy": traceback.format_exc()},
        }]}))
        sys.exit(0)
