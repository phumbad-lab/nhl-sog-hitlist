"""Backtest of the 3+ (and 2+) shots picks over real game logs. Run by the "Backtest" workflow.

For every regular-season game of every regular shooter (2025-26 and 2026-27 so far), it rebuilds
what the bot would have known that morning (last 20 games, history vs that opponent, shot rate)
and the same estimated chance the bot uses, then checks what actually happened.
No odds are used ("regardless of price"). Writes backtest_results.txt.
"""
import json
import sys
import time
import urllib.error
from collections import defaultdict

import sog_hitlist as m

SEASONS = ["20242025", "20252026", "20262027"]   # the first only seeds history
EVAL = {"20252026", "20262027"}
MIN_SHOTS_PER_GAME = 2.0
MIN_GP = 30
WINDOW = 20
SPLIT = "2026-01-15"

out_lines = []


def say(s=""):
    print(s)
    out_lines.append(s)


def get(url, tries=3):
    for i in range(tries):
        try:
            return m.nhl_get(url)
        except Exception:
            time.sleep(1 + i)
    return {}


def pool():
    ids = {}
    for season in ("20252026", "20262027"):
        try:
            rows = m.stats_rows("skater/summary", season)
        except Exception as e:
            say(f"(couldn't read {season} skater list: {e})")
            rows = []
        for r in rows:
            gp, sh = r.get("gamesPlayed") or 0, r.get("shots") or 0
            need_gp = MIN_GP if season == "20252026" else 5
            if gp >= need_gp and sh / gp >= MIN_SHOTS_PER_GAME:
                ids[str(r["playerId"])] = r.get("skaterFullName", "")
    return ids


def games(pid):
    allg = []
    for season in SEASONS:
        data = get(f"{m.NHL_WEB}/player/{pid}/game-log/{season}/2")
        for g in data.get("gameLog", []):
            allg.append((g["gameDate"], season, g.get("opponentAbbrev", ""), g.get("shots") or 0,
                         g.get("homeRoadFlag", "")))
        time.sleep(0.05)
    return sorted(allg)


def streak(hist, k):
    n = 0
    for s in reversed(hist):
        if s < k:
            break
        n += 1
    return n


