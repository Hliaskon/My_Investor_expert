import pandas as pd
import os, smtplib, time, requests, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from report import build_html

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
# FIX F/G: WATCHLIST_FILE δέχεται comma-separated λίστα CSVs — έτσι ένα
# run μπορεί να καλύψει SP500 + Ευρώπη + Ασία μαζί, π.χ.:
#   WATCHLIST_FILE=watchlist.csv,watchlist_europe.csv,watchlist_asia.csv
def _load_watchlist(spec: str) -> pd.DataFrame:
    files = [f.strip() for f in spec.split(",") if f.strip()]
    frames = []
    for f in files:
        path = os.path.join(BASE_DIR, f)
        if os.path.exists(path):
            frames.append(pd.read_csv(path))
        else:
            print(f"[WARNING] watchlist file δεν βρέθηκε: {path} — skip")
    if not frames:
        raise FileNotFoundError(f"Κανένα watchlist file δεν βρέθηκε από: {spec}")
    combined = pd.concat(frames, ignore_index=True)
    before   = len(combined)
    combined = combined.drop_duplicates(subset="ticker", keep="first")
    if len(combined) < before:
        print(f"[INFO] Αφαιρέθηκαν {before - len(combined)} duplicate tickers "
              f"μεταξύ των watchlist αρχείων")
    return combined

WATCHLIST_FILE = os.environ.get("WATCHLIST_FILE", "watchlist.csv")
WATCHLIST      = _load_watchlist(WATCHLIST_FILE)
ALPHA_KEY      = os.environ.get("ALPHA_KEY", "")  # πλέον προαιρετικό, δεν χρησιμοποιείται

RISK_FREE_RATE  = 0.042
ERP             = 0.055

# FIX M (πείραμα): η Yahoo μπλοκάρει (429) requests από το κοινόχρηστο
# GitHub Actions IP pool — επιβεβαιώθηκε empirically, ακόμα και σε US
# blue-chips (JPM, BAC, ...), όχι μόνο σε διεθνή tickers. Δοκιμάζουμε
# curl_cffi session με browser-impersonation (μιμείται το TLS fingerprint
# ενός πραγματικού Chrome) — η θεωρία είναι ότι η Yahoo μπλοκάρει και με
# βάση fingerprint, όχι μόνο IP volume. ΔΕΝ το έχω δοκιμάσει live (δεν
# έχω δικτυακή πρόσβαση σε finance.yahoo.com από το dev environment) —
# αν αποτύχει ξανά, σημαίνει καθαρό IP-reputation block, χρειάζεται
# διαφορετική λύση (paid API ή τοπικό/self-hosted runner).
try:
    from curl_cffi import requests as _curl_requests
    _YF_SESSION = _curl_requests.Session(impersonate="chrome")
except Exception as _e:
    print(f"[WARNING] curl_cffi δεν φορτώθηκε ({_e}) — fallback σε default yfinance session")
    _YF_SESSION = None
TERMINAL_GROWTH = 0.025
# FIX G: το AV batch-limit (25/ημέρα) δεν υπάρχει πια — yfinance δεν έχει
# επίσημο daily cap. SCREEN_ALL=1 (default) τρέχει ΟΛΟ το watchlist κάθε
# φορά. Βάλε SCREEN_ALL=0 + BATCH_SIZE για να επιστρέψεις σε batching
# (π.χ. αν το yfinance αρχίσει να μπλοκάρει σε πολύ μεγάλα runs).
SCREEN_ALL      = os.environ.get("SCREEN_ALL", "1") == "1"
BATCH_SIZE      = int(os.environ.get("BATCH_SIZE", "10000"))
# Delay μεταξύ tickers. FIX K: 0.6s αποδείχτηκε πολύ επιθετικό — το
# GitHub Actions IP είναι κοινόχρηστο και η Yahoo μπλόκαρε 85/85 requests
# στο build_watchlist.py test. 1.5s default· full universe (~950 tickers)
# ≈ 24 λεπτά, ακόμα άνετα μέσα στο 6ωρο όριο του GitHub Actions job.
REQUEST_DELAY   = float(os.environ.get("REQUEST_DELAY", "1.5"))

