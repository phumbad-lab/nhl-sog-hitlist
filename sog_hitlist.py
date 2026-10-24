"""
Morning NHL shots-on-goal hit list with DraftKings prices, sent to Telegram.

Built for: consistent middle-of-the-pack shooters (not the stars, whose short
milestones are overpriced), short-priced 2+/3+ legs to parlay into a +200 to
+350 ticket, and plus-money 3+ shooters played as straights.

Each morning (default 7 AM Eastern):
  1. Rank teams by shots allowed per game; tonight's games against the top
     LEAKY_TEAMS (default 20) are in play.
  2. On the other side of those games, keep skaters who are in their team's top
     6 forwards or top 4 defensemen by ice time (lines/pairs 1-2) and average
     MIN_RATE to MAX_RATE shots per game (default 1.5 to 5; the price limit drops overpriced stars). PP1 is shown
     (top 5 on the team in power-play time) and can be required with REQUIRE_PP1.
  3. For each, count how often he got 2+, 3+, 4+ shots in his last 20 games and
     in every game vs tonight's opponent (this season + last 3).
  4. Pull DraftKings' milestone prices (2+, 3+, ...) for the games on the list:
     one call per game, about 2-5 credits a day, capped per month.
  5. Send one message:
       Anchors       2+/3+ legs he's hit in 80%+ of his last 20 games AND 85%+ of
                     4+ games vs tonight's opponent, not priced past -400
       Plus-money    3+ legs at plus money he's hit in 65%+ of his last 20 and
                     80%+ of 4+ games vs tonight's opponent
       Ticket        3-4 anchors that add up to roughly +200 to +350
  If DK hasn't posted some games at send time, one follow-up with prices is
  sent once they appear (checks are free until they do), by FOLLOWUP_UNTIL.
  The next morning, yesterday's legs are graded from NHL game logs.

Environment variables:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   required to send
  ODDS_API_KEY        optional; without it the list uses fair prices only
  TELEGRAM_SILENT     "true" (default) = no sound
  SEND_HOUR, SEND_MINUTE  send at or after this time Eastern (default 7:05, five minutes
                      after the saves alert)
  FOLLOWUP_UNTIL      last hour for the DK-prices follow-up (default 12)
  LEAKY_TEAMS         top shots-allowed teams whose opponents are in play (default 20)
  MIN_RATE, MAX_RATE  shots-per-game band for shooters (default 1.5, 5)
  RECENT_HIT          anchor: share of his last RECENT_GAMES he hit the milestone, percent (default 80)
  VS_HIT              anchor: share of games vs tonight's opponent he hit it, percent (default 80)
  VS_MIN_GAMES        games vs the opponent needed before that record counts (default 4)
  PLUS_RECENT_HIT     3+ section: last-N share, percent (default 65)
  PLUS_VS_HIT         3+ section: vs-opponent share, percent (default 80)
  PLUS_STREAK         3+ section: 3+ shots in each of his last N games (default 5)
  PLUS_MIN_PRICE      3+ section: DK price must be this or better (default -110)
  FUN_K, FUN_MIN_PRICE  fun bet: milestone and lowest DK price (default 3+, +100)
  FUN_RECENT_HIT, FUN_STREAK  fun bet form: % of recent games at the milestone (60) and 2+ streak (1)
  ANCHOR_MAX_K        biggest milestone an anchor can be (default 2; 3+ legs have their own section)
  PP_UNITS            1 = only PP1 forwards get the top-9 exception, 2 = PP1 or PP2 (default 2)
  MAX_JUICE           anchors must be priced this or longer at DK (default -400)
  TARGET_MAX_JUICE    shorter than MAX_JUICE down to this = "additional targets", names only (default -600)
  PLUS_EDGE           points a 3+ leg's estimate must beat DK's price by (default 0)
  ANCHORS, PLUS_LEGS  how many of each to list (default 0 = every anchor; 0 = 3+ section off)
  ODDS_MONTHLY_CAP    most credits this bot spends per month (default 75)
  ODDS_RESERVE        never spend when the account is at or below this (default 200),
                      which protects the saves bot sharing the key
  BLEND_GAMES         early-season blending of player shot rates with last season (default 10; 0 = off)
  TEAM_BLEND_GAMES    same for team shots allowed / tightest defenses (default 0 = this season only)
  TOP_FORWARDS, TOP_D ice-time rank cutoffs (default 6, 4)
  PP1_TOP_FORWARDS    PP1 forwards also count if this high in ice time (default 9)
  HOT_RECENT, HOT_VS  hot hand: an anchor at HOT_RECENT% of his last RECENT_GAMES (default 90,
                      i.e. 9/10) only needs HOT_VS% vs the opponent (default 50)
  RECENT_GAMES        window for the recent-form bars (default 10)
  STREAK              anchors need 2+ shots in each of their last N games (default 5)
  TIGHT_TEAMS         skip shooters facing the N stingiest defenses (default 0 = every opponent in play)
  REQUIRE_PP1         "true" = only players on the first power-play unit
  FORCE               "true" = send the morning list now even if already sent
  CHECK               comma-separated player names: message whether each made today's
                      list and, if not, which rule left him out (spends no credits)
"""

import csv
import json
import math
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NHL_STATS = "https://api.nhle.com/stats/rest/en"
NHL_WEB = "https://api-web.nhle.com/v1"
ODDS_API = "https://api.the-odds-api.com/v4"
SPORT = "icehockey_nhl"
DK_MARKET = "player_shots_on_goal_alternate"   # DK's 2+/3+/4+ milestones
LOCAL_TZ = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
LOG_FILE = os.path.join(HERE, "hitlist.csv")
LOG_FIELDS = ["date", "section", "player", "player_id", "team", "opponent", "leg", "hit_pct",
              "fair_odds", "dk_odds", "dk_seen_at", "in_ticket", "actual_sog", "result", "units"]
TAIL_KEEP = 20          # recent games kept per player (enough to measure streaks)
SEASONS_BACK = 3
THRESHOLDS = (2, 3, 4, 5)
MIN_RECENT = 8          # need at least this many recent games to judge consistency (capped at the window)
ROLE_BLEND_GAMES = 5    # ice time blends toward this season fast, since line changes show quickly
PP1_SIZE, PP1_MIN_SECS = 5, 60   # PP1 = team's top 5 skaters in PP time, with 1:00+ a game
PP_UNIT_MIN_SECS = 30            # PP2 = the next 5, with 0:30+ a game
SHRINK_GAMES = 15       # pull hit rates toward what the shot rate predicts, worth this many games
DISPERSION = 0.25       # shot counts vary a bit more than Poisson: variance = mean x 1.25


# The workflow passes every repo Variable as one JSON blob (ALL_VARS), so new settings
# work without editing the workflow. Explicit environment values still win.
try:
    for _k, _v in json.loads(os.getenv("ALL_VARS") or "{}").items():
        if _v not in (None, "") and not os.getenv(_k):
            os.environ[_k] = str(_v)
except (ValueError, AttributeError):
    pass


SETTING_WARNINGS = []   # variables that couldn't be read; reported in messages instead of crashing


def env_num(name, default, cast=int):
    """Read a numeric setting, forgiving '1,500', '10%', '+100' and stray spaces.
    A value that still isn't a number falls back to the default and is reported."""
    raw = (os.getenv(name, "") or "").strip()
    if not raw:
        return cast(default)
    cleaned = raw.replace(",", "").replace("%", "").replace("$", "").replace(" ", "").lstrip("+")
    try:
        return cast(float(cleaned)) if cast is int else cast(cleaned)
    except ValueError:
        SETTING_WARNINGS.append(f"{name} = '{raw}' isn't a number, so the default {default} is used")
        return cast(default)


