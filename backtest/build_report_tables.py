"""Assemble year-by-year CSV tables (pick, prior-year return, return-while-held,
portfolio value) for each variant, from the full 1996-2025 run."""
import csv
import json
from pathlib import Path

import priceio
from run_backtest import load_year_winners, this_year_return

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"


def main():
    full = json.loads((RESULTS_DIR / "full_1996_2025.json").read_text())
    year_winners = load_year_winners()
    calendar = priceio.trading_calendar()

    for vname in ["1_top1_nofilter", "2_top1_sma200", "3_top5_sma200", "4_sector5_sma200"]:
        rows = []
        for rec in full[vname]["yearly"]:
            y = rec["year"]
            targets = rec["targets"]
            prior_info = year_winners.get(str(y - 1))
            prior_returns = []
            if prior_info:
                lookup = {t: r for t, r in ([prior_info["top1"]] if prior_info["top1"] else [])}
                lookup.update({t: r for t, r in prior_info["top5"]})
                lookup.update({t: r for _, t, r in prior_info["top_sectors"]})
                prior_returns = [lookup.get(t) for t in targets]
            held_returns = [this_year_return(t, y, calendar) for t in targets]
            rows.append({
                "year": y,
                "picks": ";".join(targets),
                "prior_year_return_pct": ";".join(
                    f"{r*100:.1f}" if r is not None else "NA" for r in prior_returns
                ),
                "return_while_held_pct": ";".join(
                    f"{r*100:.1f}" if r is not None else "NA" for r in held_returns
                ),
                "portfolio_value": round(rec["value"], 2),
                "cum_tax_paid": round(rec["cum_tax_paid"], 2),
                "cum_costs_paid": round(rec["cum_costs_paid"], 2),
            })
        out_path = RESULTS_DIR / f"yearbyyear_{vname}.csv"
        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {out_path}")

    # benchmark
    rows = []
    for rec in full["benchmark_spy_drip"]["yearly"]:
        rows.append({"year": rec["year"], "portfolio_value": round(rec["value"], 2)})
    with open(RESULTS_DIR / "yearbyyear_benchmark.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "portfolio_value"])
        w.writeheader()
        w.writerows(rows)

    # coverage table
    with open(RESULTS_DIR / "coverage_by_year.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "n_candidates_point_in_time", "n_priced", "pct_priced"])
        for y in range(1995, 2025):
            info = year_winners[str(y)]
            w.writerow([y, info["n_candidates"], info["n_priced"],
                        f"{100*info['n_priced']/max(info['n_candidates'],1):.0f}%"])


if __name__ == "__main__":
    main()