# FIX D: sectors όπου το FCF proxy (EPS × 0.7) δεν είναι αξιόπιστο για DCF.
# Τράπεζες/ασφαλιστικές δεν έχουν "free cash flow" με την κλασική έννοια —
# το EPS×0.7 proxy δίνει τυχαία/παραπλανητικά νούμερα. Το Graham value ήδη
# τα εξαιρούσε (GRAHAM_EXCLUDED_SECTORS) — τώρα εξαιρείται και το DCF.
# Εναλλακτικό σήμα γι' αυτά τα sectors: sector-relative P/E/P/B
# (βλ. macro_regime.calculate_sector_pe / evaluate_sector_valuation).
DCF_UNRELIABLE_SECTORS = {"Financials"}

# ─────────────────────────────────────────────────────────────────────
# FIX A: Sector name normalization (πηγή: yfinance .info['sector'],
# προηγουμένως Alpha Vantage). yfinance χρησιμοποιεί ήδη πιο κοντινά στα
# δικά μας ονόματα (π.χ. ήδη "Consumer Cyclical"/"Consumer Defensive"),
# αλλά κρατάμε το map ως ασφάλεια για ό,τι δεν ταιριάζει 1:1.
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
    "Financials":             1,
    "Healthcare":             0,
    "Energy":                 2,
    "Consumer Cyclical":      2,
    "Consumer Defensive":     0,
    "Industrials":            1,
    "Basic Materials":        2,
    "Real Estate":            1,
    "Utilities":              0,
}


