"""
macro_regime.py — Macro Overlay Module
Spec v1.0 — Hlias Koninis — 2026-04-13

Layer 1: Macro Regime (GDP + CPI + PMI + Yield Curve)
Layer 2: Sector Overlay (P/E vs historical)
Layer 3: Fear & Liquidity (VIX + Credit Spreads + Fed Rate)
"""

import time
import datetime

SECTOR_HISTORICAL_PE = {
    "Healthcare":             {"avg_pe": 18.0, "cheap_threshold": 15.0, "expensive_threshold": 22.0},
    "Industrials":            {"avg_pe": 20.0, "cheap_threshold": 16.0, "expensive_threshold": 25.0},
    "Technology":             {"avg_pe": 26.0, "cheap_threshold": 20.0, "expensive_threshold": 32.0},
    "Consumer Cyclical":      {"avg_pe": 22.0, "cheap_threshold": 16.0, "expensive_threshold": 28.0},
    "Consumer Defensive":     {"avg_pe": 19.0, "cheap_threshold": 15.0, "expensive_threshold": 23.0},
    "Energy":                 {"avg_pe": 14.0, "cheap_threshold": 10.0, "expensive_threshold": 18.0},
    "Financials":             {"avg_pe": 13.0, "cheap_threshold": 10.0, "expensive_threshold": 16.0},
    "Utilities":              {"avg_pe": 17.0, "cheap_threshold": 13.0, "expensive_threshold": 21.0},
    "Basic Materials":        {"avg_pe": 17.0, "cheap_threshold": 13.0, "expensive_threshold": 21.0},
    "Airlines":               {"avg_pe": 10.0, "cheap_threshold": 7.0,  "expensive_threshold": 14.0},
    "Communication Services": {"avg_pe": 18.0, "cheap_threshold": 14.0, "expensive_threshold": 22.0},
}

