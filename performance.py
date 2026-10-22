"""
performance.py — Μέτρηση αν το σήμα του screener προβλέπει αποδόσεις.

Γιατί υπάρχει: το παλιό Performance Tracker μετρούσε ΑΠΟΛΥΤΗ απόδοση των
shortlist picks. Αυτό δεν λέει τίποτα — σε ανοδική αγορά όλα "κερδίζουν".
Το ερώτημα είναι: (α) νικούν οι STRONG BUY/BUY το benchmark; (β) νικούν
τις HOLD/AVOID; (γ) υπάρχει σταθερή συσχέτιση score → μελλοντική απόδοση;

Πηγές σημάτων:
  - snapshots/YYYY-MM-DD.csv  — ΟΛΟ το universe κάθε εβδομάδα (από FIX SNAP
    και μετά). Το yfinance δεν δίνει point-in-time ιστορικά fundamentals,
    άρα το μόνο τίμιο backtest είναι αυτό που χτίζουμε εμείς από τώρα.
  - history.csv               — παλιό ledger (μόνο shortlist), για ημερομηνίες
    χωρίς snapshot.

Μεθοδολογία (ρητές υποθέσεις):
  - Entry = πρώτο close ΜΕΤΑ την ημερομηνία σήματος (το run γίνεται Κυριακή,
    άρα Δευτέρα close) — αποφεύγει look-ahead.
  - Total return από adjusted close (yfinance auto_adjust → splits+μερίσματα).
  - Excess = απόδοση μετοχής − απόδοση benchmark της ίδιας αγοράς, ίδιο
    διάστημα, στο τοπικό νόμισμα.
  - Ορίζοντες σε ημερολογιακές ημέρες· exit = τελευταίο close ≤ entry+h.
  - Εβδομαδιαία σήματα επικαλύπτονται (η ίδια μετοχή κάθε εβδομάδα) → οι
    παρατηρήσεις ΔΕΝ είναι ανεξάρτητες· τα n και t-stat υπερεκτιμούν τη
    στατιστική βεβαιότητα.
"""
import datetime
import os
import time

import pandas as pd

HORIZONS = {"1m": 30, "3m": 91, "6m": 182, "12m": 365}
TIERS    = ["STRONG BUY", "BUY", "HOLD", "AVOID"]
MIN_OBS_PER_DATE_FOR_IC = 10

SNAPSHOT_COLUMNS = [
    "ticker", "sector", "market", "price", "pe", "pb", "eps", "roe", "de",
    "ev_ebitda", "roic", "roic_source", "fcf_yield", "fcf_source",
    "g_base_pct", "growth_source", "dcf_base_mos", "graham_mos",
    "analyst_upside", "pct_from_low", "rsi", "pct_vs_dma200",
    "insider_net_pct", "beta", "wacc", "div_yield", "risk_overall",
    "fragility", "tier", "tier_score", "valuation_score", "quality_score",
    "macro_score", "catalyst_score", "data_completeness", "data_warning",
    "currency_note", "passed_filters",
]

# Benchmark ανά exchange suffix — total-return ETFs (adjusted close
# περιλαμβάνει μερίσματα). ΥΠΟΘΕΣΗ: EXSA.DE (STOXX Europe 600, EUR) για όλη
# την ηπειρωτική Ευρώπη, και για .SW/.ST/.CO/.OL που διαπραγματεύονται σε
# άλλο νόμισμα — εκεί το excess περιέχει και FX θόρυβο.
_BENCH_BY_SUFFIX = {".L": "ISF.L", ".T": "1306.T", ".HK": "2800.HK"}
_EUROPE_SUFFIXES = (".DE", ".PA", ".AS", ".MI", ".MC", ".BR", ".HE", ".SW",
                    ".CO", ".ST", ".OL", ".VI", ".LS", ".IR")
US_BENCHMARK = "SPY"


def benchmark_for(ticker: str) -> str:
    t = str(ticker).upper()
    for sfx, bench in _BENCH_BY_SUFFIX.items():
        if t.endswith(sfx):
            return bench
    if t.endswith(_EUROPE_SUFFIXES):
        return "EXSA.DE"
    return US_BENCHMARK   # US + US-listed ADRs


# ─────────────────────────────────────────────────────────────────────
# Snapshots
# ─────────────────────────────────────────────────────────────────────
def save_snapshot(scored_df: pd.DataFrame, snap_dir: str, date: datetime.date = None) -> str:
    """Γράφει ΟΛΟ το scored universe. Ίδια ημέρα → overwrite (idempotent)."""
    date = date or datetime.date.today()
    os.makedirs(snap_dir, exist_ok=True)
    df = scored_df.copy()
    if "risk" in df.columns and "risk_overall" not in df.columns:
        df["risk_overall"] = df["risk"].apply(lambda r: r.get("overall") if isinstance(r, dict) else None)
    for c in SNAPSHOT_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[SNAPSHOT_COLUMNS]
    df.insert(0, "date", date.isoformat())
    path = os.path.join(snap_dir, f"{date.isoformat()}.csv")
    df.to_csv(path, index=False)
    print(f"[SNAPSHOT] {len(df)} μετοχές → {path}")
    return path


