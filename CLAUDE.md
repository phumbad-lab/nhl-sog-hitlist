# CLAUDE.md: NHL SOG hit list working notes

Read this first. It's the one place to pick up where we left off. Update it when something changes.

## What this is and how it's used

- A morning Telegram message of NHL **player shots-on-goal** legs to bet, built for the owner (phumbad-lab), who bets SOG props **for fun** on **DraftKings** (and copies picks to FanDuel by hand).
- Style: short-priced **2+ legs** (about -150 to -400) parlayed into a **+200 to +350** ticket; the occasional plus-money **3+** straight.
- Real bets are tracked in **Pikkit**, not here. `hitlist.csv` only records what the bot listed and how those legs did.
- Companion project: **`phumbad-lab/nhl-saves-alerts`** (goalie saves alerts). It has its own CLAUDE.md and shares the Odds API key and the Telegram bot (see the hard rule below).

## Hard rule: never read the shared Telegram bot

Two bots are involved:
- **Shared bot** (`TELEGRAM_BOT_TOKEN`): the saves app's bot. **The saves app reads replies to it** (`getUpdates`, offset in its `state.json` as `tg_offset`) so the owner can log bets by replying "in". This app may only *send* with it, and only as a fallback.
- **Sol Shoty** (`SOG_BOT_TOKEN`, `t.me/Solshotey_bot`, created Oct 11): this app's own bot. The list is sent from it when the secret is set, and text replies read **only** from it.

Rules:
- Never call `getUpdates`, set a webhook or read replies with `TELEGRAM_BOT_TOKEN`. Two readers steal each other's messages.
- `telegram_api()` / `answer_texts()` use `SOG_BOT_TOKEN` only, and refuse to run without it (zero Telegram calls). Tested Oct 11 with recorded requests: the shared token is never used.
- History: replies were first built on the shared bot (Oct 11), removed within the hour because of this conflict (they never processed a message), then restored the same evening on Sol Shoty.
- `TELEGRAM_CHAT_ID` is the same for both bots (it's the owner's private chat ID).

## Working agreement (owner's preferences)