def get_macro_inputs(fred_client):
    inputs = {}
    today  = datetime.date.today().isoformat()
    inputs["date"] = today

    def fred_safe(series_id, observation_start="2022-01-01", retries=2):
        for attempt in range(retries + 1):
            try:
                time.sleep(0.2)
                return fred_client.get_series(series_id, observation_start=observation_start)
            except Exception as e:
                if attempt < retries:
                    time.sleep(1)
                else:
                    print(f"[MACRO] Failed to fetch {series_id}: {e}")
                    return None

    # GDP Growth YoY % — REAL (inflation-adjusted), όχι nominal.
    # FIX Z (κρίσιμο): το series "GDP" του FRED είναι ΟΝΟΜΑΣΤΙΚΟ ΑΕΠ
    # (nominal, δεν αφαιρεί πληθωρισμό). Το "GDPC1" είναι το πραγματικό
    # (real) ΑΕΠ. Το classifier threshold "gdp_growing = gdp_yoy > 2.0"
    # (βλ. παρακάτω) είναι βαθμονομημένο για πραγματικό GDP growth
    # (τυπικό εύρος ~1.5-3%) — nominal growth = real growth + πληθωρισμός,
    # οπότε σε high-inflation περιβάλλον (π.χ. Core PCE 3%+) φούσκωνε
    # τεχνητά το νούμερο (φάνηκε ως 6.6% σε batch 35) και έσπρωχνε
    # συστηματικά την ταξινόμηση προς "Overheating"/"Expansion".
    gdp = fred_safe("GDPC1")
    if gdp is not None and len(gdp.dropna()) >= 4:
        inputs["gdp_yoy"]      = round(gdp.pct_change(4).dropna().iloc[-1] * 100, 2)
        inputs["gdp_date"]     = str(gdp.dropna().index[-1].date())
    else:
        inputs["gdp_yoy"]  = 2.0
        inputs["gdp_date"] = "N/A"

    # CPI YoY %
    cpi = fred_safe("CPIAUCSL")
    if cpi is not None and len(cpi.dropna()) >= 12:
        inputs["cpi_yoy"] = round(cpi.pct_change(12).dropna().iloc[-1] * 100, 2)
    else:
        inputs["cpi_yoy"] = 3.0

    # Core PCE YoY % (Fed preferred)
    pce = fred_safe("PCEPILFE")
    if pce is not None and len(pce.dropna()) >= 12:
        inputs["pce_yoy"] = round(pce.pct_change(12).dropna().iloc[-1] * 100, 2)
    else:
        inputs["pce_yoy"] = 2.8

    # Yield Curve 10Y-2Y
    spread = fred_safe("T10Y2Y", observation_start="2024-01-01")
    if spread is not None and len(spread.dropna()) > 0:
        inputs["yield_spread"] = round(float(spread.dropna().iloc[-1]), 3)
    else:
        inputs["yield_spread"] = 0.0  # flat — neutral fallback

    # Fed Funds Rate
    fed = fred_safe("FEDFUNDS", observation_start="2024-01-01")
    if fed is not None and len(fed.dropna()) > 0:
        fed_clean          = fed.dropna()
        inputs["fed_rate"] = round(float(fed_clean.iloc[-1]), 2)
        ref                = fed_clean.iloc[-4] if len(fed_clean) >= 4 else fed_clean.iloc[0]
        if inputs["fed_rate"] < float(ref) - 0.05:
            inputs["fed_direction"] = "cutting"
        elif inputs["fed_rate"] > float(ref) + 0.05:
            inputs["fed_direction"] = "hiking"
        else:
            inputs["fed_direction"] = "holding"
    else:
        inputs["fed_rate"]      = 4.33
        inputs["fed_direction"] = "holding"

    # VIX
    try:
        import yfinance as yf
        vix_data       = yf.download("^VIX", period="5d", progress=False)
        inputs["vix"]  = round(float(vix_data["Close"].iloc[-1]), 1)
    except Exception as e:
        print(f"[MACRO] VIX fetch failed: {e} — using default 20")
        inputs["vix"] = 20.0

    # HY Credit Spread
    hy = fred_safe("BAMLH0A0HYM2", observation_start="2024-01-01")
    if hy is not None and len(hy.dropna()) > 0:
        hy_clean               = hy.dropna()
        inputs["hy_spread"]    = round(float(hy_clean.iloc[-1]), 1)
        ref_hy                 = hy_clean.iloc[-66] if len(hy_clean) >= 66 else hy_clean.iloc[0]
        inputs["hy_spread_change"] = round(float(hy_clean.iloc[-1]) - float(ref_hy), 1)
    else:
        inputs["hy_spread"]        = 400.0
        inputs["hy_spread_change"] = 0.0

    return inputs


def classify_regime(inputs):
    gdp_growing    = inputs["gdp_yoy"] > 2.0
    inflation_high = inputs["pce_yoy"] > 2.5

    if gdp_growing and inflation_high:
        return {
            "regime":          "OVERHEATING",
            "regime_gr":       "Υπερθέρμανση",
            "favored_sectors": ["Energy", "Basic Materials", "Financials", "Industrials"],
            "avoid_sectors":   ["Utilities", "Real Estate", "Technology"],
            "color":           "#FF6B35",
            "description":     "Ανάπτυξη + υψηλός πληθωρισμός. Ευνοούνται real assets και κυκλικοί κλάδοι.",
        }
    elif gdp_growing and not inflation_high:
        return {
            "regime":          "GOLDILOCKS",
            "regime_gr":       "Goldilocks — Ιδανικό",
            "favored_sectors": ["Technology", "Consumer Cyclical", "Industrials", "Healthcare"],
            "avoid_sectors":   ["Utilities", "Energy"],
            "color":           "#2ECC71",
            "description":     "Ανάπτυξη + χαμηλός πληθωρισμός. Ιδανικό περιβάλλον για μετοχές.",
        }
    elif not gdp_growing and inflation_high:
        return {
            "regime":          "STAGFLATION",
            "regime_gr":       "Στασιμοπληθωρισμός",
            "favored_sectors": ["Healthcare", "Utilities", "Consumer Defensive", "Energy"],
            "avoid_sectors":   ["Consumer Cyclical", "Real Estate", "Technology"],
            "color":           "#E74C3C",
            "description":     "Επιβράδυνση + υψηλός πληθωρισμός. Το δυσκολότερο περιβάλλον για μετοχές.",
        }
    else:
        return {
            "regime":          "RECESSION",
            "regime_gr":       "Ύφεση / Επιβράδυνση",
            "favored_sectors": ["Healthcare", "Consumer Defensive", "Utilities"],
            "avoid_sectors":   ["Financials", "Energy", "Industrials", "Consumer Cyclical"],
            "color":           "#8E44AD",
            "description":     "Επιβράδυνση + χαμηλός πληθωρισμός. Defensive positioning.",
        }


