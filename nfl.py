#!/usr/bin/env python3
"""
nfl.py — Alfred keyword: nfl
Single entry-point router for all NFL commands.

  nfl           → Current week's scores (live → upcoming → final)
  nfls          → Standings by division
  nflp {name}   → Player stats search
  nflt {query}  → Team stats (browse or search)

Alfred's `withspace: false` passes characters directly after 'nfl' to this script.
"""
from __future__ import annotations

import json
import os
import sys


def main():
    query = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    # ── Route based on query prefix ──────────────────────────────────────────
    if query.startswith("s"):
        # nfls → standings
        from nfl_standings import main as standings_main
        standings_main()

    elif query.startswith("p"):
        # nflp {name} → player search
        player_query = query[1:].strip()
        sys.argv = [sys.argv[0], player_query]
        from nfl_player import main as player_main
        player_main()

    elif query.startswith("t"):
        # nflt {query} → team search
        team_query = query[1:].strip()
        sys.argv = [sys.argv[0], team_query]
        from nfl_team import main as team_main
        team_main()

    else:
        # Default: show current week's scores
        scores_main()


# ══════════════════════════════════════════════════════════════════════════════
# Scores logic
# ══════════════════════════════════════════════════════════════════════════════
from utils import (
    alfred_error, alfred_output,
    api_get, cache_get, cache_get_stale, cache_set,
    team_logo_path, team_abbr_from_id,
    utc_to_local, utc_to_local_datetime,
    CACHE_DIR, WORKFLOW_DIR,
)
from image_utils import make_matchup_icon

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
CACHE_TTL = 30
RERUN_LIVE = 5.0


def matchup_icon(away_abbr: str, home_abbr: str) -> str:
    name = f"matchup_{away_abbr}_{home_abbr}.png"
    path = os.path.join(CACHE_DIR, name)
    if os.path.exists(path):
        return path
    away_logo = team_logo_path(away_abbr)
    home_logo = team_logo_path(home_abbr)
    if make_matchup_icon(away_logo, home_logo, path):
        return path
    return home_logo


