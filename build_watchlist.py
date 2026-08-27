"""
build_watchlist.py — Dynamic Watchlist Generator
Χρήση:
  python build_watchlist.py --market sp500   [--output watchlist.csv] [--dry-run]
  python build_watchlist.py --market europe  [--output watchlist_europe.csv] [--dry-run]
  python build_watchlist.py --market all     [--output watchlist_all.csv]   [--dry-run]

Fetches S&P 500 / DAX / FTSE 100 / EURO STOXX 50 από Wikipedia,
εφαρμόζει Tier-0 pre-filter via yfinance,
αποθηκεύει value-eligible stocks σε CSV.

Tier-0 criteria (broad — excludes obvious non-value):
  PE < 40, PB < 6, EPS > 0, MarketCap > $1B

ΣΗΜΑΝΤΙΚΟ πριν τρέξεις --market europe σε παραγωγή:
  Το screener.py χρησιμοποιεί Alpha Vantage OVERVIEW για fundamentals
  (P/E, EPS, Beta, D/E). Η κάλυψη του AV για μη-US tickers (.DE, .L, .PA)
  ΔΕΝ είναι επιβεβαιωμένη — δεν έχω δικτυακή πρόσβαση στο AV API για να
  το ελέγξω εγώ. ΤΡΕΞΕ ΠΡΩΤΑ validate_international_coverage.py σε ~10
  tickers πριν κάνεις commit ολόκληρη τη λίστα. Αν το AV OVERVIEW δεν
  καλύπτει ένα ticker, ο screener απλά θα το αγνοήσει σιωπηλά
  (except στο screen_ticker) — καλύτερα να το ξέρεις πριν, όχι μετά.

Τρέχει εκτός GitHub Actions — locally, on-demand.
"""

import pandas as pd
import time
import argparse

GICS_TO_SECTOR = {
    "Information Technology":  "Technology",
    "Health Care":             "Healthcare",
    "Financials":              "Financials",
    "Consumer Discretionary":  "Consumer Cyclical",
    "Consumer Staples":        "Consumer Defensive",
    "Energy":                  "Energy",
    "Communication Services":  "Communication Services",
    "Industrials":             "Industrials",
    "Materials":               "Basic Materials",
    "Real Estate":             "Real Estate",
    "Utilities":               "Utilities",
}

TIER0_PE_MAX   = 40     # excludes NVDA 60+, TSLA 80+, AMZN 50+
TIER0_PB_MAX   = 6      # excludes AAPL 50x, MSFT 14x
TIER0_EPS_MIN  = 0      # must be profitable
TIER0_MCAP_MIN = 1e9    # $1B+


def fetch_sp500() -> pd.DataFrame:
    print("Fetching S&P 500 from Wikipedia...")
    tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    df     = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
    df.columns = ["ticker", "name", "gics_sector"]
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    print(f"  {len(df)} tickers")
    return df


def _find_col(table, keywords):
    """Εντοπίζει στήλη ανάμεσα στα columns ενός Wikipedia table με βάση keywords.
    Άμυνα ενάντια σε αλλαγές στη δομή του πίνακα (δεν κάνω hardcode ονόματα)."""
    for c in table.columns:
        cl = str(c).lower()
        if any(kw in cl for kw in keywords):
            return c
    return None


def fetch_dax(suffix: str = ".DE") -> pd.DataFrame:
    """DAX 40 (Γερμανία, Xetra). Wikipedia: 'DAX' page."""
    print("Fetching DAX (Γερμανία) από Wikipedia...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/DAX")
        for t in tables:
            tick_col = _find_col(t, ["ticker", "symbol"])
            name_col = _find_col(t, ["company", "name"])
            sect_col = _find_col(t, ["sector", "industry", "prime standard"])
            if tick_col and name_col:
                df = t[[tick_col, name_col] + ([sect_col] if sect_col else [])].copy()
                df.columns = ["ticker", "name"] + (["gics_sector"] if sect_col else [])
                if "gics_sector" not in df.columns:
                    df["gics_sector"] = "Unknown"
                df["ticker"] = df["ticker"].astype(str).str.strip() + suffix
                df["market"] = "Germany"
                print(f"  {len(df)} tickers")
                return df[["ticker", "name", "gics_sector", "market"]]
    except Exception as e:
        print(f"  [WARNING] DAX fetch απέτυχε: {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector", "market"])


