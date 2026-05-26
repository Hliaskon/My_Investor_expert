import pandas as pd
import os, smtplib, time, requests, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from report import build_html

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
WATCHLIST  = pd.read_csv(os.path.join(BASE_DIR, "watchlist.csv"))
ALPHA_KEY  = os.environ.get("ALPHA_KEY", "")

RISK_FREE_RATE  = 0.042
ERP             = 0.055
TERMINAL_GROWTH = 0.025
BATCH_SIZE      = 40   # ↑ από 24 — καλύπτει μεγαλύτερο universe

# ─────────────────────────────────────────────────────────────────────
# FIX A: Alpha Vantage sector name normalization
# AV επιστρέφει "Financial Services", "Health Care" κλπ.
# Τα δικά μας ονόματα: "Financials", "Healthcare" κλπ.
# Fallback μόνο — primary source είναι πάντα το watchlist.csv
# ─────────────────────────────────────────────────────────────────────
SECTOR_AV_MAP = {
    "Financial Services":     "Financials",
    "Finance":                "Financials",
    "FINANCE":                "Financials",
    "Health Care":            "Healthcare",
    "HEALTH CARE":            "Healthcare",
    "Consumer Discretionary": "Consumer Cyclical",
    "Consumer Staples":       "Consumer Defensive",
    "Information Technology": "Technology",
    "INFORMATION TECHNOLOGY": "Technology",
    "Materials":              "Basic Materials",
    "MATERIALS":              "Basic Materials",
}

def normalize_sector(av_sector: str) -> str:
    return SECTOR_AV_MAP.get(av_sector, av_sector)

SECTOR_RISK = {
    "Technology":             {"macro": "low",    "sector": "medium"},
    "Communication Services": {"macro": "low",    "sector": "medium"},
    "Financials":             {"macro": "high",   "sector": "medium"},
    "Healthcare":             {"macro": "low",    "sector": "medium"},
    "Energy":                 {"macro": "high",   "sector": "high"},
    "Consumer Cyclical":      {"macro": "medium", "sector": "medium"},
    "Consumer Defensive":     {"macro": "low",    "sector": "low"},
    "Industrials":            {"macro": "medium", "sector": "low"},
    "Basic Materials":        {"macro": "high",   "sector": "high"},
    "Real Estate":            {"macro": "high",   "sector": "medium"},
    "Utilities":              {"macro": "low",    "sector": "low"},
}

SECTOR_G_CAP = {
    "Technology":             0.15,
    "Communication Services": 0.10,
    "Financials":             0.08,
    "Healthcare":             0.12,
    "Energy":                 0.07,
    "Consumer Cyclical":      0.10,
    "Consumer Defensive":     0.06,
    "Industrials":            0.08,
    "Basic Materials":        0.07,
    "Real Estate":            0.06,
    "Utilities":              0.05,
}

GRAHAM_EXCLUDED_SECTORS = {
    "Financials",
    "Consumer Cyclical",
    "Energy",
    "Real Estate",
}

SECTOR_BASE_RISK = {
    "Technology":             1,
    "Communication Services": 0,
    "Financials":             2,
    "Healthcare":             0,
    "Energy":                 2,
    "Consumer Cyclical":      2,
    "Consumer Defensive":     0,
    "Industrials":            1,
    "Basic Materials":        2,
    "Real Estate":            1,
    "Utilities":              0,
}


def alpha_get(function, symbol, extra={}):
    url    = "https://www.alphavantage.co/query"
    params = {"function": function, "symbol": symbol, "apikey": ALPHA_KEY, **extra}
    r      = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "Error Message" in data or "Note" in data:
        raise ValueError(data.get("Error Message") or data.get("Note"))
    return data

def safe_float(val, default=0):
    try:
        return float(val or default)
    except:
        return default

def wacc(beta):
    return RISK_FREE_RATE + beta * ERP

