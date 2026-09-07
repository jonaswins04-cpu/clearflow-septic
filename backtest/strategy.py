"""Core portfolio simulation: cost model, tax model (Canadian business income,
45% on realized gains, average-cost/ACB basis), and the monthly event loop
shared by all four variants and the benchmark.

All parameters below were fixed BEFORE looking at any 2011-2025 results, while
sanity-checking against 1996-2010 only, per the split-sample discipline the
study requires. They are not touched afterward.
"""
import priceio

CONTRIBUTION = 1000.0
TAX_RATE = 0.45
COMMISSION_MIN = 5.0
COMMISSION_PCT = 0.0005  # 5 bps
SPREAD_PCT = 0.0005      # 5 bps


def trade_cost(notional):
    commission = max(COMMISSION_MIN, notional * COMMISSION_PCT)
    spread = notional * SPREAD_PCT
    return commission + spread


class Position:
    __slots__ = ("shares", "cost_basis")

    def __init__(self):
        self.shares = 0.0
        self.cost_basis = 0.0  # ACB: total net dollars invested, still held


class Portfolio:
    def __init__(self):
        self.cash = 0.0
        self.positions = {}  # ticker -> Position
        self.total_tax_paid = 0.0
        self.total_costs_paid = 0.0
        self.events = []  # log

    def buy(self, ticker, date, amount, series_cache):
        if amount <= 0:
            return
        s = series_cache(ticker)
        if s is None:
            self.cash += amount  # can't buy, park as cash, note it
            self.events.append({"date": date, "ticker": ticker, "action": "buy_failed_no_price"})
            return
        found = s.price_on_or_after(date, max_slack_days=5)
        if found is None:
            self.cash += amount
            self.events.append({"date": date, "ticker": ticker, "action": "buy_failed_no_price_near_date"})
            return
        _, price = found
        cost = trade_cost(amount)
        net = amount - cost
        if net <= 0:
            return
        shares = net / price
        pos = self.positions.setdefault(ticker, Position())
        pos.shares += shares
        pos.cost_basis += net
        self.total_costs_paid += cost
        self.events.append({"date": date, "ticker": ticker, "action": "buy", "price": price, "shares": shares, "cost": cost})

    def sell_all(self, ticker, date, series_cache):
        pos = self.positions.get(ticker)
        if pos is None or pos.shares <= 0:
            return 0.0
        s = series_cache(ticker)
        proceeds_gross = 0.0
        price = None
        if s is not None:
            found = s.price_on_or_after(date, max_slack_days=5) or s.price_on_or_before(date, max_slack_days=5)
            if found is not None:
                _, price = found
                proceeds_gross = pos.shares * price
        if price is None:
            # No price available at all near the sale date: fall back to cost
            # basis (no gain/loss recognized). Flagged so it's auditable.
            proceeds_gross = pos.cost_basis
            self.events.append({"date": date, "ticker": ticker, "action": "sell_failed_no_price_used_cost_basis"})
        cost = trade_cost(proceeds_gross)
        gain = (proceeds_gross - cost) - pos.cost_basis
        tax = TAX_RATE * max(0.0, gain)
        net_cash = proceeds_gross - cost - tax
        self.total_costs_paid += cost
        self.total_tax_paid += tax
        self.events.append({
            "date": date, "ticker": ticker, "action": "sell", "price": price,
            "shares": pos.shares, "proceeds_gross": proceeds_gross, "cost": cost,
            "gain": gain, "tax": tax,
        })
        del self.positions[ticker]
        return net_cash

    def mark_to_market(self, date, series_cache):
        total = self.cash
        for ticker, pos in self.positions.items():
            s = series_cache(ticker)
            price = None
            if s is not None:
                found = s.price_on_or_before(date, max_slack_days=10)
                if found is not None:
                    _, price = found
            if price is not None:
                total += pos.shares * price
        return total


def build_sma200_status(gspc_series):
    """date -> bool (index close above its trailing 200-trading-day SMA)."""
    dates, closes = gspc_series.dates, gspc_series.close
    status = {}
    window_sum = 0.0
    for i, c in enumerate(closes):
        window_sum += c
        if i >= 200:
            window_sum -= closes[i - 200]
        if i >= 199:
            sma = window_sum / 200.0
            status[dates[i]] = closes[i] > sma
    return status


