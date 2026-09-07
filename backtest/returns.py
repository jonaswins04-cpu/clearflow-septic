"""Determine each calendar year's winner(s) from point-in-time candidates."""
import json
from pathlib import Path
import priceio

DATA_DIR = Path(__file__).parent / "data"


def load_sector_map():
    """Ticker -> current GICS sector. NOTE: this is TODAY's sector mapping,
    not point-in-time. A candidate no longer in today's S&P 500 (i.e. most
    delisted/acquired names) has no sector and is excluded from variant 4's
    ranking. This is a real, documented limitation - see report caveats."""
    import csv
    path = DATA_DIR / "sp500_sectors_current.csv"
    m = {}
    for row in csv.DictReader(open(path)):
        sym = row["Symbol"].replace(".", "-")
        m[sym] = row["GICS Sector"]
    return m


def year_return(ticker, start_date, end_date, calendar, slack_days=10):
    s = priceio.load(ticker)
    if s is None:
        return None, "no_price_data"
    if not s.is_liquid_enough():
        return None, "illiquid_or_ticker_collision"
    if not s.is_trustworthy_series():
        return None, "yahoo_dead_archive_untrustworthy"
    if not s.existed_by(start_date):
        return None, "yahoo_first_trade_after_start"
    p0 = s.price_on_or_after(start_date, max_slack_days=slack_days)
    p1 = s.price_on_or_before(end_date, max_slack_days=slack_days)
    if p0 is None or p1 is None:
        return None, "missing_start_or_end_price"
    (_, price0), (_, price1) = p0, p1
    if price0 <= 0:
        return None, "bad_price"
    return (price1 / price0) - 1.0, "ok"


def rank_year(year, year_candidates, calendar):
    """Return sorted list of (ticker, return) descending, and coverage stats.

    The point-in-time membership snapshot dates (info['start_date']/'end_date')
    are used ONLY to decide who is an eligible candidate. The actual return is
    always measured over the true calendar-year trading window (first trading
    day on/after Jan 1 to last trading day on/before Dec 31), independent of
    which snapshot dates happened to be available for the membership check.
    This matters most for 1995, whose membership is approximated from a single
    1996-01-02 snapshot - using that snapshot date itself as the return window
    would degenerate every return to exactly 0.
    """
    info = year_candidates[str(year)]
    start_date = priceio.first_trading_day_on_or_after(calendar, f"{year}-01-01")
    end_date = priceio.last_trading_day_on_or_before(calendar, f"{year}-12-31")
    results = []
    reasons = {}
    for t in info["tickers"]:
        r, reason = year_return(t, start_date, end_date, calendar)
        reasons[reason] = reasons.get(reason, 0) + 1
        if r is not None:
            results.append((t, r))
    results.sort(key=lambda x: -x[1])
    return {
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "n_candidates": len(info["tickers"]),
        "n_priced": len(results),
        "reasons": reasons,
        "ranked": results,
        "approximated": info["approximated"],
    }


def rank_year_by_sector(year, year_candidates, calendar, sector_map, n_sectors=5):
    """Top N sectors (by their best-performing member's return), best company
    in each. Only candidates with a KNOWN (today's) sector are eligible."""
    full = rank_year(year, year_candidates, calendar)
    by_sector = {}
    for t, r in full["ranked"]:
        sec = sector_map.get(t)
        if sec is None:
            continue
        if sec not in by_sector or r > by_sector[sec][1]:
            by_sector[sec] = (t, r)
    sector_ranked = sorted(by_sector.items(), key=lambda kv: -kv[1][1])
    top = sector_ranked[:n_sectors]
    full["sector_coverage_n_priced_with_sector"] = len(by_sector)
    full["top_sectors"] = [(sec, t, r) for sec, (t, r) in top]
    return full


def main():
    year_candidates = json.loads((DATA_DIR / "year_candidates.json").read_text())
    calendar = priceio.trading_calendar()
    sector_map = load_sector_map()

    all_ranks = {}
    for y in range(1995, 2025):
        rk = rank_year_by_sector(y, year_candidates, calendar, sector_map)
        all_ranks[y] = rk
        top1 = rk["ranked"][0] if rk["ranked"] else None
        top5 = rk["ranked"][:5]
        print(
            f"{y}: priced {rk['n_priced']}/{rk['n_candidates']} "
            f"| winner={top1} | top5={[t for t,_ in top5]} "
            f"| sectors_priced={rk['sector_coverage_n_priced_with_sector']} "
            f"| top_sectors={[(s,t,round(r,3)) for s,t,r in rk['top_sectors']]}"
        )

    # Save a compact version for the strategy engine to consume
    out = {}
    for y, rk in all_ranks.items():
        out[y] = {
            "n_candidates": rk["n_candidates"],
            "n_priced": rk["n_priced"],
            "reasons": rk["reasons"],
            "top1": rk["ranked"][0] if rk["ranked"] else None,
            "top5": rk["ranked"][:5],
            "top_sectors": rk["top_sectors"],
            "sector_coverage_n_priced_with_sector": rk["sector_coverage_n_priced_with_sector"],
            "approximated": rk["approximated"],
        }
    (DATA_DIR / "year_winners.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
