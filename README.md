# NHL SOG hit list

One Telegram message at 7:05 AM Eastern (five minutes after the saves alert) with tonight's best shots-on-goal legs and DraftKings prices. It targets consistent middle-of-the-pack shooters, not the stars whose milestones are overpriced. It gives you:

- **Anchors:** short-priced 2+/3+ legs to parlay
- **3+ shooters:** 3+ legs at -110 or better, worth a straight bet
- **Ticket:** 3–4 anchors that add up to roughly +200 to +350

```
SOG hit list · Thu Oct 8
ANCHORS
1. Clayton Keller (UTA) 2+ vs BOS · (f -475) · DK -275 ✓ · L20 17/20 · vs BOS 2+ in 6/6
2. Cale Makar (COL) 2+ vs CGY · (f -413) · DK -360 · L20 17/20 · vs CGY 2+ in 7/8
3. Nikolaj Ehlers (CAR) 2+ vs VAN · (f -330) · DK -250 ✓ · L20 16/20 · vs VAN 2+ in 7/8

3+ SHOOTERS: none tonight

TICKET: Keller 2+, Ehlers 2+, Makar 2+ → DK ≈ +144 · hits 51% on history

Yesterday:
✅ Clayton Keller 2+: 3
❌ Cale Makar 2+: 1
Ticket ❌ missed
Season: anchors 14/17 · 3+ shooters 3-2 +1.4u · tickets 2/4

Credits: 452 left
```

## How players are picked
1. **Opponent:** shooters facing one of the **5 tightest defenses** (fewest shots allowed per game, e.g. Carolina) are skipped. Every other matchup is fair game.
2. **Top-two lines:** only players in their team's **top 6 forwards or top 4 defensemen by ice time** are considered (lines 1–2 and pairs 1–2). A forward on the **first or second power-play unit** also counts if he's in the **top 9**. Ice time leans on this season and switches over after about 5 games.
3. **Mid-tier shooters:** of those, it keeps skaters averaging **1.5 to 5 shots a game**. Stars are allowed; the -375 price limit drops their overpriced legs. Anyone who missed his team's last game (injury or scratch) is dropped.
4. **Power play:** **PP1** is the team's top 5 skaters in power-play time with 1:00+ a game. Set `REQUIRE_PP1` to `true` to list only PP1 players.
5. **Hot hand required:** he must have **2+ shots in each of his last 5 games** (a 0 last game rules him out), and **2+ in 8 of his last 10**.
6. **Head-to-head:** **80%+ of his games vs tonight's opponent, with at least 4 of them** (4/4, 5/6, 6/7...). A 1/2 or 2/4 history doesn't count. **Hot-hand exception:** at **9/10 or better** recently, he only needs **50%+** vs the opponent (still in 4+ games).
7. **Anchors (2+):** 2+ legs that clear all of the above. Legs DK prices shorter than **-375** are dropped. The fair price blends his record with what a typical shooter at his rate does, since hot streaks cool off.
   Each line reads e.g. `L10 9/10 (8 straight)`: 9 of his last 10 games at the milestone, and 8 games in a row at 2+.
8. **3+ shooters:** 3+ legs with **3+ shots in each of his last 5 games**, 3+ in **65%+ of his last 10** and **80%+ of 4+ games vs the opponent**, and a DK price of **-110 or better**. Many nights this section is empty.
9. **Ticket:** the best-value anchors stacked until the price reaches about +200, with at most 4 legs and at most 2 from one game.

**Reading a line:** `(f -475) · DK -275 ✓` means the fair price is -475 and DK is only asking -275; ✓ marks DK's price as better than fair (`DK not up` if DK hasn't posted yet). The fair price comes from his record (here 17/20 recently and 6/6 vs BOS, 23/26 combined) pulled slightly toward what a typical shooter at his rate does, since hot streaks cool off. That works out to about an 83% chance, worth -475.

**Early season:** shots allowed and shot rates are blended with last season until about 10 games in (`BLEND_GAMES`).

## Checking your own picks
**Actions › SOG hit list › Run workflow**, type names in **check** (e.g. `Stutzle, Batherson`), and run. You get a message saying whether each player made today's list, and if not, which rule left him out:

```
SOG check · Thu Oct 8
✅ Nick Schmaltz (UTA) on the list, anchor #5: 2+ at 79%, DK -210
   2.4 shots/gm · 19:05 TOI F#3 PP1 · vs CHI (#2 in shots allowed) · 2+ 79% · 3+ 50% · 4+ 15%
❌ Cutter Gauthier (ANA): 4.2 shots/gm is above the 5 cap (priced like a star)
   4.2 shots/gm · 19:40 TOI F#1 PP1 · vs PHI (#3 in shots allowed) · 2+ 94% · 3+ 82% · 4+ 60%
```

Last names are fine unless two players share one. A check uses no odds credits, and it doesn't change the day's list or log.