def fetch_ftse100(suffix: str = ".L") -> pd.DataFrame:
    """FTSE 100 (Αγγλία, LSE). Wikipedia: 'FTSE 100 Index' page."""
    print("Fetching FTSE 100 (Αγγλία) από Wikipedia...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/FTSE_100_Index")
        for t in tables:
            tick_col = _find_col(t, ["ticker", "epic", "symbol"])
            name_col = _find_col(t, ["company"])
            sect_col = _find_col(t, ["sector", "ftse industry"])
            if tick_col and name_col:
                df = t[[tick_col, name_col] + ([sect_col] if sect_col else [])].copy()
                df.columns = ["ticker", "name"] + (["gics_sector"] if sect_col else [])
                if "gics_sector" not in df.columns:
                    df["gics_sector"] = "Unknown"
                df["ticker"] = df["ticker"].astype(str).str.strip() + suffix
                df["market"] = "UK"
                print(f"  {len(df)} tickers")
                return df[["ticker", "name", "gics_sector", "market"]]
    except Exception as e:
        print(f"  [WARNING] FTSE 100 fetch απέτυχε: {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector", "market"])


def fetch_euro_stoxx50() -> pd.DataFrame:
    """
    EURO STOXX 50 — 50 μεγαλύτερες blue-chip εταιρείες της Ευρωζώνης
    (Γαλλία, Γερμανία, Ολλανδία, Ιταλία, Ισπανία κλπ). Καλή προσέγγιση
    για "ευρύτερη Ευρώπη" πέρα από DAX/FTSE — τα exchange suffixes
    διαφέρουν ανά χώρα, οπότε εξάγονται από τη στήλη 'exchange' αν υπάρχει
    στο Wikipedia table, αλλιώς μένουν χωρίς suffix (χρειάζεται manual fix).
    """
    print("Fetching EURO STOXX 50 (ευρύτερη Ευρώπη) από Wikipedia...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/EURO_STOXX_50")
        for t in tables:
            tick_col = _find_col(t, ["ticker", "symbol"])
            name_col = _find_col(t, ["company", "name"])
            sect_col = _find_col(t, ["sector", "industry", "icb"])
            if tick_col and name_col:
                df = t[[tick_col, name_col] + ([sect_col] if sect_col else [])].copy()
                df.columns = ["ticker", "name"] + (["gics_sector"] if sect_col else [])
                if "gics_sector" not in df.columns:
                    df["gics_sector"] = "Unknown"
                df["ticker"] = df["ticker"].astype(str).str.strip()
                df["market"] = "Eurozone"
                print(f"  {len(df)} tickers — ΠΡΟΣΟΧΗ: exchange suffix (.PA/.AS/.MI/.MC/.DE) "
                      f"ΔΕΝ έχει προστεθεί αυτόματα, verify manually πριν production.")
                return df[["ticker", "name", "gics_sector", "market"]]
    except Exception as e:
        print(f"  [WARNING] EURO STOXX 50 fetch απέτυχε: {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector", "market"])


# Curated list — US-listed China ADRs. ΔΕΝ χρησιμοποιούμε HKEX (.HK) ή
# A-shares tickers γιατί το Alpha Vantage OVERVIEW πιθανότατα δεν τα καλύπτει
# (unverified — δες σχόλιο στην κορυφή του αρχείου). ADRs στο NYSE/NASDAQ
# περνάνε από το ίδιο pipeline, ΑΛΛΑ έχουν πρόσθετο κίνδυνο που δεν
# αποτυπώνεται στο risk_score() του screener.py:
#   - VIE structure: ο κάτοχος ADR δεν έχει άμεση νομική κυριότητα στην
#     underlying κινεζική εταιρεία, μόνο contractual claim.
#   - HFCAA delisting risk: εξαρτάται από PCAOB audit access — status
#     μπορεί να αλλάξει, verify πριν commit.
CHINA_ADR_WATCHLIST = [
    {"ticker": "BABA", "name": "Alibaba Group",       "gics_sector": "Consumer Cyclical"},
    {"ticker": "PDD",  "name": "PDD Holdings",         "gics_sector": "Consumer Cyclical"},
    {"ticker": "JD",   "name": "JD.com",               "gics_sector": "Consumer Cyclical"},
    {"ticker": "BIDU", "name": "Baidu",                "gics_sector": "Communication Services"},
    {"ticker": "NTES", "name": "NetEase",               "gics_sector": "Communication Services"},
    {"ticker": "TCOM", "name": "Trip.com Group",        "gics_sector": "Consumer Cyclical"},
    {"ticker": "YUMC", "name": "Yum China",             "gics_sector": "Consumer Cyclical"},
    {"ticker": "NIO",  "name": "NIO Inc",               "gics_sector": "Consumer Cyclical"},
    {"ticker": "LI",   "name": "Li Auto",               "gics_sector": "Consumer Cyclical"},
    {"ticker": "ZTO",  "name": "ZTO Express",           "gics_sector": "Industrials"},
]


