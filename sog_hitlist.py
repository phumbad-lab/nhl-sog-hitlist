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
     MIN_RATE to MAX_RATE shots per game (default 1.8 to 3.6). PP1 is shown
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
  MIN_RATE, MAX_RATE  shots-per-game band for shooters (default 1.8, 3.6)
  RECENT_HIT          anchor: share of last 20 games he hit the milestone, percent (default 80)
  VS_HIT              anchor: share of games vs tonight's opponent he hit it, percent (default 85)
  VS_MIN_GAMES        games vs the opponent needed before that record counts (default 4)
  PLUS_RECENT_HIT     plus-money 3+: last-20 share, percent (default 65)
  PLUS_VS_HIT         plus-money 3+: vs-opponent share, percent (default 80)
  MAX_JUICE           skip anchors DK prices shorter than this (default -400)
  PLUS_EDGE           points a plus-money leg's hit rate must beat DK's price by (default 5)
  ANCHORS, PLUS_LEGS  how many of each to list (default 6, 3)
  ODDS_MONTHLY_CAP    most credits this bot spends per month (default 75)
  ODDS_RESERVE        never spend when the account is at or below this (default 200),
                      which protects the saves bot sharing the key
  BLEND_GAMES         early-season blending with last season (default 10; 0 = off)
  TOP_FORWARDS, TOP_D ice-time rank cutoffs (default 6, 4)
  PP1_TOP_FORWARDS    PP1 forwards also count if this high in ice time (default 9)
  HOT_RECENT, HOT_VS  hot hand: an anchor at HOT_RECENT% of his last 20 (default 90,
                      i.e. 18/20) only needs HOT_VS% vs the opponent (default 50)
  REQUIRE_PP1         "true" = only players on the first power-play unit
  FORCE               "true" = send the morning list now even if already sent
  CHECK               comma-separated player names: message whether each made today's
                      list and, if not, which rule left him out (spends no credits)
"""

import csv
import json
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
RECENT_GAMES = 20
SEASONS_BACK = 3
THRESHOLDS = (2, 3, 4, 5)
MIN_RECENT = 8          # need at least this many recent games to judge consistency
ROLE_BLEND_GAMES = 5    # ice time blends toward this season fast, since line changes show quickly
PP1_SIZE, PP1_MIN_SECS = 5, 60   # PP1 = team's top 5 skaters in PP time, with 1:00+ a game
SHRINK_GAMES = 15       # pull hit rates toward what the shot rate predicts, worth this many games
DISPERSION = 0.25       # shot counts vary a bit more than Poisson: variance = mean x 1.25


def env_num(name, default, cast=int):
    return cast(os.getenv(name, "") or default)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
SILENT = (os.getenv("TELEGRAM_SILENT", "") or "true").strip().lower() in ("1", "true", "yes")
SEND_HOUR = env_num("SEND_HOUR", 7)
SEND_MINUTE = env_num("SEND_MINUTE", 5)
FOLLOWUP_UNTIL = env_num("FOLLOWUP_UNTIL", 12)
LEAKY_TEAMS = env_num("LEAKY_TEAMS", 20)
MIN_RATE = env_num("MIN_RATE", 1.8, float)
MAX_RATE = env_num("MAX_RATE", 3.6, float)
RECENT_HIT = env_num("RECENT_HIT", 80, float) / 100
VS_HIT = env_num("VS_HIT", 85, float) / 100
VS_MIN_GAMES = env_num("VS_MIN_GAMES", 4)
HOT_RECENT = env_num("HOT_RECENT", 90, float) / 100   # hot hand: 18/20+ recently...
HOT_VS = env_num("HOT_VS", 50, float) / 100           # ...only needs 50%+ vs the opponent
PLUS_RECENT_HIT = env_num("PLUS_RECENT_HIT", 65, float) / 100
PLUS_VS_HIT = env_num("PLUS_VS_HIT", 80, float) / 100
MAX_JUICE = env_num("MAX_JUICE", -400)
PLUS_EDGE = env_num("PLUS_EDGE", 5, float) / 100
ANCHORS = env_num("ANCHORS", 6)
PLUS_LEGS = env_num("PLUS_LEGS", 3)
ODDS_MONTHLY_CAP = env_num("ODDS_MONTHLY_CAP", 75)
ODDS_RESERVE = env_num("ODDS_RESERVE", 200)
BLEND_GAMES = env_num("BLEND_GAMES", 10, float)
TOP_FORWARDS = env_num("TOP_FORWARDS", 6)     # top 6 forwards by ice time = lines 1-2
PP1_TOP_FORWARDS = env_num("PP1_TOP_FORWARDS", 9)  # PP1 forwards also count if top 9 in ice time
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


def send_push(title, message):
    text = f"{title}\n{message}"
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print(f"[dry run, no Telegram keys]\n{text}\n")
        return
    if len(text) > 4096:
        text = text[:4080] + "\n…(cut off)"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID, "text": text,
        "disable_notification": "true" if SILENT else "false",
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
        if BLEND_GAMES > 0 and l_sa is not None:
            value = ((sa or 0) * gp + l_sa * BLEND_GAMES) / (gp + BLEND_GAMES)
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
        # A first-unit power-play forward on the third line still gets real chances.
        if (info[p]["pos"] == "F" and info[p]["pp1"] and not info[p]["top"]
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
        state["past"][key] = {"tail": [s for _, _, s in games[:RECENT_GAMES]],
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
    recent = [s for _, _, s in cur][:RECENT_GAMES]
    recent += past["tail"][:RECENT_GAMES - len(recent)]
    if len(recent) < MIN_RECENT:
        return None
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
    return {"pid": pid, "name": name, "pos": pos, "team": team, "opp": opp, "rate": rate,
            "probs": probs, "detail": detail, "r_n": len(recent), "v_n": v_n,
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


def anchor_ok(c, k):
    """Normal bar, or the hot-hand bar: 18/20+ recently with a 50%+ record vs the opponent."""
    return passes(c, k, RECENT_HIT, VS_HIT) or passes(c, k, HOT_RECENT, HOT_VS)


def anchor_leg(c):
    """Biggest milestone that clears the anchor bar."""
    ks = [k for k in THRESHOLDS if anchor_ok(c, k)]
    return max(ks) if ks else None


# ---------- DraftKings prices ----------

def month_key(now):
    return now.strftime("%Y-%m")


def dk_prices(games_wanted, day, now, state, abbrevs, spend=True):
    """{(team, opp): {"seen": iso, "lines": {player_key: {k: price}}}} for games DK has posted.
    Reuses today's saved prices; spends at most 1 credit per newly posted game."""
    store = state.setdefault("dk", {})
    if store.get("date") != day.isoformat():
        store.clear()
        store["date"] = day.isoformat()
        store["games"] = {}
    have = store["games"]
    todo = [g for g in games_wanted if "|".join(g) not in have]
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
            have["|".join(g)] = {"seen": now.strftime("%H:%M"),
                                 "by_key": {name_key(n): v for n, v in lines.items()},
                                 "by_last": {}}
            by_last = {}
            for n, v in lines.items():
                by_last.setdefault(last_key(n), []).append(v)
            have["|".join(g)]["by_last"] = {k: v[0] for k, v in by_last.items() if len(v) == 1}
    return have, note


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
    leaky = {ab for ab, _, _ in ranking[:LEAKY_TEAMS]}
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
    return {"date": day.isoformat(), "abbrevs": abbrevs, "ranking": ranking[:LEAKY_TEAMS],
            "matchups": matchups, "cands": cands}