def load_signals(snap_dir: str, history_file: str = None) -> pd.DataFrame:
    """
    Ενιαίο DataFrame σημάτων: date, ticker, tier, tier_score, source.
    Snapshots έχουν προτεραιότητα· history.csv μόνο για ημερομηνίες χωρίς
    snapshot.
    """
    frames = []
    snap_dates = set()
    if os.path.isdir(snap_dir):
        for fn in sorted(os.listdir(snap_dir)):
            if fn.endswith(".csv"):
                s = pd.read_csv(os.path.join(snap_dir, fn))
                if s.empty:
                    continue
                s["source"] = "snapshot"
                frames.append(s[["date", "ticker", "tier", "tier_score", "source"]])
                snap_dates.add(str(s["date"].iloc[0]))
    if history_file and os.path.exists(history_file):
        h = pd.read_csv(history_file)
        h = h.rename(columns={"date_flagged": "date"})
        h = h[~h["date"].astype(str).isin(snap_dates)]
        for c in ("tier", "tier_score"):
            if c not in h.columns:
                h[c] = None
        h["source"] = "history"
        frames.append(h[["date", "ticker", "tier", "tier_score", "source"]])
    if not frames:
        return pd.DataFrame(columns=["date", "ticker", "tier", "tier_score", "source"])
    sig = pd.concat(frames, ignore_index=True)
    sig["date"] = pd.to_datetime(sig["date"])
    return sig.drop_duplicates(subset=["date", "ticker"], keep="first")


# ─────────────────────────────────────────────────────────────────────
# Τιμές
# ─────────────────────────────────────────────────────────────────────
def fetch_adj_closes(tickers, start, end, session=None, chunk=150, delay=1.5) -> pd.DataFrame:
    """Wide DataFrame (index=ημερομηνία, columns=ticker) με adjusted close."""
    import yfinance as yf
    tickers = sorted(set(tickers))
    out = []
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        kw = dict(start=start, end=end, auto_adjust=True, progress=False, threads=True)
        try:
            data = yf.download(part, session=session, **kw) if session else yf.download(part, **kw)
        except TypeError:   # παλιές εκδόσεις χωρίς session param
            data = yf.download(part, **kw)
        except Exception as e:
            print(f"[PERF] download αποτυχία ({e}) για {len(part)} tickers")
            continue
        if data is None or data.empty:
            continue
        close = data["Close"] if "Close" in data.columns.get_level_values(0) else data
        if isinstance(close, pd.Series):
            close = close.to_frame(part[0])
        out.append(close)
        if i + chunk < len(tickers):
            time.sleep(delay)
    if not out:
        return pd.DataFrame()
    prices = pd.concat(out, axis=1)
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    return prices.loc[:, ~prices.columns.duplicated()].sort_index()


def _entry_exit(series: pd.Series, signal_date, days):
    s = series.dropna()
    after = s[s.index > signal_date]
    if after.empty:
        return None
    entry_date = after.index[0]
    target = entry_date + pd.Timedelta(days=days)
    if s.index[-1] < target:
        return None                       # ο ορίζοντας δεν έχει ολοκληρωθεί
    exit_px = s[s.index <= target].iloc[-1]
    return entry_date, float(after.iloc[0]), float(exit_px)


# ─────────────────────────────────────────────────────────────────────
# Αποδόσεις & στατιστικά
# ─────────────────────────────────────────────────────────────────────
def forward_returns(signals: pd.DataFrame, prices: pd.DataFrame, horizons=HORIZONS) -> pd.DataFrame:
    rows = []
    for _, sg in signals.iterrows():
        t, bench = sg["ticker"], benchmark_for(sg["ticker"])
        if t not in prices.columns or bench not in prices.columns:
            continue
        for hname, days in horizons.items():
            st = _entry_exit(prices[t], sg["date"], days)
            bm = _entry_exit(prices[bench], sg["date"], days)
            if not st or not bm or st[1] <= 0 or bm[1] <= 0:
                continue
            r  = st[2] / st[1] - 1
            rb = bm[2] / bm[1] - 1
            rows.append({"date": sg["date"], "ticker": t, "tier": sg["tier"],
                         "tier_score": sg["tier_score"], "source": sg["source"],
                         "horizon": hname, "ret": r, "bench_ret": rb, "excess": r - rb})
    return pd.DataFrame(rows)


def tier_stats(fr: pd.DataFrame) -> pd.DataFrame:
    """Ανά ορίζοντα × tier: n, ημερομηνίες, μέσο/διάμεσο excess, hit rate."""
    if fr.empty:
        return pd.DataFrame()
    d = fr[fr["tier"].isin(TIERS)]
    g = d.groupby(["horizon", "tier"])
    st = pd.DataFrame({
        "n":             g.size(),
        "n_dates":       g["date"].nunique(),
        "mean_excess":   g["excess"].mean() * 100,
        "median_excess": g["excess"].median() * 100,
        "hit_rate":      g["excess"].apply(lambda x: (x > 0).mean() * 100),
    }).reset_index()
    return st