def fetch_china_adr() -> pd.DataFrame:
    print("Φόρτωση curated λίστας US-listed China ADRs (όχι live-verified)...")
    df = pd.DataFrame(CHINA_ADR_WATCHLIST)
    df["market"] = "China (US-ADR)"
    print(f"  {len(df)} tickers — verify listing status πριν production "
          f"(delisting risk / HFCAA).")
    return df


def fetch_nikkei225(suffix: str = ".T") -> pd.DataFrame:
    """Nikkei 225 (Ιαπωνία, Tokyo Stock Exchange). Wikipedia: 'Nikkei 225' page."""
    print("Fetching Nikkei 225 (Ιαπωνία) από Wikipedia...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Nikkei_225")
        for t in tables:
            tick_col = _find_col(t, ["code", "ticker", "symbol"])
            name_col = _find_col(t, ["company", "name"])
            sect_col = _find_col(t, ["sector", "industry"])
            if tick_col and name_col:
                df = t[[tick_col, name_col] + ([sect_col] if sect_col else [])].copy()
                df.columns = ["ticker", "name"] + (["gics_sector"] if sect_col else [])
                if "gics_sector" not in df.columns:
                    df["gics_sector"] = "Unknown"
                # Tokyo codes είναι 4-ψήφιοι αριθμοί (π.χ. 7203 = Toyota) → 7203.T
                df["ticker"] = df["ticker"].astype(str).str.strip().str.zfill(4) + suffix
                df["market"] = "Japan"
                print(f"  {len(df)} tickers")
                return df[["ticker", "name", "gics_sector", "market"]]
    except Exception as e:
        print(f"  [WARNING] Nikkei 225 fetch απέτυχε: {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector", "market"])


def fetch_hang_seng(suffix: str = ".HK") -> pd.DataFrame:
    """Hang Seng Index (Χονγκ Κονγκ, HKEX). Wikipedia: 'Hang Seng Index' page."""
    print("Fetching Hang Seng (Χονγκ Κονγκ) από Wikipedia...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Hang_Seng_Index")
        for t in tables:
            tick_col = _find_col(t, ["ticker", "sehk", "stock code", "code"])
            name_col = _find_col(t, ["company", "name"])
            sect_col = _find_col(t, ["sector", "industry", "sub-index"])
            if tick_col and name_col:
                df = t[[tick_col, name_col] + ([sect_col] if sect_col else [])].copy()
                df.columns = ["ticker", "name"] + (["gics_sector"] if sect_col else [])
                if "gics_sector" not in df.columns:
                    df["gics_sector"] = "Unknown"
                # HKEX codes είναι 4-ψήφιοι αριθμοί (π.χ. 0700 = Tencent) → 0700.HK
                df["ticker"] = (df["ticker"].astype(str).str.strip()
                                 .str.replace(r"\D", "", regex=True).str.zfill(4) + suffix)
                df["market"] = "Hong Kong"
                print(f"  {len(df)} tickers")
                return df[["ticker", "name", "gics_sector", "market"]]
    except Exception as e:
        print(f"  [WARNING] Hang Seng fetch απέτυχε: {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector", "market"])


def fetch_nasdaq100_extras(sp500_set: set) -> pd.DataFrame:
    print("Fetching NASDAQ 100 additions...")
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        for t in tables:
            col = next((c for c in t.columns
                        if "ticker" in str(c).lower() or "symbol" in str(c).lower()), None)
            if col:
                new = [tk for tk in t[col].tolist() if tk not in sp500_set]
                print(f"  {len(new)} extra tickers")
                return pd.DataFrame({"ticker": new, "name": new, "gics_sector": "Unknown"})
    except Exception as e:
        print(f"  [WARNING] {e}")
    return pd.DataFrame(columns=["ticker", "name", "gics_sector"])


