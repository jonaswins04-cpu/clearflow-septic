"""Download full daily price history for every candidate ticker via Yahoo
Finance's public chart API, with identity/liquidity sanity checks to guard
against ticker-symbol reuse (an old delisted S&P 500 ticker later reassigned
to an unrelated penny/shell company).

Cached to disk as one JSON file per ticker so re-runs are instant.
"""
import json
import time
import concurrent.futures as cf
from pathlib import Path
import datetime as dt
import requests

CACHE_DIR = Path("/tmp/claude-0/-home-user-clearflow-septic/b7b6d400-aece-5c1e-8f98-a27225d16a8b/scratchpad/price_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = Path(__file__).parent / "data"

PERIOD1 = int(dt.datetime(1993, 1, 1).timestamp())
PERIOD2 = int(dt.datetime(2026, 9, 7).timestamp())

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

MIN_AVG_DOLLAR_VOL = 500_000  # liquidity floor: an S&P 500 constituent trades far more than this


def fetch_one(ticker, session, retries=3):
    cache_path = CACHE_DIR / f"{ticker.replace('/', '_')}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            pass

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    params = {
        "period1": PERIOD1,
        "period2": PERIOD2,
        "interval": "1d",
        "events": "div,splits",
        "includeAdjustedClose": "true",
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, headers=HEADERS, timeout=20)
            j = r.json()
            result = j.get("chart", {}).get("result")
            if not result:
                err = j.get("chart", {}).get("error")
                out = {"ticker": ticker, "ok": False, "reason": f"no_data:{err}"}
                cache_path.write_text(json.dumps(out))
                return out
            res = result[0]
            meta = res.get("meta", {})
            ts = res.get("timestamp") or []
            quote = (res.get("indicators", {}).get("quote") or [{}])[0]
            if not ts or not quote:
                out = {"ticker": ticker, "ok": False, "reason": "delisted_placeholder"}
                cache_path.write_text(json.dumps(out))
                return out
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or quote.get("close")
            closes = quote.get("close") or []
            vols = quote.get("volume") or []

            dates = [dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") for t in ts]
            clean = [
                (d, c, a, v)
                for d, c, a, v in zip(dates, closes, adj, vols)
                if c is not None and a is not None
            ]
            if not clean:
                out = {"ticker": ticker, "ok": False, "reason": "empty_after_clean"}
                cache_path.write_text(json.dumps(out))
                return out

            dvols = [c * (v or 0) for _, c, _, v in clean]
            avg_dollar_vol = sum(dvols) / len(dvols)

            first_trade_ts = meta.get("firstTradeDate")
            first_trade_date = (
                dt.datetime.utcfromtimestamp(first_trade_ts).strftime("%Y-%m-%d")
                if first_trade_ts
                else None
            )

            out = {
                "ticker": ticker,
                "ok": True,
                "long_name": meta.get("longName") or meta.get("shortName"),
                "exchange": meta.get("fullExchangeName"),
                "first_trade_date": first_trade_date,
                "avg_dollar_vol": avg_dollar_vol,
                "n_points": len(clean),
                "dates": [x[0] for x in clean],
                "close": [x[1] for x in clean],
                "adjclose": [x[2] for x in clean],
            }
            cache_path.write_text(json.dumps(out))
            return out
        except Exception as e:
            last_err = str(e)
            time.sleep(1.5 * (attempt + 1))
    out = {"ticker": ticker, "ok": False, "reason": f"exception:{last_err}"}
    cache_path.write_text(json.dumps(out))
    return out


def fetch_all(tickers, max_workers=6):
    session = requests.Session()
    results = {}
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fetch_one, t, session): t for t in tickers}
        done = 0
        for fut in cf.as_completed(futs):
            t = futs[fut]
            try:
                results[t] = fut.result()
            except Exception as e:
                results[t] = {"ticker": t, "ok": False, "reason": f"fatal:{e}"}
            done += 1
            if done % 100 == 0:
                print(f"  ...{done}/{len(tickers)} fetched")
    return results


def main():
    all_tickers = json.loads((DATA_DIR / "all_tickers.json").read_text())
    extra = ["SPY", "^GSPC"]
    tickers = sorted(set(all_tickers) | set(extra))
    print(f"Fetching {len(tickers)} tickers (with cache at {CACHE_DIR}) ...")
    t0 = time.time()
    results = fetch_all(tickers)
    print(f"Done in {time.time()-t0:.0f}s")

    ok = [t for t, r in results.items() if r.get("ok")]
    bad = [t for t, r in results.items() if not r.get("ok")]
    print(f"OK: {len(ok)}  FAILED/NO-DATA: {len(bad)}")

    illiquid = [
        t for t in ok
        if results[t]["avg_dollar_vol"] < MIN_AVG_DOLLAR_VOL and results[t]["n_points"] > 5
    ]
    print(f"Flagged as too-illiquid to plausibly be a real S&P500 constituent: {len(illiquid)}")
    if illiquid:
        print(illiquid[:40])

    summary = {
        t: {
            "ok": r.get("ok", False),
            "reason": r.get("reason"),
            "long_name": r.get("long_name"),
            "first_trade_date": r.get("first_trade_date"),
            "avg_dollar_vol": r.get("avg_dollar_vol"),
            "n_points": r.get("n_points"),
        }
        for t, r in results.items()
    }
    (DATA_DIR / "fetch_summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
