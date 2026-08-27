# My Investor Expert

Αυτοματοποιημένο value-investing screener. Τρέχει κάθε Κυριακή, σαρώνει το
watchlist (SP500 + προαιρετικά Ευρώπη/Ασία), υπολογίζει DCF/Graham valuation,
βαθμολογεί κάθε μετοχή σε **STRONG BUY / BUY / HOLD / AVOID**, και στέλνει
αναφορά με email.

**Δεν αποτελεί επενδυτική συμβουλή.** Είναι screening/idea-generation
εργαλείο — η τελική απόφαση και ο έλεγχος παραμένουν δικά σου. Δες
[Γνωστοί περιορισμοί](#γνωστοί-περιορισμοί--τι-να-μην-εμπιστευτείς-τυφλά)
πριν βασιστείς σε οτιδήποτε προτείνει.

## Πώς δουλεύει

```
build_watchlist.py  →  watchlist*.csv  →  screener.py  →  report.py  →  email
   (Wikipedia scrape)   (ticker λίστες)    (yfinance +      (HTML)
                                             DCF/Graham/
                                             tier scoring)
```

1. **`build_watchlist.py`** — τραβάει tickers από Wikipedia (SP500, DAX,
   FTSE100, EuroStoxx50, Nikkei225, Hang Seng) ή curated λίστα (US-listed
   China ADRs), προαιρετικό Tier-0 pre-filter με yfinance (PE/PB/EPS/MCap).
2. **`screener.py`** — για κάθε ticker: τραβάει fundamentals από yfinance,
   υπολογίζει DCF (bear/base/bull), Graham formula, EV/EBITDA, ROE/ROIC,
   fragility score, macro alignment, και τελικό **tier** (βλ. παρακάτω).
3. **`macro_regime.py`** — macro overlay από FRED (GDP, Core PCE, yield
   curve, Fed rate, VIX, HY spreads) → κατηγοριοποιεί σε regime
   (OVERHEATING/GOLDILOCKS/STAGFLATION/RECESSION) → favored/avoid sectors.
4. **`report.py`** — χτίζει το HTML email. Πλήρης ανάλυση μόνο για
   STRONG BUY/BUY (μέχρι 10, ώστε να μη σκάει το όριο μεγέθους του Gmail).
5. **`history.csv`** — κάθε shortlist pick καταγράφεται με ημερομηνία+τιμή.
   Μετά από 21+ μέρες, εμφανίζεται "Performance Tracker" section στο email
   με πραγματική απόδοση — έτσι μαθαίνεις αν το σήμα όντως δουλεύει.

## Tier System (STRONG BUY / BUY / HOLD / AVOID)

Πολυπαραγοντικό, διαφανές scoring — όχι μαύρο κουτί:

| Συνιστώσα | Τι ελέγχει |
|---|---|
| **EPS quality gate** (hard veto) | Αν EPS σχεδόν μηδενικό σχετικά με την τιμή → AVOID αυτόματα (αποτρέπει artifacts τύπου "DCF MoS +35000%") |
| **Data completeness gate** | Αν λείπουν >50% βασικών πεδίων → ανώτατο HOLD |
| **Valuation convergence** (0-40) | DCF MoS>20% (+15) · Graham MoS>20% (+10) · EV/EBITDA<8x (+10) · Analyst upside>15% (+5) |
| **Quality** (0-30, Buffett-style) | ROE≥15% (+15) · ROIC>WACC (+10) · D/E<1.0 (+5) |
| **Macro/Risk** (0-20) | Favored sector (+10) · Risk όχι high (+10) |

```
STRONG BUY: score≥65 ΚΑΙ data≥75%
BUY:        score≥45 ΚΑΙ data≥60%
HOLD:       score≥25, ή data<50%
AVOID:      τα υπόλοιπα, ή αποτυχία EPS gate
```

Πλήρης επεξήγηση όλων των δεικτών (P/E, DCF, Graham, ROIC, Fragility,
Sector Valuation κλπ): **[GUIDE.md](./GUIDE.md)**

## Setup

### GitHub Secrets (Settings → Secrets and variables → Actions → Secrets)

| Secret | Χρήση |
|---|---|
| `EMAIL_SENDER` | Gmail address που στέλνει το report |
| `EMAIL_PASSWORD` | Gmail App Password (όχι το κανονικό password) |
| `EMAIL_RECEIVER` | Πού στέλνεται το email |
| `ANTHROPIC_API_KEY` | Για το Claude summary (3 bullets) στο email |
| `FRED_API_KEY` | Για το macro dashboard (δωρεάν key από fred.stlouisfed.org) |

### GitHub Variables (ίδιο μενού, tab "Variables")

| Variable | Default | Χρήση |
|---|---|---|
| `WATCHLIST_FILE` | `watchlist.csv` | Comma-separated λίστα CSV για συνδυασμό αγορών, π.χ. `watchlist.csv,watchlist_europe.csv` |

## Workflows

### `Stock Screener` (αυτόματο)
Κάθε **Κυριακή 06:00 UTC** (09:00 Ελλάδας καλοκαίρι, 08:00 χειμώνα).
Σαρώνει ολόκληρο το `WATCHLIST_FILE`, στέλνει email, κάνει commit το
`history.csv`. Μπορεί να τρέξει χειροκίνητα από Actions → Stock Screener →
Run workflow.

### `Build Watchlist` (χειροκίνητο)
Actions → Build Watchlist → Run workflow → επίλεξε αγορά:
- `sp500` — S&P 500 (Wikipedia)
- `europe` — DAX 40 + FTSE 100 + EURO STOXX 50
- `asia` — Nikkei 225 + Hang Seng
- `china_adr` — Curated US-listed China ADRs (BABA, JD, PDD κλπ — **όχι**
  HKEX/A-shares, βλ. περιορισμούς παρακάτω)
- `all` — όλα μαζί

Έχει και `dry_run` checkbox — παρακάμπτει το yfinance Tier-0 filter, παίρνει
όλα τα tickers χωρίς έλεγχο PE/PB. Χρήσιμο αν η Yahoo μπλοκάρει.

## Γνωστοί περιορισμοί — τι να μην εμπιστευτείς τυφλά

- **Χωρίς backtest ακόμα.** Το `history.csv`/performance tracker μόλις
  ξεκίνησε να μαζεύει δεδομένα. Μέχρι να έχεις 2-3 μήνες ιστορικού, δεν
  ξέρεις αν το tier σήμα προβλέπει πραγματικά κάτι.
- **yfinance είναι unofficial** (reverse-engineered, όχι επίσημο API).
  Χρησιμοποιεί `curl_cffi` με browser-impersonation για να παρακάμψει
  rate-limiting της Yahoo σε shared GitHub Actions IPs — αυτό μπορεί να
  σταματήσει να δουλεύει όποτε αλλάξει κάτι η Yahoo.
- **DCF βασίζεται σε πρόχειρο FCF proxy** (`EPS × 0.7`, flat σε όλους τους
  κλάδους) και single-quarter earnings growth ως driver. Χρήσιμο για
  σύγκριση, όχι ακριβής αποτίμηση.
- **Macro regime** βασίζεται σε GDP/CPI quarterly data (lag φυσιολογικός)
  και δυαδική ταξινόμηση (growing/not, high-inflation/not) — πολύ πιο
  απλοϊκό από πραγματική hedge-fund macro ανάλυση.
- **Ticker universe** από Wikipedia scraping — έχουμε ήδη βρει και
  διορθώσει πολλαπλά stale entries (εταιρείες που συγχωνεύτηκαν/
  delisted). Πιθανόν υπάρχουν κι άλλα ανακάλυπτα λάθη.
- **Καμία ποιοτική κρίση** (moat, management, ανταγωνιστική θέση) — μόνο
  αριθμοί. Ούτε ο Graham ούτε ο Buffett αγόραζαν τυφλά από screener output.

## Αρχεία

| Αρχείο | Σκοπός |
|---|---|
| `screener.py` | Κύρια λογική: fetch, DCF, Graham, tier scoring, email |
| `build_watchlist.py` | Δημιουργεί/ενημερώνει watchlist CSVs |
| `macro_regime.py` | FRED macro data → regime classification |
| `report.py` | HTML email template |
| `watchlist.csv` | US universe (S&P 500 + NASDAQ 100 extras) |
| `watchlist_europe.csv` / `watchlist_asia.csv` / `watchlist_china_adr.csv` | Παράγονται από `Build Watchlist` workflow |
| `history.csv` | Ιστορικό προτάσεων για performance tracking |
| `GUIDE.md` | Πλήρης επεξήγηση κάθε δείκτη/threshold |
| `validate_international_coverage.py` | Έλεγχος αν το yfinance καλύπτει διεθνή tickers πριν τα προσθέσεις μαζικά |