def dcf_value(fcf_per_share, g_rate, wacc_rate, years=5):
    if not fcf_per_share or fcf_per_share <= 0:
        return None
    total = 0
    for t in range(1, years + 1):
        total += fcf_per_share * (1 + g_rate)**t / (1 + wacc_rate)**t
    fcf5     = fcf_per_share * (1 + g_rate)**years
    terminal = fcf5 * (1 + TERMINAL_GROWTH) / (wacc_rate - TERMINAL_GROWTH)
    total   += terminal / (1 + wacc_rate)**years
    return round(total, 2)

def graham_value(eps, g_pct, sector, bond_yield=4.4):
    if sector in GRAHAM_EXCLUDED_SECTORS:
        return None
    if not eps or eps <= 0:
        return None
    return round(eps * (8.5 + 2 * g_pct) * (4.4 / bond_yield), 2)

def risk_score(pe, pb, beta, de, sector):
    sr = SECTOR_RISK.get(sector, {"macro": "medium", "sector": "medium"})
    if pe and pe < 12 and pb and pb < 1.2:
        val_risk = "low"
    elif pe and pe > 30:
        val_risk = "high"
    else:
        val_risk = "medium"
    if (de and de > 2) or (beta and beta > 1.5):
        biz_risk = "high"
    elif (de and de > 1) or (beta and beta > 1.2):
        biz_risk = "medium"
    elif de and de < 0.5 and beta and beta < 0.8:
        biz_risk = "low"
    else:
        biz_risk = "medium"
    levels  = {"low": 0, "medium": 1, "high": 2}
    base    = SECTOR_BASE_RISK.get(sector, 1)
    avg     = (levels[val_risk] + levels[biz_risk] +
               levels[sr["macro"]] + levels[sr["sector"]] + base) / 5
    overall = "low" if avg < 0.6 else ("high" if avg > 1.2 else "medium")
    return {"business": biz_risk, "valuation": val_risk,
            "macro": sr["macro"], "sector": sr["sector"], "overall": overall}

def calc_52w_proximity(price, low52, high52):
    try:
        low  = safe_float(low52)
        high = safe_float(high52)
        if low <= 0 or price <= 0:
            return None, None
        pct_from_low = round((price - low) / low * 100, 1)
        if pct_from_low < 15:   flag = "near_low"
        elif pct_from_low < 30: flag = "neutral"
        else:                   flag = "away_from_low"
        return pct_from_low, flag
    except:
        return None, None

def calc_fragility(de, current_ratio, beta):
    score = 0
    if de and de > 2:        score += 2
    elif de and de > 1:      score += 1
    if beta and beta > 1.3:  score += 2
    elif beta and beta > 1.0: score += 1
    if score <= 1:   return "antifragile"
    elif score <= 3: return "neutral"
    else:            return "fragile"