def select(rs, day, now, state, spend=True):
    """Shortlist, price the shortlisted games at DK, and pick anchors / plus-money / ticket."""
    cands = [c for c in rs["cands"] if not c["missed"]]
    abbrevs, matchups = rs["abbrevs"], rs["matchups"]
    # Shortlist before pricing, so credits only go to games that matter.
    anchors = [dict(c, k=anchor_leg(c)) for c in cands if anchor_leg(c)]
    anchors.sort(key=lambda c: (record(c, c["k"]), c["probs"][str(c["k"])]), reverse=True)
    plus_pool = []
    for c in cands:
        k = max(3, (anchor_leg(c) or 2) + 1)
        if str(k) in c["probs"] and passes(c, k, PLUS_RECENT_HIT, PLUS_VS_HIT):
            plus_pool.append(dict(c, k=k))
    plus_pool.sort(key=lambda c: (record(c, c["k"]), c["probs"][str(c["k"])]), reverse=True)
    shortlist = anchors[:ANCHORS * 2] + plus_pool[:PLUS_LEGS * 3]
    games_wanted = []
    for c in shortlist:
        g = (c["team"], c["opp"])
        if g not in games_wanted and (g[1], g[0]) not in games_wanted:
            games_wanted.append(g)

    have, note = dk_prices(games_wanted, day, now, state, abbrevs, spend)

    final_anchors = []
    for c in anchors:
        price, seen = dk_price(c, c["k"], have)
        if price is not None and price < MAX_JUICE:
            continue                       # overpriced: not worth a parlay slot
        final_anchors.append(dict(c, price=price, seen=seen, p=c["probs"][str(c["k"])]))
        if len(final_anchors) == ANCHORS:
            break
    final_plus = []
    for c in plus_pool:
        price, seen = dk_price(c, c["k"], have)
        p = c["probs"][str(c["k"])]
        if price is not None and price >= 100 and p - implied(price) >= PLUS_EDGE:
            final_plus.append(dict(c, price=price, seen=seen, p=p))
    final_plus = final_plus[:PLUS_LEGS]

    unpriced = [g for g in games_wanted if "|".join(g) not in have and "|".join(g[::-1]) not in have]
    return {"ranking": rs["ranking"], "matchups": matchups,
            "anchors": final_anchors, "plus": final_plus, "unpriced": unpriced,
            "note": note, "ticket": build_ticket(final_anchors)}


