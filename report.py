from jinja2 import Environment
import datetime
import pandas as pd

def tier_badge(tier, reason=None):
    """FIX R: STRONG BUY/BUY/HOLD/AVOID badge — το πιο ορατό στοιχείο σε
    κάθε γραμμή, με hover-style tooltip (title attr) που εξηγεί το γιατί."""
    styles = {
        "STRONG BUY": ("background:#1a7a4a;color:#fff", "🟢🟢 STRONG BUY"),
        "BUY":        ("background:#e6f9ef;color:#1a7a4a", "🟢 BUY"),
        "HOLD":       ("background:#fff8e1;color:#8a6000", "🟡 HOLD"),
        "AVOID":      ("background:#fdecea;color:#c0392b", "🔴 AVOID"),
    }
    style, label = styles.get(tier, styles["HOLD"])
    title = f' title="{reason}"' if reason else ""
    return (f'<span{title} style="font-size:12px;font-weight:800;padding:4px 12px;'
            f'border-radius:14px;{style}">{label}</span>')

def risk_badge(level):
    colors = {
        "low":    ("background:#e6f9ef;color:#1a7a4a", "Χαμηλός"),
        "medium": ("background:#fff8e1;color:#8a6000",  "Μέτριος"),
        "high":   ("background:#fdecea;color:#c0392b",  "Υψηλός"),
    }
    style, label = colors.get(level, colors["medium"])
    return f'<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;{style}">{label}</span>'

def mos_badge(val):
    if val is None:
        return "<span style='color:#aaa'>—</span>"
    if val > 20:
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'
    elif val > 0:
        return f'<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'
    else:
        return f'<span style="background:#fdecea;color:#c0392b;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'

def w52_badge(pct_from_low, flag):
    if pct_from_low is None:
        return "<span style='color:#aaa;font-size:10px'>N/A</span>"
    if flag == "near_low":
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">📉 +{pct_from_low}% από low ✓</span>'
    elif flag == "neutral":
        return f'<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">↔ +{pct_from_low}% από low</span>'
    else:
        return f'<span style="background:#f5f5f5;color:#888;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">+{pct_from_low}% από low</span>'

def fragility_badge(level):
    if level == "antifragile":
        return '<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">🛡 Antifragile</span>'
    elif level == "neutral":
        return '<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">⚖ Neutral</span>'
    else:
        return '<span style="background:#fdecea;color:#c0392b;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">⚠ Fragile</span>'

def roe_quality_badge(roe_val, roe_quality):
    """Επιλογή Α: ROE vs Buffett 15% threshold — 100% αξιόπιστο"""
    if roe_val is None or roe_quality is None:
        return "<span style=\'color:#aaa;font-size:10px\'>N/A</span>"
    if roe_quality == "strong":
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">✓ ROE {roe_val}% ≥ 15%</span>'
    elif roe_quality == "moderate":
        return f'<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">~ ROE {roe_val}% (10-15%)</span>'
    else:
        return f'<span style="background:#fdecea;color:#c0392b;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">✗ ROE {roe_val}% &lt; 10%</span>'

