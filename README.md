# NHL SOG hit list

One Telegram message at 7:05 AM Eastern (five minutes after the saves alert) with tonight's best shots-on-goal legs and DraftKings prices. It targets consistent middle-of-the-pack shooters, not the stars whose milestones are overpriced. It gives you:

- **Anchors:** short-priced 2+/3+ legs to parlay
- **Plus-money shooters:** 3+ legs worth a straight bet
- **Ticket:** 3–4 anchors that add up to roughly +200 to +350

```
SOG hit list · Thu Oct 8
ANCHORS
1. Clayton Keller (UTA) 2+ vs BOS · (f -475) · DK -275 ✓ · L20 17/20 · vs BOS 2+ in 6/6
2. Cale Makar (COL) 2+ vs CGY · (f -413) · DK -360 · L20 17/20 · vs CGY 2+ in 7/8
3. Nikolaj Ehlers (CAR) 2+ vs VAN · (f -330) · DK -250 ✓ · L20 16/20 · vs VAN 2+ in 7/8

PLUS-MONEY SHOOTERS: none tonight

TICKET: Keller 2+, Ehlers 2+, Makar 2+ → DK ≈ +144 · hits 51% on history

Yesterday:
✅ Clayton Keller 2+: 3
❌ Cale Makar 2+: 1
Ticket ❌ missed
Season: anchors 14/17 · plus-money 3-2 +1.4u · tickets 2/4

Credits: 452 left
```

## How players are picked
1. **Leaky defenses:** teams are ranked by shots allowed per game. Tonight's games against the top 12 are in play, usually about half the slate.
2. **Top-two lines:** on the other side of those games, only players in their team's **top 6 forwards or top 4 defensemen by ice time** are considered (lines 1–2 and pairs 1–2). Ice time leans on this season and switches over after about 5 games, so line changes show up quickly.
3. **Mid-tier shooters:** of those, it keeps skaters averaging **1.8 to 3.6 shots a game**. Stars above 3.6 are left out because their 2+ and 3+ are priced too short. Anyone who missed his team's last game (injury or scratch) is dropped.
4. **Power play:** **PP1** is shown for the team's top 5 skaters in power-play time with 1:00+ a game. Set `REQUIRE_PP1` to `true` to list only PP1 players.
5. **Hit rate:** for 2+, 3+, 4+ and 5+, it counts how often he got there in his **last 20 games** and in **every game vs tonight's opponent** (this season plus the last 3). Those are combined, then blended with what a typical shooter at his shot rate would do. A lucky 20/20 streak reads as ~90%, not a sure thing, while genuine consistency still stands out.
6. **Anchors:** the biggest milestone he's hit in **80%+ of his last 20 games** (16/20 or better) **and 85%+ of his games vs tonight's opponent, with at least 4 of them** (4/4, 6/6, 6/7, 7/8...). A 1/2 or 2/4 history doesn't count. Legs DK prices shorter than **-400** are dropped as not worth a parlay slot.
7. **Plus-money shooters:** 3+ (or one above his anchor) that he's hit in **65%+ of his last 20** and **80%+ of 4+ games vs the opponent**, listed only when DK pays plus money and the estimate beats DK's price by 5+ points. Many nights this section is empty.
8. **Ticket:** the best-value anchors stacked until the price reaches about +200, with at most 4 legs and at most 2 from one game.

**Reading a line:** `(f -475) · DK -275 ✓` means the fair price is -475 and DK is only asking -275; ✓ marks DK's price as better than fair (`DK not up` if DK hasn't posted yet). The fair price comes from his record (here 17/20 recently and 6/6 vs BOS, 23/26 combined) pulled slightly toward what a typical shooter at his rate does, since hot streaks cool off. That works out to about an 83% chance, worth -475.

**Early season:** shots allowed and shot rates are blended with last season until about 10 games in (`BLEND_GAMES`).

## Checking your own picks
**Actions › SOG hit list › Run workflow**, type names in **check** (e.g. `Stutzle, Batherson`), and run. You get a message saying whether each player made today's list, and if not, which rule left him out:

```
SOG check · Thu Oct 8
✅ Nick Schmaltz (UTA) on the list, anchor #5: 2+ at 79%, DK -210
   2.4 shots/gm · 19:05 TOI F#3 PP1 · vs CHI (#2 in shots allowed) · 2+ 79% · 3+ 50% · 4+ 15%
❌ Cutter Gauthier (ANA): 4.2 shots/gm is above the 3.6 cap (priced like a star)
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

| Variable | What it does | Default |
|---|---|---|
| `SEND_HOUR` / `SEND_MINUTE` | Send at or after this time, Eastern | `7` / `5` |
| `FOLLOWUP_UNTIL` | Last hour for the DK-prices follow-up | `12` |
| `LEAKY_TEAMS` | Top shots-allowed teams whose opponents are in play | `12` |
| `MIN_RATE` / `MAX_RATE` | Shots-per-game band for shooters | `1.8` / `3.6` |
| `RECENT_HIT` / `VS_HIT` | Anchor bars: last-20 % and vs-opponent % | `80` / `85` |
| `VS_MIN_GAMES` | Games vs the opponent needed before that record counts | `4` |
| `PLUS_RECENT_HIT` / `PLUS_VS_HIT` | Plus-money bars at 3+ | `65` / `80` |
| `MAX_JUICE` | Drop anchors DK prices shorter than this | `-400` |
| `PLUS_EDGE` | Points a plus-money leg's estimate must beat DK's price by | `5` |
| `ANCHORS` / `PLUS_LEGS` | How many of each to list | `6` / `3` |
| `ODDS_MONTHLY_CAP` | Most odds credits per month | `75` |
| `ODDS_RESERVE` | Never spend at or below this many credits left | `200` |
| `TOP_FORWARDS` / `TOP_D` | Ice-time rank cutoffs (lines 1–2, pairs 1–2) | `6` / `4` |
| `REQUIRE_PP1` | `true` = only first power-play unit players | `false` |
| `BLEND_GAMES` | Early-season blending with last season (`0` = off) | `10` |
| `TELEGRAM_SILENT` | `true` = no sound | `true` |

## Log
`hitlist.csv` has every listed leg: section (anchor / plus), player, opponent, milestone, hit %, fair price, DK price, when DK posted it, and whether it was on the ticket. It's graded the next morning from NHL game logs, with units at the DK price. A player who didn't play is voided and dropped from the ticket, as DK does.

## Good to know
- Hit rates are history, not guarantees. Teammates' legs tend to hit or miss together, so a ticket with two legs from one team is riskier than its % suggests.
- The ticket price multiplies separate legs. If you build it as a DK SGP, same-game legs are priced differently.
- On a night with no games against a leaky defense, you get a one-line message.
