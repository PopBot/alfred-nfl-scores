#!/usr/bin/env python3
"""
nfl_player.py — Alfred keyword: nflp {query}
Search NFL players for current season stats & headshot from ESPN CDN.
QBs: Pass YDS / TD / INT / CMP% / RTG
RBs: Rush YDS / TD / AVG / REC / REC YDS
WR/TE: REC / REC YDS / TD / AVG
DEF/K: Tackles / Sacks / INTs / FGs
"""
from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import (
    alfred_error, alfred_output,
    api_get, cache_get, cache_get_stale, cache_set,
    player_headshot_path, TEAM_BY_ABBR, WORKFLOW_DIR,
)

CACHE_TTL = 300  # 5 minutes
SEARCH_URL = "https://site.web.api.espn.com/apis/search/v2"


def search_players(query: str) -> list[dict]:
    key = f"nfl_search_{query.lower().replace(' ', '_')}"
    cached = cache_get(key, CACHE_TTL)
    if cached is not None:
        return cached

    params = {"query": query, "limit": 6, "type": "player"}
    try:
        data = api_get(SEARCH_URL, params=params)
    except Exception:
        return []

    results = []
    for res_group in data.get("results", []):
        for item in res_group.get("contents", []):
            sport = item.get("sport")
            league = item.get("defaultLeagueSlug")
            # Only keep NFL football players
            if sport == "football" and league == "nfl":
                uid = item.get("uid", "")
                athlete_id = uid.split("~a:")[-1] if "~a:" in uid else item.get("id")
                img_url = item.get("image", {}).get("default")
                results.append({
                    "id": athlete_id,
                    "name": item.get("displayName"),
                    "team": item.get("subtitle", ""),
                    "web_url": item.get("link", {}).get("web", f"https://www.espn.com/nfl/player/_/id/{athlete_id}"),
                    "headshot_url": img_url,
                })

    cache_set(key, results)
    return results


def fetch_player_overview(player_id: str) -> dict:
    key = f"nfl_player_ov_{player_id}"
    cached = cache_get(key, CACHE_TTL) or cache_get_stale(key)
    if cached:
        return cached

    url = f"https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{player_id}/overview"
    try:
        data = api_get(url)
        cache_set(key, data)
        return data
    except Exception:
        return {}


def format_player_stats(labels: list[str], stats: list[str]) -> str:
    """Format player stats nicely based on positional label layout."""
    if not labels or not stats or len(labels) != len(stats):
        return "Season stats currently unavailable"

    # 1. Quarterback: starts with CMP, ATT, CMP%, YDS, AVG, TD, INT, LNG, SACK, RTG
    if len(labels) >= 10 and labels[0] == "CMP" and labels[3] == "YDS" and labels[9] == "RTG":
        pass_yds = stats[3]
        cmp_pct = stats[2]
        td = stats[5]
        int_ = stats[6]
        rtg = stats[9]
        rush_yds = stats[11] if len(stats) > 11 else "0"
        rush_td = stats[13] if len(stats) > 13 else "0"
        sub = f"{pass_yds} PASS YDS · {td} TD · {int_} INT · {cmp_pct}% CMP · {rtg} RTG"
        if rush_yds != "0" or rush_td != "0":
            sub += f" · {rush_yds} RUSH YDS ({rush_td} TD)"
        return sub

    # 2. Running Back: CAR, YDS, AVG, TD, LNG, REC, YDS, AVG, TD, LNG
    if len(labels) >= 9 and labels[0] == "CAR" and labels[1] == "YDS" and labels[5] == "REC":
        rush_yds = stats[1]
        rush_avg = stats[2]
        rush_td = stats[3]
        rec = stats[5]
        rec_yds = stats[6]
        rec_td = stats[8]
        return f"{rush_yds} RUSH YDS ({rush_td} TD, {rush_avg} YPC) · {rec} REC ({rec_yds} YDS, {rec_td} TD)"

    # 3. Wide Receiver / Tight End:
    # ESPN returns either ['REC', 'TGTS', 'YDS', 'AVG', 'TD', 'LNG', ...]
    # or ['REC', 'YDS', 'AVG', 'TD', 'LNG', ...]
    if len(labels) >= 4 and labels[0] == "REC" and ("YDS" in labels[:3]):
        rec = stats[0]
        if labels[1] == "TGTS" and len(labels) >= 5:
            tgts = stats[1]
            rec_yds = stats[2]
            rec_avg = stats[3]
            rec_td = stats[4]
            return f"{rec} REC ({tgts} TGTS) · {rec_yds} YDS · {rec_td} TD · {rec_avg} AVG"
        else:
            rec_yds = stats[1]
            rec_avg = stats[2]
            rec_td = stats[3]
            return f"{rec} REC · {rec_yds} YDS · {rec_td} TD · {rec_avg} AVG"

    # 4. Defense: TOT, SOLO, AST, SACK, FF, FR, YDS, INT, ..., PD
    pairs = dict(zip(labels, stats))
    if any(k in pairs for k in ("TKL", "TOT", "SACK", "SCK", "SOLO")):
        tkl = pairs.get("TOT", pairs.get("TKL", pairs.get("SOLO", "—")))
        sck = pairs.get("SACK", pairs.get("SCK", "—"))
        int_ = pairs.get("INT", "—")
        pd = pairs.get("PD")
        ff = pairs.get("FF", "—")
        sub = f"{tkl} TKL · {sck} SACKS · {int_} INT · {ff} FF"
        if pd is not None and pd != "0":
            sub += f" · {pd} PD"
        return sub

    # 5. Kicker: ESPN returns ['FG%', 'FG', '1-19', ..., 'LNG', 'XPM', 'XPA', 'PTS']
    # or ['FGM', 'FGA', 'FG%', ...]
    if any(k in pairs for k in ("FG", "FGM", "FG%", "PTS")):
        fg = pairs.get("FG")
        if not fg:
            fgm = pairs.get("FGM", "—")
            fga = pairs.get("FGA", "—")
            fg = f"{fgm}/{fga}"
        else:
            fg = fg.replace("-", "/")
        pct = pairs.get("FG%", "—")
        lng = pairs.get("LNG", "—")
        pts = pairs.get("PTS")
        xpm = pairs.get("XPM")
        xpa = pairs.get("XPA")
        sub = f"{fg} FG ({pct}%) · Long: {lng}"
        if xpm is not None and xpa is not None:
            sub += f" · {xpm}/{xpa} XP"
        if pts is not None:
            sub += f" · {pts} PTS"
        return sub

    # Fallback
    return " · ".join(f"{lbl}: {val}" for lbl, val in list(zip(labels, stats))[:5])


