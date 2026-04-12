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
BATCH_SIZE      = 24

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

# Fix #1 — DCF growth cap ανά sector
# Αποτρέπει unrealistic g assumptions (π.χ. BIIB 19%)
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

# Fix #2 — Graham Formula exclusions
# Σε αυτούς τους κλάδους η Graham Formula παράγει artifacts
GRAHAM_EXCLUDED_SECTORS = {
    "Financials",        # Διαφορετική κεφαλαιακή δομή — P/B είναι ο σωστός δείκτης
    "Consumer Cyclical", # Cyclical earnings → formula εκτινάσσεται
    "Energy",            # Commodity-driven earnings, όχι stable growth
    "Real Estate",       # Asset-based αποτίμηση, όχι earnings-based
}

# Fix #3 — Sector base risk για καλύτερη διαφοροποίηση
SECTOR_BASE_RISK = {
    "Technology":             1,
    "Communication Services": 0,
    "Financials":             2,   # macro + leverage sensitive
    "Healthcare":             0,   # defensive
    "Energy":                 2,   # commodity + geopolitical
    "Consumer Cyclical":      2,   # airlines, auto = υψηλός κίνδυνος
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
        return None  # N/A — formula δεν εφαρμόζεται σε αυτόν τον κλάδο
    if not eps or eps <= 0:
        return None
    return round(eps * (8.5 + 2 * g_pct) * (4.4 / bond_yield), 2)

def risk_score(pe, pb, beta, de, sector):
    sr = SECTOR_RISK.get(sector, {"macro": "medium", "sector": "medium"})

    # Valuation risk
    if pe and pe < 12 and pb and pb < 1.2:
        val_risk = "low"
    elif pe and pe > 30:
        val_risk = "high"
    else:
        val_risk = "medium"

    # Business risk — Fix #3: ενισχυμένα thresholds
    if (de and de > 2) or (beta and beta > 1.5):
        biz_risk = "high"
    elif (de and de > 1) or (beta and beta > 1.2):
        biz_risk = "medium"
    elif de and de < 0.5 and beta and beta < 0.8:
        biz_risk = "low"
    else:
        biz_risk = "medium"

    levels   = {"low": 0, "medium": 1, "high": 2}
    # Fix #3: προσθέτουμε sector base risk ως 5η διάσταση
    base     = SECTOR_BASE_RISK.get(sector, 1)
    avg      = (levels[val_risk] + levels[biz_risk] +
                levels[sr["macro"]] + levels[sr["sector"]] + base) / 5
    overall  = "low" if avg < 0.6 else ("high" if avg > 1.2 else "medium")

    return {
        "business":  biz_risk,
        "valuation": val_risk,
        "macro":     sr["macro"],
        "sector":    sr["sector"],
        "overall":   overall,
    }

def calc_52w_proximity(price, low52, high52):
    """
    Πόσο % πάνω από το 52-week low είναι η τρέχουσα τιμή.
    <15% = behavioral buying zone (αγορά υπεραντέδρασε)
    15-30% = neutral
    >30% = απομακρύνθηκε από low
    """
    try:
        low  = safe_float(low52)
        high = safe_float(high52)
        if low <= 0 or price <= 0:
            return None, None
        pct_from_low  = round((price - low) / low * 100, 1)
        pct_from_high = round((high - price) / high * 100, 1)
        if pct_from_low < 15:
            flag = "near_low"      # Strong behavioral signal
        elif pct_from_low < 30:
            flag = "neutral"
        else:
            flag = "away_from_low"
        return pct_from_low, flag
    except:
        return None, None

def calc_fragility(de, current_ratio, beta):
    """
    Taleb-inspired fragility score.
    Fragile = υψηλό χρέος + χαμηλή ρευστότητα + υψηλή μεταβλητότητα.
    """
    score = 0
    if de and de > 2:
        score += 2
    elif de and de > 1:
        score += 1
    if beta and beta > 1.3:
        score += 2
    elif beta and beta > 1.0:
        score += 1
    if score <= 1:
        return "antifragile"
    elif score <= 3:
        return "neutral"
    else:
        return "fragile"

def screen_ticker(ticker):
    try:
        ov = alpha_get("OVERVIEW", ticker)
        if not ov or not ov.get("Symbol"):
            raise ValueError("Empty overview")

        pe        = safe_float(ov.get("TrailingPE"))           or None
        pb        = safe_float(ov.get("PriceToBookRatio"))     or None
        eps       = safe_float(ov.get("EPS"))                  or None
        beta      = safe_float(ov.get("Beta"), 1)              or 1.0
        de        = safe_float(ov.get("DebtToEquityRatio"))    or None
        roe       = safe_float(ov.get("ReturnOnEquityTTM"))    or None
        div       = safe_float(ov.get("DividendYield"))
        sector    = ov.get("Sector", "Unknown")
        target    = safe_float(ov.get("AnalystTargetPrice"))   or None
        high52    = ov.get("52WeekHigh")
        low52     = ov.get("52WeekLow")
        g_est     = safe_float(ov.get("QuarterlyEarningsGrowthYOY"), 0.08) or 0.08
        ev_ebitda = safe_float(ov.get("EVToEBITDA"))           or None
        ma50      = safe_float(ov.get("50DayMovingAverage"))
        shares    = safe_float(ov.get("SharesOutstanding"))

        # Price: EPS × PE fallback → 50DMA
        price = None
        if eps and pe:
            price = round(abs(eps) * abs(pe), 2)
        if not price and ma50 > 0:
            price = ma50
        if not price:
            raise ValueError("No price available")

        w      = wacc(beta)
        # Fix #1: g cap ανά sector — αποτρέπει BIIB-style 19% g assumptions
        sector_cap = SECTOR_G_CAP.get(sector, 0.12)
        g_base = max(0.02, min(abs(g_est), sector_cap))
        g_bear = max(0.01, g_base - 0.06)
        g_bull = min(0.25, g_base + 0.08)

        # Fat tail bear case (Taleb): extra -3% growth, +2% WACC
        g_bear_fat = max(0.005, g_bear - 0.03)

        fcf_ps       = eps * 0.7 if eps else None
        dcf_base     = dcf_value(fcf_ps, g_base, w)
        dcf_bear     = dcf_value(fcf_ps, g_bear_fat, w + 0.02)  # fat tail
        dcf_bull     = dcf_value(fcf_ps, g_bull, w - 0.010)
        # Fix #2: sector-aware Graham Formula
        gv           = graham_value(eps, g_base * 100, sector)

        # ROIC proxy (ROA × leverage)
        roa  = safe_float(ov.get("ReturnOnAssetsTTM")) or None
        roic = round(roa * 100, 1) if roa else None
        roic_vs_wacc = None
        if roic is not None:
            roic_vs_wacc = "positive" if roic > w * 100 else "negative"

        # 52-week proximity (behavioral)
        pct_from_low, w52_flag = calc_52w_proximity(price, low52, high52)

        # Fragility score (Taleb)
        fragility = calc_fragility(de, None, beta)

        # CAPE proxy: usar 10y avg EPS si disponible, sino trailing
        # Alpha Vantage no da 10y EPS history en free tier
        # Usamos trailing PE como proxy y lo marcamos
        cape_proxy = pe  # proxy — no es CAPE real

        def mos(val):
            if val and price and price > 0:
                return round((val - price) / price * 100, 1)
            return None

        # Analyst upside
        analyst_upside = None
        if target and price:
            analyst_upside = round((target - price) / price * 100, 1)

        return {
            "ticker":          ticker,
            "sector":          sector,
            "price":           price,
            "pe":              round(pe, 1)         if pe    else None,
            "pb":              round(pb, 2)         if pb    else None,
            "eps":             eps,
            "beta":            round(beta, 2),
            "wacc":            round(w * 100, 1),
            "de":              round(de, 1)         if de    else None,
            "roe":             round(roe * 100, 1)  if roe   else None,
            "div_yield":       round(div * 100, 2),
            "g_base_pct":      round(g_base * 100, 1),
            "g_cap_pct":       round(sector_cap * 100, 1),  # Fix #1: εμφανίζεται στο email
            "graham_value":    gv,
            "graham_mos":      mos(gv),
            "dcf_bear":        dcf_bear,
            "dcf_base":        dcf_base,
            "dcf_bull":        dcf_bull,
            "dcf_bear_mos":    mos(dcf_bear),
            "dcf_base_mos":    mos(dcf_base),
            "dcf_bull_mos":    mos(dcf_bull),
            "high52":          high52,
            "low52":           low52,
            "pct_from_low":    pct_from_low,
            "w52_flag":        w52_flag,
            "analyst_target":  target,
            "analyst_upside":  analyst_upside,
            "sparkline":       [],
            "risk":            risk_score(pe, pb, beta, de, sector),
            "ev_ebitda":       round(ev_ebitda, 1) if ev_ebitda else None,
            "roic":            roic,
            "roic_vs_wacc":    roic_vs_wacc,
            "fcf_yield":       None,
            "rd_pct":          None,
            "rd_flag":         None,
            "fragility":       fragility,
            "cape_proxy":      round(cape_proxy, 1) if cape_proxy else None,
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def get_batch(df, week_number):
    tickers   = df["ticker"].tolist()
    total     = len(tickers)
    n_batches = max(1, -(-total // BATCH_SIZE))
    batch_idx = (week_number - 1) % n_batches
    start     = batch_idx * BATCH_SIZE
    batch     = tickers[start:start + BATCH_SIZE]
    print(f"Week {week_number} → Batch {batch_idx+1}/{n_batches}: {batch}")
    return batch, batch_idx + 1, n_batches

def apply_filters(df):
    if df.empty or "pe" not in df.columns:
        print("No data to filter.")
        return pd.DataFrame()
    f = df.copy()
    f = f[f["pe"].notna()           & (f["pe"] < 20)]
    f = f[f["pb"].notna()           & (f["pb"] < 2.5)]
    f = f[f["dcf_base_mos"].notna() & (f["dcf_base_mos"] > 15)]
    return f.sort_values("dcf_base_mos", ascending=False)

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
    batch, batch_idx, n_batches = get_batch(WATCHLIST, week_number)

    batch_info = (f"Σήμερα: {today}. Εβδομάδα {week_number}, "
                  f"batch {batch_idx}/{n_batches} ({len(batch)} μετοχές): {', '.join(batch)}.")

    print(f"Starting screener — {batch_info}")

    results = []
    for ticker in batch:
        if "." in ticker:
            print(f"Skipping {ticker}")
            continue
        print(f"Fetching {ticker}...")
        result = screen_ticker(ticker)
        results.append(result)
        time.sleep(13)

    valid = [r for r in results if r]
    if not valid:
        print("No valid data. Exiting.")
        exit(0)

    df        = pd.DataFrame(valid)
    shortlist = apply_filters(df)
    print(f"Shortlist: {len(shortlist)} stocks")

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols = ["ticker","price","dcf_bear","dcf_base","dcf_bull",
                "dcf_bear_mos","dcf_base_mos","dcf_bull_mos","risk",
                "roic","roic_vs_wacc","ev_ebitda","pct_from_low",
                "w52_flag","fragility"]
        summary = claude_summary(
            shortlist[cols].to_json(orient="records"), batch_info
        )

    html = build_html(df, shortlist, summary)
    send_email(html, week_number, batch_idx, n_batches)
