# Sequoia-X V3: The King Returns

> A-Share Quantitative Stock Selection System V3 | **中文版**: [README.md](./README.md)

---

## Local TDX workflow

Default provider: `http://192.168.1.74:8080`. Only Shanghai/Shenzhen main-board,
STAR Market and ChiNext A-shares are scanned. ST, delisting names, Beijing stocks,
B-shares, funds and indexes are excluded before strategy ranking.
The daily command produces a local Markdown report; it never sends Feishu messages.

```bash
python main.py
python main.py --backfill
python main.py --parallel --max-workers 2
```

TDX automatically fills history for newly discovered stocks. Run after market close.

## Built-in Strategies

| Strategy | Description |
|---|---|
| **TurtleTrade** | Turtle breakout: close breaks 20-day high + turnover > ¥100M + bullish candle to avoid fakeouts, sorted by float market cap |
| **MaVolume** | MA golden cross + volume surge: MA5 crosses above MA20, today's volume > 1.5× 20-day average |
| **HighTightFlag** | High & tight flag: 40-day gain > 60% + 10-day amplitude converging + high-level resilience on shrinking volume |
| **LimitUpShakeout** | Post-limit-up shakeout: after yesterday's limit-up, today sells off on volume but holds yesterday's close |
| **UptrendLimitDown** | Limit-down mispricing in uptrend: catches panic limit-down-grade long candles within a healthy trend |
| **RpsBreakout** | Extreme RPS momentum breakout: top 10% by 120-day gain market-wide + near the 120-day high |
| **RpsYilin** | Yilin-style strict RPS breakout: RPS top 5% + true breakout + volume surge + trend filter |
| **TripleVolumeBreakout** | Triple-volume consolidation breakout: 3× volume signal + low-volume consolidation + composite score ranking |
| **BowlRebound** | Bowl rebound: trend pullback + historical volume spike + KDJ oversold bounce |
| **FirstNewHigh30DaysBreakout** | First 30-day new high: first breakout + bullish MA alignment + volume + Bollinger mid-band strength |
| **PrivatePlacement** | Private placement announcement monitor (akshare announcement data, placements within last 7 days) |
| **TrendMeanReversion** | Uptrend oversold reversion: healthy trend + short-term oversold + stabilization confirmation to avoid catching falling knives |
| **StopFall** | Stop-fall candidates: S2 initial stabilization / S3 confirmed stabilization tiers + market-breadth dynamic scoring |

Adding a new strategy takes three steps: create a file inheriting `BaseStrategy` in `sequoia_x/strategy/` → import it at the top of `main.py` → append it to the `strategy_classes` list.

---

## Strategy Details

### TurtleTrade — Turtle Breakout

- **Selection logic**: Close breaks the highest high of the previous 20 days; today's turnover > ¥100M; a solid bullish candle closing above yesterday's close (avoids open-high-close-low fakeouts); selected stocks sorted by float market cap, largest first.
- **Applicable conditions**: Trending breakout markets; the turnover threshold filters out small, illiquid stocks — suited to steady trend following.

### MaVolume — MA Golden Cross + Volume

- **Selection logic**: MA5 crosses above MA20 (below yesterday, above today); today's volume > 1.5× the 20-day average volume.
- **Applicable conditions**: Golden-cross confirmation at the start of an uptrend — for early entry at trend initiation.

### HighTightFlag — High & Tight Flag

- **Selection logic**: 40-day range gain > 60% (high/low ratio > 1.6); 10-day amplitude < 1.15 (extreme convergence); 10-day low not below 80% of the 40-day high (high-level resilience); today's volume < 0.6× the 20-day average volume.
- **Applicable conditions**: Late-stage tight consolidation of strong stocks at highs, waiting for an upside breakout; suited to converging, strong markets.

### LimitUpShakeout — Post-Limit-Up Shakeout