# SOG_BOT_TOKEN is this app's own Telegram bot (Sol Shoty). TELEGRAM_BOT_TOKEN is the bot shared
# with the saves app; it is only a fallback for SENDING. Replies are read ONLY from SOG_BOT_TOKEN,
# because the saves app reads replies on the shared bot and two readers steal each other's messages.
SOG_BOT_TOKEN = os.getenv("SOG_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = SOG_BOT_TOKEN or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
SILENT = (os.getenv("TELEGRAM_SILENT", "") or "true").strip().lower() in ("1", "true", "yes")
SEND_HOUR = env_num("SEND_HOUR", 7)
SEND_MINUTE = env_num("SEND_MINUTE", 5)
FOLLOWUP_UNTIL = env_num("FOLLOWUP_UNTIL", 12)
LEAKY_TEAMS = env_num("LEAKY_TEAMS", 32)
TIGHT_TEAMS = env_num("TIGHT_TEAMS", 0)       # skip shooters facing the N stingiest defenses (0 = off)
RECENT_GAMES = env_num("RECENT_GAMES", 10)    # "last N" window for the recent-form bars
STREAK = env_num("STREAK", 5)                 # must have 2+ shots in each of his last N games
MIN_RATE = env_num("MIN_RATE", 1.5, float)
MAX_RATE = env_num("MAX_RATE", 5, float)
RECENT_HIT = env_num("RECENT_HIT", 80, float) / 100
VS_HIT = env_num("VS_HIT", 80, float) / 100
VS_MIN_GAMES = env_num("VS_MIN_GAMES", 4)
HOT_RECENT = env_num("HOT_RECENT", 90, float) / 100   # hot hand: 18/20+ recently...
HOT_VS = env_num("HOT_VS", 50, float) / 100           # ...only needs 50%+ vs the opponent
PLUS_RECENT_HIT = env_num("PLUS_RECENT_HIT", 65, float) / 100
PLUS_VS_HIT = env_num("PLUS_VS_HIT", 80, float) / 100
MAX_JUICE = env_num("MAX_JUICE", -400)
# Oct 24: only legs the model rates 80%+ are listed. Through Oct 23, 2+ legs under 80% hit 17/31 (55%)
# vs 56/63 (89%) at 80%+. Legs under the bar are logged as "below" and graded quietly, not shown.
MIN_CHANCE = env_num("MIN_CHANCE", 80, float) / 100


def meets_chance(p):
    """Compared at whole percents, as shown in messages (79.6% shows and counts as 80%)."""
    return round(p * 100) >= round(MIN_CHANCE * 100)
TARGET_MAX_JUICE = env_num("TARGET_MAX_JUICE", -600)   # -401 to -600 (or no DK line yet) = additional targets
REFRESH_MINUTES = env_num("REFRESH_MINUTES", 60)   # re-check a posted game for missing player lines this often
PLUS_EDGE = env_num("PLUS_EDGE", 0, float) / 100
PLUS_K = env_num("PLUS_K", 3)                  # the 3+ shots section
FUN_K = env_num("FUN_K", 3)                    # fun bet milestone
FUN_MIN_PRICE = env_num("FUN_MIN_PRICE", 100)  # fun bet must pay plus money
FUN_RECENT_HIT = env_num("FUN_RECENT_HIT", 60, float) / 100   # 3+ in 6 of his last 10
FUN_STREAK = env_num("FUN_STREAK", 1)          # and 2+ shots last game (was 3 until Oct 12; backtest: streak length made no difference)
ANCHOR_MAX_K = env_num("ANCHOR_MAX_K", 2)      # anchors are 2+ legs; 3+ legs go in their own section
PLUS_STREAK = env_num("PLUS_STREAK", 5)        # 3+ shots in each of his last N games
PLUS_MIN_PRICE = env_num("PLUS_MIN_PRICE", -110)  # DK price must be -110 or better
ANCHORS = env_num("ANCHORS", 0)               # 0 = list every anchor
PLUS_LEGS = env_num("PLUS_LEGS", 0)           # 0 = 3+ section off (Oct 12; the fun bet covers 3+)
ODDS_MONTHLY_CAP = env_num("ODDS_MONTHLY_CAP", 75)
ODDS_RESERVE = env_num("ODDS_RESERVE", 200)
BLEND_GAMES = env_num("BLEND_GAMES", 10, float)            # player shot rates
TEAM_BLEND_GAMES = env_num("TEAM_BLEND_GAMES", 0, float)   # team shots allowed (0 = this season only)
TOP_FORWARDS = env_num("TOP_FORWARDS", 6)     # top 6 forwards by ice time = lines 1-2
PP1_TOP_FORWARDS = env_num("PP1_TOP_FORWARDS", 9)  # power-play forwards also count if top 9 in ice time
PP_UNITS = env_num("PP_UNITS", 2)                  # 1 = PP1 only, 2 = PP1 or PP2
TOP_D = env_num("TOP_D", 4)                   # top 4 D by ice time = pairs 1-2
REQUIRE_PP1 = os.getenv("REQUIRE_PP1", "").strip().lower() in ("1", "true", "yes")
CHECK = os.getenv("CHECK", "").strip()
FORCE = os.getenv("FORCE", "").strip().lower() in ("1", "true", "yes")


# ---------- helpers ----------

def nhl_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nhl-sog-hitlist/2.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def odds_get(path, params):
    """GET from The Odds API. Returns (data, remaining credits or None)."""
    url = f"{ODDS_API}{path}?{urllib.parse.urlencode(dict(params, apiKey=ODDS_API_KEY))}"
    req = urllib.request.Request(url, headers={"User-Agent": "nhl-sog-hitlist/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            rem = resp.headers.get("x-requests-remaining")
            return json.loads(resp.read().decode("utf-8")), (int(float(rem)) if rem not in (None, "") else None)
    except urllib.error.HTTPError as e:
        print(f"Odds API error {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
        return None, None


def name_key(name):
    plain = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", plain.lower())


def last_key(name):
    parts = (name or "").split()
    return name_key(parts[-1]) if parts else ""


def season_id(day, back=0):
    start = (day.year if day.month >= 8 else day.year - 1) - back
    return f"{start}{start + 1}"


def to_american(p):
    if p <= 0 or p >= 1:
        return "—"
    return f"{-100 * p / (1 - p):.0f}" if p >= 0.5 else f"+{100 * (1 - p) / p:.0f}"


def implied(price):
    return 100 / (price + 100) if price > 0 else -price / (-price + 100)


def decimal(price):
    return 1 + (price / 100 if price > 0 else 100 / -price)


def fmt_price(price):
    return "—" if price is None else (f"+{price}" if price > 0 else str(price))


def send_push(title, message, silent=None):
    text = f"{title}\n{message}"
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print(f"[dry run, no Telegram keys]\n{text}\n")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…(cut off)"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": text,
        "disable_notification": "true" if (SILENT if silent is None else silent) else "false",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if not result.get("ok"):
                sys.exit(f"Telegram error: {result}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Telegram rejected the message ({e.code}). Check TELEGRAM_BOT_TOKEN and "
                 f"TELEGRAM_CHAT_ID. {e.read().decode('utf-8', 'ignore')[:300]}")


def load_state():
    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}
    state.setdefault("past", {})        # per-player summaries of finished seasons (never change)
    state.setdefault("odds_used", {})   # {"2026-10": credits}
    return state


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, separators=(",", ":"), sort_keys=True)
        f.write("\n")


def load_log():
    try:
        with open(LOG_FILE, newline="") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        return []


def save_log(rows):
    with open(LOG_FILE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ---------- NHL data ----------

def stats_rows(report, season):
    exp = f"seasonId={season} and gameTypeId=2"
    base = f"{NHL_STATS}/{report}"
    raw = nhl_get(f"{base}?{urllib.parse.urlencode({'limit': -1, 'cayenneExp': exp})}")
    rows, total = raw.get("data", []), raw.get("total") or 0
    while total and len(rows) < total:
        page = nhl_get(f"{base}?{urllib.parse.urlencode({'start': len(rows), 'limit': 100, 'cayenneExp': exp})}")
        if not page.get("data"):
            break
        rows += page["data"]
    return rows


def team_abbrevs():
    data = nhl_get(f"{NHL_WEB}/standings/now")
    return {name_key(t["teamName"]["default"]): t["teamAbbrev"]["default"] for t in data.get("standings", [])}


def leaky_ranking(day, abbrevs):
    """[(abbrev, shots allowed/game, games)] most shots allowed first; blended early in the season."""
    cur = {name_key(r["teamFullName"]): r for r in stats_rows("team/summary", season_id(day))}
    last = {name_key(r["teamFullName"]): r for r in stats_rows("team/summary", season_id(day, 1))}
    out = []
    for key, ab in abbrevs.items():
        c, l = cur.get(key, {}), last.get(key, {})
        gp, sa, l_sa = c.get("gamesPlayed") or 0, c.get("shotsAgainstPerGame"), l.get("shotsAgainstPerGame")
        if TEAM_BLEND_GAMES > 0 and l_sa is not None:
            value = ((sa or 0) * gp + l_sa * TEAM_BLEND_GAMES) / (gp + TEAM_BLEND_GAMES)
        elif gp and sa is not None:
            value = sa
        else:
            continue
        out.append((ab, value, gp))
    return sorted(out, key=lambda t: t[1], reverse=True)


def skater_table(season):
    return {str(r["playerId"]): r for r in stats_rows("skater/summary", season) if r.get("gamesPlayed")}


def toi_table(season):
    """{player_id: (games, total TOI secs/game, PP TOI secs/game)}"""
    return {str(r["playerId"]): (r.get("gamesPlayed") or 0, r.get("timeOnIcePerGame") or 0,
                                 r.get("ppTimeOnIcePerGame") or 0)
            for r in stats_rows("skater/timeonice", season) if r.get("gamesPlayed")}


def blend_role(pid, toi_cur, toi_last):
    c, l = toi_cur.get(pid, (0, 0, 0)), toi_last.get(pid, (0, 0, 0))
    if l[0] >= 10:
        w = ROLE_BLEND_GAMES
        return ((c[1] * c[0] + l[1] * w) / (c[0] + w), (c[2] * c[0] + l[2] * w) / (c[0] + w))
    return (c[1], c[2])


def team_roles(players, toi_cur, toi_last):
    """{pid: {"toi", "pp", "rank" (within F or D), "top" (lines 1-2 / pairs 1-2), "pp1"}}"""
    info = {pid: dict(zip(("toi", "pp"), blend_role(pid, toi_cur, toi_last)), pos=pos)
            for pid, _, pos in players}
    for grp, cutoff in (("F", TOP_FORWARDS), ("D", TOP_D)):
        ranked = sorted((p for p in info if info[p]["pos"] == grp), key=lambda p: info[p]["toi"], reverse=True)
        for i, p in enumerate(ranked, 1):
            info[p]["rank"], info[p]["top"] = i, i <= cutoff and info[p]["toi"] > 0
    pp_ranked = sorted(info, key=lambda p: info[p]["pp"], reverse=True)
    for i, p in enumerate(pp_ranked, 1):
        info[p]["pp1"] = i <= PP1_SIZE and info[p]["pp"] >= PP1_MIN_SECS
        info[p]["pp_unit"] = i <= PP1_SIZE * PP_UNITS and info[p]["pp"] >= PP_UNIT_MIN_SECS
        # A power-play forward (PP1, or PP2 when PP_UNITS=2) on the third line still gets chances.
        if (info[p]["pos"] == "F" and info[p]["pp_unit"] and not info[p]["top"]
                and info[p]["rank"] <= PP1_TOP_FORWARDS and info[p]["toi"] > 0):
            info[p]["top"] = True
    return info


def fmt_toi(secs):
    return f"{int(secs // 60)}:{int(secs % 60):02d}"


def roster(abbrev):
    data = nhl_get(f"{NHL_WEB}/roster/{abbrev}/current")
    return [(str(p["id"]), f"{p['firstName']['default']} {p['lastName']['default']}",
             "D" if group == "defensemen" else "F")
            for group in ("forwards", "defensemen") for p in data.get(group, [])]


def shot_rate(pid, cur, last):
    c, l = cur.get(pid, {}), last.get(pid, {})
    c_gp, c_sh = c.get("gamesPlayed") or 0, c.get("shots") or 0
    l_gp, l_sh = l.get("gamesPlayed") or 0, l.get("shots") or 0
    if l_gp >= 10 and BLEND_GAMES > 0:
        return (c_sh + l_sh / l_gp * BLEND_GAMES) / (c_gp + BLEND_GAMES)
    return c_sh / c_gp if c_gp else None


def season_games(pid, season):
    try:
        data = nhl_get(f"{NHL_WEB}/player/{pid}/game-log/{season}/2")
    except urllib.error.HTTPError:
        return []
    games = [(g["gameDate"], g.get("opponentAbbrev", ""), g.get("shots") or 0) for g in data.get("gameLog", [])]
    return sorted(games, reverse=True)


def past_summary(pid, day, state):
    """Finished seasons, summarized once and kept: last 20 games' shots + counts vs each opponent."""
    seasons = [season_id(day, b) for b in range(1, SEASONS_BACK + 1)]
    key = f"{pid}:{seasons[0]}"
    if key not in state["past"]:
        games = []
        for s in seasons:
            games += season_games(pid, s)
        games.sort(reverse=True)
        vs = {}
        for _, opp, shots in games:
            v = vs.setdefault(opp, [0, 0] + [0] * len(THRESHOLDS))
            v[0] += 1
            v[1] += shots
            for i, k in enumerate(THRESHOLDS):
                v[2 + i] += shots >= k
        state["past"][key] = {"tail": [s for _, _, s in games[:TAIL_KEEP]],
                              "last": games[0][0] if games else "", "vs": vs}
    return state["past"][key]


# ---------- evaluation ----------

def chance_at_least(mean, k):
    """P(shots >= k) for a negative binomial with this mean (variance = mean x (1 + DISPERSION))."""
    if mean <= 0:
        return 0.0
    r = mean / DISPERSION
    q = r / (r + mean)
    pk, below = q ** r, 0.0
    for i in range(k):
        below += pk
        pk *= (i + r) / (i + 1) * (1 - q)
    return max(0.0, 1 - below)


def evaluate(pid, name, pos, team, opp, rate, day, state):
    """Hit rates at each milestone from recent form + history vs this opponent."""
    cur = [g for g in season_games(pid, season_id(day)) if g[0] < day.isoformat()]
    past = past_summary(pid, day, state)
    history = ([s for _, _, s in cur] + past["tail"])[:TAIL_KEEP]   # newest first
    recent = history[:RECENT_GAMES]
    if len(recent) < min(MIN_RECENT, RECENT_GAMES):
        return None
    streaks = {}
    for k in THRESHOLDS:
        n = 0
        for shots in history:
            if shots < k:
                break
            n += 1
        streaks[str(k)] = n
    streak = streaks["2"]
    pv = past["vs"].get(opp, [0, 0] + [0] * len(THRESHOLDS))
    cur_vs = [s for _, o, s in cur if o == opp]
    v_n, v_sum = pv[0] + len(cur_vs), pv[1] + sum(cur_vs)
    probs, detail = {}, {}
    for i, k in enumerate(THRESHOLDS):
        r_hits = sum(s >= k for s in recent)
        v_hits = pv[2 + i] + sum(s >= k for s in cur_vs)
        # Blend his actual record with what an average shooter at his rate would do, so a
        # lucky 20/20 streak doesn't read as a sure thing but real consistency still shows.
        prior = chance_at_least(rate, k)
        probs[str(k)] = (r_hits + v_hits + prior * SHRINK_GAMES) / (len(recent) + v_n + SHRINK_GAMES)
        detail[str(k)] = (r_hits, v_hits)
    def txt(n):
        return f"{n}+" if n == len(history) and n >= TAIL_KEEP else str(n)
    return {"pid": pid, "name": name, "pos": pos, "team": team, "opp": opp, "rate": rate,
            "streaks": streaks, "streak_txts": {k: txt(n) for k, n in streaks.items()},
            "streak_txt": txt(streak),
            "probs": probs, "detail": detail, "r_n": len(recent), "v_n": v_n, "streak": streak,
            "last_shots": history[0] if history else None,
            "vs_avg": v_sum / v_n if v_n else None,
            "last_played": cur[0][0] if cur else past["last"]}


def passes(c, k, recent_min, vs_min):
    """Did he hit k+ in enough of his last 20 AND of his (4+) games vs tonight's opponent?"""
    r_hits, v_hits = c["detail"][str(k)]
    return (r_hits / c["r_n"] >= recent_min and c["v_n"] >= VS_MIN_GAMES
            and v_hits / c["v_n"] >= vs_min)


def record(c, k):
    r_hits, v_hits = c["detail"][str(k)]
    return (r_hits + v_hits) / (c["r_n"] + c["v_n"])


def streak_at(c, k):
    return c.get("streaks", {}).get(str(k), c.get("streak", 0) if k == 2 else 0)


def anchor_ok(c, k):
    """A current streak at this milestone, plus the normal bar or the hot-hand bar
    (e.g. 9/10 recently with a 50%+ record vs the opponent)."""
    if streak_at(c, k) < STREAK:
        return False
    return passes(c, k, RECENT_HIT, VS_HIT) or passes(c, k, HOT_RECENT, HOT_VS)


def anchor_leg(c):
    """Biggest milestone that clears the anchor bar."""
    ks = [k for k in THRESHOLDS if k <= ANCHOR_MAX_K and anchor_ok(c, k)]
    return max(ks) if ks else None


# ---------- DraftKings prices ----------

def month_key(now):
    return now.strftime("%Y-%m")


def dk_prices(games_wanted, day, now, state, abbrevs, spend=True, refresh=()):
    """{(team, opp): {"seen": iso, "lines": {player_key: {k: price}}}} for games DK has posted.
    Reuses today's saved prices; spends at most 1 credit per newly posted game."""
    store = state.setdefault("dk", {})
    if store.get("date") != day.isoformat():
        store.clear()
        store["date"] = day.isoformat()
        store["games"] = {}
    have = store["games"]
    # Re-fetch posted games in `refresh` too: DK often adds players to a game after posting it.
    todo = [g for g in games_wanted if "|".join(g) not in have or g in refresh]
    if not todo or not ODDS_API_KEY or not spend:
        return have, None
    start = datetime.combine(day, datetime.min.time(), LOCAL_TZ)
    events, credits = odds_get(f"/sports/{SPORT}/events", {
        "commenceTimeFrom": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo": (start + timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    ids = {}
    for e in events or []:
        h, a = abbrevs.get(name_key(e["home_team"])), abbrevs.get(name_key(e["away_team"]))
        if h and a:
            ids[frozenset((h, a))] = e["id"]
    note = None
    for g in todo:
        used = state["odds_used"].get(month_key(now), 0)
        if used >= ODDS_MONTHLY_CAP:
            note = f"monthly odds cap reached ({ODDS_MONTHLY_CAP} credits)"
            break
        if credits is not None and credits <= ODDS_RESERVE:
            note = f"odds credits at reserve ({credits}), saved for the saves bot"
            break
        eid = ids.get(frozenset(g))
        if not eid:
            continue
        data, rem = odds_get(f"/sports/{SPORT}/events/{eid}/odds", {
            "bookmakers": "draftkings", "markets": DK_MARKET, "oddsFormat": "american"})
        if rem is not None:
            credits = rem
        lines = {}
        for bm in (data or {}).get("bookmakers", []):
            for m in bm.get("markets", []):
                if m.get("key") != DK_MARKET:
                    continue
                for o in m.get("outcomes", []):
                    if (o.get("name") or "").lower() != "over" or o.get("point") is None:
                        continue
                    k = int(o["point"] + 0.5)          # Over 1.5 = 2+
                    lines.setdefault(o.get("description") or "", {})[str(k)] = int(round(o["price"]))
        if lines:
            state["odds_used"][month_key(now)] = used + 1
            old = have.get("|".join(g)) or have.get("|".join(g[::-1])) or {}
            have.pop("|".join(g[::-1]), None)
            have["|".join(g)] = {"seen": old.get("seen") or now.strftime("%H:%M"), "fetched": iso_utc(now),
                                 "by_key": {name_key(n): v for n, v in lines.items()},
                                 "by_last": {}}
            by_last = {}
            for n, v in lines.items():
                by_last.setdefault(last_key(n), []).append(v)
            have["|".join(g)]["by_last"] = {k: v[0] for k, v in by_last.items() if len(v) == 1}
    return have, note


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def game_entry(have, g):
    return have.get("|".join(g)) or have.get("|".join(g[::-1]))


def dk_price(c, k, have):
    game = have.get(f"{c['team']}|{c['opp']}") or have.get(f"{c['opp']}|{c['team']}")
    if not game:
        return None, None
    prices = game["by_key"].get(name_key(c["name"])) or game["by_last"].get(last_key(c["name"])) or {}
    return prices.get(str(k)), game["seen"]


# ---------- build the list ----------

def stat_tables(day):
    return {"cur": skater_table(season_id(day)), "last": skater_table(season_id(day, 1)),
            "toi_cur": toi_table(season_id(day)), "toi_last": toi_table(season_id(day, 1))}


def research(day, state):
    """The NHL-data part of the list (no odds). Saved for the day so follow-ups reuse it."""
    abbrevs = team_abbrevs()
    ranking = leaky_ranking(day, abbrevs)
    in_play = min(LEAKY_TEAMS, len(ranking) - TIGHT_TEAMS)   # ranking: most shots allowed first
    leaky = {ab for ab, _, _ in ranking[:in_play]}
    games = [g for g in nhl_get(f"{NHL_WEB}/score/{day.isoformat()}").get("games", [])
             if g.get("gameScheduleState", "OK") == "OK"]
    matchups = []
    for g in games:
        a, h = g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]
        if h in leaky:
            matchups.append((a, h))
        if a in leaky:
            matchups.append((h, a))

    cands = []
    if matchups:
        ctx = stat_tables(day)
        for team, opp in matchups:
            players = roster(team)
            roles = team_roles(players, ctx["toi_cur"], ctx["toi_last"])
            for pid, name, pos in players:
                role = roles[pid]
                if not role["top"] or (REQUIRE_PP1 and not role["pp1"]):
                    continue
                rate = shot_rate(pid, ctx["cur"], ctx["last"])
                if rate is None or not (MIN_RATE <= rate <= MAX_RATE):
                    continue
                try:
                    c = evaluate(pid, name, pos, team, opp, rate, day, state)
                except Exception as e:
                    print(f"Skipped {name} ({e})")
                    continue
                if c:
                    cands.append(dict(c, toi=role["toi"], rank=role["rank"], pp1=role["pp1"]))
    # Flag anyone who missed his team's most recent game (injury / scratch).
    team_last = {}
    for c in cands:
        team_last[c["team"]] = max(team_last.get(c["team"], ""), c["last_played"])
    for c in cands:
        c["missed"] = c["last_played"] < team_last[c["team"]]
    return {"date": day.isoformat(), "abbrevs": abbrevs, "ranking": ranking[:in_play],
            "matchups": matchups, "cands": cands}


def select(rs, day, now, state, spend=True):
    """Shortlist, price the shortlisted games at DK, and pick anchors / plus-money / ticket."""
    cands = [c for c in rs["cands"] if not c["missed"]]
    abbrevs, matchups = rs["abbrevs"], rs["matchups"]
    # Shortlist before pricing, so credits only go to games that matter.
    anchors = [dict(c, k=anchor_leg(c)) for c in cands if anchor_leg(c)]
    # Ranked by chance of hitting (the estimate behind the fair price); record breaks ties.
    anchors.sort(key=lambda c: (c["probs"][str(c["k"])], record(c, c["k"])), reverse=True)
    below = [dict(c, price=None, seen=None, p=c["probs"][str(c["k"])])
             for c in anchors if not meets_chance(c["probs"][str(c["k"])])]
    anchors = [c for c in anchors if meets_chance(c["probs"][str(c["k"])])]
    plus_pool = []
    for c in cands:
        k = PLUS_K
        if anchor_leg(c) == k:
            continue                       # already listed as an anchor at this milestone
        if (str(k) in c["probs"] and streak_at(c, k) >= PLUS_STREAK
                and passes(c, k, PLUS_RECENT_HIT, PLUS_VS_HIT)):
            plus_pool.append(dict(c, k=k))
    plus_pool.sort(key=lambda c: (record(c, c["k"]), c["probs"][str(c["k"])]), reverse=True)
    # Price games one at a time, in order of need, so credits only go to games whose
    # players could still make the list (an overpriced star doesn't use up the slots).
    have, note, tried, unpriced = {}, None, set(), []

    refreshed = set()

    def price_for(c):
        nonlocal have, note
        g = (c["team"], c["opp"])
        key = frozenset(g)
        if key not in tried and note is None:
            tried.add(key)
            have, note = dk_prices([g], day, now, state, abbrevs, spend)
        price, seen = dk_price(c, c["k"], have)
        # Game posted but no line for him yet: re-check that game, at most once an hour.
        entry = game_entry(have, g)
        if price is None and entry and spend and note is None and key not in refreshed:
            fetched = entry.get("fetched")
            age = (now - datetime.strptime(fetched, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                   ) if fetched else timedelta(hours=24)
            if age >= timedelta(minutes=REFRESH_MINUTES):
                refreshed.add(key)
                have, note = dk_prices([g], day, now, state, abbrevs, spend, refresh={g})
                price, seen = dk_price(c, c["k"], have)
        if price is None and not any(frozenset(u) == key for u in unpriced):
            if "|".join(g) not in have and "|".join(g[::-1]) not in have:
                unpriced.append(g)
        return price, seen

    # Anchors: DK -400 or longer. Additional targets: -401 to -600, or no DK line yet.
    # Shorter than -600 isn't shown. Every qualifier's game is priced (1 credit a game).
    final_anchors, targets = [], []
    for c in anchors:
        price, seen = price_for(c)
        g = (c["team"], c["opp"])
        posted = "|".join(g) in have or "|".join(g[::-1]) in have
        leg = dict(c, price=price, seen=seen, p=c["probs"][str(c["k"])], game_posted=posted)
        if price is not None and price >= MAX_JUICE:
            if not ANCHORS or len(final_anchors) < ANCHORS:
                final_anchors.append(leg)
        elif price is None or price >= TARGET_MAX_JUICE:
            targets.append(leg)
    final_plus = []
    for c in plus_pool:
        if len(final_plus) == PLUS_LEGS:
            break
        price, seen = price_for(c)
        p = c["probs"][str(c["k"])]
        if price is not None and price >= PLUS_MIN_PRICE and p - implied(price) >= PLUS_EDGE:
            final_plus.append(dict(c, price=price, seen=seen, p=p))
    if not have:
        have = state.get("dk", {}).get("games", {})

    # Fun bet: the plus-money 3+ leg most likely to hit, among players in form.
    # Uses games already priced today, so it costs no extra credits.
    fun, taken = None, {c["pid"] for c in final_plus}
    for c in cands:
        if c["pid"] in taken or str(FUN_K) not in c["probs"]:
            continue
        r_hits, _ = c["detail"][str(FUN_K)]
        if r_hits / c["r_n"] < FUN_RECENT_HIT or streak_at(c, 2) < FUN_STREAK:
            continue
        leg = dict(c, k=FUN_K)
        price, seen = dk_price(leg, FUN_K, have)
        if price is None or price < FUN_MIN_PRICE:
            continue
        p = c["probs"][str(FUN_K)]
        if fun is None or (p, price) > (fun["p"], fun["price"]):
            fun = dict(leg, price=price, seen=seen, p=p)
    missing = [a["name"] for a in targets if a["price"] is None and a.get("game_posted")]
    return {"ranking": rs["ranking"], "matchups": matchups, "fun": fun, "missing": missing,
            "lined": sum(a["price"] is not None for a in final_anchors + targets),
            "anchors": final_anchors, "targets": targets, "below": below, "plus": final_plus, "unpriced": unpriced,
            "note": note, "ticket": build_ticket(final_anchors)}


def build_ticket(anchors):
    """Stack the anchors most likely to hit until the ticket pays about +200: max 4 legs,
    2 per game. Legs DK has priced come first, so the ticket price is real."""
    legs, dec, prob, per_game = [], 1.0, 1.0, {}
    for a in sorted(anchors, key=lambda a: (a["price"] is not None, a["p"]), reverse=True):
        price = a["price"]
        game = frozenset((a["team"], a["opp"]))
        if per_game.get(game, 0) == 2:
            continue
        per_game[game] = per_game.get(game, 0) + 1
        legs.append(a)
        dec *= decimal(price) if price is not None else 1 / a["p"]
        prob *= a["p"]
        if dec >= 3.0 or len(legs) == 4:
            break
    if len(legs) < 2:
        return None
    priced = all(a["price"] is not None for a in legs)
    return {"legs": legs, "dec": dec, "prob": prob, "priced": priced}


def dec_to_american(dec):
    return f"+{(dec - 1) * 100:.0f}" if dec >= 2 else f"{-100 / (dec - 1):.0f}"


def format_list(day, res, followup=False):
    title = (f"SOG +2 Hit List · DK prices update · {day.strftime('%a %b %-d')}" if followup
             else f"SOG +2 Hit List · {day.strftime('%a %b %-d')}")
    out = []
    if not res["matchups"]:
        return title, "None of tonight's games are against a leaky defense."
    targets = res.get("targets") or []
    if not res["anchors"] and not res["plus"] and not res.get("fun") and not targets:
        out.append("No consistent mid-tier shooters clear the bar tonight.")
    def leg_line(a, prefix):
        r_hits, v_hits = a["detail"][str(a["k"])]
        if a["price"] is None:
            price = "no DK line" if a.get("game_posted") else "DK not up"
        else:
            price = f"DK {fmt_price(a['price'])}" + (" ✓" if a["p"] > implied(a["price"]) + 0.03 else "")
        # The list is all 2+ legs (title says so), so the milestone isn't repeated per player.
        leg = "" if a["k"] == 2 else f" {a['k']}+"
        return (f"{prefix}{a['name']} ({a['team']}){leg} vs {a['opp']} · (f {to_american(a['p'])}) · "
                f"{price} · L{a['r_n']} {r_hits}/{a['r_n']} "
                f"({a.get('streak_txts', {}).get(str(a['k']), a.get('streak_txt', 0))} straight) · "
                f"vs {a['opp']} {v_hits}/{a['v_n']}")

    if res["anchors"]:
        out.append("ANCHORS")
        out += [leg_line(a, f"{i}. ") for i, a in enumerate(res["anchors"], 1)]
    elif targets:
        out.append(f"ANCHORS: none tonight at {MAX_JUICE} or better")
    if targets:
        def tag(t):
            if t["price"] is not None:
                return fmt_price(t["price"])
            return "no DK line" if t.get("game_posted") else "DK not up"
        out.append("\nADDITIONAL TARGETS")
        out.append(" · ".join(f"{t['name']} {tag(t)}" for t in targets))
    has_any = res["anchors"] or targets
    if res["plus"]:
        out.append(f"\n{PLUS_K}+ SHOOTERS ({fmt_price(PLUS_MIN_PRICE)} or better)")
        out += [leg_line(p, "") for p in res["plus"]]
    elif has_any and PLUS_LEGS:
        out.append(f"\n{PLUS_K}+ SHOOTERS: none tonight")
    f = res.get("fun")
    if f:
        r_hits, v_hits = f["detail"][str(f["k"])]
        out.append(f"\nFUN BET")
        out.append(f"{f['name']} ({f['team']}) {f['k']}+ vs {f['opp']} · DK {fmt_price(f['price'])} · "
                   f"history {f['p']:.0%} vs DK {implied(f['price']):.0%} · L{f['r_n']} {r_hits}/{f['r_n']} · "
                   f"vs {f['opp']} {f['k']}+ in {v_hits}/{f['v_n']} · {f.get('streak_txt', 0)} straight at 2+")
    elif has_any:
        out.append("\nFUN BET: none tonight")
    if res.get("missing") and not followup and not res["note"]:
        names = ", ".join(n.split()[-1] for n in res["missing"])
        out.append(f"\nDK hasn't posted lines for {names} yet; prices follow when they're up "
                   f"(by {FOLLOWUP_UNTIL % 12 or 12} {'PM' if FOLLOWUP_UNTIL >= 12 else 'AM'}).")
    if res["unpriced"] and not followup and not res["note"]:
        out.append(f"\nDK hasn't posted {len(res['unpriced'])} of these games yet; "
                   f"prices follow when they're up (by {FOLLOWUP_UNTIL % 12 or 12} {'PM' if FOLLOWUP_UNTIL >= 12 else 'AM'}).")
    if res["note"]:
        out.append(f"\nDK prices skipped: {res['note']}. Compare against the fair prices.")
    return title, "\n".join(out)


def log_today(day, res):
    """Replace today's rows with the current list (a follow-up adds prices)."""
    rows = [r for r in load_log() if r["date"] != day.isoformat()]
    ticket = {a["pid"] for a in (res["ticket"] or {}).get("legs", [])}
    fun = [res["fun"]] if res.get("fun") else []
    # Targets are logged (graded quietly, for later reviews) but not shown in results or the record.
    for section, legs in (("anchor", res["anchors"]), ("target", res.get("targets") or []),
                          ("below", res.get("below") or []),
                          ("plus", res["plus"]), ("fun", fun)):
        for a in legs:
            rows.append({"date": day.isoformat(), "section": section, "player": a["name"],
                         "player_id": a["pid"], "team": a["team"], "opponent": a["opp"], "leg": a["k"],
                         "hit_pct": f"{a['p'] * 100:.0f}", "fair_odds": to_american(a["p"]),
                         "dk_odds": fmt_price(a["price"]) if a["price"] is not None else "",
                         "dk_seen_at": a.get("seen") or "",
                         "in_ticket": "Y" if section == "anchor" and a["pid"] in ticket else ""})
    save_log(rows)


# ---------- grading ----------

def units(r):
    try:
        price = int(r["dk_odds"])
    except (TypeError, ValueError):
        return None
    return decimal(price) - 1 if r["result"] == "W" else -1.0 if r["result"] == "L" else 0.0


def grade(day):
    rows = load_log()
    pending = [r for r in rows if not r.get("result") and r["date"] < day.isoformat()]
    if not pending:
        return None
    logs = {}
    for r in pending:
        if r["player_id"] not in logs:
            try:
                d = datetime.strptime(r["date"], "%Y-%m-%d").date()
                logs[r["player_id"]] = {g[0]: g[2] for g in season_games(r["player_id"], season_id(d))}
            except Exception as e:
                print(f"Couldn't grade {r['player']} ({e})")
                continue
        shots = logs[r["player_id"]].get(r["date"])
        if shots is None:
            if (day - datetime.strptime(r["date"], "%Y-%m-%d").date()).days >= 2:
                r.update(actual_sog="", result="VOID")   # didn't play
            continue
        r.update(actual_sog=shots, result="W" if shots >= int(r["leg"]) else "L")
        u = units(r)
        r["units"] = f"{u:+.2f}" if u is not None else ""
    save_log(rows)
    graded = [r for r in pending if r.get("result") and r["section"] not in ("target", "below")]
    if not graded:
        return None

    lines = ["Yesterday:"]
    for r in graded:
        mark = {"W": "✅", "L": "❌"}.get(r["result"], "void")
        tag = {"plus": f" ({PLUS_K}+ shooter)", "fun": " (fun bet)"}.get(r["section"], "")
        shots = r["actual_sog"] if r["actual_sog"] != "" else "-"
        leg = "" if r["leg"] == "2" and not tag else f" {r['leg']}+"
        lines.append(f"{mark} {r['player']}{leg}{tag}: {shots}")
    return "\n".join(lines)


RECORD_SINCE = os.getenv("RECORD_SINCE", "").strip()   # e.g. 2026-10-10; empty = every graded leg


def record_block(rows):
    """Running win rate for each kind of recommendation (voids excluded)."""
    out = []
    for section, label in (("anchor", "Anchors"), ("fun", "Fun bets")) + ((("plus", f"{PLUS_K}+ shooters"),) if PLUS_LEGS else ()):
        done = [r for r in rows if r["section"] == section and r.get("result") in ("W", "L")
                and (not RECORD_SINCE or r["date"] >= RECORD_SINCE)]
        if not done and section == "plus":
            continue
        wins = sum(r["result"] == "W" for r in done)
        out.append(f"{label}: {wins}/{len(done)}, {wins / len(done):.0%}" if done else f"{label}: no results yet")
    title = "RECORD" + (f" (since {datetime.strptime(RECORD_SINCE, '%Y-%m-%d').strftime('%b %-d')})"
                        if RECORD_SINCE else "")
    return title + "\n" + "\n".join(out)


def season_line(rows):
    a = [r for r in rows if r["section"] == "anchor" and r.get("result") in ("W", "L")]
    p = [r for r in rows if r["section"] == "plus" and r.get("result") in ("W", "L")]
    parts = []
    if a:
        parts.append(f"anchors {sum(r['result'] == 'W' for r in a)}/{len(a)}")
    if p:
        u = sum(float(r["units"] or 0) for r in p)
        parts.append(f"{PLUS_K}+ shooters {sum(r['result'] == 'W' for r in p)}-{sum(r['result'] == 'L' for r in p)} {u:+.1f}u")
    f = [r for r in rows if r["section"] == "fun" and r.get("result") in ("W", "L")]
    if f:
        u = sum(float(r["units"] or 0) for r in f)
        parts.append(f"fun bets {sum(r['result'] == 'W' for r in f)}-{sum(r['result'] == 'L' for r in f)} {u:+.1f}u")
    tickets = {}
    for r in rows:
        if r["in_ticket"] == "Y":
            tickets.setdefault(r["date"], []).append(r.get("result"))
    done = [v for v in tickets.values() if all(v) and any(x != "VOID" for x in v)]
    if done:
        hit = sum(all(x in ("W", "VOID") for x in v) for v in done)
        parts.append(f"tickets {hit}/{len(done)}")
    return ("Season: " + " · ".join(parts)) if parts else ""


# ---------- check mode ----------

def find_player(query, tables):
    """[(pid, full name, team)] matching a full or last name in this or last season's stats."""
    q, hits = name_key(query), {}
    for t in tables:
        for pid, r in t.items():
            full = r.get("skaterFullName", "")
            if q in (name_key(full), last_key(full)) and pid not in hits:
                hits[pid] = (pid, full, (r.get("teamAbbrevs") or "").split(",")[-1].strip())
    return list(hits.values())


def checklist(c, role, pos, team, opp, rate, have, sa_rank, n_teams):
    """Every rule, one per line: his number, the bar, and ✅/❌. Used by the player check."""
    mark = lambda ok: "✅" if ok else "❌"
    out = []
    if TIGHT_TEAMS and sa_rank.get(opp, 0) > n_teams - TIGHT_TEAMS:
        out.append(f"❌ Opponent: {opp} is a top-{TIGHT_TEAMS} tight defense")
    if LEAKY_TEAMS < n_teams and sa_rank.get(opp, 99) > LEAKY_TEAMS:
        out.append(f"❌ Opponent: {opp} isn't a top-{LEAKY_TEAMS} leaky defense")
    pp = "PP1" if role.get("pp1") else "PP2" if role.get("pp_unit") else "no PP unit"
    bar = (f"top {TOP_FORWARDS} F (top {PP1_TOP_FORWARDS} if on PP{'1' if PP_UNITS == 1 else '1/PP2'})"
           if pos == "F" else f"top {TOP_D} D")
    out.append(f"{mark(role['top'])} Ice time: {pos}#{role['rank']} ({fmt_toi(role['toi'])}), {pp} · needs {bar}")
    if REQUIRE_PP1:
        out.append(f"{mark(role.get('pp1'))} PP1 · required")
    out.append(f"{mark(MIN_RATE <= rate <= MAX_RATE)} Shots/game: {rate:.1f} · needs {MIN_RATE:g} to {MAX_RATE:g}")
    if not c:
        out.append("❌ Not enough recent games to judge")
        return out
    if "missed" in c:
        out.append(f"{mark(not c['missed'])} Played his team's last game")
    r_n, v_n = c["r_n"], c["v_n"]
    r2, v2 = c["detail"]["2"]
    out.append(f"{mark(r2 / r_n >= RECENT_HIT)} Last {r_n}: 2+ in {r2}/{r_n} · needs {math.ceil(RECENT_HIT * r_n - 1e-9)}")
    streak = c.get("streak", 0)
    out.append(f"{mark(streak >= STREAK)} Streak: 2+ in {c.get('streak_txt', streak)} straight "
               f"(last game {c.get('last_shots')}) · needs {STREAK}")
    hot = r2 / r_n >= HOT_RECENT and HOT_VS < VS_HIT
    vs_bar = HOT_VS if hot else VS_HIT
    vs_ok = v_n >= VS_MIN_GAMES and v2 / v_n >= vs_bar
    out.append(f"{mark(vs_ok)} Vs {opp}: 2+ in {v2}/{v_n} · needs {vs_bar:.0%} of {VS_MIN_GAMES}+ games"
               + (f" (hot-hand bar; {HOT_RECENT:.0%}+ recently)" if hot else ""))
    p2, p3 = c["probs"]["2"], c["probs"].get("3")
    price, _ = dk_price(c, 2, have)
    if price is None:
        posted = f"{team}|{opp}" in have or f"{opp}|{team}" in have
        out.append(f"➖ DK 2+: {'no line yet' if posted else 'game not posted yet'}")
    elif price >= MAX_JUICE:
        out.append(f"✅ DK 2+: {fmt_price(price)} · anchor needs {MAX_JUICE} or better")
    elif price >= TARGET_MAX_JUICE:
        out.append(f"🔸 DK 2+: {fmt_price(price)} · additional target ({MAX_JUICE} to {TARGET_MAX_JUICE})")
    else:
        out.append(f"❌ DK 2+: {fmt_price(price)} · shorter than {TARGET_MAX_JUICE}, not listed")
    out.append(f"{mark(meets_chance(p2))} Chance 2+: {p2:.0%} (fair {to_american(p2)}) · needs {MIN_CHANCE:.0%}"
               + (f" · 3+ {p3:.0%}" if p3 is not None else ""))
    if str(FUN_K) in c["detail"]:
        r3 = c["detail"][str(FUN_K)][0]
        p_fun, _ = dk_price(c, FUN_K, have)
        fun_ok = (r3 / r_n >= FUN_RECENT_HIT and streak >= FUN_STREAK
                  and p_fun is not None and p_fun >= FUN_MIN_PRICE)
        out.append(f"{'🎲' if fun_ok else '➖'} Fun bet {FUN_K}+: {r3}/{r_n} (needs {math.ceil(FUN_RECENT_HIT * r_n - 1e-9)}) · "
                   f"DK {fmt_price(p_fun) if p_fun is not None else 'no line'} (needs {fmt_price(FUN_MIN_PRICE)} or better)")
    return out


def check_players(names, day, now, state):
    rs = state.get("today") if (state.get("today") or {}).get("date") == day.isoformat() else None
    if rs is None:   # today's list hasn't run yet: answer from the rules alone
        rs = {"date": day.isoformat(), "abbrevs": team_abbrevs(), "ranking": [], "matchups": [], "cands": []}
    res = select(rs, day, now, state, spend=False)
    listed = {}
    for i, a in enumerate(res["anchors"], 1):
        listed[a["pid"]] = f"anchor #{i}: {a['k']}+ at {a['p']:.0%}" + (f", DK {fmt_price(a['price'])}" if a["price"] is not None else "")
    for t in res.get("targets") or []:
        listed.setdefault(t["pid"], f"additional target: {t['k']}+ at {t['p']:.0%}"
                          + (f", DK {fmt_price(t['price'])}" if t["price"] is not None else ""))
    for p in res["plus"]:
        listed.setdefault(p["pid"], f"{PLUS_K}+ shooters: {p['k']}+ at DK {fmt_price(p['price'])}, hits {p['p']:.0%}")
    # What was actually SENT today (from the log). Settings may have changed since, so the
    # rebuilt list above can differ; the answer must reflect what the owner received.
    sent_rows = [r for r in load_log() if r["date"] == day.isoformat() and r["section"] != "below"]
    list_was_sent = state.get("last_sent") == day.isoformat() and bool(sent_rows)
    sent = {}
    for r in sent_rows:
        label = {"anchor": "anchor", "target": "additional target", "plus": f"{PLUS_K}+ shooters",
                 "fun": "fun bet"}.get(r["section"], r["section"])
        price = f", DK {r['dk_odds']}" if r.get("dk_odds") else ""
        sent.setdefault(r["player_id"], []).append(f"{label}: {r['leg']}+{price}")
    ranking = leaky_ranking(day, rs["abbrevs"])
    sa_rank = {ab: i for i, (ab, _, _) in enumerate(ranking, 1)}
    opp_of = {}
    for g in nhl_get(f"{NHL_WEB}/score/{day.isoformat()}").get("games", []):
        a, h = g["awayTeam"]["abbrev"], g["homeTeam"]["abbrev"]
        opp_of[a], opp_of[h] = h, a
    ctx = stat_tables(day)
    cand_by_pid = {c["pid"]: c for c in rs["cands"]}
    out = []
    for query in [n.strip() for n in names.split(",") if n.strip()]:
        hits = [h for h in find_player(query, (ctx["cur"], ctx["last"])) if h[2] in opp_of] or \
               find_player(query, (ctx["cur"], ctx["last"]))
        if not hits:
            out.append(f"❓ {query}: no NHL skater by that name")
            continue
        if len(hits) > 1:
            out.append(f"❓ {query}: more than one match ({', '.join(h[1] for h in hits)}); use the full name")
            continue
        pid, name, team = hits[0]
        players = roster(team) if team in opp_of else []
        on_roster = {p[0]: p for p in players}
        if team not in opp_of or pid not in on_roster:
            out.append(f"➖ {name}: {team} doesn't play today" if team not in opp_of
                       else f"➖ {name}: not on {team}'s current roster")
            continue
        opp, pos = opp_of[team], on_roster[pid][2]
        role = team_roles(players, ctx["toi_cur"], ctx["toi_last"])[pid]
        rate = shot_rate(pid, ctx["cur"], ctx["last"]) or 0
        c = cand_by_pid.get(pid) or evaluate(pid, name, pos, team, opp, rate, day, state)
        dk_have = state.get("dk", {}).get("games", {})
        n_teams = len(ranking)
        checks = checklist(c, role, pos, team, opp, rate, dk_have, sa_rank, n_teams)
        head = f"{name} ({team}) vs {opp}"
        if list_was_sent and pid in sent:
            status = f"✅ {head}: on today's list ({'; '.join(sent[pid])})"
        elif list_was_sent and pid in listed:
            status = (f"❌ {head}: not on today's list. Settings changed after it was sent; "
                      f"under the current ones he'd qualify ({listed[pid]})")
        elif list_was_sent:
            status = f"❌ {head}: not on today's list"
        elif pid in listed:
            status = f"✅ {head}: qualifies ({listed[pid]}); today's list hasn't been sent yet"
        else:
            status = f"❌ {head}: doesn't qualify (today's list hasn't been sent yet)"
        out.append(status + "\n" + "\n".join(checks))
    return f"SOG check · {day.strftime('%a %b %-d')}", "\n".join(out)


# ---------- main ----------

# ---------- text replies ----------

OFFSET_FILE = os.path.join(HERE, "telegram_offset.txt")
REPLY = os.getenv("REPLY", "").strip().lower() in ("1", "true", "yes")
HELP_TEXT = ("Text me a player's last name (or several, separated by commas) and I'll say whether he "
             "made today's list and, if not, which rule cut him.\n"
             "Text a team and a number for who's most likely to get that many shots in its game "
             "today: FLA 3 · BUF 2\n"
             "Examples: dorofeyev · kadri, raddysh · FLA 3 · settings")


def telegram_api(method, params):
    # Only ever this app's own bot: never the bot shared with the saves app.
    url = f"https://api.telegram.org/bot{SOG_BOT_TOKEN}/{method}"
    req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


GAME_BOARD_SIZE = 6
NHL_TEAMS = {"ANA", "BOS", "BUF", "CAR", "CBJ", "CGY", "CHI", "COL", "DAL", "DET", "EDM", "FLA", "LAK",
             "MIN", "MTL", "NJD", "NSH", "NYI", "NYR", "OTT", "PHI", "PIT", "SEA", "SJS", "STL", "TBL",
             "TOR", "UTA", "VAN", "VGK", "WPG", "WSH"}
GAME_RE = re.compile(r"^([A-Za-z]{3})\s*(\d)\+?$")


def game_board(team, k, day, state):
    """'FLA 3': everyone in FLA's game today, ranked by chance of k+ shots. Uses the
    morning research and saved DK prices, so it costs no credits."""
    rs = state.get("today") or {}
    title = f"{team} {k}+ · {day.strftime('%a %b %-d')}"
    if rs.get("date") != day.isoformat():
        return title, "Today's research hasn't run yet. Try again after the 7:05 list."
    cands = [c for c in rs["cands"] if team in (c["team"], c["opp"]) and not c.get("missed")]
    if not cands:
        playing = sorted({c["team"] for c in rs["cands"]})
        return title, f"{team} doesn't play today (or none of its players pass the role and shot-rate filters)." + \
            (f"\nPlaying today: {', '.join(playing)}" if playing else "")
    if str(k) not in cands[0]["probs"]:
        return title, f"I only track 2+ to {THRESHOLDS[-1]}+. Try e.g. {team} 3."
    opp = cands[0]["opp"] if cands[0]["team"] == team else cands[0]["team"]
    have = state.get("dk", {}).get("games", {})
    cands.sort(key=lambda c: c["probs"][str(k)], reverse=True)
    lines = [f"{team} vs {opp}: most likely to get {k}+ shots"]
    for i, c in enumerate(cands[:GAME_BOARD_SIZE], 1):
        price, _ = dk_price(c, k, have)
        r_hits, v_hits = c["detail"][str(k)]
        lines.append(f"{i}. {c['name']} ({c['team']}) {c['probs'][str(k)]:.0%} · "
                     f"DK {fmt_price(price) if price is not None else 'no line'} · "
                     f"L{c['r_n']} {r_hits}/{c['r_n']} · vs {c['opp']} {v_hits}/{c['v_n']}")
    lines.append("\nTop-line players only (top 6 F, top 4 D, PP forwards; 1.5–5 shots a game).")
    return title, "\n".join(lines)


def answer_texts():
    """Reply to new messages in your chat with the shots bot. Other chats are ignored.
    Refuses to run without SOG_BOT_TOKEN, so it can never read the bot shared with the saves app."""
    if not (SOG_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("Replies are off: add the SOG_BOT_TOKEN secret (this app's own bot) to turn them on.")
        return
    try:
        offset = int(open(OFFSET_FILE).read().strip() or 0)
    except (FileNotFoundError, ValueError):
        offset = 0
    updates = telegram_api("getUpdates", {"offset": offset, "timeout": 0}).get("result", [])
    if not updates:
        print("No new messages.")
        return
    now = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    day = now.date()
    state = load_state()          # read only: replies never change the day's list or log
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id")) != TELEGRAM_CHAT_ID:
            continue
        text = (msg.get("text") or "").strip()
        words = re.sub(r"^/?(check|start)\b", "", text, flags=re.I).strip(" :,")
        if not words or words.lower() in ("help", "/help", "start"):
            send_push("SOG bot", HELP_TEXT, silent=False)
        elif words.lower() == "settings":
            send_push(f"SOG settings · {day.strftime('%a %b %-d')}", settings_report(), silent=False)
        elif GAME_RE.match(words) and GAME_RE.match(words).group(1).upper() in NHL_TEAMS:
            m_ = GAME_RE.match(words)
            title, body = game_board(m_.group(1).upper(), int(m_.group(2)), day, state)
            send_push(title, body, silent=False)
        else:
            try:
                title, body = check_players(words, day, now, state)
            except Exception as e:
                title, body = "SOG check", f"Couldn't check '{words}' right now ({e}). Try again in a few minutes."
            send_push(title, body, silent=False)
        print(f"Answered: {text!r}")
    with open(OFFSET_FILE, "w") as f:
        f.write(f"{offset}\n")


SETTINGS = ["SEND_HOUR", "SEND_MINUTE", "FOLLOWUP_UNTIL", "ANCHORS", "ANCHOR_MAX_K", "RECENT_GAMES",
            "RECENT_HIT", "STREAK", "VS_HIT", "VS_MIN_GAMES", "HOT_RECENT", "HOT_VS", "MIN_RATE",
            "MAX_RATE", "TOP_FORWARDS", "TOP_D", "PP1_TOP_FORWARDS", "PP_UNITS", "REQUIRE_PP1",
            "TIGHT_TEAMS", "LEAKY_TEAMS", "BLEND_GAMES", "TEAM_BLEND_GAMES", "MAX_JUICE", "TARGET_MAX_JUICE", "MIN_CHANCE", "PLUS_K",
            "PLUS_LEGS", "PLUS_RECENT_HIT", "PLUS_VS_HIT", "PLUS_STREAK", "PLUS_MIN_PRICE", "PLUS_EDGE",
            "FUN_K", "FUN_MIN_PRICE", "FUN_RECENT_HIT", "FUN_STREAK", "ODDS_MONTHLY_CAP", "ODDS_RESERVE",
            "RECORD_SINCE"]
PERCENTS = {"MIN_CHANCE", "RECENT_HIT", "VS_HIT", "HOT_RECENT", "HOT_VS", "PLUS_RECENT_HIT", "PLUS_VS_HIT",
            "PLUS_EDGE", "FUN_RECENT_HIT"}


def settings_report():
    """Every setting as the script sees it; * marks ones set in the Variables tab."""
    lines = []
    for name in SETTINGS:
        val = globals().get(name)
        if name in PERCENTS:
            val = f"{val * 100:g}"
        elif isinstance(val, float):
            val = f"{val:g}"
        lines.append(f"{'*' if os.getenv(name) else ' '} {name} = {val}")
    lines.append("")
    lines.append("* = set in your Variables tab; the rest are built-in defaults.")
    lines.append(f"Odds API key: {'present' if ODDS_API_KEY else 'MISSING'}")
    if SETTING_WARNINGS:
        lines += ["", "⚠️ Fix in the Variables tab:"] + [f"- {w}" for w in SETTING_WARNINGS]
    return "\n".join(lines)


def credits_line(state, now):
    """'Credits: 452 left' (shared with the saves bot). Listing events is free and reports the balance.
    Also carries any unreadable-setting warnings."""
    warn = ("⚠️ " + "; ".join(SETTING_WARNINGS) + "\n") if SETTING_WARNINGS else ""
    if not ODDS_API_KEY:
        return warn.strip()
    _, left = odds_get(f"/sports/{SPORT}/events", {})
    return warn + (f"Credits: {left} left" if left is not None else "")


def priced_count(state):
    return len(state.get("dk", {}).get("games", {}))


def main():
    now = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    day = now.date()
    state = load_state()
    sent_today = state.get("last_sent") == day.isoformat()

    if REPLY:
        answer_texts()
        return

    if CHECK.strip().lower() == "settings":
        send_push(f"SOG settings · {day.strftime('%a %b %-d')}", settings_report())
        print("Sent settings.")
        return

    if CHECK:
        title, body = check_players(CHECK, day, now, state)
        send_push(title, body)
        save_state(state)
        print("Sent player check.")
        return

    if FORCE or (not sent_today and (SEND_HOUR, SEND_MINUTE) <= (now.hour, now.minute) and now.hour < 23):
        results = grade(day)
        rs = research(day, state)
        state["today"] = rs
        res = select(rs, day, now, state)
        title, body = format_list(day, res)
        if results:
            body += "\n\n" + results
        body += "\n\n" + record_block(load_log())
        line = credits_line(state, now)
        body += f"\n\n{line}" if line else ""
        send_push(title, body)
        if res["matchups"]:
            log_today(day, res)
        state["last_sent"] = day.isoformat()
        waiting = bool(res["unpriced"] or res.get("missing")) and not res["note"] and bool(ODDS_API_KEY)
        state["followup"] = {"base": priced_count(state), "lined": res.get("lined", 0)} if waiting else None
        print("Sent morning list.")
    elif sent_today and state.get("followup") and now.hour < FOLLOWUP_UNTIL:
        # Checks on unposted games are free; send one update once prices arrive
        # (all of them, or whatever has posted by the last hour of the window).
        rs = state.get("today") if (state.get("today") or {}).get("date") == day.isoformat() else None
        res = select(rs or research(day, state), day, now, state)
        gained = (priced_count(state) > state["followup"]["base"]
                  or res.get("lined", 0) > state["followup"].get("lined", 0))
        settled = not res["unpriced"] and not res.get("missing")
        if gained and (settled or res["note"] or now.hour >= FOLLOWUP_UNTIL - 1):
            title, body = format_list(day, res, followup=True)
            line = credits_line(state, now)
            body += f"\n\n{line}" if line else ""
            send_push(title, body)
            log_today(day, res)
            state["followup"] = None
            print("Sent DK prices follow-up.")
        else:
            print(f"Waiting on DK for {len(res['unpriced'])} game(s) and lines for {res.get('missing')}.")
    elif sent_today and state.get("followup"):
        state["followup"] = None
        print("Follow-up window closed.")
    else:
        print(f"Nothing to do (sends after {SEND_HOUR}:{SEND_MINUTE:02d} ET; last sent {state.get('last_sent')}).")

    # Keep only player summaries for the current set of finished seasons.
    tag = f":{season_id(day, 1)}"
    state["past"] = {k: v for k, v in state["past"].items() if k.endswith(tag)}
    save_state(state)


if __name__ == "__main__":
    main()