def roic_badge(roic, roic_vs_wacc, wacc_val):
    """Επιλογή Γ: ROIC proxy (D/E adjusted ROE) — informational, not exact"""
    if roic is None:
        return "<span style=\'color:#aaa;font-size:10px\'>N/A</span>"
    disclaimer = " (proxy)"
    if roic_vs_wacc == "positive":
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">~ {roic}%{disclaimer} &gt; WACC {wacc_val}%</span>'
    else:
        return f'<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">~ {roic}%{disclaimer} &lt; WACC {wacc_val}%</span>'

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family:Arial,sans-serif; max-width:980px; margin:0 auto; padding:20px; color:#222; background:#f9f9f9; }
  .card { background:#fff; border-radius:10px; border:1px solid #eee; padding:22px 26px; margin-bottom:14px; }
  .header { background:#1a1a2e; color:#fff; padding:20px 26px; border-radius:10px; display:flex; align-items:center; gap:14px; }
  .header h1 { margin:0; font-size:17px; font-weight:700; }
  .header p  { margin:3px 0 0; font-size:11px; color:#aaa; }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
  .stat { background:#f5f5f5; border-radius:8px; padding:12px 14px; }
  .stat-label { font-size:10px; color:#888; text-transform:uppercase; letter-spacing:.5px; }
  .stat-value { font-size:22px; font-weight:700; color:#1a1a2e; margin:3px 0; }
  .stat-sub   { font-size:10px; color:#1a7a4a; }
  .sec { font-size:12px; font-weight:700; color:#1a1a2e; margin:0 0 14px; padding-bottom:8px; border-bottom:2px solid #f0f0f0; text-transform:uppercase; letter-spacing:.4px; }
  .summary-box { background:#f0f4ff; border-left:4px solid #3a5bd9; padding:14px 18px; border-radius:0 6px 6px 0; }
  .summary-box p { font-size:13px; color:#2d2d4e; margin:5px 0; line-height:1.65; }
  .srow { border:1px solid #eee; border-radius:8px; padding:14px 16px; margin-bottom:12px; }
  .srow-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
  .ticker-big { font-weight:700; color:#1a1a2e; font-size:14px; }
  .sector-tag { font-size:10px; color:#888; margin-left:8px; }
  .two-col   { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .three-col { display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin-top:10px; }
  .four-col  { display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:10px; margin-top:10px; }
  .col-title { font-size:9px; color:#888; font-weight:700; text-transform:uppercase; letter-spacing:.5px; margin-bottom:7px; }
  .mini-card { background:#f8f8f8; border-radius:6px; padding:10px 12px; }
  .mini-label{ font-size:10px; color:#888; margin-bottom:3px; }
  .mini-val  { font-size:15px; font-weight:700; color:#1a1a2e; margin:2px 0; }
  .mini-sub  { font-size:10px; color:#888; margin-top:3px; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { background:#1a1a2e; color:#ccc; font-weight:500; padding:8px 10px; text-align:left; font-size:10px; letter-spacing:.3px; }
  td { padding:8px 10px; border-bottom:1px solid #f5f5f5; vertical-align:middle; }
  tr:nth-child(even) td { background:#fafafa; }
  .green { color:#1a7a4a; font-weight:600; }
  .red   { color:#c0392b; }
  .muted { color:#888; }
  .guide-row td { padding:10px 10px; border-bottom:1px solid #f0f0f0; font-size:12px; }
  .guide-row:nth-child(even) td { background:#fafafa; }
  .guide-name { font-weight:700; color:#1a1a2e; white-space:nowrap; }
  .guide-source { font-size:10px; color:#3a5bd9; font-weight:600; }
  .footer { font-size:10px; color:#aaa; text-align:center; padding-top:14px; border-top:1px solid #eee; margin-top:8px; }
</style>
</head>
<body>

<div class="header">
  <div style="width:40px;height:40px;background:#3a5bd9;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:20px">📊</div>
  <div>
    <h1>Weekly Stock Screener</h1>
    <p>{{ date }} &nbsp;·&nbsp; Batch {{ batch_idx }}/{{ n_batches }} &nbsp;·&nbsp; {{ total }} μετοχές screened</p>
  </div>
</div>

<div class="card" style="margin-top:14px">
  <div class="stats">
    <div class="stat">
      <div class="stat-label">Screened</div>
      <div class="stat-value">{{ total }}</div>
      <div class="stat-sub">αυτή την εβδομάδα</div>
    </div>
    <div class="stat">
      <div class="stat-label">Shortlist</div>
      <div class="stat-value" style="color:#1a7a4a">{{ shortlist|length }}</div>
      <div class="stat-sub">περνάει όλα τα φίλτρα</div>
    </div>
    <div class="stat">
      <div class="stat-label">Best DCF MoS</div>
      <div class="stat-value" style="color:#1a7a4a">
        {% if shortlist %}{{ shortlist[0].dcf_base_mos }}%{% else %}—{% endif %}
      </div>
      <div class="stat-sub">{% if shortlist %}{{ shortlist[0].ticker }}{% endif %}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Near 52w Low</div>
      <div class="stat-value" style="color:#1a7a4a">
        {{ shortlist | selectattr('w52_flag', 'equalto', 'near_low') | list | length }}
      </div>
      <div class="stat-sub">behavioral signal</div>
    </div>
  </div>
</div>

{% if macro_html %}
{{ macro_html }}
{% endif %}

{% if performance %}
<div class="card">
  <div class="sec">📈 Performance Tracker — Παλιότερες Προτάσεις</div>
  <table>
    <tr>
      <th>Ticker</th><th>Ημ/νία Πρότασης</th><th>Τιμή Τότε</th>
      <th>Τιμή Τώρα</th><th>Απόδοση</th><th>Ημέρες</th>
    </tr>
    {% for p in performance %}
    <tr>
      <td class="green" style="font-weight:700">{{ p.ticker }}</td>
      <td class="muted">{{ p.date_flagged }}</td>
      <td>${{ p.price_at_flag }}</td>
      <td>${{ p.price_now }}</td>
      <td class="{{ 'green' if p.return_pct > 0 else 'red' }}" style="font-weight:700">
        {{ '%+.1f'|format(p.return_pct) }}%
      </td>
      <td class="muted">{{ p.days_held }}</td>
    </tr>
    {% endfor %}
  </table>
  <div style="font-size:10px;color:#888;margin-top:10px">
    Μετοχές που φλαγκαρίστηκαν πριν 21+ ημέρες — πραγματική απόδοση από την ημέρα πρότασης έως σήμερα.
  </div>
</div>
{% endif %}

{% if summary %}
<div class="card">
  <div class="sec">Claude Summary</div>
  <div class="summary-box">
    {% for line in summary.split('\n') %}
      {% if line.strip() %}<p>{{ line }}</p>{% endif %}
    {% endfor %}
  </div>
</div>
{% endif %}

{% if shortlist %}
<div class="card">
  <div class="sec">STRONG BUY / BUY — Πλήρης Ανάλυση ({{ shortlist|length }} από {{ shortlist_total }} στο shortlist — HOLD/AVOID στον πίνακα παρακάτω)</div>
  {% for r in shortlist %}
  <div class="srow">

    <div class="srow-top">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="ticker-big">{{ r.ticker }}</span>
        {{ tier_badge(r.tier, r.tier_reason) }}
        <span class="sector-tag">{{ r.sector }}</span>
        {{ risk_badge(r.risk.overall) }}
        {{ fragility_badge(r.fragility) }}
        {{ w52_badge(r.pct_from_low, r.w52_flag) }}
        {% if alignment_map and r.ticker in alignment_map %}
          {% set al = alignment_map[r.ticker] %}
          <span style="background:{{ al.bg }};color:{{ al.color }};font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px" title="{{ al.detail }}">{{ al.label }}</span>
        {% endif %}
      </div>
      <div style="font-size:15px;font-weight:700">${{ r.price }}</div>
    </div>

    <div style="font-size:10px;color:#888;margin:-6px 0 10px 2px">
      Confidence Score: <strong>{{ r.tier_score }}/90</strong> ·
      Data completeness: <strong>{{ r.data_completeness }}%</strong> ·
      {{ r.tier_reason }}
    </div>

    <!-- DCF + Risk -->
    <div class="two-col">
      <div>
        <div class="col-title">DCF Analysis — WACC {{ r.wacc }}% · g {{ r.g_base_pct }}% · Fat Tail Bear</div>
        <table>
          <tr><th>Σενάριο</th><th>Εσωτερική Αξία</th><th>MoS vs τιμή</th></tr>
          <tr><td>🐻 Bear (fat tail)</td><td>${{ r.dcf_bear or '—' }}</td><td>{{ mos_badge(r.dcf_bear_mos) }}</td></tr>
          <tr><td><strong>📊 Base</strong></td><td class="green">${{ r.dcf_base or '—' }}</td><td>{{ mos_badge(r.dcf_base_mos) }}</td></tr>
          <tr><td>🚀 Bull</td><td>${{ r.dcf_bull or '—' }}</td><td>{{ mos_badge(r.dcf_bull_mos) }}</td></tr>
          <tr><td>Graham Formula</td><td>${{ r.graham_value or '—' }}</td><td>{{ mos_badge(r.graham_mos) }}</td></tr>
        </table>
      </div>
      <div>
        <div class="col-title">Risk Analysis — 4 Διαστάσεις</div>
        <table>
          <tr><th>Διάσταση</th><th>Επίπεδο</th></tr>
          <tr><td>Επιχειρηματικός (D/E, Beta)</td><td>{{ risk_badge(r.risk.business) }}</td></tr>
          <tr><td>Αποτίμησης (P/E, P/B)</td><td>{{ risk_badge(r.risk.valuation) }}</td></tr>
          <tr><td>Μακροοικονομικός</td><td>{{ risk_badge(r.risk.macro) }}</td></tr>
          <tr><td>Κλάδου</td><td>{{ risk_badge(r.risk.sector) }}</td></tr>
        </table>
      </div>
    </div>

    <!-- Επιπλέον δείκτες -->
    <div class="four-col">
      <div class="mini-card">
        <div class="mini-label">ROE Quality <span style="font-size:9px;color:#3a5bd9">(Buffett)</span></div>
        <div style="margin-top:4px">{{ roe_quality_badge(r.roe, r.roe_quality) }}</div>
        <div class="mini-sub">Threshold: ≥ 15%</div>
      </div>
      <div class="mini-card" style="border:1px dashed #ddd">
        <div class="mini-label">ROIC est. <span style="font-size:9px;color:#888">(proxy)</span></div>
        <div style="margin-top:4px">{{ roic_badge(r.roic, r.roic_vs_wacc, r.wacc) }}</div>
        <div class="mini-sub" style="color:#aaa;font-size:9px">D/E adjusted ROE — not exact</div>
      </div>
      <div class="mini-card">
        <div class="mini-label">EV/EBITDA</div>
        <div class="mini-val">{% if r.ev_ebitda %}{{ r.ev_ebitda }}x{% else %}N/A{% endif %}</div>
        <div class="mini-sub">
          {% if r.ev_ebitda %}
            {% if r.ev_ebitda < 8 %}<span style="color:#1a7a4a">✓ Φθηνό</span>
            {% elif r.ev_ebitda < 12 %}<span style="color:#8a6000">~ Μέτριο</span>
            {% else %}<span style="color:#c0392b">⚠ Ακριβό</span>{% endif %}
          {% endif %}
        </div>
      </div>
      <div class="mini-card">
        <div class="mini-label">Analyst Target</div>
        <div class="mini-val">{% if r.analyst_target %}${{ r.analyst_target | round(0) | int }}{% else %}N/A{% endif %}</div>
        <div class="mini-sub">
          {% if r.analyst_upside %}
            {% if r.analyst_upside > 15 %}<span style="color:#1a7a4a">+{{ r.analyst_upside }}% upside</span>
            {% elif r.analyst_upside > 0 %}<span style="color:#8a6000">+{{ r.analyst_upside }}%</span>
            {% else %}<span style="color:#c0392b">{{ r.analyst_upside }}%</span>{% endif %}
          {% endif %}
        </div>
      </div>
      <div class="mini-card">
        <div class="mini-label">Dividend Yield</div>
        <div class="mini-val">{{ r.div_yield }}%</div>
        <div class="mini-sub">
          {% if r.div_yield > 4 %}<span style="color:#1a7a4a">✓ Υψηλό</span>
          {% elif r.div_yield > 2 %}<span style="color:#8a6000">~ Μέτριο</span>
          {% elif r.div_yield > 0 %}<span style="color:#888">Χαμηλό</span>
          {% else %}<span style="color:#aaa">Καμία</span>{% endif %}
        </div>
      </div>
    </div>

    <div style="font-size:11px;color:#555;margin-top:10px">
      P/E {{ r.pe or '—' }} &nbsp;·&nbsp;
      P/B {{ r.pb or '—' }} &nbsp;·&nbsp;
      Beta {{ r.beta }} &nbsp;·&nbsp;
      D/E {{ r.de or '—' }} &nbsp;·&nbsp;
      ROE {{ r.roe or '—' }}% &nbsp;·&nbsp;
      52w Low ${{ r.low52 or '—' }} &nbsp;·&nbsp;
      52w High ${{ r.high52 or '—' }}
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

<!-- Πλήρης Λίστα -->
<div class="card">
  <div class="sec">Πλήρης Λίστα — Top {{ all_stocks|length }}{% if total > all_stocks|length %} από {{ total }} screened (ταξινομημένα κατά DCF MoS){% endif %}</div>
  <table>
    <tr>
      <th>Ticker</th><th>Τιμή</th><th>P/E</th><th>P/B</th>
      <th>DCF MoS</th><th>Graham MoS</th><th>EV/EBITDA</th>
      <th>52w Low</th><th>Fragility</th><th>Risk</th>
    </tr>
    {% for r in all_stocks %}
    <tr>
      <td style="font-weight:700">{{ r.ticker }}</td>
      <td>${{ r.price }}</td>
      <td>{{ r.pe or '—' }}</td>
      <td>{{ r.pb or '—' }}</td>
      <td>{{ mos_badge(r.dcf_base_mos) }}</td>
      <td>{{ mos_badge(r.graham_mos) }}</td>
      <td>{% if r.ev_ebitda %}{{ r.ev_ebitda }}x{% else %}—{% endif %}</td>
      <td>{{ w52_badge(r.pct_from_low, r.w52_flag) }}</td>
      <td>{{ fragility_badge(r.fragility) }}</td>
      <td>{{ risk_badge(r.risk.overall) }}</td>
    </tr>
    {% endfor %}
  </table>
  {% if total > all_stocks|length %}
  <div style="font-size:10px;color:#888;margin-top:10px">
    Το email έχει όριο μεγέθους (Gmail κόβει μηνύματα >~100KB) — δείχνει μόνο τις top {{ all_stocks|length }}.
    Το πλήρες σύνολο ({{ total }} μετοχές) είναι στο history.csv του repo.
  </div>
  {% endif %}
</div>

<div class="footer">
  Παράγεται αυτόματα κάθε Κυριακή μέσω GitHub Actions &nbsp;·&nbsp;
  Φίλτρα: P/E &lt; 20 · P/B &lt; 2.5 · DCF Base MoS &gt; 15% &nbsp;·&nbsp;
  Bear case: fat tail assumptions (Taleb) &nbsp;·&nbsp;
  <a href="https://github.com/Hliaskon/My_Investor_expert/blob/main/GUIDE.md" style="color:#3a5bd9">Οδηγός Δεικτών (τι σημαίνει κάθε νούμερο)</a> &nbsp;·&nbsp;
  Δεν αποτελεί επενδυτική συμβουλή
</div>

</body>
</html>
"""

def _records_no_nan(df):
    """
    FIX O: pandas μετατρέπει None → NaN (float) σε numeric στήλες — και
    δεν μπορεί να αποθηκεύσει None ξανά μέσα σε float64 column (γυρνάει
    πάντα σε NaN, ακόμα κι αν κάνεις .where()). Λύση: καθαρισμός ΜΕΤΑ το
    to_dict(), σε επίπεδο dict — εκεί το None επιμένει κανονικά.
    Στο Jinja template, "{{ r.de or '—' }}" δεν πιάνει NaN (είναι truthy
    στην Python!) — γι' αυτό έβγαινε κυριολεκτικά "nan" στο email αντί
    για "—" (DCF για τράπεζες, D/E, EV/EBITDA όπου λείπει δεδομένο).
    """
    if df.empty:
        return []
    records = df.to_dict("records")
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, float) and pd.isna(v):
                rec[k] = None
    return records


def build_html(df_all, df_short, summary="", macro_html="", alignment_map=None,
               batch_idx=1, n_batches=5, performance_df=None):
    if alignment_map is None:
        alignment_map = {}
    env = Environment()
    env.globals["risk_badge"]      = risk_badge
    env.globals["tier_badge"]      = tier_badge
    env.globals["mos_badge"]       = mos_badge
    env.globals["w52_badge"]       = w52_badge
    env.globals["fragility_badge"] = fragility_badge
    env.globals["roic_badge"]      = roic_badge
    env.globals["roe_quality_badge"] = roe_quality_badge
    t = env.from_string(TEMPLATE)
    performance = ([] if performance_df is None or performance_df.empty
                    else performance_df.to_dict("records"))

    # FIX S: το πλήρες σύνολο (π.χ. 217+ μετοχές) κάνει το HTML >380KB —
    # το Gmail κόβει μηνύματα >~100KB ("[Message clipped]"), χάνοντας τον
    # Οδηγό Δεικτών που ήταν στο τέλος (γι' αυτό μετακόμισε στο GUIDE.md).
    # Εδώ περιορίζουμε τον "Πλήρης Λίστα" πίνακα σε top 60 by DCF MoS ώστε
    # να μείνει το email κάτω από το όριο.
    MAX_FULL_LIST_ROWS = 40
    df_all_sorted = df_all.copy()
    if "dcf_base_mos" in df_all_sorted.columns:
        df_all_sorted = df_all_sorted.sort_values("dcf_base_mos", ascending=False, na_position="last")
    all_stocks_trimmed = _records_no_nan(df_all_sorted.head(MAX_FULL_LIST_ROWS))

    # FIX S: πλήρης ανάλυση (DCF/Risk κάρτες) μόνο για STRONG BUY/BUY —
    # αυτά είναι τα actionable. HOLD/AVOID φαίνονται μόνο στον συμπαγή
    # "Πλήρης Λίστα" πίνακα. Λύνει και το μέγεθος email (κάθε κάρτα είναι
    # βαριά σε HTML) ΚΑΙ κάνει το email πιο εστιασμένο σε ό,τι έχει σήμα.
    if "tier" in df_short.columns:
        df_short_detailed = df_short[df_short["tier"].isin(["STRONG BUY", "BUY"])]
    else:
        df_short_detailed = df_short
    # Hard cap ανεξαρτήτως πόσα STRONG BUY/BUY βγουν μια εβδομάδα — κάθε
    # κάρτα είναι βαριά σε HTML, δεν μπορούμε να υποθέσουμε ότι θα είναι
    # πάντα λίγα.
    MAX_DETAILED_CARDS = 10
    if "tier_score" in df_short_detailed.columns:
        df_short_detailed = df_short_detailed.sort_values("tier_score", ascending=False)
    df_short_detailed = df_short_detailed.head(MAX_DETAILED_CARDS)

    return t.render(
        date          = datetime.date.today().isoformat(),
        total         = len(df_all),
        batch_idx     = batch_idx,
        n_batches     = n_batches,
        shortlist     = _records_no_nan(df_short_detailed),
        shortlist_total = len(df_short),
        all_stocks    = all_stocks_trimmed,
        summary       = summary,
        macro_html    = macro_html,
        alignment_map = alignment_map,
        performance   = performance,
    )