def yield_curve_signal(spread):
    if spread < -0.5:
        return {"signal": "INVERTED",      "label": "🔴 Ανεστραμμένη",     "detail": "Recession warning — ιστορικά 12-18 μήνες lead time"}
    elif spread < 0:
        return {"signal": "FLAT_INVERTED", "label": "🟡 Οριακά Αρνητική", "detail": "Caution — παρακολούθηση"}
    elif spread < 0.5:
        return {"signal": "FLAT",          "label": "🟡 Επίπεδη",          "detail": "Neutral — μεταβατική φάση"}
    else:
        return {"signal": "NORMAL",        "label": "🟢 Κανονική",         "detail": "Expansionary — θετικό σήμα"}


def fear_liquidity_score(inputs):
    score   = 0
    signals = []

    # VIX
    vix = inputs["vix"]
    if vix > 35:
        score += 2
        signals.append(f"VIX {vix:.1f} — Extreme Fear → contrarian BUY signal")
    elif vix > 25:
        score += 1
        signals.append(f"VIX {vix:.1f} — Elevated Fear → cautious opportunity")
    elif vix < 15:
        score -= 1
        signals.append(f"VIX {vix:.1f} — Complacency → αγορά πιθανώς overextended")
    else:
        signals.append(f"VIX {vix:.1f} — Normal range")

    # HY Spread level
    hy = inputs["hy_spread"]
    if hy < 350:
        score += 1
        signals.append(f"HY Spread {hy:.0f}bps — Tight → risk-on environment")
    elif hy > 600:
        score -= 2
        signals.append(f"HY Spread {hy:.0f}bps — Wide → systemic stress ⚠️")
    else:
        signals.append(f"HY Spread {hy:.0f}bps — Moderate")

    # HY Spread change
    hy_chg = inputs["hy_spread_change"]
    if hy_chg > 100:
        score -= 1
        signals.append(f"HY Spread widened +{hy_chg:.0f}bps (3m) — deteriorating credit")
    elif hy_chg < -50:
        score += 1
        signals.append(f"HY Spread tightened {hy_chg:.0f}bps (3m) — improving credit")

    # Fed Direction
    fed_dir  = inputs["fed_direction"]
    fed_rate = inputs["fed_rate"]
    if fed_dir == "cutting":
        score += 2
        signals.append(f"Fed ΚΟΒΕΙ επιτόκια ({fed_rate:.2f}%) — tailwind για equities")
    elif fed_dir == "hiking":
        score -= 1
        signals.append(f"Fed ΑΥΞΑΝΕΙ επιτόκια ({fed_rate:.2f}%) — headwind")
    else:
        signals.append(f"Fed ON HOLD ({fed_rate:.2f}%) — neutral")

    if score >= 3:
        verdict = {"label": "🟢 BUY ZONE",            "action": "Ευνοϊκές συνθήκες για τοποθέτηση"}
    elif score >= 1:
        verdict = {"label": "🟡 NEUTRAL / SELECTIVE", "action": "Επιλεκτική τοποθέτηση σε quality names"}
    elif score >= -1:
        verdict = {"label": "🟠 CAUTION",             "action": "Αναμονή ή μικρές θέσεις μόνο"}
    else:
        verdict = {"label": "🔴 AVOID / DEFENSIVE",   "action": "Defensive positioning — cash ή bonds"}

    return {"score": score, "signals": signals, "verdict": verdict}


