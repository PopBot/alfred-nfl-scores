# 🎯 NFL Alfred Workflow — Specification & Architecture Guide

## 1. Overview
Build a standalone, complete Alfred 5 workflow called **NFL Scores** in `~/Documents/Alfred Workflows/nfl/`.
It mirrors the architecture of the **MLB Scores** workflow (`MLB_Workflow_V2.alfredworkflow`) and the **NBA Scores** workflow (`bjornelvar/alfred_nba_scores`), tailored specifically for the NFL.

### Core Highlights:
- **Zero-auth & 100% Free**: Powered by the undocumented, public ESPN API (`site.api.espn.com` & `sports.core.api.espn.com`).
- **Single-entry Alfred trigger**: `nfl` with prefix-based subrouting (`nfl`, `nfls`, `nflp`, `nflt`).
- **Visual Richness**: Real official team logos (64x64 PNG), dynamic side-by-side dual matchup icons generated in pure Python, and high-resolution player headshots downloaded from ESPN CDN.
- **Rich Live Context**: Quarter, game clock, down & distance, yard line, possession, red zone alerts, and TV broadcast networks.
- **Standings & Team Stats**: 8 divisions across AFC & NFC; team summaries with `⌘` (offensive stats) and `⌥` (defensive stats).
- **Player Stats Search**: Multi-position support (QB, RB, WR, TE, K, Defense) with instant headshots.
- **Zero-dependency Runtime**: Bundles `requests` and dependencies inside `lib/` and uses pure-Python PNG chunk decoding/encoding so the workflow runs on any macOS install without requiring `pip install`.

---

## 2. Alfred Keystroke Commands & UX Flow

Alfred uses a single Script Filter object configured with:
- **Keyword**: `nfl`
- **withspace**: `false`
- **Script**: `python3 nfl.py "$1"`
- **escaping**: `102` (Backquotes, Double Quotes, Backslashes, Dollars)

Because `withspace` is `false`, as the user types:
- `nfl` (no query) → Routes to `scores_main()`: Current week's NFL games.
- `nfls` (query starts with `s`) → Routes to `standings_main()`: Division standings for AFC and NFC.
- `nflp mahomes` (query starts with `p `) → Routes to `player_main()`: Search NFL players and view 2026 season stats + headshots.
- `nflt chiefs` (query starts with `t `) → Routes to `team_main()`: Search/browse teams with W-L record, `⌘` offense, and `⌥` defense.

Action on `Enter` connects to an **Open URL** action passing `{query}` (ESPN gamecast/boxscore, team clubhouse, or player card URL).

---

## 3. Directory & File Structure

```
alfred_nfl_scores/
├── nfl.py                  ← Keyword: "nfl" (Router + Current Week Scores)
├── nfl_standings.py        ← Keyword: "nfls" (Division Standings)
├── nfl_player.py           ← Keyword: "nflp {query}" (Player Search & Season Stats)
├── nfl_team.py             ← Keyword: "nflt {query}" (Team Records & Off/Def Stats)
├── utils.py                ← Cache management, HTTP fetching, timezone formatting, team lookups
├── image_utils.py          ← Pure-Python PNG decoder, resizer, and dual-logo matchup compositor
├── info.plist              ← Alfred workflow configuration XML
├── icon.png                ← Workflow icon (football icon)
├── download_assets.py      ← One-time setup script to fetch all 32 team logos from ESPN CDN
├── build.py                ← Bundles dependencies into lib/ and packages NFL Scores.alfredworkflow
├── requirements.txt        ← Dev dependencies: requests, pillow (only for build/asset prep)
├── data/
│   └── teams.json          ← Metadata for all 32 NFL teams (ID, name, abbreviation, conference, division, colors, slug)
├── nfl_logos/              ← 32 pre-downloaded 64x64 PNG team logos (KC.png, SF.png, BUF.png, etc.)
└── lib/                    ← Bundled python libraries (requests, urllib3, certifi, idna, charset_normalizer)
```

---

## 4. ESPN API Endpoints Reference

No API key or authentication required. Always send header `User-Agent: Alfred-NFL-Workflow/1.0`.

### 4.1 Scoreboard (Live, Upcoming, Final)
```http
GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard
```
- Returns all games for the current NFL week.
- Live games contain `competitions[0].situation`:
  - `downDistanceText`: e.g., `"2nd & Goal at LAC 1"`
  - `possession`: Team ID with the ball
  - `isRedZone`: `true`/`false`
  - `clock` and `displayClock`: e.g. `"7:35"`
  - `period`: 1, 2, 3, 4, or OT
- Status in `competitions[0].status.type`:
  - `state == "in"`: Live game
  - `state == "pre"`: Upcoming game
  - `state == "post"`: Final game
- Broadcast info in `competitions[0].broadcasts[0].names[0]` (e.g. "CBS", "FOX", "NBC", "ESPN").
- Live leaders in `competitions[0].leaders` (Passing, Rushing, Receiving leaders).

### 4.2 Standings
```http
GET https://site.api.espn.com/apis/v2/sports/football/nfl/standings?level=3
```
- `level=3` groups by League → Conference (AFC / NFC) → 8 Divisions:
  - AFC East, AFC North, AFC South, AFC West
  - NFC East, NFC North, NFC South, NFC West
- Each entry includes team stats:
  - `wins`, `losses`, `ties`, `winPercent`
  - `differential` / `pointDifferential`
  - `streak` (e.g. "W2", "L1")
  - `pointsFor`, `pointsAgainst`
  - `divisionRecord`, `Home`, `Road`

### 4.3 Team Metadata & Roster
```http
GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams
GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/roster
```
- Full roster grouped by offense, defense, and special teams.