def build_player_item(p: dict) -> dict:
    pid = str(p["id"])
    name = p["name"]
    team = p["team"]
    web_url = p["web_url"]

    icon_path = player_headshot_path(pid, direct_url=p.get("headshot_url"))

    ov = fetch_player_overview(pid)
    splits = ov.get("statistics", {}).get("splits", [])
    labels = ov.get("statistics", {}).get("labels", [])

    if splits and labels:
        reg_season = next((s for s in splits if "regular" in s.get("displayName", "").lower()), splits[0])
        stat_summary = format_player_stats(labels, reg_season.get("stats", []))
    else:
        stat_summary = f"{team} · View player profile & statistics"

    title = f"{name} — {team}" if team else name

    return {
        "title": title,
        "subtitle": stat_summary,
        "arg": web_url,
        "icon": {"path": icon_path},
        "mods": {
            "cmd": {
                "subtitle": f"⌘ Open {name}'s Game Log",
                "arg": f"{web_url.rstrip('/')}/gamelog"
            },
            "alt": {
                "subtitle": f"⌥ Open {name}'s Split Stats",
                "arg": f"{web_url.rstrip('/')}/splits"
            }
        }
    }


def main():
    query = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    if len(query) < 2:
        alfred_output([{
            "title": "Type an NFL player's name...",
            "subtitle": "e.g. nflp mahomes, nflp henry, nflp jefferson",
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")}
        }])
        return

    players = search_players(query)
    if not players:
        alfred_output([{
            "title": f"No NFL players found for '{query}'",
            "subtitle": "Check the spelling or try searching another name",
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")}
        }])
        return

    items = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_player = {executor.submit(build_player_item, p): p for p in players[:6]}
        for future in as_completed(future_to_player):
            try:
                items.append(future.result())
            except Exception:
                pass

    ordered_items = []
    for p in players[:6]:
        pid = str(p["id"])
        match = next((it for it in items if str(it.get("arg", "")).find(pid) != -1 or p["name"] in it.get("title", "")), None)
        if match:
            ordered_items.append(match)

    alfred_output(ordered_items if ordered_items else items)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import json as _json, traceback
        print(_json.dumps({"items": [{
            "title": "⚠️ NFL Player script error",
            "subtitle": str(exc),
            "valid": False,
            "icon": {"path": os.path.join(WORKFLOW_DIR, "icon.png")},
            "text": {"copy": traceback.format_exc()},
        }]}))
        sys.exit(0)