- **Selection logic**: Yesterday's gain ≥ 9.5%; today closes bearish; today's volume > 2× yesterday's; today's low ≥ yesterday's close (holds the prior close).
- **Applicable conditions**: Volume shakeout the day after a limit-up — for short-term strong-stock continuation environments.

### UptrendLimitDown — Limit-Down Mispricing in Uptrend

- **Selection logic**: Yesterday MA20 > MA60 (in an uptrend); today's close ≤ 0.905 × yesterday's close (limit-down grade); today's volume > 2× the 20-day average volume.
- **Applicable conditions**: Panic mispricing within an uptrend, betting on a rebound after the crash; beware of continued decline the following day.

### RpsBreakout — Extreme RPS Momentum Breakout

- **Selection logic**: 120-day gain ranked market-wide, RPS ≥ 90 (top 10%); close ≥ 90% of the rolling 120-day highest high.
- **Applicable conditions**: Strong momentum continuation — suited to trend-following styles.

### RpsYilin — Yilin Strict RPS Breakout

- **Selection logic**: RPS ≥ 95 (top 5%); close truly breaks the 120-day high (prior high excludes today); today's volume > 1.5× the 20-day average; turnover > ¥100M; solid bullish candle closing up; close > MA20 > MA60; ranked by RPS, turnover and breakout magnitude, top 30 selected.
- **Applicable conditions**: The strict momentum breakout, win-rate first; suited to strong trending markets.

### TripleVolumeBreakout — Triple-Volume Consolidation Breakout

- **Selection logic**: A triple-volume signal within the last 3–90 sessions (volume ≥ 3× the prior day, bullish candle closing up); followed by low-volume consolidation (platform amplitude ≤ 30%, second-half volume lower than first-half); close not below 95% of MA60 (no breakdown); turnover ≥ ¥100M; composite score across volume quality, signal recency, consolidation degree, amplitude, trend structure, breakout strength and turnover — ≥ 55 preferred, ≥ 45 fallback, max 8 stocks.
- **Applicable conditions**: The accumulation → low-volume consolidation → breakout pattern of main capital; suited to mid/long-term swing positioning.

### BowlRebound — Bowl Rebound

- **Selection logic**: Short-term trend line (double-smoothed EMA10) above the multi-line (average of MA14/28/57/114); at least one ≥ 4× volume bullish candle in the last 15 sessions with the max-volume day bullish; today KDJ-J ≤ 30 (oversold); close back inside the "bowl" or within ±3% of the multi-line / ±2% of the trend line; turnover ≥ ¥100M; ranked by position + J value + turnover.
- **Applicable conditions**: Pullback accumulation under a healthy trend — entry when strong stocks pull back into position.

### FirstNewHigh30DaysBreakout — First 30-Day New High

- **Selection logic**: Today's high breaks the 30-day high with close ≥ 98% of the prior high, and no similar breakout in the previous 29 sessions (first new high); MA5 > MA10 > MA20 > MA60, all rising with widening gaps; 3 consecutive closes above MA20; volume > 1.2× the 5-day average and < 3× the 20-day average (volume surge without blowout); bullish candle closing in the upper half of the day's range, gain ≤ 8.5%; turnover > ¥500M; excludes ST and suspended stocks. Optional index environment filter (off by default): at least one of CSI 300 / CSI 500 / ChiNext closes above its MA20 with MA20 rising.
- **Applicable conditions**: The first breakout as bullish MA alignment begins — catches the start of trend acceleration while avoiding already-exhausted names.

### PrivatePlacement — Placement Announcement Monitor

- **Selection logic**: Fetches placement announcements via akshare, keeps only "private placement" (定向增发), filters the last 7 days by issue date, deduplicates and returns stock codes — no market data involved.
- **Applicable conditions**: An event-driven watchlist, best combined with market-based strategies for tracking.

### TrendMeanReversion — Uptrend Oversold Reversion