### 4.4 Player Search & Statistics
- **Search**:
  ```http
  GET https://site.web.api.espn.com/apis/search/v2?query={query}&limit=8&type=player
  ```
  Filters results where `sport == "football"` and `defaultLeagueSlug == "nfl"`.
  Returns `displayName`, `subtitle` (team name), athlete `id`, and headshot image URL.
- **Season Stats**:
  ```http
  GET https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{athlete_id}/overview
  ```
  Returns `statistics.labels` and `statistics.splits[0].stats` for the current regular season:
  - **QB**: Passing YDS, TD, INT, CMP%, RTG, Rushing YDS
  - **RB**: Rushing ATT, YDS, AVG, TD, REC, REC YDS
  - **WR/TE**: Receptions, Targets, YDS, AVG, TD
  - **Kicker / Defense**: Field goals, Tackles, Sacks, INTs

### 4.5 Team Statistics
```http
GET https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/statistics
```
- Provides team season categories:
  - `passing` (Yards, TDs, Interceptions, Completion %)
  - `rushing` (Yards, Attempts, Yds/Att, TDs)
  - `defensive` (Sacks, Interceptions, Tackles, Forced Fumbles)

---

## 5. Script Specifications

### 5.1 `nfl.py` (Current Week Scores)
1. Fetches current scoreboard from ESPN API.
2. Orders games:
   - **🔴 LIVE** first (sorted by quarter/clock)
   - **Upcoming** second (sorted by kickoff date/time)
   - **Final** third (sorted by completion recency)
3. Title & Subtitle formatting:
   - **Live**:
     - *Title*: `KC 24  BUF 21  — 7:35 4th`
     - *Subtitle*: `🏈 BUF 2nd & 5 at KC 28 🔴 RED ZONE · CBS`
   - **Upcoming**:
     - *Title*: `DAL @ PHI  — Sunday 1:00 PM`
     - *Subtitle*: `Lincoln Financial Field · FOX`
   - **Final**:
     - *Title*: `BAL 28  CIN 24  — Final`
     - *Subtitle*: `BAL (3-1) · CIN (2-2)`
4. Matchup Icon: Generates composite 64x64 PNG `matchup_{AWAY}_{HOME}.png` using `image_utils.make_matchup_icon`.
5. Modifiers:
   - `⌘` (Cmd): Open Game Box Score
   - `⌥` (Alt): Open Play-by-Play
6. Auto-refresh: Sets `"rerun": 5.0` whenever at least one game is actively live.

### 5.2 `nfl_standings.py` (`nfls`)
1. Fetches standings using `level=3`.
2. Groups by the 8 NFL Divisions in standard order:
   - AFC East, AFC North, AFC South, AFC West
   - NFC East, NFC North, NFC South, NFC West
3. Inserts disabled header items: `── AFC East ──`.
4. Team item format:
   - *Title*: `1. Buffalo Bills`
   - *Subtitle*: `3-0  Diff: +34  Streak: W3  PF: 92  PA: 58  Div: 1-0`
   - *Icon*: `nfl_logos/{abbr}.png`
   - *Arg*: Team clubhouse / schedule URL

### 5.3 `nfl_player.py` (`nflp {name}`)
1. If query < 2 characters: displays helpful placeholder `Type an NFL player's name (e.g. nflp mahomes)`.
2. Queries ESPN Search API for matching NFL players.
3. Concurrently fetches season statistics overview for top matches.
4. Downloads & caches headshots locally in `.cache/headshots/{player_id}.png` (7-day TTL).
5. Dynamic subtitle based on player's position:
   - **QB**: `3,240 YDS · 26 TD · 7 INT · 68.2 CMP% · 104.5 RTG`
   - **RB**: `840 RUSH YDS · 8 TD · 4.8 YPC · 35 REC · 280 REC YDS`
   - **WR / TE**: `64 REC · 890 YDS · 7 TD · 13.9 AVG`
   - **DEF**: `52 TKL · 9.5 SCK · 2 INT · 1 FF`
   - **K**: `22/24 FG (91.7%) · Long 57 · 31/31 XP`
6. Arg: Player card link on ESPN.

### 5.4 `nfl_team.py` (`nflt {query}`)
1. Matches query against team name, location, abbreviation, division, or conference.
2. If empty query: lists all 32 teams sorted by win percentage / conference.
3. Default Subtitle: Record, Division rank, Streak, Points For/Against.
4. Modifiers:
   - `⌘` (Cmd): Team Offense: Passing YPG, Rushing YPG, Total TDs, 3rd Down %
   - `⌥` (Alt): Team Defense: Sacks, Takeaways/INTs, Points Allowed/Game

---

## 6. Caching Strategy (`utils.py`)
- Directory: `.cache/` inside the workflow root.
- Stale-while-revalidate pattern for instant UI responsiveness in Alfred.
- **TTLs**:
  - Live scores: `30` seconds (live auto-rerun in 5s)
  - Standings: `300` seconds (5 min)
  - Team stats: `300` seconds (5 min)
  - Player search/overview: `300` seconds (5 min)
  - Player headshots: `604,800` seconds (7 days)

---

## 7. Build & Packaging Verification Checklist
- [ ] All 32 NFL team logos downloaded as crisp 64x64 PNGs.
- [ ] `info.plist` contains valid Alfred 5 XML with keyword `nfl`, `withspace: false`, and connected Open URL action.
- [ ] Tested CLI commands:
  - `python3 nfl.py`
  - `python3 nfl.py s`
  - `python3 nfl.py "p mahomes"`
  - `python3 nfl.py "t chiefs"`
- [ ] Packaging script outputs `NFL Scores.alfredworkflow`.
- [ ] Double-click installation test into Alfred 5 on macOS.
