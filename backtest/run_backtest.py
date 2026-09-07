import json
from pathlib import Path

import priceio
import returns as returns_mod
import strategy
import metrics

DATA_DIR = Path(__file__).parent / "data"
RESULTS_DIR = Path(__file__).parent / "results"


def load_year_winners():
    return json.loads((DATA_DIR / "year_winners.json").read_text())


def make_targets_fn(year_winners, mode):
    def fn(y):
        info = year_winners.get(str(y)) or year_winners.get(y)
        if info is None:
            return []
        if mode == "top1":
            top1 = info["top1"]
            return [top1[0]] if top1 else []
        elif mode == "top5":
            return [t for t, _ in info["top5"]]
        elif mode == "sector5":
            return [t for _, t, _ in info["top_sectors"]]
        raise ValueError(mode)
    return fn


def this_year_return(ticker, year, calendar):
    r, reason = returns_mod.year_return(
        ticker,
        priceio.first_trading_day_on_or_after(calendar, f"{year}-01-01"),
        priceio.last_trading_day_on_or_before(calendar, f"{year}-12-31"),
        calendar,
    )
    return r


def half_metrics(nav_series, start_year, end_year):
    sub = [r for r in nav_series if start_year <= int(r["date"][:4]) <= end_year]
    if not sub:
        return {}
    rebased = [{"date": r["date"], "nav": r["nav"] / sub[0]["nav"]} for r in sub]
    cagr = metrics.cagr_from_nav(rebased)
    mdd, pd_, td_ = metrics.max_drawdown(rebased)
    wy, wret = metrics.worst_calendar_year(rebased)
    return {
        "cagr": cagr,
        "max_drawdown": mdd,
        "max_drawdown_peak": pd_,
        "max_drawdown_trough": td_,
        "worst_year": wy,
        "worst_year_return": wret,
        "start_nav_rebased_final": rebased[-1]["nav"],
    }


def run_all(start_year, end_year, label, year_winners, calendar):
    variants = {
        "1_top1_nofilter": (make_targets_fn(year_winners, "top1"), False),
        "2_top1_sma200": (make_targets_fn(year_winners, "top1"), True),
        "3_top5_sma200": (make_targets_fn(year_winners, "top5"), True),
        "4_sector5_sma200": (make_targets_fn(year_winners, "sector5"), True),
    }

    out = {}
    for name, (targets_fn, use_filter) in variants.items():
        res = strategy.run_variant(name, targets_fn, use_filter, start_year, end_year)
        nav_series = metrics.build_nav_series(res["monthly_values"])
        cagr = metrics.cagr_from_nav(nav_series)
        mdd, pd_, td_ = metrics.max_drawdown(nav_series)
        wy, wret = metrics.worst_calendar_year(nav_series)
        irr = metrics.money_weighted_irr(res["monthly_values"])
        n_contrib_months = len(res["monthly_values"])
        total_contributed = n_contrib_months * strategy.CONTRIBUTION

        out[name] = {
            "final_value": res["final_value"],
            "total_contributed": total_contributed,
            "total_tax_paid": res["total_tax_paid"],
            "total_costs_paid": res["total_costs_paid"],
            "nav_cagr": cagr,
            "money_weighted_irr": irr,
            "max_drawdown": mdd,
            "max_drawdown_peak": pd_,
            "max_drawdown_trough": td_,
            "worst_calendar_year": wy,
            "worst_calendar_year_return": wret,
            "first_half_1996_2010": half_metrics(nav_series, 1996, 2010),
            "second_half_2011_2025": half_metrics(nav_series, 2011, 2025),
            "yearly": res["yearly"],
        }
        print(f"[{label}] {name}: final=${res['final_value']:,.0f} contributed=${total_contributed:,.0f} "
              f"CAGR(nav)={cagr:.1%} IRR={irr:.1%} maxDD={mdd:.1%} worstYr={wy}({wret:.1%}) "
              f"tax=${res['total_tax_paid']:,.0f} costs=${res['total_costs_paid']:,.0f}")

    bench = strategy.run_benchmark(start_year, end_year)
    bnav = metrics.build_nav_series(bench["monthly_values"])
    bcagr = metrics.cagr_from_nav(bnav)
    bmdd, bpd, btd = metrics.max_drawdown(bnav)
    bwy, bwret = metrics.worst_calendar_year(bnav)
    birr = metrics.money_weighted_irr(bench["monthly_values"])
    out["benchmark_spy_drip"] = {
        "final_value": bench["final_value"],
        "total_contributed": len(bench["monthly_values"]) * strategy.CONTRIBUTION,
        "total_tax_paid": 0.0,
        "total_costs_paid": bench["total_costs_paid"],
        "nav_cagr": bcagr,
        "money_weighted_irr": birr,
        "max_drawdown": bmdd,
        "max_drawdown_peak": bpd,
        "max_drawdown_trough": btd,
        "worst_calendar_year": bwy,
        "worst_calendar_year_return": bwret,
        "first_half_1996_2010": half_metrics(bnav, 1996, 2010),
        "second_half_2011_2025": half_metrics(bnav, 2011, 2025),
        "yearly": bench["yearly"],
    }
    print(f"[{label}] benchmark_spy_drip: final=${bench['final_value']:,.0f} "
          f"CAGR(nav)={bcagr:.1%} IRR={birr:.1%} maxDD={bmdd:.1%} worstYr={bwy}({bwret:.1%})")

    return out


def main():
    year_winners = load_year_winners()
    calendar = priceio.trading_calendar()

    print("=== SANITY CHECK: 1996-2010 only ===")
    sanity = run_all(1996, 2010, "sanity-1996-2010", year_winners, calendar)
    (RESULTS_DIR / "sanity_1996_2010.json").write_text(json.dumps(sanity, indent=1))

    print("\n=== FULL RUN: 1996-2025 (out-of-sample 2011-2025 included, run once) ===")
    full = run_all(1996, 2025, "full-1996-2025", year_winners, calendar)
    (RESULTS_DIR / "full_1996_2025.json").write_text(json.dumps(full, indent=1))


if __name__ == "__main__":
    main()