## DraftKings prices and credits
- Prices come from DK's milestone market only, and only for games with a shortlisted player. That's 1 credit per game, about 2–5 credits a day.
- **Monthly cap: 75 credits** (`ODDS_MONTHLY_CAP`).
- It never spends when your Odds API account is at **200 credits or less** (`ODDS_RESERVE`), so the saves bot sharing the key keeps its share. If it's capped, the list still goes out with fair prices.
- If DK hasn't posted some games at 7 AM, the list says so. Checking an unposted game is free, so it keeps checking until noon. You get **one** follow-up with prices once they're all up, or with whatever has posted by the last hour.
- `hitlist.csv` records the time DK prices were first seen (`dk_seen_at`). After a week or two you'll know whether 7 AM is early enough or `SEND_HOUR` should move.

## Setup (about 10 minutes)
1. On GitHub, create a **new repository** named `nhl-sog-hitlist`.
2. Upload `sog_hitlist.py` and `README.md` (Add file › Upload files).
3. **Add file › Create new file**, name it `.github/workflows/sog-hitlist.yml`, and paste in the contents of `sog-hitlist.yml`.
4. **Settings › Secrets and variables › Actions › New repository secret**. Add the same three values your saves bot uses:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ODDS_API_KEY`
5. **Actions** tab › **SOG hit list** › **Run workflow**, tick **force**, and run it. The list arrives in a few minutes. The first run is slowest because it pulls three seasons of game logs, which are saved for later days.

Don't upload `state.json` or `hitlist.csv`; the bot creates and updates them.

**Timing:** the bot never sends before 7:05 AM Eastern. A cron-job.org job at 7:05 triggers it on time. GitHub's own schedule is the backup (it often runs late) and handles the DK-prices follow-up.

## Options (Settings › Secrets and variables › Actions › Variables tab)

Add any of these as a repository variable and it takes effect on the next run. The workflow passes every variable through automatically, so it never needs editing to add one.

| Variable | What it does | Default |
|---|---|---|
| `SEND_HOUR` / `SEND_MINUTE` | Send at or after this time, Eastern | `7` / `5` |
| `FOLLOWUP_UNTIL` | Last hour for the DK-prices follow-up | `12` |
| `TIGHT_TEAMS` | Skip shooters facing this many of the stingiest defenses | `5` |
| `LEAKY_TEAMS` | Older setting: only use opponents in the top N for shots allowed (`32` = all) | `32` |
| `RECENT_GAMES` | Window for the recent-form bars ("last N") | `10` |
| `STREAK` | Anchors need 2+ shots in each of their last N games | `5` |
| `MIN_RATE` / `MAX_RATE` | Shots-per-game band for shooters | `1.5` / `5` |
| `RECENT_HIT` / `VS_HIT` | Anchor bars: last-10 % and vs-opponent % | `80` / `80` |
| `VS_MIN_GAMES` | Games vs the opponent needed before that record counts | `4` |
| `PLUS_RECENT_HIT` / `PLUS_VS_HIT` | 3+ section: last-10 % and vs-opponent % | `65` / `80` |
| `PLUS_STREAK` | 3+ section: 3+ shots in each of his last N games | `5` |
| `PLUS_MIN_PRICE` | 3+ section: DK price must be this or better | `-110` |
| `PP_UNITS` | `1` = only PP1 forwards get the top-9 exception, `2` = PP1 or PP2 | `2` |
| `ANCHOR_MAX_K` | Biggest milestone an anchor can be (3+ legs have their own section) | `2` |
| `MAX_JUICE` | Drop anchors DK prices shorter than this | `-375` |
| `PLUS_EDGE` | Points a 3+ leg's estimate must beat DK's price by | `0` |
| `ANCHORS` / `PLUS_LEGS` | How many of each to list | `6` / `3` |
| `ODDS_MONTHLY_CAP` | Most odds credits per month | `75` |
| `ODDS_RESERVE` | Never spend at or below this many credits left | `200` |
| `TOP_FORWARDS` / `TOP_D` | Ice-time rank cutoffs (lines 1–2, pairs 1–2) | `6` / `4` |
| `REQUIRE_PP1` | `true` = only first power-play unit players | `false` |
| `PP1_TOP_FORWARDS` | PP1 forwards also count if this high in team ice time | `9` |
| `HOT_RECENT` / `HOT_VS` | Hot hand: recent % that lowers the vs-opponent bar, and the lower bar | `90` / `50` |
| `BLEND_GAMES` | Early-season blending of player shot rates with last season (`0` = off) | `10` |
| `TEAM_BLEND_GAMES` | Same for team shots allowed, which decides the tightest defenses (`0` = this season only) | `0` |
| `TELEGRAM_SILENT` | `true` = no sound | `true` |

## Log
`hitlist.csv` has every listed leg: section (anchor / plus), player, opponent, milestone, hit %, fair price, DK price, when DK posted it, and whether it was on the ticket. It's graded the next morning from NHL game logs, with units at the DK price. A player who didn't play is voided and dropped from the ticket, as DK does.

## Good to know
- Hit rates are history, not guarantees. Teammates' legs tend to hit or miss together, so a ticket with two legs from one team is riskier than its % suggests.
- The ticket price multiplies separate legs. If you build it as a DK SGP, same-game legs are priced differently.
- On a night with no games against a leaky defense, you get a one-line message.
