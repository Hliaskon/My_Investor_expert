import pandas as pd
import pytest

from conftest import BASE_INFO, ANNUAL_COLS, QUARTERLY_COLS


def _info(**over):
    return {**BASE_INFO, **over}


# ── Βήμα 1: νόμισμα, τιμή, ROIC, WACC ───────────────────────────────

def test_same_currency_eps_unchanged(S, yf):
    yf.infos["US"] = _info()
    r = S.screen_ticker("US", "Industrials")
    assert r["eps"] == 10.0
    assert r["currency_note"] is None and r["data_warning"] is None


def test_gbp_pence_eps_converted(S, yf):
    yf.infos["US"]   = _info()
    yf.infos["UK.L"] = _info(trailingEps=1.0, currentPrice=1000.0, fiftyDayAverage=1000.0,
                             currency="GBp", financialCurrency="GBP")
    us, uk = S.screen_ticker("US", "Industrials"), S.screen_ticker("UK.L", "Industrials")
    assert uk["eps"] == pytest.approx(100.0)               # σε πένες, όπως η τιμή
    assert uk["dcf_base_mos"] == us["dcf_base_mos"]        # ίδια οικονομικά → ίδιο MoS
    assert "GBp" in uk["currency_note"]


def test_currency_mismatch_without_pe_disables_valuation(S, yf):
    yf.infos["ADR"] = _info(trailingPE=None, trailingEps=50.0, financialCurrency="CNY")
    r = S.screen_ticker("ADR", "Technology")
    assert r["eps"] is None and r["dcf_base"] is None
    assert r["data_warning"]


def test_price_far_from_50dma_is_flagged_not_replaced(S, yf):
    yf.infos["CRASH"] = _info(trailingEps=5.0, trailingPE=8.0, currentPrice=40.0)
    r = S.screen_ticker("CRASH", "Industrials")
    assert r["price"] == 40.0
    assert "50DMA" in r["data_warning"]


def test_data_warning_caps_tier_at_hold(S, yf):
    yf.infos["CRASH"] = _info(trailingEps=5.0, trailingPE=8.0, currentPrice=40.0)
    r = S.screen_ticker("CRASH", "Industrials")
    t = S.compute_tier({**r, "dcf_base_mos": 200, "fcf_source": "reported", "graham_mos": 50,
                        "roic_vs_wacc": "positive", "analyst_upside": 30, "analyst_target": 50},
                       favored_sectors=["Industrials"])
    assert t["total_score"] >= 65            # θα ήταν STRONG BUY χωρίς το warning
    assert t["tier"] == "HOLD" and "⚠" in t["tier_reason"]


def test_real_roic_uses_ttm_ebit(S, yf):
    yf.qf["T"] = pd.DataFrame([[30, 25, 25, 20]], index=["EBIT"], columns=QUARTERLY_COLS)
    yf.qb["T"] = pd.DataFrame([[1000] * 4, [200] * 4],
                              index=["Total Assets", "Current Liabilities"], columns=QUARTERLY_COLS)
    roic, trend_up = S.get_real_roic("T")
    assert roic == pytest.approx(100 * 0.79 / 800)   # TTM EBIT 100, IC 800
    assert trend_up is True


def test_real_roic_nan_quarter_falls_back(S, yf):
    yf.qf["T"] = pd.DataFrame([[float("nan"), 25, 25, 20]], index=["EBIT"], columns=QUARTERLY_COLS)
    yf.qb["T"] = pd.DataFrame([[1000] * 4, [200] * 4],
                              index=["Total Assets", "Current Liabilities"], columns=QUARTERLY_COLS)
    assert S.get_real_roic("T") == (None, None)


def test_wacc_floor(S):
    assert S.wacc(0.3) == S.MIN_WACC == 0.08
    assert S.wacc(1.0) == pytest.approx(S.RISK_FREE_RATE + S.ERP)


def test_reconcile_currency_same_ccy_ignores_pe_eps_drift(S):
    # PE/EPS ελαφρώς ασυνεπή (timing) χωρίς ασυμφωνία νομίσματος → καμία "διόρθωση"
    assert S.reconcile_eps_currency(100, 12, 10, "USD", "USD") == (1.0, None)


