"""
build_watchlist.py — Dynamic Watchlist Generator
Χρήση: python build_watchlist.py [--output watchlist.csv] [--dry-run]

Fetches S&P 500 from Wikipedia + NASDAQ 100 additions,
applies Tier-0 pre-filter via yfinance,
saves value-eligible stocks to watchlist.csv.

Tier-0 criteria (broad — excludes obvious non-value):
  PE < 40, PB < 6, EPS > 0, MarketCap > $1B

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
    parser.add_argument("--output",     default="watchlist.csv")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Skip yfinance — include all S&P 500 stocks")
    parser.add_argument("--sp500-only", action="store_true")
    args = parser.parse_args()

    sp500    = fetch_sp500()
    universe = sp500
    if not args.sp500_only:
        extras   = fetch_nasdaq100_extras(set(sp500["ticker"]))
        universe = pd.concat([sp500, extras], ignore_index=True)

    result = tier0_filter(universe, dry_run=args.dry_run)
    if result.empty:
        print("No stocks passed Tier-0.")
    else:
        result[["ticker", "name", "sector"]].to_csv(args.output, index=False)
        print(f"\nSaved {len(result)} stocks → {args.output}")