def _spearman(a: pd.Series, b: pd.Series) -> float:
    # rank + Pearson — αποφεύγει εξάρτηση από scipy
    return a.rank().corr(b.rank())


def ic_stats(fr: pd.DataFrame) -> pd.DataFrame:
    """
    Information Coefficient: Spearman(tier_score, excess) ανά ημερομηνία,
    μετά μέσος όρος. t ≈ mean/std·√n_dates. ΠΡΟΣΟΧΗ: σε ημερομηνίες
    history.csv το universe είναι μόνο το shortlist (restricted range →
    IC μεροληπτικά προς το 0).
    """
    if fr.empty:
        return pd.DataFrame()
    out = []
    for hname, grp in fr.dropna(subset=["tier_score"]).groupby("horizon"):
        ics = []
        for _, day in grp.groupby("date"):
            if (len(day) >= MIN_OBS_PER_DATE_FOR_IC and day["tier_score"].nunique() > 1
                    and day["excess"].nunique() > 1):
                ic = _spearman(day["tier_score"].astype(float), day["excess"])
                if pd.notna(ic):
                    ics.append(ic)
        if ics:
            s = pd.Series(ics)
            t = s.mean() / s.std() * len(s) ** 0.5 if len(s) > 1 and s.std() > 0 else None
            out.append({"horizon": hname, "n_dates": len(s), "mean_ic": s.mean(), "t_stat": t})
    return pd.DataFrame(out)


def ticker_table(signals: pd.DataFrame, prices: pd.DataFrame, min_days=21) -> pd.DataFrame:
    """Πρώτη πρόταση ανά ticker (≥min_days) — απόδοση έως σήμερα vs benchmark."""
    if signals.empty or prices.empty:
        return pd.DataFrame()
    # STRONG BUY/BUY· NaN tier = πρώτα runs του history.csv πριν υπάρξει tier
    sig = signals[signals["tier"].isin(["STRONG BUY", "BUY"]) | signals["tier"].isna()]
    first = sig.sort_values("date").drop_duplicates("ticker", keep="first")
    cutoff = pd.Timestamp(datetime.date.today()) - pd.Timedelta(days=min_days)
    rows = []
    for _, sg in first[first["date"] <= cutoff].iterrows():
        t, bench = sg["ticker"], benchmark_for(sg["ticker"])
        if t not in prices.columns or bench not in prices.columns:
            continue
        s, b = prices[t].dropna(), prices[bench].dropna()
        s_after, b_after = s[s.index > sg["date"]], b[b.index > sg["date"]]
        if s_after.empty or b_after.empty:
            continue
        r  = s.iloc[-1] / s_after.iloc[0] - 1
        rb = b.iloc[-1] / b_after.iloc[0] - 1
        rows.append({"ticker": t, "date_flagged": sg["date"].date().isoformat(),
                     "tier": sg["tier"] if pd.notna(sg["tier"]) else "—",
                     "benchmark": bench, "return_pct": round(r * 100, 1),
                     "bench_pct": round(rb * 100, 1), "excess_pct": round((r - rb) * 100, 1),
                     "days_held": (pd.Timestamp(datetime.date.today()) - sg["date"]).days})
    df = pd.DataFrame(rows)
    return df.sort_values("excess_pct", ascending=False) if not df.empty else df


def evaluate(snap_dir: str, history_file: str, session=None, delay=1.5) -> dict:
    """Ενορχήστρωση για το email. Αποτυχία → άδεια αποτελέσματα, όχι crash."""
    empty = {"tier_stats": pd.DataFrame(), "ic": pd.DataFrame(), "tickers": pd.DataFrame(),
             "n_signal_dates": 0, "first_date": None}
    try:
        sig = load_signals(snap_dir, history_file)
        if sig.empty:
            return empty
        tickers = set(sig["ticker"]) | {benchmark_for(t) for t in sig["ticker"]}
        start = (sig["date"].min() - pd.Timedelta(days=7)).date().isoformat()
        end   = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        prices = fetch_adj_closes(tickers, start, end, session=session, delay=delay)
        if prices.empty:
            print("[PERF] Καμία τιμή — παράλειψη performance section.")
            return empty
        fr = forward_returns(sig, prices)
        res = {"tier_stats": tier_stats(fr), "ic": ic_stats(fr),
               "tickers": ticker_table(sig, prices),
               "n_signal_dates": sig["date"].nunique(),
               "first_date": sig["date"].min().date().isoformat()}
        print(f"[PERF] {len(fr)} forward-return παρατηρήσεις, "
              f"{res['n_signal_dates']} ημερομηνίες σημάτων")
        return res
    except Exception as e:
        print(f"[PERF] αποτυχία αξιολόγησης ({e})")
        return empty