# FIX K: GitHub Actions runners έχουν ΚΟΙΝΟ IP pool ανάμεσα σε χιλιάδες
# repos — η Yahoo το βλέπει σαν πολύ "καυτό" IP και μπλοκάρει (429) πιο
# επιθετικά απ' ό,τι θα έκανε στο δικό σου IP. Retry με backoff βοηθάει
# ΜΟΝΟ αν είναι per-minute rate-limit· αν είναι IP-level block (ΟΛΑ τα
# tickers αποτυγχάνουν αμέσως), το backoff δεν αρκεί — θα το δεις σαν
# [ABORT] μήνυμα στο log αν συμβεί.
def _yfinance_info_with_retry(ticker: str, max_retries: int = 3, base_wait: int = 25):
    import yfinance as yf
    for attempt in range(max_retries + 1):
        try:
            info = yf.Ticker(ticker, session=_YF_SESSION).info
            if not info:
                raise ValueError("empty info")
            return info
        except Exception as e:
            is_rate_limit = "429" in str(e) or "Too Many Requests" in str(e) or \
                            "Expecting value" in str(e)
            if is_rate_limit and attempt < max_retries:
                wait = base_wait * (attempt + 1)
                print(f"  [RATE LIMIT] {ticker}: περιμένω {wait}s "
                      f"(προσπάθεια {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            raise


def get_fundamentals_yfinance(ticker: str) -> dict | None:
    """
    FIX G (η ουσιαστική αλλαγή): αντικαθιστά εντελώς το Alpha Vantage
    OVERVIEW ως πηγή fundamentals. Γιατί:
      - AV free tier: 25 calls/ημέρα, αδύνατο για SP500+Ευρώπη+Ασία (~950 tickers)
      - yfinance: κανένα επίσημο daily cap, καλύπτει ήδη .DE/.L/.PA/.T/.HK
      - Μία κλήση yf.Ticker(ticker).info δίνει ΚΑΙ fundamentals ΚΑΙ τιμή —
        1 network call/ticker αντί για 2 (AV OVERVIEW + yfinance price ξεχωριστά)

    ΓΝΩΣΤΟΣ ΠΕΡΙΟΡΙΣΜΟΣ (να το ξέρεις): yfinance είναι unofficial
    (reverse-engineered από Yahoo Finance), όχι επίσημο API. Τα ονόματα
    πεδίων στο .info έχουν αλλάξει στο παρελθόν μεταξύ εκδόσεων χωρίς
    προειδοποίηση, και η Yahoo μπορεί να μπλοκάρει IP σε πολύ επιθετικό
    scraping (γι' αυτό κρατάμε delay μεταξύ tickers). Αν κάποια μέρα
    σπάσει μαζικά, το FMP paid tier είναι το replacement — βλ. σχόλιο
    στο README.

    Επιστρέφει dict με ΤΑ ΙΔΙΑ keys που παλιά έδινε το AV OVERVIEW, ώστε
    η υπόλοιπη screen_ticker() να μη χρειάζεται αλλαγή.
    """
    try:
        info = _yfinance_info_with_retry(ticker)
        if not info or not (info.get("symbol") or info.get("longName")):
            return None

        # yfinance debtToEquity: percentage scale (π.χ. 140.3 = D/E 1.403)
        # AV DebtToEquityRatio ήταν raw ratio scale (π.χ. 1.40) — ο υπόλοιπος
        # κώδικας (risk_score, fragility) περιμένει raw ratio. Normalize εδώ.
        de_raw = info.get("debtToEquity")
        de_norm = (de_raw / 100) if de_raw is not None else None

        # yfinance dividendYield: ιστορικά ασυνεπές μεταξύ εκδόσεων (άλλες
        # φορές decimal fraction 0.024, άλλες ήδη-percentage 2.4). Defensive:
        # αν η τιμή >1, υποθέτουμε ότι είναι ήδη percentage.
        div_raw = info.get("dividendYield")
        div_norm = None
        if div_raw is not None:
            div_norm = (div_raw / 100) if div_raw > 1 else div_raw

        price = (info.get("currentPrice") or info.get("regularMarketPrice")
                  or info.get("previousClose"))

        return {
            "Symbol":                     info.get("symbol", ticker),
            "TrailingPE":                 info.get("trailingPE"),
            "PriceToBookRatio":           info.get("priceToBook"),
            "EPS":                        info.get("trailingEps"),
            "Beta":                       info.get("beta"),
            "DebtToEquityRatio":          de_norm,
            "ReturnOnEquityTTM":          info.get("returnOnEquity"),
            "DividendYield":              div_norm,
            "AnalystTargetPrice":         info.get("targetMeanPrice"),
            "52WeekHigh":                 info.get("fiftyTwoWeekHigh"),
            "52WeekLow":                  info.get("fiftyTwoWeekLow"),
            "QuarterlyEarningsGrowthYOY": info.get("earningsQuarterlyGrowth"),
            "EVToEBITDA":                 info.get("enterpriseToEbitda"),
            "50DayMovingAverage":         info.get("fiftyDayAverage"),
            "Sector":                     info.get("sector", "Unknown"),
            "_price":                     price,
        }
    except Exception as e:
        print(f"[YFINANCE] {ticker}: αποτυχία fetch fundamentals — {e}")
        return None


def get_price_yfinance(ticker: str):
    """
    Fallback μόνο — χρησιμοποιείται όταν το get_fundamentals_yfinance()
    δεν είχε τιμή στο ίδιο response (π.χ. currentPrice/regularMarketPrice
    λείπουν από το .info για κάποιο ticker).
    """
    try:
        import yfinance as yf
        t    = yf.Ticker(ticker, session=_YF_SESSION)
        info = getattr(t, "fast_info", None)
        price = None
        if info is not None:
            price = info.get("last_price") or info.get("lastPrice")
        if not price:
            hist = t.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price and price > 0:
            return round(float(price), 2)
    except Exception as e:
        print(f"[PRICE] yfinance fallback απέτυχε για {ticker}: {e}")
    return None

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

# FIX F: αγορές όπου υπάρχει πρόσθετος κίνδυνος πέρα από τα κλασικά
# fundamentals — δεν αποτυπώνεται στο risk_score() που ήταν καλιμπραρισμένο
# μόνο για US equities. China ADRs: VIE-structure (ο κάτοχος δεν έχει
# άμεση νομική κυριότητα στην underlying εταιρεία, μόνο contractual claim)
# + HFCAA delisting risk (εξαρτάται από PCAOB audit access status).
MARKET_REGULATORY_RISK = {
    "China (US-ADR)": {
        "flag": "⚠️ VIE structure + HFCAA delisting risk",
        "detail": "ADR = contractual claim, όχι άμεση κυριότητα στην underlying εταιρεία. "
                   "Verify τρέχον PCAOB/HFCAA status πριν τοποθέτηση.",
    },
}


def risk_score(pe, pb, beta, de, sector, market="US"):
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
    result  = {"business": biz_risk, "valuation": val_risk,
               "macro": sr["macro"], "sector": sr["sector"], "overall": overall}
    if market in MARKET_REGULATORY_RISK:
        result["regulatory"] = MARKET_REGULATORY_RISK[market]
        result["overall"]    = "high"  # regulatory tail-risk επικαλύπτει το βασικό scoring
    return result

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


def screen_ticker(ticker: str, watchlist_sector: str = None, watchlist_market: str = "US") -> dict | None:
    """
    Full Tier-1 analysis for one ticker.

    watchlist_sector: sector from watchlist.csv (authoritative).
    If None, falls back to Alpha Vantage sector name (normalized via SECTOR_AV_MAP).

    FIX A: Alpha Vantage returns "Financial Services" for banks, "Health Care"
    for healthcare stocks — not matching our internal "Financials"/"Healthcare".
    This caused all financial/healthcare stocks to fail the sector filter silently.
    """
    try:
        ov = get_fundamentals_yfinance(ticker)
        if not ov:
            raise ValueError("Δεν βρέθηκαν δεδομένα (yfinance)")

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
        # FIX L: "Unknown" ήταν truthy string — ποτέ δεν έκανε fallback στο
        # yfinance sector. Το watchlist_europe.csv (dry-run, χωρίς πλήρες
        # GICS mapping) έχει 137/190 "Unknown" — χωρίς αυτό το fix θα έμεναν
        # μόνιμα Unknown αντί να πάρουν το πραγματικό sector.
        wl_sector_usable = watchlist_sector if watchlist_sector and watchlist_sector.lower() != "unknown" else None
        sector    = wl_sector_usable if wl_sector_usable else normalize_sector(av_sector)
        if not wl_sector_usable and av_sector != sector:
            print(f"  [sector] {ticker}: AV='{av_sector}' → normalized='{sector}'")
        # ─────────────────────────────────────────────────────────────

        # FIX G: τιμή έρχεται μαζί με τα fundamentals από το ίδιο yfinance
        # .info call (ov["_price"]) — μηδενικό επιπλέον network cost.
        # Fallback σε ξεχωριστό yfinance call μόνο αν λείπει, μετά σε
        # EPS×PE reconstruction ως έσχατη λύση.
        price = ov.get("_price") or get_price_yfinance(ticker)
        if not price and eps and pe:
            price = round(abs(eps) * abs(pe), 2)
            print(f"[PRICE WARNING] {ticker}: yfinance χωρίς τιμή — "
                  f"fallback σε EPS×PE reconstruction (λιγότερο αξιόπιστο)")
        if not price and ma50 > 0:
            price = ma50
        if not price:
            raise ValueError("No price available")

        # Μετά τον υπολογισμό price:
        if price and ma50 and abs(price - ma50) / ma50 > 0.5:
            # Τιμή απέχει >50% από 50DMA — πιθανό data artifact
            print(f"[WARNING] {ticker}: price={price} vs 50DMA={ma50} — using 50DMA")
            price = ma50

        w          = wacc(beta)
        sector_cap = SECTOR_G_CAP.get(sector, 0.12)
        g_base     = max(0.02, min(abs(g_est), sector_cap))
        g_bear_fat = max(0.005, max(0.01, g_base - 0.06) - 0.03)
        g_bull     = min(0.25, g_base + 0.08)

        fcf_ps = eps * 0.7 if eps else None

        # FIX D: DCF εξαιρείται για sectors όπου το FCF proxy δεν βγάζει νόημα
        # (τράπεζες/ασφαλιστικές — βλ. σχόλιο στο DCF_UNRELIABLE_SECTORS).
        if sector in DCF_UNRELIABLE_SECTORS:
            dcf_base = dcf_bear = dcf_bull = None
        else:
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
            "risk":           risk_score(pe, pb, beta, de, sector, market=watchlist_market),
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
            "market":         watchlist_market,
        }

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None