- **No rules built on hunches.** Model changes get tested against results or history first (backtest, the Season line, or past graded legs). The owner approves before they ship. Show the evidence and the trade-off, then ask.
- Don't change several rules at once; one at a time so the Season line can show what helped.
- Explain things plainly (the owner isn't a programmer). Give click-by-click steps for GitHub and cron-job.org.
- Claude can push code to this repo directly (Claude GitHub App installed on all the owner's repos, Oct 11). Claude **cannot** edit repo Variables (GitHub Actions API is blocked from Claude's sandbox). To change a setting, either the owner edits the Variable, or Claude changes the built-in default in code (only takes effect if that Variable isn't set).
- Claude can't delete branches from its sandbox. Ask the owner if one needs removing.

## How it runs

- **Workflow:** `.github/workflows/sog-hitlist.yml` ("SOG hit list").
  - **cron-job.org** POSTs a `workflow_dispatch` at **7:05 AM ET daily**: `https://api.github.com/repos/phumbad-lab/nhl-sog-hitlist/actions/workflows/sog-hitlist.yml/dispatches`, body `{"ref":"main"}`, fine-grained GitHub token with Actions read/write. That's the main trigger. The job was found **disabled** on Oct 9 and enabled.
  - **GitHub schedule** `*/30 10-17 * * *` (UTC), about 6 AM to 1 PM ET, is only a backup. It often runs late.
  - The script sends **one list per day**, never before `SEND_HOUR:SEND_MINUTE` (7:05). It sends at most **one follow-up** if DK posts more of the needed games later, until `FOLLOWUP_UNTIL` (noon). Other runs exit in seconds.
- **Manual run inputs** (Actions › SOG hit list › Run workflow):
  - `force`: send today's list again even though it was already sent. **Don't force after games have started or finished**; it replaces the day's list and log, and tomorrow grades the replacement.
  - `check`: player names (e.g. `Stutzle, Batherson`) → message saying whether each made today's list and which rule cut him. `settings` → message listing every effective setting (`*` = set as a Variable) plus warnings about unreadable values. Neither changes the list, the log or credits.
  - Use **Run workflow**, not **Re-run jobs** (a re-run repeats the old run's inputs).
- **Secrets:** `SOG_BOT_TOKEN` (Sol Shoty, this app's own bot; sends the list and handles replies), `TELEGRAM_BOT_TOKEN` (shared saves bot; send-only fallback, never read), `TELEGRAM_CHAT_ID` (owner's chat, same for both bots), `ODDS_API_KEY` (shared with saves; replaced Oct 10 after the plan upgrade).
- **Text replies:** workflow `.github/workflows/sog-replies.yml` ("SOG replies") runs `sog_hitlist.py` with `REPLY=true`. It answers texts to Sol Shoty: last names (comma-separated), `settings`, `help`, and **team + number** (`FLA 3`, `BUF 2`; Oct 12): the top 6 players in that team's game today ranked by chance of that many shots, with DK price, L20 and vs-opponent record. Uses the morning research and saved DK prices (no credits); top-line players only (role + 1.5–5 shots filters). Triggered by cron-job.org every 2 minutes (8 AM–11 PM) plus a GitHub schedule backup every 10 minutes (8 AM to midnight ET). It never changes `state.json` or `hitlist.csv`; it only commits `telegram_offset.txt`.
- **Variables:** the workflow passes every repo Variable as JSON (`ALL_VARS: ${{ toJSON(vars) }}`), so new settings need no workflow edit. Numeric values are parsed leniently (`1,500`, `10%`, `+100`); a value that still isn't a number falls back to the default and shows a ⚠️ line in messages instead of crashing.
- **Files the bot maintains, never edit or upload by hand:** `state.json` (caches, today's research, DK prices, credit usage, last_sent), `hitlist.csv` (every listed leg and its grade) and `telegram_offset.txt` (last Sol Shoty message answered). The workflow commits them with `git pull --rebase` first.
- **Files people edit:** `sog_hitlist.py`, `README.md`, `.github/workflows/sog-hitlist.yml`, `.github/workflows/sog-replies.yml`, `CLAUDE.md`.
- Data sources: NHL free APIs (`api.nhle.com/stats/rest/en/...` for skater/team summaries and time on ice; `api-web.nhle.com/v1/...` for rosters, schedule, game logs, box scores). Odds: The Odds API, DraftKings only.

## Current Variables (set in the repo, as of Oct 11)

| Variable | Value | Note |
|---|---|---|
| `ANCHORS` | 8 | caps anchors at 8. Since Oct 12 the default is 0 (every anchor); owner asked to delete this Variable |
| `ODDS_MONTHLY_CAP` | 1500 | raised for the 20k plan (default 75) |
| `RECENT_GAMES` | 20 | last-20 window (default 10) |
| `RECENT_HIT` | 80 | 16/20 (same as default) |
| `STREAK` | 1 | must have had 2+ last game (default 5) |
| `VS_HIT` | 80 | same as default now |
| `LEAKY_TEAMS` | 32 | leftover from the old leaky-defense rule; harmless (32 = all teams) |

Run a `settings` check to see the live values.

## The model as it works today (and why)

For each of tonight's games, every skater on both rosters goes through these steps:

1. **Opponent:** all opponents are in play (`TIGHT_TEAMS` 0). The owner dodges truly tight defenses himself. History: started as "top 5 leakiest defenses", widened to 12, then 20, then flipped to "skip 5 tightest", then removed on Oct 10. Buffalo's league-low shots allowed came from 4 games against weak shooting teams, and Schmaltz and Guenther both hit at Buffalo that night.
2. **Role:** top 6 forwards or top 4 D by ice time (`TOP_FORWARDS` 6, `TOP_D` 4). A forward on **PP1 or PP2** also counts if he's top 9 (`PP_UNITS` 2, `PP1_TOP_FORWARDS` 9). PP1 is the team's top 5 in PP time with 1:00+ a game; PP2 is the next 5 with 0:30+. Ice time blends last season with this season, switching over after about 5 games (`ROLE_BLEND_GAMES`). Why: the owner wants line 1–2 / power-play opportunity, and the PP exception came from players like McMann.
3. **Shot rate:** 1.5 to 5 shots per game (`MIN_RATE`, `MAX_RATE`), blended with last season until about 10 games in (`BLEND_GAMES` 10). Stars are allowed; the price limit drops overpriced legs.
4. **Missed his team's last game** → dropped (injury or scratch).
5. **Recent form:** 2+ in at least `RECENT_HIT` of the last `RECENT_GAMES` (16 of 20), **and** a current 2+ streak of at least `STREAK` games (1 = had 2+ last game). Why: on Oct 10 we backtested 15 regular shooters over about 1,100 games from 2025-26. Next-game 2+ was about 71% whatever the streak length (8+ streaks: 62%), while 16+/20 gave 77% and 18+/20 gave 80%. The earlier rules (5-game streak, 8 of 10) shrank the pool without improving hit rate.
6. **Head-to-head:** 2+ in at least `VS_HIT` (80%) of at least `VS_MIN_GAMES` (4) games against tonight's opponent, this season plus the last 3. **Hot-hand exception:** at `HOT_RECENT` 90%+ recently (18/20), head-to-head only needs `HOT_VS` 50%. Why: the owner rejected 1/2 and 2/4 histories (Schaefer, Palmieri); the exception came from McMann (19/20 recently, 2/4 vs DET).
7. **Anchors (2+ only, `ANCHOR_MAX_K` 2):**
   - Estimated chance = (hits + prior × 15) / (games + 15). The prior is a negative binomial at his shot rate (`SHRINK_GAMES` 15, `DISPERSION` 0.25), so hot streaks are pulled toward normal. The fair price comes from that estimate.
   - Anchor = DK price `MAX_JUICE` (-400) or better. **Code default -400** since Oct 11 (was -375; Ovechkin at -390 prompted the change).
   - **Additional targets** (Oct 12, owner's design): qualifiers priced -401 to `TARGET_MAX_JUICE` (-600), or with no DK line / game not posted yet, shown on one line as names + price, ranked by chance of hitting. Shorter than -600 is hidden. Owner builds his own tickets and uses targets rarely; they're logged as section `target` and graded quietly, but **never shown in Yesterday or the RECORD** (record is anchors only, plus fun bets / 3+). Every qualifier's game is now priced (about 1 credit per game). Saturday Oct 10 replay: anchors 8/11, targets 6/6, no-line 2/3.
   - **Ranked by chance of hitting**; every anchor shown (`ANCHORS` 0 = no cap). ✓ means the estimate beats DK's implied chance by 3+ points.
8. **3+ section: OFF since Oct 12** (owner's call; `PLUS_LEGS` default 0). It overlapped the fun bet and never fired under these rules (its only picks, Hertl W and Landeskog L on Oct 8, came from the older plus-money version). Not shown in the list or the RECORD; code kept, `PLUS_LEGS` 3 turns it back on. Its rules were: 3+ legs with **3+ in each of the last 5 games** (`PLUS_STREAK` 5), 3+ in 65%+ of recent games (`PLUS_RECENT_HIT`), 80%+ against the opponent in 4+ games (`PLUS_VS_HIT`), and DK price **-110 or better** (`PLUS_MIN_PRICE`). `PLUS_EDGE` is 0. Up to `PLUS_LEGS` 3. Usually empty, and that's accepted. Side effect: a strong 3+ priced at -150 appears nowhere.
9. **Fun bet:** one plus-money (`FUN_MIN_PRICE` +100) 3+ leg (`FUN_K`) with 3+ in 60%+ of recent games (`FUN_RECENT_HIT`; 12/20 with the 20-game window) and 2+ in his last game (`FUN_STREAK` 1; was 3 until Oct 12. Backtest of the 15 shooters' 2025-26 logs, games where he was 12/20+ at 3+: next-game 3+ was 54% with no streak rule, 54% at 1, 55% at 2, 55% at 3, while the 3-game rule cut the pool from 153 to 97. Owner approved). The pick is the **highest chance of hitting**, not the best value against the price (the owner: "I care about the win"). Ties go to the better price. Only uses games already priced that day, so it costs no extra credits.
10. **Ticket:** no longer shown (owner's call, Oct 12); the running record replaced it. It's still computed and logged (`in_ticket` column): the anchors most likely to hit, DK-priced first, stacked to about +200, max 4 legs, max 2 per game.

**DK pricing:** market `player_shots_on_goal_alternate` (milestones; "Over 1.5" = 2+), bookmaker `draftkings` only. Games are priced one at a time in rank order until the list is full, so an overpriced star doesn't use up the slots. 1 credit per game with lines; unposted games are free. "DK not up" means the game isn't posted yet; "no DK line" means the game is posted but DK has no line for him.

**Grading:** next morning, from player game logs: W/L, VOID if he didn't play (units at the DK price are still logged). The morning message shows yesterday's legs, then a **RECORD** block every day: `Anchors: 14/20, 70%`, `Fun bets: 2/2, 100%`. (A `3+ shooters` line appears only if `PLUS_LEGS` is turned back on.) Voids are excluded. It counts every graded leg; the Variable `RECORD_SINCE` (e.g. `2026-10-10`) starts it from a date instead. Note that Oct 8–9 legs were picked under early, very different rules (anchors since Oct 10: 7/9).

## Oct 24 swap: short-priced legs are the anchors now

Owner's call after the Oct 23 review ("I want winning tickets"). Through Oct 23: legs priced -401 to -600 (then "additional targets") hit **36/40 (90%)**; legs at -400 or longer (then "anchors") hit **29/42 (69%)**. Our model added little on top of DK's price (✓ made no difference: 79% vs 78%).
- **ANCHORS** (shown first, full stats, ranked by chance): DK -401 to `TARGET_MAX_JUICE` (-600), plus players with no DK line yet. Internally still `res["targets"]`; logged as section `anchor` from Oct 24.
- **FUN BETS (-400 or longer)**: the old anchors, names + price only, ranked by chance. Internally `res["anchors"]`; logged as `fun2`; shown in Yesterday as "(fun)"; not in the RECORD.
- **3+ FUN BET**: unchanged (renamed from "FUN BET").
- **RECORD**: "Anchors" counts the -401 to -600 band across the whole history (pre-Oct 24 `target` rows count, pre-Oct 24 `anchor` rows don't); `kind()` / `SWAP_DATE` handle this. Plus "3+ fun bets".
- Rejected the same night: a model-80% floor (`MIN_CHANCE`). The replay showed anchors that passed 80% hit 15/21 (71%) vs 14/21 (67%) for those it cut; the earlier "80%+ hit 89%" was mostly the targets. Built on branch `preview/min-chance-80`, never merged (owner to delete the branch).
- Typical payouts the owner was shown: 4 legs at -400 ≈ +144, at -500 ≈ +107; 3 at -300 ≈ +137. Expect roughly even-money tickets from 2–4 anchors.

## Message format (owner-approved; keep it short)

The owner trimmed it on Oct 8: no TOI or line info in the list, no "est %", fair price shown as `(f -xxx)`. Keep yesterday's results. Show an empty fun bet as "FUN BET: none tonight". No 3+ section (removed Oct 12). No ticket line (removed Oct 12); a running RECORD block instead. Credits line is just "Credits: N left". Title "SOG +2 Hit List" (Oct 12); anchor lines and Yesterday don't repeat "2+" per player, and head-to-head reads `vs BUF 5/6` (fun bet keeps "3+").

```
SOG +2 Hit List · Sat Oct 10
ANCHORS
1. Jack Eichel (VGK) vs MIN · (f -970) · DK -550 ✓ · L20 20/20 (20+ straight) · vs MIN 5/6
2. Bo Horvat (NYI) vs TBL · (f -476) · no DK line · L20 18/20 (8 straight) · vs TBL 6/8

FUN BETS (-400 or longer)
Nick Schmaltz -275 · Sam Reinhart -320

3+ FUN BET
Mason McTavish (STL) 3+ vs CBJ · DK +130 · history 57% vs DK 43% · L20 14/20 · vs CBJ 3+ in 4/5 · 8 straight at 2+

Yesterday:
✅ Nick Schmaltz: 4
❌ Vasily Podkolzin: 1
✅ Mason McTavish 3+ (fun bet): 4

RECORD
Anchors: 35/39, 90%
3+ fun bets: 2/5, 40%

Credits: 19,9xx left
```
(Illustrative; the numbers come from the Oct 10 slate.)

The check message (Oct 12 redesign; the owner found the old one jumbled): a status line, then `checklist()` prints every rule on its own line with his number, the bar and ✅/❌: ice time + PP, shots/game, played last game, last 20, streak, vs opponent (with hot-hand note), DK 2+ price band (✅ anchor / 🔸 target / ❌ too short), 📊 chance at 2+ and 3+, and a fun bet 3+ line (🎲 if he'd qualify). All rules are shown, not just the first that failed.

## Credits

- The Odds API key is **shared with the saves app**. The owner moved to the **$30/month plan (20,000 credits) on Oct 10** and replaced the key in both repos.
- This app spends about 2–6 credits a day (21 used Oct 1–10 under the free plan). `ODDS_RESERVE` 200 means it never spends when the account is at 200 or below, which protects the saves app.
- **If he goes back to the free 500-credit plan:** set `ODDS_MONTHLY_CAP` back to **75** (or delete the Variable), consider `ANCHORS` back to **6**, keep `ODDS_RESERVE` at **200**, and in the saves repo undo its paid-plan settings (see that repo's notes; its README suggested `RECHECK_MINUTES` 10 / `RECHECK_RESERVE` 1000 for the paid plan, and the free-plan defaults were 60 / 150). Also update the key Secret in **both** repos.
- A second free account to dodge limits was advised against (Odds API terms let them cut off access for suspected abuse).

## Known limits, and what went wrong and how it was fixed

- **Oct 9 list never sent:** cron-job.org job was disabled. Enabled; 7:05 has fired on time since.
- **Variables not reaching the script:** (1) workflow pasted into the repo root instead of `.github/workflows/`; (2) later an older workflow with an explicit env list (missing `RECENT_GAMES`, `STREAK`). Fixed with the `ALL_VARS` workflow. Diagnose with a `settings` check.
- **Crash (exit code 1):** `ANCHORS` was entered as `8-10`. Fixed with lenient parsing and ⚠️ warnings.
- **"Re-ran it but nothing came":** a run without `force` exits silently once today's list is sent (by design).
- **Claude's sandbox can't reach the NHL APIs** through the shell (proxy 403). WebFetch works. **Box scores come back stale**: add a cache-buster like `?nocache=1234` to `api-web.nhle.com/v1/gamecenter/{id}/boxscore`. Player game logs lag for a while after games end.
- To preview a list offline: copy the repo's `state.json` and run `select(state["today"], ...)` with `spend=False` (no network, no credits). Research itself needs the NHL APIs, so only GitHub can build a fresh list.
- NHL time-on-ice reports early in the season can show odd game counts; role blending smooths that.
- DK often posts a game before all its players' lines (Oct 12: Boldy and Kaprizov showed "no DK line" all day). Fixed Oct 12: until noon, a posted game with a listed player missing a line is re-checked every `REFRESH_MINUTES` (60), about 1 credit each. The morning message says "DK hasn't posted lines for X yet". The one follow-up goes out when everything is priced, or with whatever's priced by the last hour (11 AM).
- GitHub notice: the `ubuntu-latest` runner moves to Ubuntu 26 from Oct 19, 2026. The script is plain Python 3 standard library, so it should be fine; glance at the first run after that date.
- **Check said Ovechkin was on the list when he wasn't (Oct 11):** the check rebuilt today's list with *current* settings (`MAX_JUICE` had moved from -375 to -400 after the 7:05 send). Fixed: "on today's list" now comes from `hitlist.csv` (what was actually sent). If he'd qualify under the current settings, it says so separately.
- Claude's sandbox can't reach `api.telegram.org` either (proxy 403), so it can't verify bot tokens directly. GitHub runs are the test.
- Never paste bot tokens into files or commits. They belong only in GitHub Secrets. The Sol Shoty token was pasted into the chat on Oct 11; regenerating it (BotFather › /revoke) is optional.

## Decisions and rejected ideas

- DraftKings prices only (the owner copies to FanDuel himself).
- Rejected: watch list of favorite players ("they were axed for a reason"). Leaky/tight defense filters (removed). Value-based fun bet and ticket (switched to chance of hitting). 5-game streak and last-10 rule (replaced after the backtest). Second free Odds API key.
- 7:05 send time: five minutes after the saves alert.

## Pending, and things to test later

- **About Oct 17–18 (one week of the new rules):** review the Season line with the owner before changing anything:
  - Do hot-hand-exception legs (weak head-to-head, e.g. Podkolzin 5/8, the one miss on Oct 10) hit as often as regular anchors?
  - How are the L20 16/20 + streak 1 rules performing?
  - What's the fun bet record?
  - Is 7:05 early enough for DK? (`dk_seen_at` column in `hitlist.csv`)
  - How many credits are being used?
- Possible: a full streak / record **backtest** run as a workflow, over all top-line shooters for a whole season. Offered, not built; the Oct 10 hand backtest used 15 players.
- Possible: ticket target (+200) as a setting. Offered, not built.
- Owner's idea (Oct 12): **opponent shots allowed by position** (forwards vs D), as on shotpropz.com ("SOG Against by Position", YTD and L10). Could be built free from NHL box scores. Not built: needs a backtest first, and early-season samples are tiny (the Buffalo lesson). **Revisit around mid-November** with ~15 games per team; test whether position-allowed rank changes the anchors' hit rate before adding any rule. Head-to-head already exists for anchors (step 6); the fun bet doesn't check it. That's a possible test too. Options to put to the owner then: (a) a rule, only if the backtest shows it helps; (b) a display-only tag on anchor lines, e.g. `BUF #4 vs D` (no filtering). Owner: "we'll revisit" (Oct 12).
- Check that Sol Shoty's first replies and first 7:05 list arrive after `SOG_BOT_TOKEN` is added.
- Pending owner check: confirm the old cron-job.org replies job, if kept, points at `sog-replies.yml` with hours 8–23.
- Results so far: Oct 10 anchors 5/6, ticket hit (about +330), fun bet McTavish 3+ +130 hit.