def build_ticket(anchors):
    """Stack the best-value anchors until the ticket pays about +200: max 4 legs, 2 per game."""
    def value(a):
        return a["p"] - implied(a["price"]) if a["price"] is not None else -1 + a["p"]
    legs, dec, prob, per_game = [], 1.0, 1.0, {}
    for a in sorted(anchors, key=value, reverse=True):
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
    title = (f"SOG hit list · DK prices update · {day.strftime('%a %b %-d')}" if followup
             else f"SOG hit list · {day.strftime('%a %b %-d')}")
    out = []
    if not res["matchups"]:
        return title, "None of tonight's games are against a leaky defense."
    if not res["anchors"] and not res["plus"]:
        out.append("No consistent mid-tier shooters clear the bar tonight.")
    def leg_line(a, prefix):
        r_hits, v_hits = a["detail"][str(a["k"])]
        if a["price"] is None:
            price = "DK not up"
        else:
            price = f"DK {fmt_price(a['price'])}" + (" ✓" if a["p"] > implied(a["price"]) + 0.03 else "")
        return (f"{prefix}{a['name']} ({a['team']}) {a['k']}+ vs {a['opp']} · (f {to_american(a['p'])}) · "
                f"{price} · L{a['r_n']} {r_hits}/{a['r_n']} · vs {a['opp']} {a['k']}+ in {v_hits}/{a['v_n']}")

    if res["anchors"]:
        out.append("ANCHORS")
        out += [leg_line(a, f"{i}. ") for i, a in enumerate(res["anchors"], 1)]
    if res["plus"]:
        out.append("\nPLUS-MONEY SHOOTERS")
        out += [leg_line(p, "") for p in res["plus"]]
    elif res["anchors"]:
        out.append("\nPLUS-MONEY SHOOTERS: none tonight")
    t = res["ticket"]
    if t:
        names = ", ".join(f"{a['name'].split()[-1]} {a['k']}+" for a in t["legs"])
        price = f"DK ≈ {dec_to_american(t['dec'])} · " if t["priced"] else ""
        out.append(f"\nTICKET: {names} → {price}hits {t['prob']:.0%} on history")
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
    for section, legs in (("anchor", res["anchors"]), ("plus", res["plus"])):
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
    graded = [r for r in pending if r.get("result")]
    if not graded:
        return None

    lines = ["Yesterday:"]
    for r in graded:
        mark = {"W": "✅", "L": "❌"}.get(r["result"], "void")
        tag = " (plus)" if r["section"] == "plus" else ""
        shots = r["actual_sog"] if r["actual_sog"] != "" else "-"
        lines.append(f"{mark} {r['player']} {r['leg']}+{tag}: {shots}")
    for d in sorted({r["date"] for r in graded}):
        legs = [r for r in rows if r["date"] == d and r["in_ticket"] == "Y"]
        if legs and all(r.get("result") for r in legs):
            res = [r["result"] for r in legs if r["result"] != "VOID"]
            if res:
                lines.append("Ticket " + ("✅ hit" if all(x == "W" for x in res) else "❌ missed"))
    return "\n".join(lines) + "\n" + season_line(load_log())


def season_line(rows):
    a = [r for r in rows if r["section"] == "anchor" and r.get("result") in ("W", "L")]
    p = [r for r in rows if r["section"] == "plus" and r.get("result") in ("W", "L")]
    parts = []
    if a:
        parts.append(f"anchors {sum(r['result'] == 'W' for r in a)}/{len(a)}")
    if p:
        u = sum(float(r["units"] or 0) for r in p)
        parts.append(f"plus-money {sum(r['result'] == 'W' for r in p)}-{sum(r['result'] == 'L' for r in p)} {u:+.1f}u")
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