- **Selection logic**: Healthy trend (MA20 > MA60, close > MA60, 60-day gain > 0); close 3%–10% below MA20; 5-day decline of 6%–18%; turnover > ¥100M; excludes near-limit-down closes on two consecutive days or today (avoid catching falling knives); must satisfy one of: bullish close / close above yesterday / long lower shadow (lower shadow ≥ 35% of the day's range and close ≥ 2% above the low); scored by deviation from MA20 + pullback depth + height above MA60.
- **Applicable conditions**: Pullback stabilization within an uptrend — never for sustained bear markets.

### StopFall — Stop-Fall Candidates

- **Selection logic**: Hard filters: listed ≥ 80 sessions, 60-day drawdown ≤ -12%, distance to prior low ≤ 2× ATR, negative 20-day return, no one-word limit-down, excludes ST/delisting; seven-factor scoring (low support 25%, decelerating decline 15%, selling exhaustion 15%, 5-day relative strength 15%, 3-day close position 10%, volatility normalization 10%, breakout strength 10%) requiring ≥ 4 confirmations; the passing score is set by market breadth (share of all stocks above MA20) — improving (≥ 45% or +5pp over 5 days) = 60, neutral = 65, weak (< 30%) = 70; in weak markets only S3 is output (close breaking the 5-day highest close — confirmed stabilization), otherwise high-score S2 (initial stabilization) is also output.
- **Applicable conditions**: Late-decline and ranging markets hunting for stabilizing names; screening gets stricter as the market weakens — naturally adaptive.

---

## Setup

Python >= 3.10. Install with `uv sync --extra dev` (or `pip install -e ".[dev]"`).
Copy `.env.example` to `.env` only for a new installation; preserve existing configuration.

```env
DATA_SOURCE=tdx
TDX_BASE_URL=http://192.168.1.74:8080
TDX_DB_PATH=data/sequoia_tdx.db
TDX_TIMEOUT_SECONDS=30
START_DATE=2024-01-01
REPORT_OUTPUT_DIR=reports
```

Run `uv run python main.py`. Reports are written to `reports/Sequoia-X_选股报告_YYYY-MM-DD.md`.
An existing `REPORT_OUTPUT_DIR` overrides the default. Reports include the actual data date
and pool/scan counts. Failed or stale TDX symbols are excluded. The placement strategy
still uses akshare for event data; its results are restricted to the same stock pool.
`DATA_SOURCE=baostock` keeps the legacy provider and its separate `DB_PATH`.

## Project Structure

```
Sequoia-X/
├── main.py                        # Entry: sync + strategies + local report
├── launch_sequoia_x.command       # macOS double-click launcher: daily mode
├── launch_sequoia_x_backfill.command  # macOS double-click launcher: backfill mode
├── pyproject.toml                 # Dependency declaration + ruff/pytest config
├── .env.example                   # Environment variable template
├── data/                          # SQLite databases (runtime-generated, not in git)
├── scripts/
│   └── bench.py                   # Strategy timing benchmark (no push, no data changes)
├── sequoia_x/
│   ├── core/
│   │   ├── config.py              # Pydantic-settings configuration management
│   │   └── logger.py              # rich structured logging
│   ├── data/
│   │   ├── tdx.py                 # TDX HTTP adapter
│   │   ├── factory.py             # Provider selection
│   │   ├── universe.py            # Shared stock filters
│   │   └── engine.py              # Data engine (baostock backfill + incremental sync + SQLite)
│   ├── strategy/
│   │   ├── base.py                # Strategy abstract base class
│   │   ├── turtle_trade.py        # Turtle trading strategy
│   │   ├── ma_volume.py           # MA + volume strategy
│   │   ├── high_tight_flag.py     # High & tight flag strategy
│   │   ├── limit_up_shakeout.py   # Limit-up shakeout strategy
│   │   ├── uptrend_limit_down.py  # Uptrend limit-down strategy
│   │   ├── rps_breakout.py        # RPS breakout strategy
│   │   ├── RPS_YILIN.py           # Yilin strict RPS breakout strategy
│   │   ├── ThreeTimeYilinStrategy_v3.py  # Triple-volume consolidation breakout strategy
│   │   ├── bowl_rebound.py        # Bowl rebound strategy
│   │   ├── FirstNewHigh30DaysBreakoutStrategy.py  # First 30-day new high breakout strategy
│   │   ├── stop_fall.py           # Stop-fall candidate strategy
│   │   ├── private_placement.py   # Placement announcement monitor strategy
│   │   └── trend_mean_reversion.py  # Uptrend oversold reversion strategy
│   └── notify/
│       ├── feishu.py              # Feishu interactive card push
│       └── report.py              # Daily Markdown selection report
└── tests/                         # Property-based tests (hypothesis)
```

---

## Data Notes

- `/code/all?exchange=sh|sz` supplies security codes and names; `/kline/day` supplies paginated daily bars (800 per page); `/finance` supplies circulating shares for Turtle ranking.
- Go `Price` fields (OHLC and Amount) are divided by 1000; Volume is multiplied by 100 to convert lots to shares.
- TDX daily bars are **unadjusted**. Corporate actions can distort technical signals. This adapter does not claim adjusted-price equivalence with baostock.
- `data/sequoia_tdx.db` isolates raw TDX bars from legacy adjusted history. Do not point the providers at the same database.
- Daily synchronization overlaps the last stored day, deduplicates dates, and excludes unfinished current-day bars before 15:00 Shanghai time.

## Tests

```bash
uv run pytest
```

Covers configuration management, the data engine, Feishu push, logging, the entry point and strategy interfaces, using hypothesis for property-based testing.

---

## License

MIT

## Weekly direction / daily candidates

Enabled by default with `WEEKLY_FILTER_ENABLED=true`. Weekly close must exceed MA10,
MA10 must exceed MA20, and MA20 must rise versus the preceding completed week.
At least 21 completed weekly bars are required. Daily data is aggregated to Friday
labels, using only labels no later than the last daily observation. Holiday-shortened
weeks are conservatively delayed without an exchange calendar; partial first weeks are omitted.
Original daily rankings are calculated before filtering, including RPS. The report lists
accepted/rejected candidates and weekly dates. Setup and announcement signals remain watchlists.

Optionally set `HOLDING_SYMBOLS=["600000","000001"]`. Positions are checked independently
of entry candidates: two closes below daily MA20 or a close below the previous ten-day
low generates an exit observation. Missing data is explicitly reported. No positions means
no exit assessment. This module does not place orders or model cost stops, entry dates,
or execution availability. Parameters are initial hypotheses, not backtested performance.
Disabling the weekly module restores the original report and disables its exit observations.

## Local-only execution

Run `python main.py --skip-sync` (optionally `--parallel --max-workers 2`).
Uses cached TDX prices and universe, skips announcements and live market-cap queries,
and retains weekly filtering and local reporting. Empty usable data is an error;
`--skip-sync` and `--backfill` are mutually exclusive. Cached ST status can be stale.
The baostock provider does not yet persist security status and cannot run offline.

## Report diagnostics

Candidates are grouped by risk review, observed 20-day breakout, pullback/stabilization,
consolidation, and relative strength. This changes presentation only, not selection.
`REPORT_SHARP_DROP_PCT=8` and `REPORT_OVERHEAT_PCT=20` flag a large daily decline or
close-to-daily-MA20 excess; these are uncalibrated display thresholds, not limit-price rules.
Tables include price, daily return, daily/weekly MA20 distances, volume relative to the prior
20 sessions, turnover, RPS120, prior highs and structural reference levels. Missing history
is displayed as a dash. Historical triple-volume dates and platform status are explicit.
All strategy overlaps are listed without attractiveness ratings. Cached scan omissions
and unknown security-status freshness are disclosed; corporate actions remain unverified.