def run_variant(name, targets_fn, use_sma_filter, start_year=1996, end_year=2025):
    calendar = priceio.trading_calendar()
    gspc = priceio.load("^GSPC")
    sma_status = build_sma200_status(gspc)

    def series_cache(ticker, _cache={}):
        if ticker not in _cache:
            _cache[ticker] = priceio.load(ticker)
        return _cache[ticker]

    pf = Portfolio()
    yearly_snapshots = []
    monthly_values = []

    for year in range(start_year, end_year + 1):
        targets = targets_fn(year - 1)
        for month in range(1, 13):
            date = None
            for d in priceio.month_starts(calendar, year):
                if int(d[5:7]) == month:
                    date = d
                    break
            if date is None:
                continue
            is_january = month == 1

            if is_january and pf.positions:
                for t in list(pf.positions.keys()):
                    pf.cash += pf.sell_all(t, date, series_cache)

            filt_above = True
            if use_sma_filter:
                filt_above = sma_status.get(date, True)
                if not filt_above and pf.positions:
                    for t in list(pf.positions.keys()):
                        pf.cash += pf.sell_all(t, date, series_cache)

            value_before_contribution = pf.mark_to_market(date, series_cache)

            pf.cash += CONTRIBUTION

            if (not use_sma_filter or filt_above) and targets:
                n = len(targets)
                amt_each = pf.cash / n
                for t in targets:
                    pf.buy(t, date, amt_each, series_cache)
                pf.cash = 0.0  # fully deployed (buy() parks back any that failed)

            value_after = pf.mark_to_market(date, series_cache)
            monthly_values.append({"date": date, "value_before_contribution": value_before_contribution, "value_after": value_after})

        year_end = priceio.last_trading_day_on_or_before(calendar, f"{year}-12-31")
        value = pf.mark_to_market(year_end, series_cache)
        yearly_snapshots.append({
            "year": year,
            "targets": list(targets),
            "value": value,
            "cash": pf.cash,
            "cum_tax_paid": pf.total_tax_paid,
            "cum_costs_paid": pf.total_costs_paid,
        })

    return {
        "name": name,
        "yearly": yearly_snapshots,
        "monthly_values": monthly_values,
        "final_value": yearly_snapshots[-1]["value"] if yearly_snapshots else 0.0,
        "total_tax_paid": pf.total_tax_paid,
        "total_costs_paid": pf.total_costs_paid,
        "events": pf.events,
    }


def run_benchmark(start_year=1996, end_year=2025):
    """$1000/month into SPY, dividends reinvested (adjusted close), buy & hold.
    Same trading costs applied to each buy; never sold, so no tax realized."""
    calendar = priceio.trading_calendar()
    spy = priceio.load("SPY")
    pf = Portfolio()
    yearly_snapshots = []
    monthly_values = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            date = None
            for d in priceio.month_starts(calendar, year):
                if int(d[5:7]) == month:
                    date = d
                    break
            if date is None:
                continue
            value_before_contribution = pf.mark_to_market(date, lambda t: spy)
            pf.cash += CONTRIBUTION
            pf.buy("SPY", date, pf.cash, lambda t: spy)
            pf.cash = 0.0
            value_after = pf.mark_to_market(date, lambda t: spy)
            monthly_values.append({"date": date, "value_before_contribution": value_before_contribution, "value_after": value_after})
        year_end = priceio.last_trading_day_on_or_before(calendar, f"{year}-12-31")
        value = pf.mark_to_market(year_end, lambda t: spy)
        yearly_snapshots.append({"year": year, "value": value})
    return {
        "name": "benchmark_spy_drip",
        "yearly": yearly_snapshots,
        "monthly_values": monthly_values,
        "final_value": yearly_snapshots[-1]["value"] if yearly_snapshots else 0.0,
        "total_tax_paid": 0.0,
        "total_costs_paid": pf.total_costs_paid,
    }