def main():
    ids = pool()
    say(f"Players: {len(ids)} regular shooters ({MIN_SHOTS_PER_GAME}+ shots a game)")
    rows = []
    for n, (pid, name) in enumerate(ids.items(), 1):
        g = games(pid)
        if n % 25 == 0:
            print(f"  fetched {n}/{len(ids)}", file=sys.stderr)
        for i in range(WINDOW, len(g)):
            date, season, opp, shots, ha = g[i]
            if season not in EVAL:
                continue
            prior = g[:i]
            hist = [x[3] for x in prior]
            last20 = hist[-WINDOW:]
            rate = sum(hist[-40:]) / len(hist[-40:])
            vs = [x[3] for x in prior if x[2] == opp]
            rec = {"pid": pid, "name": name, "date": date, "season": season, "opp": opp, "home": ha == "H",
                   "shots": shots, "rate": rate, "last": hist[-1], "vs_n": len(vs)}
            for k in (2, 3):
                r_hits = sum(s >= k for s in last20)
                v_hits = sum(s >= k for s in vs)
                p0 = m.chance_at_least(rate, k)
                rec[f"r{k}"] = r_hits
                rec[f"v{k}"] = v_hits
                rec[f"s{k}"] = streak(hist, k)
                rec[f"p{k}"] = (r_hits + v_hits + p0 * m.SHRINK_GAMES) / (WINDOW + len(vs) + m.SHRINK_GAMES)
                rec[f"hit{k}"] = shots >= k
            rows.append(rec)
    say(f"Player-games evaluated: {len(rows)}")
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)
    days = len(by_date)
    say(f"Game days: {days}")

    def rate_of(sel, k):
        return (sum(r[f"hit{k}"] for r in sel), len(sel))

    def fmt(h, n):
        return f"{h}/{n} = {h / n:.1%}" if n else "none"

    for k in (3, 2):
        say("")
        say(f"===== {k}+ SHOTS =====")
        say("Model's chance vs what actually happened:")
        edges = [0, .5, .6, .65, .7, .75, .8, .85, .9, 1.01]
        for lo, hi in zip(edges, edges[1:]):
            sel = [r for r in rows if lo <= r[f"p{k}"] < hi]
            h, n = rate_of(sel, k)
            if n:
                say(f"  model {lo:.0%}-{min(hi, 1):.0%}: {fmt(h, n)}")
        say("Top picks each game day (ranked by model chance):")
        for top in (1, 3, 5):
            sel = [r for d in by_date.values() for r in sorted(d, key=lambda r: -r[f"p{k}"])[:top]]
            say(f"  top {top}: {fmt(*rate_of(sel, k))}")

        # Choose filters on the first half of 2025-26, then check them on games they never saw
        # (Jan 15 onward plus this season), so a lucky combination can't fool us.
        train = [r for r in rows if r["date"] < SPLIT]
        test = [r for r in rows if r["date"] >= SPLIT]
        tdays = len({r["date"] for r in test}) or 1
        say(f"Filters for {k}+: chosen on games before {SPLIT}, checked on {SPLIT} onward")
        found = []
        for rmin in range(12, 21):
            for ratemin in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5):
                for vsmin, vsn in ((0, 0), (.6, 4), (.8, 4), (1.0, 4)):
                    for smin in (0, 1, 3):
                        for home in (None, True):
                            def ok(r):
                                return (r[f"r{k}"] >= rmin and r["rate"] >= ratemin and r[f"s{k}"] >= smin
                                        and (home is None or r["home"])
                                        and (vsn == 0 or (r["vs_n"] >= vsn and r[f"v{k}"] / r["vs_n"] >= vsmin)))
                            h, n = rate_of([r for r in train if ok(r)], k)
                            if n >= 40:
                                found.append((h / n, n, rmin, ratemin, vsmin, smin, home, ok))
        found.sort(key=lambda f: (-f[0], -f[1]))
        def desc(rmin, ratemin, vsmin, smin, home):
            return (f"L20 {k}+ >= {rmin}/20, {ratemin}+ shots/gm"
                    + (f", vs opp {k}+ >= {vsmin:.0%} (4+ games)" if vsmin else "")
                    + (f", {k}+ streak >= {smin}" if smin else "") + (", home only" if home else ""))
        say("  Best 12 on the first half -> how they did afterwards:")
        for hr, n, rmin, ratemin, vsmin, smin, home, ok in found[:12]:
            th, tn = rate_of([r for r in test if ok(r)], k)
            say(f"  first half {hr:.1%} of {n} -> after {fmt(th, tn)} ({tn / tdays:.2f} a day): "
                + desc(rmin, ratemin, vsmin, smin, home))
        big90 = sorted([f for f in found if f[0] >= .90], key=lambda f: -f[1])[:5]
        say(f"  Widest filters at 90%+ on the first half ({len([f for f in found if f[0] >= .90])} reach it):")
        for hr, n, rmin, ratemin, vsmin, smin, home, ok in big90:
            th, tn = rate_of([r for r in test if ok(r)], k)
            say(f"  first half {hr:.1%} of {n} -> after {fmt(th, tn)} ({tn / tdays:.2f} a day): "
                + desc(rmin, ratemin, vsmin, smin, home))

        # The single most likely player each day, at different floors.
        say(f"Likeliest {k}+ player each day, only when his chance is at least:")
        for floor in (.6, .7, .75, .8, .85):
            sel = []
            for d in by_date.values():
                best = max(d, key=lambda r: r[f"p{k}"])
                if best[f"p{k}"] >= floor:
                    sel.append(best)
            h, n = rate_of(sel, k)
            say(f"  {floor:.0%}: {fmt(h, n)} ({n} of {days} days)")

    with open("backtest_results.txt", "w") as f:
        f.write("\n".join(out_lines) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        say("CRASHED:\n" + traceback.format_exc())
        with open("backtest_results.txt", "w") as f:
            f.write("\n".join(out_lines) + "\n")
        raise
