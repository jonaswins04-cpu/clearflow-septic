# S&P 500 "prior-year winner" backtest, 1996-2025

Each January, buy last calendar year's best-performing S&P 500 stock (point-in-time
membership only). Contribute $1,000 on the first trading day of every month.
Four variants + a $1,000/month S&P 500 (SPY, dividends reinvested) benchmark.
45% tax on realized gains (Canadian business income), $5-or-5bps commission +
5bps spread per trade. Built/sanity-checked on 1996-2010, then run once on
2011-2025 out-of-sample, per the requested split-sample discipline.

## Pipeline

1. `membership.py` - parses the point-in-time S&P 500 membership file
   (`data/sp_500_historical_components.csv`, from
   github.com/hanshof/sp500_constituents) into per-year candidate sets. A
   ticker is eligible to be judged on year Y's return only if it was a member
   at BOTH the first snapshot on/after Jan 1 Y and the last snapshot on/before
   Dec 31 Y. **Exception: 1995** - the source data starts 1996-01-02, so 1995
   membership is approximated from that single snapshot rather than a true
   start/end intersection. Output: `data/year_candidates.json`.
2. `fetch_prices.py` - downloads full daily price history per ticker from
   Yahoo Finance's public chart API (Stooq, the originally-requested source,
   is blocked by an anti-bot wall in this sandbox that survives solving its
   JS proof-of-work challenge - see caveats). Cached under
   `/tmp/.../scratchpad/price_cache/*.json` (not committed - regenerate with
   `python3 fetch_prices.py`, ~45s for ~1100 tickers).
3. `returns.py` - ranks each year's candidates by return, applying identity/
   liquidity safeguards (see caveats), and picks the top-1 / top-5 / top-5-
   sectors. Output: `data/year_winners.json`.
4. `strategy.py` / `metrics.py` - the monthly simulation (cost model, 45% tax
   on realized gains via average-cost/ACB basis, 200-day SMA filter) and
   contribution-neutral performance metrics (NAV/unit accounting, so CAGR/
   drawdown/worst-year reflect investment performance, not contribution
   timing).
5. `run_backtest.py` - runs the sanity check (1996-2010) and the full study
   (1996-2025, single run). Output: `results/*.json`.
6. `build_report_tables.py` - year-by-year CSVs per variant.

## Reasons to distrust this result (read before citing any number)

- **Stooq (the requested source) is unusable here.** It's reachable but
  walled off by a bot-check that survives solving its own JS proof-of-work
  puzzle; the bulk CSV endpoint returns "Access denied" regardless. Switched
  to Yahoo Finance's public chart API.
- **Yahoo cannot serve ANY historical data for a security once it's fully
  delisted** (confirmed directly: WBA, TWTR, CELG, ABMD, TIF, XLNX, RHT, and
  ~395 others all 404 "symbol may be delisted", even though most of them
  traded for decades). This is a structural gap, not a bug, and it is why
  priced coverage rises steadily from 38% of candidates in 1995 to 97% in
  2024 (`results/coverage_by_year.csv`) - older cohorts have had more time for
  their members to get acquired/merged/delisted. It systematically excludes
  companies later acquired from ever being picked as a year's winner, which
  reintroduces a form of survivorship bias (via data availability rather
  than index membership) most severely in the early years.
- **Ticker-symbol reuse produced at least one silent wrong-company match**:
  `MCIC` (the real 1990s MCI Communications) resolves today to an unrelated
  penny stock, "MultiCorp International" (avg daily dollar volume ~$12K/day).
  Guarded against with a liquidity floor ($500K/day) and a firstTradeDate
  check, but there is no guarantee this catches every case - only that it
  catches the ones checked.
- **Found and excluded a second, more subtle corruption**: Yahoo serves some
  delisted tickers under an internal "YHD" (dead-archive) exchange code with
  no real company name in the metadata. One of these, `TWX`, showed an
  unexplained ~7x raw-price jump within calendar 1998 with no matching
  corporate action - a spliced/corrupted series. All 12 "YHD"-flagged tickers
  found in the candidate universe were excluded; this changed the 1997 and
  1998 computed winners (previously TWX both years).
- **1995 is the weakest year in the study on two independent counts**: its
  membership is a single-snapshot approximation (see above), and its
  computed winner, AutoNation (`AN`, +954%), is by far the most extreme
  return anywhere in the 30-year dataset (next-highest is +324%). It is
  plausibly real - AutoNation was Wayne Huizenga's mid-1990s reconstruction
  of Republic Industries - but nothing in this network-restricted sandbox
  could independently corroborate it. Treat 1995 as the least trustworthy
  single year here.
- **Variant 4's sector labels are TODAY's GICS sector** (from
  github.com/datasets/s-and-p-500-companies), not point-in-time. Any
  candidate no longer in today's S&P 500 - i.e. most delisted/acquired
  names, a large fraction especially pre-2015 - has no sector at all and is
  invisible to variant 4's ranking. Variant 4's opportunity set is biased
  toward large, durable survivors.
- **The single-stock variants are extremely sensitive to data-provenance
  noise, and this is a finding, not just a caveat.** Re-running the identical
  pipeline after a routine data refresh (which shifted average-dollar-volume
  computations slightly) flipped the computed winner in 5 of 30 years at the
  liquidity-threshold margin (2001, 2008, 2020, 2021, 2022). Because variant
  1 puts 100% of the portfolio in one stock and compounds for 30 years,
  those small swaps changed the final value by millions of dollars between
  two runs of the same code on the same methodology. That fragility is
  inherent to "concentrate the whole portfolio in one stock" - it is the
  main reason to treat any single point estimate from variant 1 or 2 with
  real skepticism, independent of any data bug.
- **Tax model is simplified**: average-cost (ACB) basis, 45% on any positive
  realized gain, no benefit from losses offsetting other gains (real CRA
  business-income treatment allows loss offsets, so true after-tax results
  could be somewhat better than shown here).
- **Trading costs use one modern-era assumption for all 30 years**
  ($5-or-5bps commission + 5bps spread); real 1996-2000 retail commissions
  were far higher, so early years are mildly cost-optimistic. This is a
  second-order effect next to the tax drag.
- **The benchmark (SPY, dividends reinvested) is far more trustworthy than
  any strategy column**: one continuously-listed security, no identity
  ambiguity, no delisting gap. Read the benchmark number with much higher
  confidence than the variant numbers.