def get_batch(df: pd.DataFrame, week_number: int):
    """
    FIX G: SCREEN_ALL=1 (default) → επιστρέφει ΟΛΟ το watchlist, καμία
    διαίρεση σε batches. Χωρίς το AV daily cap δεν χρειάζεται πια —
    και λύνει άμεσα το "θέλω να αξιολογούνται όλες οι μετοχές".
    Batching παραμένει διαθέσιμο (SCREEN_ALL=0) ως safety valve.
    """
    if SCREEN_ALL:
        print(f"Week {week_number} → FULL UNIVERSE ({len(df)} μετοχές, χωρίς batching)")
        return df.copy(), 1, 1
    total     = len(df)
    n_batches = max(1, -(-total // BATCH_SIZE))
    batch_idx = (week_number - 1) % n_batches
    start     = batch_idx * BATCH_SIZE
    batch_df  = df.iloc[start : start + BATCH_SIZE].copy()
    print(f"Week {week_number} → Batch {batch_idx+1}/{n_batches} "
          f"({len(batch_df)} stocks): {batch_df['ticker'].tolist()}")
    return batch_df, batch_idx + 1, n_batches


REQUIRED_FIELDS_FOR_CONFIDENCE = ["pe", "pb", "eps", "roe", "de", "ev_ebitda",
                                    "dcf_base", "analyst_target"]


def compute_tier(row: dict, favored_sectors=None) -> dict:
    """
    FIX R: αντικαθιστά το binary "DCF MoS>15% = shortlist" με πολυπαραγοντική
    βαθμολόγηση. Γιατί το χρειαζόμαστε: ένα και μόνο κριτήριο (DCF), βασισμένο
    σε μία και μόνο μέθοδο (crude FCF proxy), δεν είναι αρκετό σήμα για να
    δικαιολογήσει "buy" — ο ίδιος ο Graham έλεγε να συγκλίνουν πολλαπλές
    ανεξάρτητες εκτιμήσεις πριν εμπιστευτείς μία τιμή.

    4 συνιστώσες, όλες διαφανείς (breakdown), καμία "μαύρο κουτί":

    1. EPS QUALITY GATE (hard veto): αν το EPS είναι σχεδόν μηδενικό σχετικά
       με την τιμή (<2% earnings yield), το DCF %MoS γίνεται μαθηματικά
       ασταθές — ακριβώς έτσι έσκασε το PARA (+35616%). Αν αποτύχει αυτό το
       gate, tier = AVOID ανεξαρτήτως όλων των άλλων.

    2. DATA COMPLETENESS GATE: μετράει πόσα από τα 8 βασικά πεδία υπάρχουν
       πραγματικά (όχι None). Αν λείπουν πάνω από τα μισά, tier ανώτατο HOLD
       — δεν μπορεί να είναι "Strong Buy" όταν δεν ξέρουμε καν το μισό
       προφίλ της εταιρείας.

    3. VALUATION CONVERGENCE (0-40 pts): DCF MoS>20 (+15), Graham MoS>20
       (+10), EV/EBITDA<8x (+10), Analyst upside>15% (+5). Περισσότερες
       ανεξάρτητες μέθοδοι που συμφωνούν = ισχυρότερο σήμα.

    4. QUALITY (0-30 pts, Buffett-style): ROE≥15% (+15), ROIC>WACC (+10),
       D/E<1.0 (+5).

    5. MACRO/RISK (0-20 pts): favored sector (+10), risk όχι high (+10).

    Tier thresholds:
      STRONG BUY: score≥65 ΚΑΙ completeness≥75%
      BUY:        score≥45 ΚΑΙ completeness≥60%
      HOLD:       score≥25, ή completeness<50%
      AVOID:      όλα τα άλλα, ή αποτυχία EPS quality gate
    """
    favored_sectors = favored_sectors or []
    b = {}

    def _present(v):
        """FIX R+O: v μπορεί να είναι pandas NaN (όχι Python None) όταν
        έρχεται από DataFrame row — ίδιο root cause με το FIX O στο report.py."""
        if v is None:
            return False
        if isinstance(v, float) and pd.isna(v):
            return False
        return True

    present = sum(1 for f in REQUIRED_FIELDS_FOR_CONFIDENCE if _present(row.get(f)))
    completeness = present / len(REQUIRED_FIELDS_FOR_CONFIDENCE)
    b["data_completeness_pct"] = round(completeness * 100)

    price = row.get("price")
    eps   = row.get("eps")
    eps_quality_ok = bool(_present(eps) and _present(price) and price > 0
                           and abs(eps) >= 0.02 * price)
    b["eps_quality_ok"] = eps_quality_ok

    val_score = 0
    dcf_mos = row.get("dcf_base_mos")
    if _present(dcf_mos) and dcf_mos > 20: val_score += 15
    graham_mos = row.get("graham_mos")
    if _present(graham_mos) and graham_mos > 20: val_score += 10
    ev_ebitda = row.get("ev_ebitda")
    if _present(ev_ebitda) and 0 < ev_ebitda < 8: val_score += 10
    upside = row.get("analyst_upside")
    if _present(upside) and upside > 15: val_score += 5
    b["valuation_score"] = val_score

    q_score = 0
    roe = row.get("roe")
    if _present(roe) and roe >= 15: q_score += 15
    if row.get("roic_vs_wacc") == "positive": q_score += 10
    de = row.get("de")
    if _present(de) and de < 1.0: q_score += 5
    b["quality_score"] = q_score

    m_score = 0
    if row.get("sector") in favored_sectors: m_score += 10
    risk = row.get("risk") or {}
    if risk.get("overall") in ("low", "medium"): m_score += 10
    b["macro_score"] = m_score

    total = val_score + q_score + m_score
    b["total_score"] = total

    if not eps_quality_ok:
        tier = "AVOID"
        b["tier_reason"] = "Χαμηλή ποιότητα EPS (near-zero earnings yield) — DCF % αναξιόπιστο"
    elif completeness < 0.5:
        tier = "HOLD"
        b["tier_reason"] = "Ελλιπή δεδομένα (<50% πεδίων) — ανώτατο HOLD ανεξαρτήτως score"
    elif total >= 65 and completeness >= 0.75:
        tier = "STRONG BUY"
        b["tier_reason"] = f"Score {total}/90, {b['data_completeness_pct']}% δεδομένα — σύγκλιση σημάτων"
    elif total >= 45 and completeness >= 0.6:
        tier = "BUY"
        b["tier_reason"] = f"Score {total}/90, {b['data_completeness_pct']}% δεδομένα"
    elif total >= 25:
        tier = "HOLD"
        b["tier_reason"] = f"Score {total}/90 — μερικά θετικά σήματα, όχι αρκετά"
    else:
        tier = "AVOID"
        b["tier_reason"] = f"Score {total}/90 — ανεπαρκή σήματα"
    b["tier"] = tier
    return b


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
    # FIX D: sectors στο DCF_UNRELIABLE_SECTORS δεν έχουν dcf_base_mos
    # (None by design — βλ. screen_ticker). Αν εφαρμόσουμε το ίδιο φίλτρο
    # θα αποκλειστούν αυτόματα ΟΛΕΣ οι τράπεζες/ασφαλιστικές. Γι' αυτές
    # περνάνε στο shortlist χωρίς DCF κριτήριο· η αποτίμησή τους κρίνεται
    # από sector-relative P/E (macro overlay) — ήδη φαίνεται στο email.
    n2       = len(f)
    exempt   = f["sector"].isin(DCF_UNRELIABLE_SECTORS)
    dcf_mask = f["dcf_base_mos"].notna() & (f["dcf_base_mos"] > 15)
    mask     = dcf_mask | exempt
    excl     = f[~mask]["ticker"].tolist()
    n_exempt = int(exempt.sum())
    f        = f[mask]
    print(f"[FILTER] DCF MoS >15%:  {len(f):>3}/{n2} pass | excl {len(excl)} "
          f"| {n_exempt} exempt (DCF-unreliable sector, π.χ. Financials): {excl}")

    # ── FIX Q: sanity cap — DCF MoS >300% είναι σχεδόν πάντα computation
    # artifact (μικρό/στρεβλωμένο EPS × 5ετής compound growth), όχι
    # πραγματική ευκαιρία. Παράδειγμα που το έδειξε: PARA +35616%.
    # Legit deep-value cyclical (π.χ. energy μετοχές σε κάτω κύκλο) μπορεί
    # να δείξει νόμιμα 100-250% — το όριο στα 300% τα αφήνει, κόβει μόνο
    # τα ξεκάθαρα σπασμένα.
    MAX_SANE_MOS = 300
    n3       = len(f)
    absurd   = f["dcf_base_mos"].notna() & (f["dcf_base_mos"].abs() > MAX_SANE_MOS)
    absurd_tickers = f[absurd]["ticker"].tolist()
    f        = f[~absurd]
    if absurd_tickers:
        print(f"[FILTER] Sanity cap (|MoS|>{MAX_SANE_MOS}%): αφαιρέθηκαν {len(absurd_tickers)} "
              f"πιθανά computation artifacts: {absurd_tickers}")

    # ── Macro: SOFT sort (NOT exclusion) ──────────────────────────────
    if favored_sectors and len(f) > 0:
        f["macro_favored"] = f["sector"].isin(favored_sectors)
        n_fav = int(f["macro_favored"].sum())
        print(f"[FILTER] Macro align:   {n_fav}/{len(f)} in favored sectors "
              f"— sorted first, others NOT excluded")
    else:
        f["macro_favored"] = False

    # ── FIX R: πολυπαραγοντικό tier (STRONG BUY/BUY/HOLD/AVOID) ────────
    # αντικαθιστά το μονο-κριτηριακό DCF sort. Υπολογίζεται εδώ (όχι στο
    # screen_ticker) γιατί χρειάζεται το favored_sectors που ξέρουμε μόνο
    # μετά την macro classification.
    if len(f) > 0:
        tier_rows = f.to_dict("records")
        tier_results = [compute_tier(r, favored_sectors) for r in tier_rows]
        f["tier"]              = [t["tier"] for t in tier_results]
        f["tier_score"]        = [t["total_score"] for t in tier_results]
        f["tier_reason"]       = [t["tier_reason"] for t in tier_results]
        f["data_completeness"] = [t["data_completeness_pct"] for t in tier_results]

        TIER_ORDER = {"STRONG BUY": 0, "BUY": 1, "HOLD": 2, "AVOID": 3}
        f["_tier_sort"] = f["tier"].map(TIER_ORDER)
        f = f.sort_values(["_tier_sort", "tier_score"], ascending=[True, False])
        f = f.drop(columns=["_tier_sort"])

        tier_counts = f["tier"].value_counts().to_dict()
        print(f"[FILTER] Tiers: {tier_counts}")
    else:
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


HISTORY_FILE = os.path.join(BASE_DIR, "history.csv")
# Μετά από πόσες ημέρες να εμφανίζεται μια παλιά πρόταση στο performance
# tracker (αποφεύγει θόρυβο με μετοχές που φλαγκαρίστηκαν πριν 2 ημέρες)
PERFORMANCE_MIN_DAYS = 21


def record_history(shortlist_df: pd.DataFrame):
    """
    FIX H (ιστορικότητα): αποθηκεύει κάθε νέο shortlist pick σε history.csv
    ώστε το επόμενο run να μπορεί να συγκρίνει "τι πρότεινα τότε vs τι
    έγινε μετά". Append-only — δεν διαγράφει παλιά entries.

    ΠΡΟΣΟΧΗ: αυτό το αρχείο πρέπει να γίνεται git commit από το GitHub
    Action μετά το run, αλλιώς χάνεται στο επόμενο run (ephemeral runner
    filesystem). Δες το ενημερωμένο screener.yml.
    """
    if shortlist_df.empty:
        return
    today = datetime.date.today().isoformat()
    new_rows = shortlist_df[["ticker", "sector", "price", "dcf_base_mos",
                              "graham_mos", "risk"]].copy()
    new_rows["date_flagged"]  = today
    new_rows["risk_overall"]  = new_rows["risk"].apply(
        lambda r: r.get("overall") if isinstance(r, dict) else None)
    new_rows = new_rows.drop(columns=["risk"])
    new_rows = new_rows.rename(columns={"price": "price_at_flag"})

    if os.path.exists(HISTORY_FILE):
        existing = pd.read_csv(HISTORY_FILE)
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows
    combined.to_csv(HISTORY_FILE, index=False)
    print(f"[HISTORY] Καταγράφηκαν {len(new_rows)} νέα picks → {HISTORY_FILE} "
          f"(σύνολο: {len(combined)} εγγραφές)")


def check_performance() -> pd.DataFrame:
    """
    Διαβάζει το history.csv, βρίσκει picks παλαιότερα από
    PERFORMANCE_MIN_DAYS, τραβάει ΤΡΕΧΟΥΣΑ τιμή (yfinance) και υπολογίζει
    πραγματική απόδοση από τη στιγμή που φλαγκαρίστηκαν.

    Επιστρέφει DataFrame: ticker, date_flagged, price_at_flag,
    price_now, return_pct, days_held. Άδειο αν δεν υπάρχει ιστορικό ακόμα.
    """
    if not os.path.exists(HISTORY_FILE):
        print("[PERFORMANCE] Δεν υπάρχει ακόμα history.csv — πρώτο run.")
        return pd.DataFrame()

    hist  = pd.read_csv(HISTORY_FILE)
    hist["date_flagged"] = pd.to_datetime(hist["date_flagged"])
    cutoff = datetime.datetime.now() - datetime.timedelta(days=PERFORMANCE_MIN_DAYS)
    eligible = hist[hist["date_flagged"] <= cutoff].copy()
    if eligible.empty:
        print(f"[PERFORMANCE] Καμία πρόταση >{PERFORMANCE_MIN_DAYS} ημερών ακόμα.")
        return pd.DataFrame()

    # Κρατάμε μόνο το ΠΡΩΤΟ flag ανά ticker (αποφεύγει duplicate rows αν
    # η ίδια μετοχή προτάθηκε ξανά αργότερα)
    eligible = eligible.sort_values("date_flagged").drop_duplicates(
        subset="ticker", keep="first")

    rows = []
    for _, r in eligible.iterrows():
        current = get_price_yfinance(r["ticker"])
        if current is None:
            continue
        ret_pct = round((current - r["price_at_flag"]) / r["price_at_flag"] * 100, 1)
        days    = (datetime.datetime.now() - r["date_flagged"]).days
        rows.append({
            "ticker":        r["ticker"],
            "date_flagged":  r["date_flagged"].date().isoformat(),
            "price_at_flag": r["price_at_flag"],
            "price_now":     current,
            "return_pct":    ret_pct,
            "days_held":     days,
        })
        time.sleep(REQUEST_DELAY)

    result = pd.DataFrame(rows).sort_values("return_pct", ascending=False)
    print(f"[PERFORMANCE] {len(result)} παλιές προτάσεις με tracked απόδοση")
    return result


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

    # FIX F: το παλιό φίλτρο "if '.' in ticker: skip" έμπλοκε ΚΑΘΕ ticker με
    # τελεία — σωστό για ξεχασμένα US class-share tickers (π.χ. BF.B) αλλά
    # θα έμπλοκε ΚΑΙ κάθε ευρωπαϊκό ticker (SAP.DE, ULVR.L, MC.PA). Τώρα
    # επιτρέπονται ρητά τα γνωστά exchange suffixes· ό,τι άλλο έχει τελεία
    # συνεχίζει να παραλείπεται όπως πριν.
    INTL_SUFFIXES = (".DE", ".L", ".PA", ".AS", ".MI", ".MC", ".SW", ".T", ".HK")

    results = []
    consecutive_failures = 0
    for _, row in batch_df.iterrows():
        ticker = str(row["ticker"])
        if "." in ticker and not ticker.endswith(INTL_SUFFIXES):
            print(f"Skipping {ticker} (μη αναγνωρισμένο format)")
            continue

        # FIX K: αν αποτύχουν 15 στη σειρά, είναι πιθανό IP-level block από
        # τη Yahoo (κοινό GitHub Actions IP pool), όχι μεμονωμένα προβλήματα.
        # Σταματάμε αντί να σπαταλάμε ώρες σε retries που δεν θα πετύχουν.
        if consecutive_failures >= 15:
            print(f"\n[ABORT] {consecutive_failures} συνεχόμενες αποτυχίες — πιθανό IP block "
                  f"από Yahoo. Σταματάω εδώ· ό,τι μαζεύτηκε μέχρι τώρα θα σταλεί κανονικά.")
            break

        # FIX A: pass watchlist sector — authoritative, no AV mismatch
        ws = str(row["sector"]) if "sector" in row.index and pd.notna(row["sector"]) else None
        # FIX F: market column προαιρετική — backward compatible με παλιό watchlist.csv
        wm = str(row["market"]) if "market" in row.index and pd.notna(row["market"]) else "US"
        print(f"Fetching {ticker} (sector: {ws}, market: {wm})...")
        r = screen_ticker(ticker, watchlist_sector=ws, watchlist_market=wm)
        results.append(r)
        consecutive_failures = 0 if r else consecutive_failures + 1
        time.sleep(REQUEST_DELAY)

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

    # FIX H: ιστορικότητα — performance παλιών picks ΠΡΙΝ γράψουμε νέα,
    # μετά καταγραφή των νέων για το επόμενο run
    performance_df = check_performance()
    record_history(shortlist)

    summary = ""
    if not shortlist.empty and os.environ.get("ANTHROPIC_API_KEY"):
        cols = ["ticker", "price", "dcf_bear", "dcf_base", "dcf_bull",
                "dcf_bear_mos", "dcf_base_mos", "dcf_bull_mos", "risk",
                "roic", "roic_vs_wacc", "ev_ebitda", "pct_from_low",
                "w52_flag", "fragility", "macro_favored"]
        summary = claude_summary(shortlist[cols].to_json(orient="records"), batch_info)

    html = build_html(df, shortlist, summary, macro_html=macro_html,
                      alignment_map=alignment_map,
                      batch_idx=batch_idx, n_batches=n_batches,
                      performance_df=performance_df)
    send_email(html, week_number, batch_idx, n_batches)