def check_players(names, day, now, state):
    rs = state.get("today") if (state.get("today") or {}).get("date") == day.isoformat() else None
    rs = rs or research(day, state)
    res = select(rs, day, now, state, spend=False)
    listed = {}
    for i, a in enumerate(res["anchors"], 1):
        listed[a["pid"]] = f"anchor #{i}: {a['k']}+ at {a['p']:.0%}" + (f", DK {fmt_price(a['price'])}" if a["price"] is not None else "")
    for p in res["plus"]:
        listed.setdefault(p["pid"], f"plus-money: {p['k']}+ at DK {fmt_price(p['price'])}, hits {p['p']:.0%}")
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
        facts = (f"{rate:.1f} shots/gm · {fmt_toi(role['toi'])} TOI {pos}#{role['rank']}"
                 + (" PP1" if role["pp1"] else "") + f" · vs {opp} (#{sa_rank.get(opp, '?')} in shots allowed)")
        if c:
            facts += "\n   " + " · ".join(
                f"{k}+: L{c['r_n']} {c['detail'][str(k)][0]}/{c['r_n']}, vs {opp} {c['detail'][str(k)][1]}/{c['v_n']}"
                for k in (2, 3))
        if pid in listed:
            out.append(f"✅ {name} ({team}) on the list, {listed[pid]}\n   {facts}")
            continue
        top_n = TOP_FORWARDS if pos == "F" else TOP_D
        if pos == "F" and role["pp1"]:
            top_n = PP1_TOP_FORWARDS
        if sa_rank.get(opp, 99) > LEAKY_TEAMS:
            why = f"{opp} isn't a top-{LEAKY_TEAMS} leaky defense"
        elif not role["top"]:
            why = f"not top {top_n} {pos} on {team} in ice time"
        elif REQUIRE_PP1 and not role["pp1"]:
            why = "not on PP1"
        elif not (MIN_RATE <= rate <= MAX_RATE):
            why = (f"{rate:.1f} shots/gm is above the {MAX_RATE:g} cap (priced like a star)" if rate > MAX_RATE
                   else f"{rate:.1f} shots/gm is under the {MIN_RATE:g} floor")
        elif not c:
            why = "not enough recent games to judge"
        elif c.get("missed"):
            why = "missed his team's last game"
        elif not anchor_leg(c):
            r2, v2 = c["detail"]["2"]
            if c["v_n"] < VS_MIN_GAMES:
                why = f"only {c['v_n']} game(s) vs {opp}; needs {VS_MIN_GAMES}+ to count"
            elif v2 / c["v_n"] < VS_HIT and r2 / c["r_n"] >= HOT_RECENT:
                why = f"2+ in {v2}/{c['v_n']} vs {opp}, under even the hot-hand {HOT_VS:.0%} bar"
            elif v2 / c["v_n"] < VS_HIT:
                why = (f"2+ in {v2}/{c['v_n']} vs {opp}, under the {VS_HIT:.0%} bar "
                       f"(or {HOT_VS:.0%} with 18/20+ recently; he's {r2}/{c['r_n']})")
            else:
                why = f"2+ in {r2}/{c['r_n']} of his last {c['r_n']}, under the {RECENT_HIT:.0%} bar"
        else:
            k = anchor_leg(c)
            price, _ = dk_price(c, k, state.get("dk", {}).get("games", {}))
            why = (f"DK {fmt_price(price)} on {k}+ is shorter than {MAX_JUICE}" if price is not None and price < MAX_JUICE
                   else f"qualified ({k}+ at {c['probs'][str(k)]:.0%}) but ranked below the top {ANCHORS}")
        out.append(f"❌ {name} ({team}): {why}\n   {facts}")
    return f"SOG check · {day.strftime('%a %b %-d')}", "\n".join(out)


# ---------- main ----------

def credits_line(state, now):
    """'Credits: 452 left' (shared with the saves bot). Listing events is free and reports the balance."""
    if not ODDS_API_KEY:
        return ""
    _, left = odds_get(f"/sports/{SPORT}/events", {})
    return f"Credits: {left} left" if left is not None else ""


def priced_count(state):
    return len(state.get("dk", {}).get("games", {}))


def main():
    now = datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    day = now.date()
    state = load_state()
    sent_today = state.get("last_sent") == day.isoformat()

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
        line = credits_line(state, now)
        body += f"\n\n{line}" if line else ""
        send_push(title, body)
        if res["matchups"]:
            log_today(day, res)
        state["last_sent"] = day.isoformat()
        waiting = bool(res["unpriced"]) and not res["note"] and bool(ODDS_API_KEY)
        state["followup"] = {"base": priced_count(state)} if waiting else None
        print("Sent morning list.")
    elif sent_today and state.get("followup") and now.hour < FOLLOWUP_UNTIL:
        # Checks on unposted games are free; send one update once prices arrive
        # (all of them, or whatever has posted by the last hour of the window).
        rs = state.get("today") if (state.get("today") or {}).get("date") == day.isoformat() else None
        res = select(rs or research(day, state), day, now, state)
        gained = priced_count(state) > state["followup"]["base"]
        if gained and (not res["unpriced"] or res["note"] or now.hour >= FOLLOWUP_UNTIL - 1):
            title, body = format_list(day, res, followup=True)
            line = credits_line(state, now)
            body += f"\n\n{line}" if line else ""
            send_push(title, body)
            log_today(day, res)
            state["followup"] = None
            print("Sent DK prices follow-up.")
        else:
            print(f"Waiting on DK for {len(res['unpriced'])} game(s).")
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
