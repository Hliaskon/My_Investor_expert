"""
test_macro.py — Local validation για το macro_regime module
Τρέξε locally πριν deploy στο GitHub Actions:
  python test_macro.py
"""
import os
import sys

# Βάλε το FRED key σου εδώ για local test
# ΜΗΝ το κάνεις commit στο GitHub
FRED_KEY = os.environ.get("FRED_API_KEY", "")

if not FRED_KEY:
    print("ERROR: FRED_API_KEY not set.")
    print("Τρέξε: export FRED_API_KEY=your_key_here")
    sys.exit(1)

try:
    from fredapi import Fred
except ImportError:
    print("ERROR: fredapi not installed. Τρέξε: pip install fredapi")
    sys.exit(1)

from macro_regime import (
    get_macro_inputs,
    classify_regime,
    yield_curve_signal,
    fear_liquidity_score,
    calculate_sector_pe,
    evaluate_sector_valuation,
    check_stock_macro_alignment,
    render_macro_html,
)

print("=" * 50)
print("MACRO REGIME MODULE — LOCAL TEST")
print("=" * 50)

fred   = Fred(api_key=FRED_KEY)
inputs = get_macro_inputs(fred)

print("\n=== MACRO INPUTS ===")
for k, v in inputs.items():
    print(f"  {k:25s}: {v}")

regime     = classify_regime(inputs)
yield_sig  = yield_curve_signal(inputs["yield_spread"])
fear       = fear_liquidity_score(inputs)

print(f"\n=== REGIME: {regime['regime']} — {regime['regime_gr']} ===")
print(f"  Favored : {regime['favored_sectors']}")
print(f"  Avoid   : {regime['avoid_sectors']}")

print(f"\n=== YIELD CURVE: {yield_sig['label']} ===")
print(f"  Spread  : {inputs['yield_spread']:+.3f}%")
print(f"  Detail  : {yield_sig['detail']}")

print(f"\n=== FEAR & LIQUIDITY: Score {fear['score']} — {fear['verdict']['label']} ===")
for s in fear["signals"]:
    print(f"  • {s}")

# Test sector valuation με dummy data
import pandas as pd
test_df = pd.DataFrame([
    {"ticker": "BIIB", "sector": "Healthcare",  "pe": 16.2},
    {"ticker": "HON",  "sector": "Industrials", "pe": 21.4},
    {"ticker": "JPM",  "sector": "Financials",  "pe": 11.8},
    {"ticker": "DAL",  "sector": "Airlines",    "pe": 8.1},
])
sector_pe   = calculate_sector_pe(test_df)
sector_vals = evaluate_sector_valuation(sector_pe)

print(f"\n=== SECTOR VALUATION ===")
for sv in sector_vals:
    print(f"  {sv['sector']:25s}: {sv['label']} — {sv['note']}")

# Test alignment
print(f"\n=== STOCK MACRO ALIGNMENT ===")
for _, row in test_df.iterrows():
    align = check_stock_macro_alignment(row["sector"], regime)
    print(f"  {row['ticker']:6s} ({row['sector']:20s}): {align['label']} — {align['detail']}")

# Test HTML render
html = render_macro_html(inputs, regime, yield_sig, fear, sector_vals)
with open("/tmp/macro_test.html", "w") as f:
    f.write(f"<html><body style='background:#0d0d1a;padding:20px'>{html}</body></html>")
print(f"\n✅ HTML rendered → /tmp/macro_test.html")
print("\nΌλα ΟΚ. Έτοιμο για deploy.")
