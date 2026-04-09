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

BATCH_SIZE = 24  # Alpha Vantage free: 25 calls/day, 1 call/ticker + 1 buffer

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

def alpha_get(function, symbol, extra={}):
    url    = "https://www.alphavantage.co/query"
    params = {"function": function, "symbol": symbol, "apikey": ALPHA_KEY, **extra}
    r      = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "Error Message" in data or "Note" in data:
        raise ValueError(data.get("Error Message") or data.get("Note"))
    return data

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

def graham_value(eps, g_pct, bond_yield=4.4):
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
    if (de and de > 3) or (beta and beta > 1.5):
        biz_risk = "high"
    elif de and de < 0.5 and beta and beta < 0.8:
        biz_risk = "low"
    else:
        biz_risk = "medium"
    levels  = {"low": 0, "medium": 1, "high": 2}
    avg     = (levels[val_risk] + levels[biz_risk] + levels[sr["macro"]] + levels[sr["sector"]]) / 4
    overall = "low" if avg < 0.75 else ("high" if avg > 1.5 else "medium")
    return {"business": biz_risk, "valuation": val_risk, "macro": sr["macro"], "sector": sr["sector"], "overall": overall}

def safe_float(val, default=0):
    try:
        return float(val or default)
    except:
        return default

def screen_ticker(ticker):
    try:
        # Μόνο 1 call: OVERVIEW περιέχει όλα τα βασικά metrics
        ov = alpha_get("OVERVIEW", ticker)
        if not ov or not ov.get("Symbol"):
            raise ValueError("Empty overview")

        pe        = safe_float(ov.get("TrailingPE"))         or None
        pb        = safe_float(ov.get("PriceToBookRatio"))   or None
        eps       = safe_float(ov.get("EPS"))                or None
        beta      = safe_float(ov.get("Beta"), 1)            or 1.0
        de        = safe_float(ov.get("DebtToEquityRatio"))  or None
        roe       = safe_float(ov.get("ReturnOnEquityTTM"))  or None
        div       = safe_float(ov.get("DividendYield"))
        sector    = ov.get("Sector", "Unknown")
        target    = safe_float(ov.get("AnalystTargetPrice")) or None
        high52    = ov.get("52WeekHigh")
        low52     = ov.get("52WeekLow")
        g_est     = safe_float(ov.get("QuarterlyEarningsGrowthYOY"), 0.08) or 0.08
        ev_ebitda = safe_float(ov.get("EVToEBITDA"))         or None

        # Price: EPS × TrailingPE (proxy — αρκεί για screening)
        price = None
        if eps and pe:
            price = round(eps * pe, 2)
        if not price:
            # Fallback: 50day moving average
            ma50 = safe_float(ov.get("50DayMovingAverage"))
            if ma50 > 0:
                price = ma50
        if not price:
            raise ValueError("No price available")

        w      = wacc(beta)
        g_base = max(0.02, min(abs(g_est), 0.25))
        g_bear = max(0.01, g_base - 0.06)
        g_bull = min(0.35, g_base + 0.08)

        fcf_ps   = eps * 0.7 if eps else None
        dcf_base = dcf_value(fcf_ps, g_base, w)
        dcf_bear = dcf_value(fcf_ps, g_bear, w + 0.015)
        dcf_bull = dcf_value(fcf_ps, g_bull, w - 0.010)
        gv       = graham_value(eps, g_base * 100)

        roic_vs_wacc = None
        roic         = safe_float(ov.get("ReturnOnAssetsTTM")) or None
        if roic:
            roic = round(roic * 100, 1)
            roic_vs_wacc = "positive" if roic > w * 100 else "negative"

        def mos(val):
            if val and price and price > 0:
                return round((val - price) / price * 100, 1)
            return None

        return {
            "ticker":         ticker,
            "sector":         sector,
            "price":          price,
            "pe":             round(pe, 1)        if pe   else None,
            "pb":             round(pb, 2)        if pb   else None,
            "eps":            eps,
            "beta":           round(beta, 2),
            "wacc":           round(w * 100, 1),
            "de":             round(de, 1)        if de   else None,
            "roe":            round(roe * 100, 1) if roe  else None,
            "div_yield":      round(div * 100, 2),
            "g_base_pct":     round(g_base * 100, 1),
            "graham_value":   gv,
            "graham_mos":     mos(gv),
            "dcf_bear":       dcf_bear,
            "dcf_base":       dcf_base,
            "dcf_bull":       dcf_bull,
            "dcf_bear_mos":   mos(dcf_bear),
            "dcf_base_mos":   mos(dcf_base),
            "dcf_bull_mos":   mos(dcf_bull),
            "net_cash_ps":    0,
            "high52":         high52,
            "low52":          low52,
            "analyst_target": target,
            "sparkline":      [],
            "risk":           risk_score(pe, pb, beta, de, sector),
            "ev_ebitda":      round(ev_ebitda, 1) if ev_ebitda else None,
            "roic":           roic,
            "roic_vs_wacc":   roic_vs_wacc,
            "fcf_yield":      None,
            "rd_pct":         None,
            "rd_flag":        None,
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def get_batch(df, week_number):
    """Επιλέγει batch βάσει εβδομάδας — rotation κάθε 5 εβδομάδες"""
    tickers = df["ticker"].tolist()
    total   = len(tickers)
    n_batches = max(1, -(-total // BATCH_SIZE))  # ceiling division
    batch_idx = (week_number - 1) % n_batches
    start = batch_idx * BATCH_SIZE
    end   = start + BATCH_SIZE
    batch = tickers[start:end]
    print(f"Week {week_number} → Batch {batch_idx + 1}/{n_batches}: {batch}")
    return batch

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
            "Δεδομένο shortlist μετοχών (JSON) με DCF Bear/Base/Bull scenarios, "
            "Risk Analysis, ROIC, EV/EBITDA, γράψε 3 bullets στα ελληνικά. "
            "Εστίασε: κορυφαία ευκαιρία βάσει risk-adjusted MoS, κάποια red flag, "
            "και macro context.\n\n" + stocks_json
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
    today        = datetime.date.today()
    week_number  = today.isocalendar()[1]
    tickers_all  = WATCHLIST["ticker"].tolist()
    total        = len(tickers_all)
    n_batches    = max(1, -(-total // BATCH_SIZE))
    batch_idx    = ((week_number - 1) % n_batches) + 1
    batch        = get_batch(WATCHLIST, week_number)

    batch_info = (f"Σήμερα: {today}. Αυτή είναι η εβδομάδα {week_number}, "
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
        time.sleep(13)  # 25 calls/day = ~1 call/58s για ασφάλεια

    valid = [r for r in results if r]
    if not valid:
        print("No valid data. Exiting.")
        exit(0)

    df        = pd.DataFrame(valid)
    shortlist = apply_filters(df)
    print(f"Shortlist: {len(shortlist)} stocks")

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols    = ["ticker","price","dcf_bear","dcf_base","dcf_bull",
                   "dcf_bear_mos","dcf_base_mos","dcf_bull_mos","risk",
                   "roic","roic_vs_wacc","ev_ebitda"]
        summary = claude_summary(shortlist[cols].to_json(orient="records"), batch_info)

    html = build_html(df, shortlist, summary)
    send_email(html, week_number, batch_idx, n_batches)