def format_game_item(event: dict) -> tuple[dict, int]:
    """
    Format single event to Alfred item.
    Returns (item_dict, sort_order) where:
      sort_order 0 = LIVE
      sort_order 1 = UPCOMING
      sort_order 2 = FINAL
    """
    comp = event.get("competitions", [{}])[0]
    competitors = comp.get("competitors", [])

    home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
    away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})

    home_team = home_comp.get("team", {})
    away_team = away_comp.get("team", {})

    home_abbr = home_team.get("abbreviation", "H")
    away_abbr = away_team.get("abbreviation", "A")

    home_score = home_comp.get("score", "0")
    away_score = away_comp.get("score", "0")

    status = comp.get("status", {}).get("type", {})
    state = status.get("state", "pre")  # 'in', 'pre', 'post'
    status_detail = status.get("shortDetail", status.get("detail", ""))

    broadcast = ""
    broadcasts = comp.get("broadcasts", [])
    if broadcasts:
        names = broadcasts[0].get("names", [])
        if names:
            broadcast = names[0]

    # Links
    links = event.get("links", [])
    gamecast_url = f"https://www.espn.com/nfl/game/_/gameId/{event.get('id', '')}"
    boxscore_url = f"https://www.espn.com/nfl/boxscore/_/gameId/{event.get('id', '')}"
    pbp_url = f"https://www.espn.com/nfl/playbyplay/_/gameId/{event.get('id', '')}"

    for l in links:
        rel = l.get("rel", [])
        if "boxscore" in rel:
            boxscore_url = l.get("href", boxscore_url)
        elif "pbp" in rel:
            pbp_url = l.get("href", pbp_url)
        elif "live" in rel:
            gamecast_url = l.get("href", gamecast_url)

    icon_path = matchup_icon(away_abbr, home_abbr)

    # 1. LIVE GAME
    if state == "in":
        situation = comp.get("situation", {})
        down_dist = situation.get("downDistanceText", "")
        possession_id = str(situation.get("possession", ""))
        possession_abbr = away_abbr if str(away_team.get("id")) == possession_id else (
            home_abbr if str(home_team.get("id")) == possession_id else ""
        )
        is_redzone = situation.get("isRedZone", False)

        sub_parts = []
        if possession_abbr and down_dist:
            sub_parts.append(f"🏈 {possession_abbr} {down_dist}")
        elif down_dist:
            sub_parts.append(f"🏈 {down_dist}")

        if is_redzone:
            sub_parts.append("🔴 RED ZONE")

        if broadcast:
            sub_parts.append(f"· {broadcast}")

        subtitle = " ".join(sub_parts) if sub_parts else f"🔴 LIVE · {status_detail}"
        title = f"{away_abbr} {away_score}  {home_abbr} {home_score}  — {status_detail}"

        return {
            "title": title,
            "subtitle": subtitle,
            "arg": gamecast_url,
            "icon": {"path": icon_path},
            "mods": {
                "cmd": {"subtitle": "⌘ Open Box Score", "arg": boxscore_url},
                "alt": {"subtitle": "⌥ Open Play-by-Play", "arg": pbp_url},
            }
        }, 0

    # 2. UPCOMING GAME
    elif state == "pre":
        start_date_str = event.get("date") or comp.get("startDate", "")
        time_display = utc_to_local(start_date_str) if start_date_str else "TBD"

        away_record = away_comp.get("records", [{}])[0].get("summary", "")
        home_record = home_comp.get("records", [{}])[0].get("summary", "")
        record_str = f"({away_record}) @ ({home_record})" if away_record and home_record else ""

        venue = comp.get("venue", {}).get("fullName", "")
        sub_items = [s for s in [record_str, venue, broadcast] if s]
        subtitle = " · ".join(sub_items) if sub_items else "Upcoming game"

        title = f"{away_abbr} @ {home_abbr}  — {time_display}"

        return {
            "title": title,
            "subtitle": subtitle,
            "arg": gamecast_url,
            "icon": {"path": icon_path},
            "mods": {
                "cmd": {"subtitle": "⌘ Open Game Preview", "arg": gamecast_url},
                "alt": {"subtitle": "⌥ Open Play-by-Play", "arg": pbp_url},
            }
        }, 1

    # 3. FINAL GAME
    else:
        away_record = away_comp.get("records", [{}])[0].get("summary", "")
        home_record = home_comp.get("records", [{}])[0].get("summary", "")
        rec_parts = []
        if away_record: rec_parts.append(f"{away_abbr} ({away_record})")
        if home_record: rec_parts.append(f"{home_abbr} ({home_record})")
        subtitle = " · ".join(rec_parts) if rec_parts else "Final"

        title = f"{away_abbr} {away_score}  {home_abbr} {home_score}  — Final"

        return {
            "title": title,
            "subtitle": subtitle,
            "arg": boxscore_url,
            "icon": {"path": icon_path},
            "mods": {
                "cmd": {"subtitle": "⌘ Open Box Score", "arg": boxscore_url},
                "alt": {"subtitle": "⌥ Open Play-by-Play", "arg": pbp_url},
            }
        }, 2


def scores_main():
    key = "nfl_scoreboard"
    data = cache_get(key, CACHE_TTL)
    if not data:
        stale = cache_get_stale(key)
        try:
            data = api_get(SCOREBOARD_URL)
            cache_set(key, data)
        except Exception as e:
            if stale:
                data = stale
            else:
                alfred_error("Could not fetch NFL scores", str(e))
                return

    events = data.get("events", [])
    if not events:
        alfred_output([{
            "title": "No NFL games scheduled for this week 🏈",
            "subtitle": "Check back soon for upcoming matchups",
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")}
        }])
        return

    formatted_items = []
    has_live = False

    for ev in events:
        try:
            item, order = format_game_item(ev)
            if order == 0:
                has_live = True
            formatted_items.append((order, item))
        except Exception:
            continue

    # Sort order: Live (0) first, then Upcoming (1), then Final (2)
    formatted_items.sort(key=lambda x: x[0])
    items = [item for _, item in formatted_items]

    # Re-run after 5s if there is any live game currently ongoing
    alfred_output(items, rerun=RERUN_LIVE if has_live else None)


if __name__ == "__main__":
    main()