def calculate_sector_pe(stocks_df):
    import pandas as pd
    sector_pe = {}
    if "pe" not in stocks_df.columns:
        return sector_pe
    for sector in stocks_df["sector"].unique():
        sub      = stocks_df[stocks_df["sector"] == sector]
        valid_pe = sub["pe"].replace([float("inf"), -float("inf")], None).dropna()
        valid_pe = valid_pe[valid_pe > 0]
        if len(valid_pe) > 0:
            sector_pe[sector] = round(valid_pe.median(), 1)
    return sector_pe


def evaluate_sector_valuation(sector_pe_dict):
    results = []
    for sector, current_pe in sector_pe_dict.items():
        if sector not in SECTOR_HISTORICAL_PE:
            continue
        hist = SECTOR_HISTORICAL_PE[sector]
        if current_pe <= hist["cheap_threshold"]:
            label = "🟢 Φθηνός"
            note  = f"P/E {current_pe}x vs ιστορικό avg {hist['avg_pe']}x"
        elif current_pe >= hist["expensive_threshold"]:
            label = "🔴 Ακριβός"
            note  = f"P/E {current_pe}x vs ιστορικό avg {hist['avg_pe']}x — premium"
        else:
            label = "🟡 Fair Value"
            note  = f"P/E {current_pe}x vs ιστορικό avg {hist['avg_pe']}x"
        results.append({
            "sector":     sector,
            "current_pe": current_pe,
            "label":      label,
            "note":       note,
        })
    return sorted(results, key=lambda x: x["current_pe"])


def check_stock_macro_alignment(stock_sector, regime_data):
    if stock_sector in regime_data["favored_sectors"]:
        return {
            "aligned": True,
            "label":   "✅ Macro Tailwind",
            "detail":  f"Ευνοείται στο {regime_data['regime_gr']} regime",
            "bg":      "#e6f9ef",
            "color":   "#1a7a4a",
        }
    elif stock_sector in regime_data["avoid_sectors"]:
        return {
            "aligned": False,
            "label":   "⚠️ Macro Headwind",
            "detail":  "Δεν ευνοείται — extra caution",
            "bg":      "#fdecea",
            "color":   "#c0392b",
        }
    else:
        return {
            "aligned": None,
            "label":   "➡️ Neutral",
            "detail":  "Ουδέτερος κλάδος",
            "bg":      "#f5f5f5",
            "color":   "#888",
        }