# ── Βήμα 2: DCF πάνω σε reported FCF ────────────────────────────────

def test_dcf_uses_reported_fcf_and_lowest_growth_source(S, yf):
    yf.infos["A"] = _info(earningsQuarterlyGrowth=0.90)     # θόρυβος τριμήνου — αγνοείται
    yf.cf["A"]  = pd.DataFrame([[7000, 6000, 6000, 5000]], index=["Free Cash Flow"], columns=ANNUAL_COLS)
    yf.fin["A"] = pd.DataFrame([[1331, 1210, 1100, 1000]], index=["Total Revenue"], columns=ANNUAL_COLS)
    yf.ge["A"]  = pd.DataFrame({"stockTrend": [0.1, 0.2, 0.06]}, index=["0q", "0y", "LTG"])
    r = S.screen_ticker("A", "Industrials")
    assert r["fcf_source"] == "reported" and r["fcf_yield"] == 6.0
    assert r["growth_source"] == "analyst_ltg" and r["g_base_pct"] == 6.0   # min(6%, CAGR 10%)
    assert r["dcf_base"] == S.dcf_value(6.0, 0.06, 0.097, terminal_g=0.025)


def test_revenue_cagr_capped_by_sector(S, yf):
    yf.infos["F"] = _info()
    yf.cf["F"]  = pd.DataFrame([[6000] * 4], index=["Free Cash Flow"], columns=ANNUAL_COLS)
    yf.fin["F"] = pd.DataFrame([[1331, 1210, 1100, 1000]], index=["Total Revenue"], columns=ANNUAL_COLS)
    r = S.screen_ticker("F", "Industrials")
    assert r["growth_source"] == "rev_cagr" and r["g_base_pct"] == 8.0      # Industrials cap


def test_no_cashflow_falls_back_to_proxy_without_score(S, yf):
    yf.infos["B"] = _info()
    r = S.screen_ticker("B", "Industrials")
    assert r["fcf_source"] == "eps_proxy" and r["growth_source"] == "default"
    assert r["g_base_pct"] == 3.0 and r["fcf_yield"] is None
    proxy    = S.compute_tier({**r, "dcf_base_mos": 50})
    reported = S.compute_tier({**r, "dcf_base_mos": 50, "fcf_source": "reported"})
    assert reported["valuation_score"] - proxy["valuation_score"] == 15


def test_negative_fcf_and_shrinking_revenue(S, yf):
    yf.infos["C"] = _info()
    yf.cf["C"]  = pd.DataFrame([[-100, -50, 20, 10]], index=["Free Cash Flow"], columns=ANNUAL_COLS)
    yf.fin["C"] = pd.DataFrame([[800, 900, 950, 1000]], index=["Total Revenue"], columns=ANNUAL_COLS)
    r = S.screen_ticker("C", "Industrials")
    assert r["dcf_base"] is None and r["g_base_pct"] == 0.0


def test_fcf_from_ocf_plus_capex(S, yf):
    yf.infos["D"] = _info()
    yf.cf["D"] = pd.DataFrame([[9000] * 4, [-3000] * 4],
                              index=["Operating Cash Flow", "Capital Expenditure"], columns=ANNUAL_COLS)
    assert S.screen_ticker("D", "Industrials")["fcf_yield"] == 6.0


def test_fcf_converted_to_price_currency(S, yf):
    yf.infos["E.L"] = _info(currency="GBp", financialCurrency="GBP", trailingEps=0.1)
    yf.cf["E.L"] = pd.DataFrame([[60] * 4], index=["Free Cash Flow"], columns=ANNUAL_COLS)  # 6p/share
    r = S.screen_ticker("E.L", "Industrials")
    assert r["fcf_yield"] == 6.0 and not r["data_warning"]


def test_terminal_growth_never_exceeds_wacc_spread(S):
    assert S.dcf_value(5, 0.0, 0.08, terminal_g=0.01) < S.dcf_value(5, 0.0, 0.08)
    assert S.dcf_value(-1, 0.05, 0.08) is None
