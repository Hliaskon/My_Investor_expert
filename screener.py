import pandas as pd
import os, smtplib, time, random, requests, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from report import build_html

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
WATCHLIST  = pd.read_csv(os.path.join(BASE_DIR, "watchlist.csv"))
ALPHA_KEY  = os.environ.get("ALPHA_KEY", "")

RISK_FREE_RATE  = 0.042
ERP             = 0.055
TERMINAL_GROWTH = 0.025

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

def screen_ticker(ticker):
    try:
        # Call 1: OVERVIEW
        ov = alpha_get("OVERVIEW", ticker)
        if not ov or not ov.get("Symbol"):
            raise ValueError("Empty overview")
        time.sleep(13)

        # Call 2: GLOBAL_QUOTE
        q   = alpha_get("GLOBAL_QUOTE", ticker)
        gq  = q.get("Global Quote", {})
        print(f"  GQ keys: {list(gq.keys())}")

        price = None
        for k, v in gq.items():
            if "price" in k.lower():
                try:
                    price = float(v)
                except Exception:
                    pass
                break

        if not price:
            # Fallback: EPS * PE από OVERVIEW
            eps_ov = float(ov.get("EPS", 0) or 0)
            pe_ov  = float(ov.get("TrailingPE", 0) or 0)
            if eps_ov > 0 and pe_ov > 0:
                price = round(eps_ov * pe_ov, 2)
                print(f"  Using fallback price: {price}")
            else:
                raise ValueError("No price available")

        pe     = float(ov.get("TrailingPE",              0) or 0) or None
        pb     = float(ov.get("PriceToBookRatio",         0) or 0) or None
        eps    = float(ov.get("EPS",                      0) or 0) or None
        beta   = float(ov.get("Beta",                     1) or 1)
        de     = float(ov.get("DebtToEquityRatio",        0) or 0) or None
        roe    = float(ov.get("ReturnOnEquityTTM",        0) or 0) or None
        div    = float(ov.get("DividendYield",            0) or 0)
        sector = ov.get("Sector", "Unknown")
        target = float(ov.get("AnalystTargetPrice",       0) or 0) or None
        high52 = ov.get("52WeekHigh")
        low52  = ov.get("52WeekLow")
        g_est  = float(ov.get("QuarterlyEarningsGrowthYOY", 0.08) or 0.08)

        fcf_ps = eps * 0.7 if eps else None
        w      = wacc(beta)
        g_base = max(0.02, min(abs(g_est), 0.25))
        g_bear = max(0.01, g_base - 0.06)
        g_bull = min(0.35, g_base + 0.08)

        dcf_base = dcf_value(fcf_ps, g_base, w)
        dcf_bear = dcf_value(fcf_ps, g_bear, w + 0.015)
        dcf_bull = dcf_value(fcf_ps, g_bull, w - 0.010)
        gv       = graham_value(eps, g_base * 100)

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
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def apply_filters(df):
    if df.empty or "pe" not in df.columns:
        print("No data to filter.")
        return pd.DataFrame()
    f = df.copy()
    f = f[f["pe"].notna()           & (f["pe"] < 20)]
    f = f[f["pb"].notna()           & (f["pb"] < 2.5)]
    f = f[f["dcf_base_mos"].notna() & (f["dcf_base_mos"] > 15)]
    return f.sort_values("dcf_base_mos", ascending=False)

def claude_summary(stocks_json):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=700,
        messages=[{"role": "user", "content":
            "Είσαι value investing assistant. Δεδομένο shortlist μετοχών (JSON) "
            "με DCF Bear/Base/Bull scenarios και Risk Analysis, γράψε 3 bullets "
            "στα ελληνικά. Εστίασε: κορυφαία ευκαιρία βάσει risk-adjusted MoS, "
            "κάποια red flag, και macro context.\n\n" + stocks_json
        }]
    )
    return msg.content[0].text

def send_email(html_body):
    sender   = os.environ["EMAIL_SENDER"]
    password = os.environ["EMAIL_PASSWORD"]
    receiver = os.environ["EMAIL_RECEIVER"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "📊 Weekly Stock Screener — DCF & Risk Report"
    msg["From"]    = sender
    msg["To"]      = receiver
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(sender, password)
        s.sendmail(sender, receiver, msg.as_string())
    print("Email sent!")

if __name__ == "__main__":
    # week_number = datetime.date.today().isocalendar()[1]
    # if week_number % 2 != 0:
    #     print(f"Week {week_number} — skipping (odd week)")
    #     exit(0)

    print("Starting screener with Alpha Vantage...")

    results = []
    for ticker in WATCHLIST["ticker"]:
        if "." in ticker:
            print(f"Skipping {ticker} (not supported)")
            continue
        print(f"Fetching {ticker}...")
        result = screen_ticker(ticker)
        results.append(result)
        time.sleep(14)

    valid = [r for r in results if r]
    if not valid:
        print("No valid data retrieved. Exiting.")
        exit(0)

    df        = pd.DataFrame(valid)
    shortlist = apply_filters(df)
    print(f"Shortlist: {len(shortlist)} stocks")

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols    = ["ticker","price","dcf_bear","dcf_base","dcf_bull",
                   "dcf_bear_mos","dcf_base_mos","dcf_bull_mos","risk"]
        summary = claude_summary(shortlist[cols].to_json(orient="records"))

    html = build_html(df, shortlist, summary)
    send_email(html)