def screen_ticker(ticker: str, watchlist_sector: str = None) -> dict | None:
    """
    Full Tier-1 analysis for one ticker.

    watchlist_sector: sector from watchlist.csv (authoritative).
    If None, falls back to Alpha Vantage sector name (normalized via SECTOR_AV_MAP).

    FIX A: Alpha Vantage returns "Financial Services" for banks, "Health Care"
    for healthcare stocks — not matching our internal "Financials"/"Healthcare".
    This caused all financial/healthcare stocks to fail the sector filter silently.
    """
    try:
        ov = alpha_get("OVERVIEW", ticker)
        if not ov or not ov.get("Symbol"):
            raise ValueError("Empty overview")

        pe        = safe_float(ov.get("TrailingPE"))           or None
        pb        = safe_float(ov.get("PriceToBookRatio"))     or None
        eps       = safe_float(ov.get("EPS"))                  or None
        beta      = max(0.3, safe_float(ov.get("Beta"), 1) or 1.0)
        de        = safe_float(ov.get("DebtToEquityRatio"))    or None
        roe       = safe_float(ov.get("ReturnOnEquityTTM"))    or None
        div       = safe_float(ov.get("DividendYield"))
        target    = safe_float(ov.get("AnalystTargetPrice"))   or None
        high52    = ov.get("52WeekHigh")
        low52     = ov.get("52WeekLow")
        g_est     = safe_float(ov.get("QuarterlyEarningsGrowthYOY"), 0.08) or 0.08
        ev_ebitda = safe_float(ov.get("EVToEBITDA"))           or None
        ma50      = safe_float(ov.get("50DayMovingAverage"))

        # ── FIX A: sector source priority ────────────────────────────
        # 1st: watchlist.csv sector (already normalized, always correct)
        # 2nd: Alpha Vantage sector → normalize via SECTOR_AV_MAP
        # 3rd: "Unknown" fallback
        av_sector = ov.get("Sector", "Unknown")
        sector    = watchlist_sector if watchlist_sector else normalize_sector(av_sector)
        if not watchlist_sector and av_sector != sector:
            print(f"  [sector] {ticker}: AV='{av_sector}' → normalized='{sector}'")
        # ─────────────────────────────────────────────────────────────

        price = None
        if eps and pe:
            price = round(abs(eps) * abs(pe), 2)
        if not price and ma50 > 0:
            price = ma50
        if not price:
            raise ValueError("No price available")

        w          = wacc(beta)
        sector_cap = SECTOR_G_CAP.get(sector, 0.12)
        g_base     = max(0.02, min(abs(g_est), sector_cap))
        g_bear_fat = max(0.005, max(0.01, g_base - 0.06) - 0.03)
        g_bull     = min(0.25, g_base + 0.08)

        fcf_ps   = eps * 0.7 if eps else None
        dcf_base = dcf_value(fcf_ps, g_base, w)
        dcf_bear = dcf_value(fcf_ps, g_bear_fat, w + 0.02)
        dcf_bull = dcf_value(fcf_ps, g_bull, w - 0.010)
        gv       = graham_value(eps, g_base * 100, sector)

        roe_quality = None
        if roe is not None:
            roe_pct = round(roe * 100, 1)
            roe_quality = "strong" if roe_pct >= 15 else ("moderate" if roe_pct >= 10 else "weak")

        roic_proxy = roic_vs_wacc = None
        if roe is not None:
            roe_pct    = round(roe * 100, 1)
            roic_proxy = round(roe_pct * (1 / (1 + de)), 1) if (de and de > 0) else roe_pct
            roic_vs_wacc = "positive" if roic_proxy > round(w * 100, 1) else "negative"

        pct_from_low, w52_flag = calc_52w_proximity(price, low52, high52)
        fragility              = calc_fragility(de, None, beta)

        def mos(val):
            if val and price and price > 0:
                return round((val - price) / price * 100, 1)
            return None

        analyst_upside = round((target - price) / price * 100, 1) if (target and price) else None

        return {
            "ticker":         ticker,
            "sector":         sector,
            "price":          price,
            "pe":             round(pe, 1)         if pe    else None,
            "pb":             round(pb, 2)         if pb    else None,
            "eps":            eps,
            "beta":           round(beta, 2),
            "wacc":           round(w * 100, 1),
            "de":             round(de, 1)         if de    else None,
            "roe":            round(roe * 100, 1)  if roe   else None,
            "div_yield":      round(div * 100, 2),
            "g_base_pct":     round(g_base * 100, 1),
            "g_cap_pct":      round(sector_cap * 100, 1),
            "graham_value":   gv,
            "graham_mos":     mos(gv),
            "dcf_bear":       dcf_bear,
            "dcf_base":       dcf_base,
            "dcf_bull":       dcf_bull,
            "dcf_bear_mos":   mos(dcf_bear),
            "dcf_base_mos":   mos(dcf_base),
            "dcf_bull_mos":   mos(dcf_bull),
            "high52":         high52,
            "low52":          low52,
            "pct_from_low":   pct_from_low,
            "w52_flag":       w52_flag,
            "analyst_target": target,
            "analyst_upside": analyst_upside,
            "sparkline":      [],
            "risk":           risk_score(pe, pb, beta, de, sector),
            "ev_ebitda":      round(ev_ebitda, 1) if ev_ebitda else None,
            "roic":           roic_proxy,
            "roic_vs_wacc":   roic_vs_wacc,
            "roe_quality":    roe_quality,
            "fcf_yield":      None,
            "rd_pct":         None,
            "rd_flag":        None,
            "fragility":      fragility,
            "cape_proxy":     round(pe, 1) if pe else None,
            "macro_favored":  False,   # overwritten by apply_filters()
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None


def get_batch(df: pd.DataFrame, week_number: int):
    """
    Returns current batch as DataFrame slice — preserves all columns
    including 'sector' for passing to screen_ticker().
    """
    total     = len(df)
    n_batches = max(1, -(-total // BATCH_SIZE))
    batch_idx = (week_number - 1) % n_batches
    start     = batch_idx * BATCH_SIZE
    batch_df  = df.iloc[start : start + BATCH_SIZE].copy()
    print(f"Week {week_number} → Batch {batch_idx+1}/{n_batches} "
          f"({len(batch_df)} stocks): {batch_df['ticker'].tolist()}")
    return batch_df, batch_idx + 1, n_batches


def apply_filters(df: pd.DataFrame, favored_sectors=None) -> pd.DataFrame:
    """
    Value investing filters with per-filter diagnostics.

    FIX B: Macro sector filter → SOFT alignment scoring (was hard exclusion).

    Previous: f = f[f["sector"].isin(favored_sectors)]
    → CI Healthcare +169% DCF, PFE +54%, WFC Financials +31% all blocked silently.

    New: stocks in favored sectors sorted first, all qualifying stocks visible.
    Macro alignment remains informational via alignment_map in the email.
    """
    if df.empty or "pe" not in df.columns:
        print("[FILTER] No data.")
        return pd.DataFrame()

    f  = df.copy()
    n0 = len(f)

    # ── P/E < 20 ──────────────────────────────────────────────────────
    mask = f["pe"].notna() & (f["pe"] < 20)
    excl = f[~mask]["ticker"].tolist()
    f    = f[mask]
    print(f"[FILTER] P/E < 20:      {len(f):>3}/{n0} pass | excl {len(excl)}: {excl}")

    # ── P/B < 2.5 ─────────────────────────────────────────────────────
    n1   = len(f)
    mask = f["pb"].notna() & (f["pb"] < 2.5)
    excl = f[~mask]["ticker"].tolist()
    f    = f[mask]
    print(f"[FILTER] P/B < 2.5:     {len(f):>3}/{n1} pass | excl {len(excl)}: {excl}")

    # ── DCF Base MoS > 15% ────────────────────────────────────────────
    n2   = len(f)
    mask = f["dcf_base_mos"].notna() & (f["dcf_base_mos"] > 15)
    excl = f[~mask]["ticker"].tolist()
    f    = f[mask]
    print(f"[FILTER] DCF MoS >15%:  {len(f):>3}/{n2} pass | excl {len(excl)}: {excl}")

    # ── Macro: SOFT sort (NOT exclusion) ──────────────────────────────
    if favored_sectors and len(f) > 0:
        f["macro_favored"] = f["sector"].isin(favored_sectors)
        n_fav = int(f["macro_favored"].sum())
        print(f"[FILTER] Macro align:   {n_fav}/{len(f)} in favored sectors "
              f"— sorted first, others NOT excluded")
        f = f.sort_values(["macro_favored", "dcf_base_mos"], ascending=[False, False])
    else:
        f["macro_favored"] = False
        f = f.sort_values("dcf_base_mos", ascending=False)

    # ── ROIC warning (informational) ──────────────────────────────────
    if "roic_vs_wacc" in f.columns:
        destroyers = f[f["roic_vs_wacc"] == "negative"]["ticker"].tolist()
        if destroyers:
            print(f"[WARNING] ROIC < WACC: {destroyers}")

    print(f"[FILTER] ── Shortlist: {len(f)} stocks ──")
    return f


def claude_summary(stocks_json, batch_info):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        messages=[{"role": "user", "content":
            f"Είσαι value investing assistant. {batch_info}\n"
            "Δεδομένο shortlist μετοχών (JSON) με DCF Bear/Base/Bull, Risk, "
            "ROIC vs WACC, EV/EBITDA, 52w low proximity, fragility score, "
            "γράψε 3 bullets στα ελληνικά. Εστίασε: κορυφαία ευκαιρία "
            "βάσει risk-adjusted MoS, κάποια red flag, macro context.\n\n"
            + stocks_json
        }]
    )
    return msg.content[0].text


def send_email(html_body, week_number, batch_idx, n_batches):
    sender   = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    receiver = os.environ["EMAIL_RECEIVER"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Stock Screener — Εβδομάδα {week_number} (Batch {batch_idx}/{n_batches})"
    msg["From"]    = sender
    msg["To"]      = receiver
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(sender, password)
        s.sendmail(sender, receiver, msg.as_string())
    print("Email sent!")


if __name__ == "__main__":
    today       = datetime.date.today()
    week_number = today.isocalendar()[1]

    # FIX A: get_batch returns DataFrame (preserves sector column)
    batch_df, batch_idx, n_batches = get_batch(WATCHLIST, week_number)

    batch_info = (f"Σήμερα: {today}. Εβδομάδα {week_number}, "
                  f"batch {batch_idx}/{n_batches} ({len(batch_df)} μετοχές): "
                  f"{', '.join(batch_df['ticker'].tolist())}.")
    print(f"Starting screener — {batch_info}")

    results = []
    for _, row in batch_df.iterrows():
        ticker = str(row["ticker"])
        if "." in ticker:
            print(f"Skipping {ticker}")
            continue
        # FIX A: pass watchlist sector — authoritative, no AV mismatch
        ws = str(row["sector"]) if "sector" in row.index and pd.notna(row["sector"]) else None
        print(f"Fetching {ticker} (sector: {ws})...")
        results.append(screen_ticker(ticker, watchlist_sector=ws))
        time.sleep(13)

    valid = [r for r in results if r]
    if not valid:
        print("No valid data. Exiting.")
        exit(0)

    df              = pd.DataFrame(valid)
    favored_sectors = []
    macro_html      = ""
    alignment_map   = {}

    if os.environ.get("FRED_API_KEY"):
        try:
            from fredapi import Fred
            from macro_regime import (
                get_macro_inputs, classify_regime, yield_curve_signal,
                fear_liquidity_score, calculate_sector_pe,
                evaluate_sector_valuation, check_stock_macro_alignment,
                render_macro_html,
            )
            fred        = Fred(api_key=os.environ["FRED_API_KEY"])
            macro_in    = get_macro_inputs(fred)
            regime      = classify_regime(macro_in)
            yield_sig   = yield_curve_signal(macro_in["yield_spread"])
            fear        = fear_liquidity_score(macro_in)
            sector_pe   = calculate_sector_pe(df)
            sector_vals = evaluate_sector_valuation(sector_pe)
            macro_html  = render_macro_html(macro_in, regime, yield_sig, fear, sector_vals)
            favored_sectors = regime.get("favored_sectors", [])
            for _, r in df.iterrows():
                alignment_map[r["ticker"]] = check_stock_macro_alignment(r["sector"], regime)
            print(f"Macro: {regime['regime']} — favored: {favored_sectors}")
        except Exception as e:
            print(f"[MACRO WARNING] {e} — continuing without macro")
            macro_html = "<p style='color:#888;font-size:12px;padding:10px'>⚠️ Macro data unavailable.</p>"
    else:
        print("FRED_API_KEY not set — skipping macro overlay")

    # FIX B: soft sector filter
    shortlist = apply_filters(df, favored_sectors=favored_sectors)

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols = ["ticker", "price", "dcf_bear", "dcf_base", "dcf_bull",
                "dcf_bear_mos", "dcf_base_mos", "dcf_bull_mos", "risk",
                "roic", "roic_vs_wacc", "ev_ebitda", "pct_from_low",
                "w52_flag", "fragility", "macro_favored"]
        summary = claude_summary(shortlist[cols].to_json(orient="records"), batch_info)

    html = build_html(df, shortlist, summary, macro_html=macro_html,
                      alignment_map=alignment_map,
                      batch_idx=batch_idx, n_batches=n_batches)
    send_email(html, week_number, batch_idx, n_batches)
