import yfinance as yf
import pandas as pd
import math, os, smtplib, json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from report import build_html
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = pd.read_csv(os.path.join(BASE_DIR, "watchlist.csv"))

RISK_FREE_RATE = 0.042   # 10Y Treasury
ERP            = 0.055   # Equity Risk Premium
TERMINAL_GROWTH = 0.025

# --- Sector-level macro/sector risk (static, update quarterly) ---
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

def wacc(beta):
    return RISK_FREE_RATE + beta * ERP

def dcf_value(fcf_per_share, g_rate, wacc_rate, years=5):
    """Simple DCF: sum of discounted FCFs + terminal value"""
    if not fcf_per_share or fcf_per_share <= 0:
        return None
    total = 0
    for t in range(1, years + 1):
        total += fcf_per_share * (1 + g_rate)**t / (1 + wacc_rate)**t
    fcf5 = fcf_per_share * (1 + g_rate)**years
    terminal = fcf5 * (1 + TERMINAL_GROWTH) / (wacc_rate - TERMINAL_GROWTH)
    total += terminal / (1 + wacc_rate)**years
    return round(total, 2)

def graham_value(eps, g_pct, bond_yield=4.4):
    if not eps or eps <= 0:
        return None
    return round(eps * (8.5 + 2 * g_pct) * (4.4 / bond_yield), 2)

def risk_score(pe, pb, beta, de, sector):
    """Returns dict with 4 risk dimensions + overall (low/medium/high)"""
    sr = SECTOR_RISK.get(sector, {"macro": "medium", "sector": "medium"})

    # Valuation risk
    if pe and pe < 12 and pb and pb < 1.2:
        val_risk = "low"
    elif pe and pe > 30:
        val_risk = "high"
    else:
        val_risk = "medium"

    # Business risk (proxy: D/E + beta)
    if de and de > 3 or beta and beta > 1.5:
        biz_risk = "high"
    elif de and de < 0.5 and beta and beta < 0.8:
        biz_risk = "low"
    else:
        biz_risk = "medium"

    levels = {"low": 0, "medium": 1, "high": 2}
    avg = (levels[val_risk] + levels[biz_risk] +
           levels[sr["macro"]] + levels[sr["sector"]]) / 4
    overall = "low" if avg < 0.75 else ("high" if avg > 1.5 else "medium")

    return {
        "business":  biz_risk,
        "valuation": val_risk,
        "macro":     sr["macro"],
        "sector":    sr["sector"],
        "overall":   overall,
    }

def get_sparkline(ticker, period="1y"):
    """Returns list of weekly closing prices for SVG sparkline"""
    try:
        hist = yf.Ticker(ticker).history(period=period, interval="1wk")
        prices = hist["Close"].dropna().tolist()
        return [round(p, 2) for p in prices[-52:]]  # max 52 points
    except:
        return []

def screen_ticker(ticker):
    try:
        t    = yf.Ticker(ticker)
        info = t.info

        price   = info.get("currentPrice") or info.get("regularMarketPrice")
        pe      = info.get("trailingPE")
        pb      = info.get("priceToBook")
        eps     = info.get("trailingEps")
        bvps    = info.get("bookValue")
        beta    = info.get("beta") or 1.0
        de      = info.get("debtToEquity")
        roe     = info.get("returnOnEquity")
        div     = info.get("dividendYield") or 0
        sector  = info.get("sector", "Unknown")
        fcf     = info.get("freeCashflow")
        shares  = info.get("sharesOutstanding") or 1
        g_est   = info.get("earningsGrowth") or info.get("revenueGrowth") or 0.08

        fcf_ps  = fcf / shares if fcf else None
        w       = wacc(beta)

        # DCF: 3 scenarios (growth ±4%)
        g_base  = max(0.02, min(g_est, 0.25))
        g_bear  = max(0.01, g_base - 0.06)
        g_bull  = min(0.35, g_base + 0.08)

        dcf_base = dcf_value(fcf_ps, g_base, w)
        dcf_bear = dcf_value(fcf_ps, g_bear, w + 0.015)
        dcf_bull = dcf_value(fcf_ps, g_bull, w - 0.010)

        gv = graham_value(eps, g_base * 100)

        # Net cash per share
        cash     = info.get("totalCash") or 0
        debt     = info.get("totalDebt") or 0
        net_cash = (cash - debt) / shares if shares else 0
        net_cash_ps = round(net_cash, 2)

        def mos(val):
            if val and price and price > 0:
                return round((val - price) / price * 100, 1)
            return None

        sparkline = get_sparkline(ticker)
        risk      = risk_score(pe, pb, beta, de, sector)
        high52    = info.get("fiftyTwoWeekHigh")
        low52     = info.get("fiftyTwoWeekLow")
        target    = info.get("targetMeanPrice")

        return {
            "ticker":      ticker,
            "sector":      sector,
            "price":       price,
            "pe":          round(pe, 1) if pe else None,
            "pb":          round(pb, 2) if pb else None,
            "eps":         eps,
            "beta":        round(beta, 2),
            "wacc":        round(w * 100, 1),
            "de":          round(de, 1) if de else None,
            "roe":         round(roe * 100, 1) if roe else None,
            "div_yield":   round(div * 100, 2),
            "g_base_pct":  round(g_base * 100, 1),
            "graham_value": gv,
            "graham_mos":  mos(gv),
            "dcf_bear":    dcf_bear,
            "dcf_base":    dcf_base,
            "dcf_bull":    dcf_bull,
            "dcf_bear_mos": mos(dcf_bear),
            "dcf_base_mos": mos(dcf_base),
            "dcf_bull_mos": mos(dcf_bull),
            "net_cash_ps": net_cash_ps,
            "high52":      high52,
            "low52":       low52,
            "analyst_target": target,
            "sparkline":   sparkline,
            "risk":        risk,
        }
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def apply_filters(df):
    f = df.copy()
    f = f[f["pe"].notna()            & (f["pe"] < 20)]
    f = f[f["pb"].notna()            & (f["pb"] < 2.5)]
    f = f[f["dcf_base_mos"].notna()  & (f["dcf_base_mos"] > 15)]
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
    msg["From"] = sender
    msg["To"]   = receiver
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(sender, password)
        s.sendmail(sender, receiver, msg.as_string())
    print("Email sent!")

if __name__ == "__main__":
    results   = [screen_ticker(t) for t in WATCHLIST["ticker"]]
    df        = pd.DataFrame([r for r in results if r])
    shortlist = apply_filters(df)

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols = ["ticker","price","dcf_bear","dcf_base","dcf_bull",
                "dcf_bear_mos","dcf_base_mos","dcf_bull_mos","risk"]
        summary = claude_summary(shortlist[cols].to_json(orient="records"))

    html = build_html(df, shortlist, summary)
    send_email(html)
