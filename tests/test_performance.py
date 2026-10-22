import os

import numpy as np
import pandas as pd
import pytest

import performance as P


@pytest.fixture
def linear_prices(yf):
    """SPY/EXSA.DE flat· WIN/SAP.DE +20%/έτος γραμμικά· LOSE −20%/έτος."""
    days = pd.bdate_range("2025-01-01", "2026-10-21")
    lin = np.linspace(0, 1, len(days)) * (len(days) / 252)
    yf.prices = pd.DataFrame({"SPY": 100.0, "EXSA.DE": 50.0,
                              "WIN": 100 * (1 + 0.20 * lin), "LOSE": 100 * (1 - 0.20 * lin),
                              "SAP.DE": 100 * (1 + 0.20 * lin)}, index=days)
    yf.lin = lin
    return yf


def _weekly_snapshots(snap_dir):
    for d in pd.date_range("2025-01-05", "2025-12-28", freq="W-SUN"):
        df = pd.DataFrame({"ticker": ["WIN", "LOSE", "SAP.DE"] + [f"X{i}" for i in range(8)],
                           "tier": ["STRONG BUY", "AVOID", "BUY"] + ["HOLD"] * 8,
                           "tier_score": [80, 10, 60] + list(range(20, 28)),
                           "risk": [{"overall": "low"}] * 11})
        P.save_snapshot(df, snap_dir, d.date())


@pytest.mark.parametrize("ticker, bench", [
    ("AAPL", "SPY"), ("BABA", "SPY"), ("SAP.DE", "EXSA.DE"), ("BP.L", "ISF.L"),
    ("7203.T", "1306.T"), ("0005.HK", "2800.HK"),
])
def test_benchmark_for(ticker, bench):
    assert P.benchmark_for(ticker) == bench


def test_save_snapshot_schema_and_idempotent(tmp_path):
    df = pd.DataFrame({"ticker": ["A"], "tier": ["BUY"], "risk": [{"overall": "low"}]})
    path = P.save_snapshot(df, str(tmp_path), pd.Timestamp("2026-01-04").date())
    P.save_snapshot(df, str(tmp_path), pd.Timestamp("2026-01-04").date())   # ίδια μέρα → overwrite
    assert os.listdir(tmp_path) == ["2026-01-04.csv"]
    s = pd.read_csv(path)
    assert list(s.columns) == ["date"] + P.SNAPSHOT_COLUMNS
    assert s.loc[0, "risk_overall"] == "low"


def test_load_signals_prefers_snapshots(tmp_path, linear_prices):
    snap = str(tmp_path / "snapshots")
    _weekly_snapshots(snap)
    hist = tmp_path / "history.csv"
    pd.DataFrame({"ticker": ["WIN", "LOSE"], "date_flagged": ["2025-01-05", "2024-12-29"],
                  "tier": [None, None], "tier_score": [None, None]}).to_csv(hist, index=False)
    sig = P.load_signals(snap, str(hist))
    assert (sig["source"] == "history").sum() == 1      # 2025-01-05 υπάρχει ως snapshot
    assert sig["date"].nunique() == 53


def test_evaluate_separates_winners_and_losers(tmp_path, linear_prices):
    snap = str(tmp_path / "snapshots")
    _weekly_snapshots(snap)
    res = P.evaluate(snap, str(tmp_path / "missing.csv"), delay=0)
    ts = res["tier_stats"].set_index(["horizon", "tier"])
    assert ts.loc[("3m", "STRONG BUY"), "mean_excess"] > 3
    assert ts.loc[("3m", "STRONG BUY"), "hit_rate"] == 100
    assert ts.loc[("3m", "AVOID"), "mean_excess"] < -3
    assert ts.loc[("3m", "AVOID"), "hit_rate"] == 0
    # Σήματα του Δεκ. 2025 δεν έχουν ολοκληρώσει 12μηνο έως 21/10/2026
    assert ts.loc[("12m", "STRONG BUY"), "n_dates"] < 52
    # X* χωρίς τιμές → <10 παρατηρήσεις ανά ημερομηνία → κανένα IC
    assert res["ic"].empty
    tk = res["tickers"].set_index("ticker")
    assert tk.loc["SAP.DE", "benchmark"] == "EXSA.DE" and tk.loc["SAP.DE", "excess_pct"] > 0


def test_entry_is_first_close_after_signal(linear_prices):
    s = linear_prices.prices["WIN"]
    entry_date, entry_px, _ = P._entry_exit(s, pd.Timestamp("2025-03-07"), 30)   # Παρασκευή
    assert entry_date == pd.Timestamp("2025-03-10")                            # Δευτέρα
    assert entry_px == s.loc["2025-03-10"]


def test_ic_perfect_rank_correlation(linear_prices):
    prices = linear_prices.prices.copy()
    for i in range(12):
        prices[f"Y{i}"] = 100 * (1 + (i - 6) * 0.02 * linear_prices.lin)
    sig = pd.DataFrame({"date": pd.Timestamp("2025-03-02"), "ticker": [f"Y{i}" for i in range(12)],
                        "tier": "HOLD", "tier_score": list(range(12)), "source": "snapshot"})
    ic = P.ic_stats(P.forward_returns(sig, prices)).set_index("horizon")
    assert ic.loc["3m", "mean_ic"] == pytest.approx(1.0)


def test_ic_skips_constant_returns(linear_prices):
    prices = linear_prices.prices.copy()
    for i in range(12):
        prices[f"Z{i}"] = 100.0
    sig = pd.DataFrame({"date": pd.Timestamp("2025-03-02"), "ticker": [f"Z{i}" for i in range(12)],
                        "tier": "HOLD", "tier_score": list(range(12)), "source": "snapshot"})
    assert P.ic_stats(P.forward_returns(sig, prices)).empty