def render_macro_html(macro_inputs, regime, yield_signal, fear_score, sector_valuations):
    favored_html = ", ".join(regime["favored_sectors"])
    avoid_html   = ", ".join(regime["avoid_sectors"])
    signals_html = "".join([f"<li style='margin-bottom:4px'>{s}</li>" for s in fear_score["signals"]])

    # Sector valuation rows
    sector_rows = ""
    for sv in sector_valuations:
        sector_rows += f"""
        <tr>
          <td style="padding:5px 8px;font-size:11px;color:#ccc;border-bottom:1px solid #2a2a3e">{sv['sector']}</td>
          <td style="padding:5px 8px;font-size:11px;color:#fff;border-bottom:1px solid #2a2a3e">{sv['current_pe']}x</td>
          <td style="padding:5px 8px;font-size:11px;border-bottom:1px solid #2a2a3e">{sv['label']}</td>
          <td style="padding:5px 8px;font-size:10px;color:#888;border-bottom:1px solid #2a2a3e">{sv['note']}</td>
        </tr>"""

    gdp_date_note = f"(data: {macro_inputs.get('gdp_date','N/A')} — quarterly lag φυσιολογικό)"

    html = f"""
    <div style="background:#1a1a2e;border-radius:10px;padding:20px;margin-bottom:14px;font-family:Arial,sans-serif">
      <div style="color:#00d4aa;font-size:15px;font-weight:700;margin-bottom:14px;border-bottom:1px solid #2a2a3e;padding-bottom:8px">
        🌍 MACRO DASHBOARD — {macro_inputs.get('date','')}
      </div>

      <!-- 3 panels -->
      <table style="width:100%;border-collapse:collapse;margin-bottom:12px">
        <tr>
          <td style="width:33%;vertical-align:top;padding-right:8px">
            <div style="background:{regime['color']}22;border:1px solid {regime['color']}55;border-radius:6px;padding:12px">
              <div style="color:#aaa;font-size:10px;text-transform:uppercase;letter-spacing:.5px">Macro Regime</div>
              <div style="color:{regime['color']};font-size:17px;font-weight:700;margin:4px 0">{regime['regime']}</div>
              <div style="color:#ccc;font-size:12px">{regime['regime_gr']}</div>
              <div style="color:#888;font-size:10px;margin-top:6px">{regime['description']}</div>
              <div style="color:#888;font-size:10px;margin-top:4px">
                GDP: {macro_inputs['gdp_yoy']:.1f}% &nbsp;·&nbsp; Core PCE: {macro_inputs['pce_yoy']:.1f}%
              </div>
              <div style="color:#666;font-size:9px;margin-top:2px">{gdp_date_note}</div>
            </div>
          </td>
          <td style="width:33%;vertical-align:top;padding-right:8px">
            <div style="background:#111;border:1px solid #333;border-radius:6px;padding:12px">
              <div style="color:#aaa;font-size:10px;text-transform:uppercase;letter-spacing:.5px">Yield Curve (10Y-2Y)</div>
              <div style="color:#fff;font-size:15px;font-weight:700;margin:4px 0">{yield_signal['label']}</div>
              <div style="color:#888;font-size:12px">{macro_inputs['yield_spread']:+.3f}%</div>
              <div style="color:#888;font-size:10px;margin-top:6px">{yield_signal['detail']}</div>
            </div>
          </td>
          <td style="width:33%;vertical-align:top">
            <div style="background:#111;border:1px solid #333;border-radius:6px;padding:12px">
              <div style="color:#aaa;font-size:10px;text-transform:uppercase;letter-spacing:.5px">Fear & Liquidity</div>
              <div style="color:#fff;font-size:15px;font-weight:700;margin:4px 0">{fear_score['verdict']['label']}</div>
              <div style="color:#888;font-size:12px">{fear_score['verdict']['action']}</div>
              <div style="color:#888;font-size:10px;margin-top:6px">
                VIX: {macro_inputs['vix']:.1f} &nbsp;·&nbsp; HY: {macro_inputs['hy_spread']:.0f}bps &nbsp;·&nbsp; Fed: {macro_inputs['fed_rate']:.2f}%
              </div>
            </div>
          </td>
        </tr>
      </table>

      <!-- Favored / Avoid -->
      <div style="background:#111;border-radius:6px;padding:10px 14px;margin-bottom:10px;font-size:12px">
        <span style="color:#2ECC71;font-weight:700">✅ Ευνοούμενοι κλάδοι:</span>
        <span style="color:#ccc;margin-left:6px">{favored_html}</span>
        &nbsp;&nbsp;|&nbsp;&nbsp;
        <span style="color:#E74C3C;font-weight:700">⚠️ Αποφυγή:</span>
        <span style="color:#ccc;margin-left:6px">{avoid_html}</span>
      </div>

      <!-- Key Signals -->
      <div style="background:#0d0d1a;border-radius:6px;padding:10px 14px;margin-bottom:10px">
        <div style="color:#aaa;font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px">Key Signals</div>
        <ul style="margin:0;padding-left:16px;color:#ccc;font-size:12px;line-height:1.8">
          {signals_html}
        </ul>
      </div>

      <!-- Sector Valuation -->
      {f'''
      <div style="background:#0d0d1a;border-radius:6px;padding:10px 14px">
        <div style="color:#aaa;font-size:10px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Sector Valuation (batch)</div>
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <th style="text-align:left;color:#666;font-size:10px;padding:4px 8px">Κλάδος</th>
            <th style="text-align:left;color:#666;font-size:10px;padding:4px 8px">P/E</th>
            <th style="text-align:left;color:#666;font-size:10px;padding:4px 8px">Αποτίμηση</th>
            <th style="text-align:left;color:#666;font-size:10px;padding:4px 8px">vs Ιστορικό</th>
          </tr>
          {sector_rows}
        </table>
      </div>''' if sector_rows else ''}
    </div>
    """
    return html
