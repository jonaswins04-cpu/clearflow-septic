"""Load cached per-ticker price series and provide date-indexed lookups."""
import json
from bisect import bisect_left, bisect_right
from pathlib import Path
import datetime as dt

CACHE_DIR = Path("/tmp/claude-0/-home-user-clearflow-septic/b7b6d400-aece-5c1e-8f98-a27225d16a8b/scratchpad/price_cache")

MIN_AVG_DOLLAR_VOL = 500_000


class Series:
    __slots__ = ("ticker", "dates", "adjclose", "close", "first_trade_date", "avg_dollar_vol", "long_name", "exchange")

    def __init__(self, d):
        self.ticker = d["ticker"]
        self.dates = d["dates"]  # sorted ascending "YYYY-MM-DD" strings
        self.adjclose = d["adjclose"]
        self.close = d["close"]
        self.first_trade_date = d.get("first_trade_date")
        self.avg_dollar_vol = d.get("avg_dollar_vol", 0.0)
        self.long_name = d.get("long_name")
        self.exchange = d.get("exchange")

    def is_liquid_enough(self):
        return self.avg_dollar_vol is not None and self.avg_dollar_vol >= MIN_AVG_DOLLAR_VOL

    def is_trustworthy_series(self):
        """Exclude Yahoo's 'YHD' dead-listing archive bucket: empirically found
        to contain at least one severely corrupted/spliced series (TWX showed
        an unexplained ~7x raw-price jump within 1998 with no corresponding
        corporate action). These records also carry no real company name
        (metadata longName is a bare numeric id), a second corroborating sign
        the record isn't a clean, continuously-tracked listing."""
        return self.exchange != "YHD"

    def existed_by(self, date_str):
        """True if Yahoo's firstTradeDate is on/before date_str (or unknown)."""
        if not self.first_trade_date:
            return True
        return self.first_trade_date <= date_str

    def price_on_or_after(self, date_str, max_slack_days=7):
        i = bisect_left(self.dates, date_str)
        if i >= len(self.dates):
            return None
        found = self.dates[i]
        if (dt.date.fromisoformat(found) - dt.date.fromisoformat(date_str)).days > max_slack_days:
            return None
        return found, self.adjclose[i]

    def price_on_or_before(self, date_str, max_slack_days=7):
        i = bisect_right(self.dates, date_str) - 1
        if i < 0:
            return None
        found = self.dates[i]
        if (dt.date.fromisoformat(date_str) - dt.date.fromisoformat(found)).days > max_slack_days:
            return None
        return found, self.adjclose[i]


_cache = {}


def load(ticker) -> Series | None:
    if ticker in _cache:
        return _cache[ticker]
    path = CACHE_DIR / f"{ticker.replace('/', '_')}.json"
    if not path.exists():
        _cache[ticker] = None
        return None
    d = json.loads(path.read_text())
    if not d.get("ok"):
        _cache[ticker] = None
        return None
    s = Series(d)
    _cache[ticker] = s
    return s


def trading_calendar():
    """Master list of NYSE trading days, taken from ^GSPC's own date list."""
    s = load("^GSPC")
    return s.dates


def first_trading_day_on_or_after(calendar, date_str):
    i = bisect_left(calendar, date_str)
    return calendar[i] if i < len(calendar) else None


def last_trading_day_on_or_before(calendar, date_str):
    i = bisect_right(calendar, date_str) - 1
    return calendar[i] if i >= 0 else None


def month_starts(calendar, year):
    """First trading day of each month in `year`."""
    out = []
    for m in range(1, 13):
        target = f"{year}-{m:02d}-01"
        d = first_trading_day_on_or_after(calendar, target)
        if d and d.startswith(f"{year}-{m:02d}"):
            out.append(d)
    return out