def tier0_filter(universe: pd.DataFrame, dry_run: bool = False) -> pd.DataFrame:
    """
    Pre-filter using yfinance (unofficial, free).
    Returns DataFrame[ticker, name, sector] for value candidates only.
    """
    try:
        import yfinance as yf
    except ImportError:
        raise RuntimeError("pip install yfinance")

    candidates, skipped = [], 0
    total = len(universe)
    print(f"\nTier-0: {total} stocks | PE<{TIER0_PE_MAX} · PB<{TIER0_PB_MAX} · EPS>0 · MCap>$1B\n")

    for _, row in universe.iterrows():
        ticker = str(row["ticker"])
        sector = GICS_TO_SECTOR.get(str(row.get("gics_sector", "")), "Unknown")
        name   = str(row.get("name", ticker))

        if dry_run:
            candidates.append({"ticker": ticker, "name": name, "sector": sector})
            continue

        try:
            info  = yf.Ticker(ticker).info
            pe    = info.get("trailingPE")
            pb    = info.get("priceToBook")
            eps   = info.get("trailingEps")
            mcap  = info.get("marketCap") or 0
            lname = info.get("longName", name)

            ok = (pe  is not None and 0 < pe  < TIER0_PE_MAX and
                  pb  is not None and 0 < pb  < TIER0_PB_MAX and
                  eps is not None and eps      > TIER0_EPS_MIN and
                  mcap > TIER0_MCAP_MIN)

            tag = "✓" if ok else "✗"
            print(f"  {tag} {ticker:<8}  PE:{str(round(pe,1) if pe else 'N/A'):<8}"
                  f"  PB:{str(round(pb,2) if pb else 'N/A'):<8}  {sector}")

            if ok:
                candidates.append({"ticker": ticker, "name": lname, "sector": sector})
            else:
                skipped += 1

        except Exception as e:
            print(f"  ? {ticker:<8}  {e}")
            skipped += 1

        time.sleep(0.3)

    result = pd.DataFrame(candidates)
    print(f"\nResult: {len(candidates)} pass / {skipped} excluded / {total} total")
    if not result.empty:
        print("\nBy sector:")
        for sec, g in result.groupby("sector"):
            print(f"  {sec:<30} {len(g)}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",     default=None)
    parser.add_argument("--dry-run",    action="store_true",
                        help="Skip yfinance Tier-0 filter — include ό,τι βρέθηκε")
    parser.add_argument("--sp500-only", action="store_true")
    parser.add_argument("--market", choices=["sp500", "europe", "asia", "china_adr", "all"],
                        default="sp500",
                        help="sp500 (US) | europe (DAX+FTSE100+EuroStoxx50) | "
                             "asia (Nikkei225+HangSeng) | china_adr (US-listed ADRs) | all")
    args = parser.parse_args()

    frames = []

    if args.market in ("sp500", "all"):
        sp500 = fetch_sp500()
        frames.append(sp500)
        if not args.sp500_only:
            frames.append(fetch_nasdaq100_extras(set(sp500["ticker"])))

    if args.market in ("europe", "all"):
        frames.append(fetch_dax())
        frames.append(fetch_ftse100())
        frames.append(fetch_euro_stoxx50())

    if args.market in ("asia", "all"):
        frames.append(fetch_nikkei225())
        frames.append(fetch_hang_seng())

    if args.market in ("china_adr", "all"):
        frames.append(fetch_china_adr())

    frames   = [f for f in frames if not f.empty]
    universe = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    if universe.empty:
        print("Καμία εταιρεία δεν βρέθηκε — έλεγξε δικτυακή πρόσβαση/Wikipedia δομή.")
        raise SystemExit(1)

    default_output = {
        "sp500": "watchlist.csv", "europe": "watchlist_europe.csv",
        "asia": "watchlist_asia.csv", "china_adr": "watchlist_china_adr.csv",
        "all": "watchlist_all.csv",
    }[args.market]
    output = args.output or default_output

    result = tier0_filter(universe, dry_run=args.dry_run)
    if result.empty:
        print("No stocks passed Tier-0.")
    else:
        cols = ["ticker", "name", "sector"] + (["market"] if "market" in result.columns else [])
        result[cols].to_csv(output, index=False)
        print(f"\nSaved {len(result)} stocks → {output}")
