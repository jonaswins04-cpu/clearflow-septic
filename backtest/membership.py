"""Point-in-time S&P 500 membership: per-year candidate universes.

A ticker is a "candidate" for calendar year Y (i.e. eligible to be judged on its
Y return for a January-of-Y+1 buy decision) only if it was a member of the S&P
500 at BOTH the first available snapshot on/after Jan 1 of Y and the last
available snapshot on/before Dec 31 of Y. This blocks look-ahead bias (e.g.
Tesla joining 2020-12-21 cannot be judged on its 2020 return).

Exception: year 1995. The source data begins 1996-01-02, so there is no
snapshot at the start of 1995. We approximate 1995 membership using the single
1996-01-02 snapshot (the earliest data point available) instead of intersecting
two snapshots. This is flagged via approximated=True and is weaker than every
other year - it is the one year in the whole study that isn't a true
start-AND-end intersection.
"""
import csv
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
MEMBERSHIP_CSV = DATA_DIR / "sp_500_historical_components.csv"


def normalize_ticker(raw: str) -> str:
    t = raw.strip()
    t = re.sub(r"\s*\(.*\)\s*$", "", t)  # "RVTY (Previously PKI)" -> "RVTY"
    t = t.replace(".", "-")  # BF.B / BRK.B -> BF-B / BRK-B (Yahoo convention)
    return t


def load_snapshots():
    rows = list(csv.reader(open(MEMBERSHIP_CSV)))[1:]
    snapshots = {}
    for date, tickers_csv in rows:
        tickers = frozenset(normalize_ticker(t) for t in tickers_csv.split(","))
        snapshots[date] = tickers
    return snapshots


def build_year_candidates(snapshots, first_year=1995, last_year=2025):
    dates = sorted(snapshots.keys())
    earliest_date = dates[0]
    years = {}
    for y in range(first_year, last_year + 1):
        start_candidates = [d for d in dates if d >= f"{y}-01-01"]
        end_candidates = [d for d in dates if d <= f"{y}-12-31"]
        start_d = start_candidates[0] if start_candidates else None
        end_d = end_candidates[-1] if end_candidates else None

        if y == first_year and start_d == earliest_date:
            # No data before the first snapshot: approximate using it alone.
            tickers = sorted(snapshots[earliest_date])
            years[y] = {
                "start_date": earliest_date,
                "end_date": earliest_date,
                "n_start": len(snapshots[earliest_date]),
                "n_end": len(snapshots[earliest_date]),
                "tickers": tickers,
                "n_candidates": len(tickers),
                "approximated": True,
            }
            continue

        if start_d is None or end_d is None:
            years[y] = {
                "start_date": start_d,
                "end_date": end_d,
                "n_start": len(snapshots[start_d]) if start_d else 0,
                "n_end": len(snapshots[end_d]) if end_d else 0,
                "tickers": [],
                "n_candidates": 0,
                "approximated": False,
            }
            continue

        start_set = snapshots[start_d]
        end_set = snapshots[end_d]
        both = sorted(start_set & end_set)
        years[y] = {
            "start_date": start_d,
            "end_date": end_d,
            "n_start": len(start_set),
            "n_end": len(end_set),
            "tickers": both,
            "n_candidates": len(both),
            "approximated": False,
        }
    return years


def main():
    snapshots = load_snapshots()
    years = build_year_candidates(snapshots)
    out_path = DATA_DIR / "year_candidates.json"
    with open(out_path, "w") as f:
        json.dump(years, f, indent=1)

    all_tickers = set()
    for y in years.values():
        all_tickers.update(y["tickers"])
    print(f"Universe: {len(all_tickers)} unique tickers across {len(years)} years")
    for y, info in sorted(years.items()):
        print(
            f"{y}: start={info['start_date']} (n={info['n_start']}) "
            f"end={info['end_date']} (n={info['n_end']}) "
            f"candidates(both)={info['n_candidates']} "
            f"{'[APPROX: single snapshot]' if info['approximated'] else ''}"
        )
    with open(DATA_DIR / "all_tickers.json", "w") as f:
        json.dump(sorted(all_tickers), f, indent=1)


if __name__ == "__main__":
    main()
