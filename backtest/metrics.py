"""Contribution-neutral performance metrics via unitization (mutual-fund-style
NAV/unit accounting), so CAGR / drawdown / worst-year reflect actual
investment performance rather than being distorted by the timing of monthly
$1000 contributions."""

CONTRIBUTION = 1000.0


def build_nav_series(monthly_values):
    units = 0.0
    nav = 1.0
    series = []
    for rec in monthly_values:
        value_before = rec["value_before_contribution"]
        value_after = rec["value_after"]
        nav_before = (value_before / units) if units > 0 else nav
        if nav_before <= 0:
            nav_before = 1e-9
        units_new = CONTRIBUTION / nav_before
        units += units_new
        nav = (value_after / units) if units > 0 else nav_before
        series.append({"date": rec["date"], "nav": nav})
    return series


def cagr_from_nav(nav_series, start_nav=1.0):
    if not nav_series:
        return None
    n_months = len(nav_series)
    years = n_months / 12.0
    final_nav = nav_series[-1]["nav"]
    if final_nav <= 0 or years <= 0:
        return None
    return (final_nav / start_nav) ** (1.0 / years) - 1.0


def max_drawdown(nav_series):
    peak = None
    max_dd = 0.0
    trough_date = None
    peak_date = None
    worst_peak_date = None
    worst_trough_date = None
    for rec in nav_series:
        v = rec["nav"]
        if peak is None or v > peak:
            peak = v
            peak_date = rec["date"]
        dd = (v / peak) - 1.0 if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            worst_peak_date = peak_date
            worst_trough_date = rec["date"]
    return max_dd, worst_peak_date, worst_trough_date


def worst_calendar_year(nav_series):
    """Return (year, return) for the calendar year with the lowest NAV-based
    total return, using Jan-start/Dec-end (or nearest available) NAV marks."""
    by_year = {}
    for rec in nav_series:
        y = int(rec["date"][:4])
        by_year.setdefault(y, []).append(rec["nav"])
    yearly_returns = {}
    years = sorted(by_year.keys())
    prev_last = None
    for y in years:
        navs = by_year[y]
        start = prev_last if prev_last is not None else navs[0]
        end = navs[-1]
        if start and start > 0:
            yearly_returns[y] = (end / start) - 1.0
        prev_last = end
    if not yearly_returns:
        return None, None
    worst_year = min(yearly_returns, key=lambda y: yearly_returns[y])
    return worst_year, yearly_returns[worst_year]


def money_weighted_irr(monthly_values):
    """Annualized IRR of the actual cash flow stream (monthly -$1000 in,
    terminal value out). Solved by bisection on the monthly rate.

    Contribution i (i=0..n-1) occurs at month-index i; the terminal value is
    marked at the same time as the final (i=n-1) contribution. Every cash flow
    is discounted to a single common reference time (t=0, the first
    contribution) so the NPV is internally consistent.
    """
    n = len(monthly_values)
    if n == 0:
        return None
    terminal = monthly_values[-1]["value_after"]

    def npv(monthly_rate):
        total = sum(-CONTRIBUTION / ((1 + monthly_rate) ** i) for i in range(n))
        total += terminal / ((1 + monthly_rate) ** (n - 1))
        return total

    lo, hi = -0.05, 0.20  # monthly rate bounds (~ -46%/yr to ~790%/yr)
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None  # no sign change in range; bail out rather than guess
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if f_lo * f_mid <= 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    monthly_rate = (lo + hi) / 2
    return (1 + monthly_rate) ** 12 - 1
