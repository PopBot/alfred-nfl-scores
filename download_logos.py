#!/usr/bin/env python3
"""
download_logos.py — Downloads official NFL logos for all 32 teams from ESPN's CDN
and saves them as 64x64 transparent PNGs in nfl_logos/.
"""
import io
import json
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import requests
from PIL import Image

TEAMS_FILE = os.path.join(os.path.dirname(__file__), "data", "teams.json")
LOGOS_DIR  = os.path.join(os.path.dirname(__file__), "nfl_logos")
os.makedirs(LOGOS_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Alfred-NFL-Workflow/1.0"}


def download_all_logos():
    with open(TEAMS_FILE) as f:
        teams = json.load(f)

    print(f"Downloading logos for {len(teams)} NFL teams...")
    for t in teams:
        abbr = t["abbreviation"]
        out_path = os.path.join(LOGOS_DIR, f"{abbr}.png")
        if os.path.exists(out_path):
            continue

        url = t.get("logo_url") or f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr.lower()}.png"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                img = img.resize((64, 64), Image.Resampling.LANCZOS)
                img.save(out_path, "PNG")
                print(f"  ✓ Saved {abbr}.png (64x64)")
            else:
                print(f"  ✗ Failed {abbr}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ✗ Error downloading {abbr}: {e}")

    print("Logo download finished.")


if __name__ == "__main__":
    download_all_logos()
