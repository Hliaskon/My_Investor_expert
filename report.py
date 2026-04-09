from jinja2 import Environment
import datetime

def sparkline_svg(prices, width=90, height=28):
    if not prices or len(prices) < 2:
        return "<span style='color:#888;font-size:10px'>n/a</span>"
    mn, mx = min(prices), max(prices)
    rng    = mx - mn or 1
    pts    = []
    for i, p in enumerate(prices):
        x = i / (len(prices) - 1) * width
        y = height - ((p - mn) / rng) * height
        pts.append(f"{x:.1f},{y:.1f}")
    poly  = " ".join(pts)
    color = "#2ecc71" if prices[-1] >= prices[0] else "#e74c3c"
    return (f'<svg width="{width}" height="{height}" style="vertical-align:middle">'
            f'<polyline points="{poly}" fill="none" stroke="{color}" '
            f'stroke-width="1.5" stroke-linejoin="round"/></svg>')

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

def rd_badge(rd_pct, rd_flag):
    if rd_pct is None:
        return "<span style='color:#aaa;font-size:10px'>N/A</span>"
    labels = {"low": ("✓ Χαμηλό", "#e6f9ef", "#1a7a4a"),
              "medium": ("~ Μέτριο", "#fff8e1", "#8a6000"),
              "high": ("⚠ Υψηλό", "#fdecea", "#c0392b")}
    label, bg, fg = labels.get(rd_flag, ("~", "#fff8e1", "#8a6000"))
    return f'<span style="background:{bg};color:{fg};font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">{label} {rd_pct}%</span>'

def roic_badge(roic, roic_vs_wacc, wacc_val):
    if roic is None:
        return "<span style='color:#aaa;font-size:10px'>N/A</span>"
    if roic_vs_wacc == "positive":
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">✓ {roic}% &gt; WACC {wacc_val}%</span>'
    else:
        return f'<span style="background:#fdecea;color:#c0392b;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px">✗ {roic}% &lt; WACC {wacc_val}%</span>'

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; max-width: 980px; margin: 0 auto;
         padding: 20px; color: #222; background: #f9f9f9; }
  .card { background:#fff; border-radius:10px; border:1px solid #eee;
          padding:22px 26px; margin-bottom:14px; }
  .header { background:#1a1a2e; color:#fff; padding:20px 26px;
             border-radius:10px; display:flex; align-items:center; gap:14px; }
  .header h1 { margin:0; font-size:17px; font-weight:700; }
  .header p  { margin:3px 0 0; font-size:11px; color:#aaa; }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
  .stat { background:#f5f5f5; border-radius:8px; padding:12px 14px; }
  .stat-label { font-size:10px; color:#888; text-transform:uppercase; letter-spacing:.5px; }
  .stat-value { font-size:22px; font-weight:700; color:#1a1a2e; margin:3px 0; }
  .stat-sub   { font-size:10px; color:#1a7a4a; }
  .sec { font-size:12px; font-weight:700; color:#1a1a2e; margin:0 0 14px;
         padding-bottom:8px; border-bottom:2px solid #f0f0f0;
         text-transform:uppercase; letter-spacing:.4px; }
  .summary-box { background:#f0f4ff; border-left:4px solid #3a5bd9;
                 padding:14px 18px; border-radius:0 6px 6px 0; }
  .summary-box p { font-size:13px; color:#2d2d4e; margin:5px 0; line-height:1.65; }
  .srow { border:1px solid #eee; border-radius:8px; padding:14px 16px; margin-bottom:12px; }
  .srow-top { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
  .ticker-big { font-weight:700; color:#1a1a2e; font-size:14px; }
  .sector-tag { font-size:10px; color:#888; margin-left:8px; }
  .two-col  { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .three-col{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; margin-top:10px; }
  .col-title{ font-size:9px; color:#888; font-weight:700; text-transform:uppercase;
              letter-spacing:.5px; margin-bottom:7px; }
  .mini-card{ background:#f8f8f8; border-radius:6px; padding:10px 12px; }
  .mini-label{ font-size:10px; color:#888; }
  .mini-val  { font-size:16px; font-weight:700; color:#1a1a2e; margin:2px 0; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { background:#1a1a2e; color:#ccc; font-weight:500; padding:8px 10px;
       text-align:left; font-size:10px; letter-spacing:.3px; }
  td { padding:8px 10px; border-bottom:1px solid #f5f5f5; vertical-align:middle; }
  tr:nth-child(even) td { background:#fafafa; }
  .green  { color:#1a7a4a; font-weight:600; }
  .red    { color:#c0392b; }
  .muted  { color:#888; }
  .guide-table th { background:#1a1a2e; color:#ccc; }
  .guide-table td { font-size:12px; padding:9px 10px; }
  .footer { font-size:10px; color:#aaa; text-align:center;
             padding-top:14px; border-top:1px solid #eee; margin-top:8px; }
</style>
</head>
<body>

<div class="header">
  <div style="width:40px;height:40px;background:#3a5bd9;border-radius:8px;
              display:flex;align-items:center;justify-content:center;font-size:20px">📊</div>
  <div>
    <h1>Weekly Stock Screener — DCF &amp; Risk Report</h1>
    <p>{{ date }} &nbsp;·&nbsp; Graham + DCF + ROIC/WACC + EV/EBITDA + FCF Yield + R&amp;D &nbsp;·&nbsp; {{ total }} μετοχές</p>
  </div>
</div>

<div class="card" style="margin-top:14px">
  <div class="stats">
    <div class="stat">
      <div class="stat-label">Screened</div>
      <div class="stat-value">{{ total }}</div>
      <div class="stat-sub">watchlist</div>
    </div>
    <div class="stat">
      <div class="stat-label">Shortlist</div>
      <div class="stat-value" style="color:#1a7a4a">{{ shortlist|length }}</div>
      <div class="stat-sub">passes filters</div>
    </div>
    <div class="stat">
      <div class="stat-label">Best DCF MoS</div>
      <div class="stat-value" style="color:#1a7a4a">
        {% if shortlist %}{{ shortlist[0].dcf_base_mos }}%{% else %}—{% endif %}
      </div>
      <div class="stat-sub">{% if shortlist %}{{ shortlist[0].ticker }}{% endif %}</div>
    </div>
    <div class="stat">
      <div class="stat-label">ROIC &gt; WACC</div>
      <div class="stat-value">
        {{ shortlist | selectattr('roic_vs_wacc', 'equalto', 'positive') | list | length }}/{{ shortlist|length }}
      </div>
      <div class="stat-sub">value creators</div>
    </div>
  </div>
</div>

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
  <div class="sec">Shortlist — Πλήρης Ανάλυση</div>

  {% for r in shortlist %}
  <div class="srow">
    <div class="srow-top">
      <div style="display:flex;align-items:center;gap:8px">
        <span class="ticker-big">{{ r.ticker }}</span>
        <span class="sector-tag">{{ r.sector }}</span>
        {{ risk_badge(r.risk.overall) }}
        {{ rd_badge(r.rd_pct, r.rd_flag) }}
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:14px;font-weight:700">${{ r.price }}</span>
      </div>
    </div>

    <!-- DCF + Risk -->
    <div class="two-col">
      <div>
        <div class="col-title">DCF Analysis (WACC {{ r.wacc }}%, g {{ r.g_base_pct }}%)</div>
        <table>
          <tr><th>Σενάριο</th><th>DCF Value</th><th>MoS</th></tr>
          <tr><td>🐻 Bear</td><td>${{ r.dcf_bear or '—' }}</td><td>{{ mos_badge(r.dcf_bear_mos) }}</td></tr>
          <tr><td><strong>📊 Base</strong></td><td class="green">${{ r.dcf_base or '—' }}</td><td>{{ mos_badge(r.dcf_base_mos) }}</td></tr>
          <tr><td>🚀 Bull</td><td>${{ r.dcf_bull or '—' }}</td><td>{{ mos_badge(r.dcf_bull_mos) }}</td></tr>
          <tr><td>Graham</td><td>${{ r.graham_value or '—' }}</td><td>{{ mos_badge(r.graham_mos) }}</td></tr>
        </table>
      </div>
      <div>
        <div class="col-title">Risk Analysis</div>
        <table>
          <tr><th>Διάσταση</th><th>Επίπεδο</th></tr>
          <tr><td>Επιχειρηματικός</td><td>{{ risk_badge(r.risk.business) }}</td></tr>
          <tr><td>Αποτίμησης</td><td>{{ risk_badge(r.risk.valuation) }}</td></tr>
          <tr><td>Μακρο</td><td>{{ risk_badge(r.risk.macro) }}</td></tr>
          <tr><td>Κλάδου</td><td>{{ risk_badge(r.risk.sector) }}</td></tr>
        </table>
      </div>
    </div>

    <!-- Νέοι δείκτες -->
    <div class="three-col" style="margin-top:12px">
      <div class="mini-card">
        <div class="mini-label">ROIC vs WACC</div>
        <div style="margin-top:4px">{{ roic_badge(r.roic, r.roic_vs_wacc, r.wacc) }}</div>
        <div style="font-size:10px;color:#888;margin-top:4px">Δημιουργεί αξία αν ROIC &gt; WACC</div>
      </div>
      <div class="mini-card">
        <div class="mini-label">EV/EBITDA</div>
        <div class="mini-val">{% if r.ev_ebitda %}{{ r.ev_ebitda }}x{% else %}N/A{% endif %}</div>
        <div style="font-size:10px;color:#888">
          {% if r.ev_ebitda %}
            {% if r.ev_ebitda < 8 %}<span style="color:#1a7a4a">✓ Φθηνό (&lt;8x){% elif r.ev_ebitda < 12 %}<span style="color:#8a6000">~ Μέτριο (8-12x){% else %}<span style="color:#c0392b">⚠ Ακριβό (&gt;12x){% endif %}</span>
          {% else %}—{% endif %}
        </div>
      </div>
      <div class="mini-card">
        <div class="mini-label">FCF Yield</div>
        <div class="mini-val">{% if r.fcf_yield %}{{ r.fcf_yield }}%{% else %}N/A{% endif %}</div>
        <div style="font-size:10px;color:#888">
          {% if r.fcf_yield %}
            {% if r.fcf_yield > 7 %}<span style="color:#1a7a4a">✓ Ισχυρό (&gt;7%){% elif r.fcf_yield > 4 %}<span style="color:#8a6000">~ Μέτριο (4-7%){% else %}<span style="color:#c0392b">⚠ Χαμηλό (&lt;4%){% endif %}</span>
          {% else %}—{% endif %}
        </div>
      </div>
    </div>

    <div style="font-size:11px;color:#555;margin-top:10px">
      P/E {{ r.pe }} &nbsp;·&nbsp; P/B {{ r.pb }} &nbsp;·&nbsp;
      Beta {{ r.beta }} &nbsp;·&nbsp; D/E {{ r.de or '—' }} &nbsp;·&nbsp;
      ROE {{ r.roe }}% &nbsp;·&nbsp; Div {{ r.div_yield }}%
      {% if r.analyst_target %}&nbsp;·&nbsp; Analyst Target ${{ r.analyst_target | round(0) | int }}{% endif %}
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

<div class="card">
  <div class="sec">Πλήρης Λίστα</div>
  <table>
    <tr>
      <th>Ticker</th><th>Τιμή</th><th>P/E</th><th>P/B</th>
      <th>DCF MoS</th><th>Graham MoS</th><th>EV/EBITDA</th>
      <th>FCF Yield</th><th>ROIC</th><th>R&amp;D</th><th>Risk</th>
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
      <td>{% if r.fcf_yield %}{{ r.fcf_yield }}%{% else %}—{% endif %}</td>
      <td>{% if r.roic %}{{ r.roic }}%{% else %}—{% endif %}</td>
      <td>{{ rd_badge(r.rd_pct, r.rd_flag) }}</td>
      <td>{{ risk_badge(r.risk.overall) }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<!-- Οδηγός Δεικτών -->
<div class="card" style="background:#f9f9f9">
  <div class="sec">Οδηγός Δεικτών</div>
  <table class="guide-table">
    <tr><th style="width:140px">Δείκτης</th><th>Τι μετράει</th><th style="width:220px">Threshold / Ερμηνεία</th></tr>
    <tr>
      <td style="font-weight:700">P/E</td>
      <td>Πόσα € πληρώνεις για κάθε € κέρδους. Χαμηλό = φθηνή μετοχή σχετικά με τα κέρδη της. Προσοχή: αγνοεί χρέος και cash flows.</td>
      <td class="green">&lt; 15 ιδανικό &nbsp;·&nbsp; &lt; 20 αποδεκτό</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="font-weight:700">P/B</td>
      <td>Τιμή προς Λογιστική Αξία. Αν P/B &lt; 1 η μετοχή κοστίζει λιγότερο από τα assets της. Χρήσιμο για banks &amp; industrials, λιγότερο για tech.</td>
      <td class="green">&lt; 1.5 ιδανικό &nbsp;·&nbsp; &lt; 2.5 αποδεκτό</td>
    </tr>
    <tr>
      <td style="font-weight:700">DCF Base MoS</td>
      <td>Margin of Safety βάσει Discounted Cash Flow (5ετής ορίζοντας, 3 σενάρια). Δείχνει πόσο % κάτω από την εκτιμώμενη εσωτερική αξία είναι η τρέχουσα τιμή. Το πιο αξιόπιστο valuation tool.</td>
      <td class="green">&gt; 20% = buying zone &nbsp;·&nbsp; &gt; 30% = ισχυρό</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="font-weight:700">Graham MoS</td>
      <td>Margin of Safety βάσει Graham Formula: EPS × (8.5 + 2g) × (4.4 / bond yield). Απλή, γρήγορη, χρήσιμη ως δεύτερη γνώμη. Τείνει να υπερτιμά growth stocks.</td>
      <td class="green">&gt; 30% ισχυρό signal</td>
    </tr>
    <tr>
      <td style="font-weight:700">EV/EBITDA</td>
      <td>Enterprise Value (market cap + χρέος - cash) διαιρεμένο με EBITDA. Καλύτερο από P/E γιατί λαμβάνει υπόψη το χρέος. Χρησιμοποιείται από hedge funds για cross-sector σύγκριση.</td>
      <td class="green">&lt; 8x φθηνό &nbsp;·&nbsp; 8-12x μέτριο &nbsp;·&nbsp; &gt;12x ακριβό</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="font-weight:700">ROIC vs WACC</td>
      <td>Return on Invested Capital vs Weighted Average Cost of Capital. Αν ROIC &gt; WACC η εταιρεία δημιουργεί αξία για τους μετόχους. Αν ROIC &lt; WACC καταστρέφει αξία ακόμα κι αν κερδίζει.</td>
      <td class="green">ROIC &gt; WACC = value creation ✓</td>
    </tr>
    <tr>
      <td style="font-weight:700">FCF Yield</td>
      <td>Free Cash Flow / Market Cap. Δείχνει πόσο % της αγοραίας αξίας επιστρέφεται ως ελεύθερες ταμειακές ροές. Πιο αξιόπιστο από EPS γιατί δεν χειραγωγείται από accounting.</td>
      <td class="green">&gt; 7% ισχυρό &nbsp;·&nbsp; 4-7% μέτριο &nbsp;·&nbsp; &lt; 4% χαμηλό</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="font-weight:700">Beta</td>
      <td>Μέτρο μεταβλητότητας vs αγορά. Beta = 1: κινείται με την αγορά. Beta &lt; 1: πιο σταθερή (defensive). Beta &gt; 1: πιο ευμετάβλητη. Χρησιμοποιείται στον υπολογισμό WACC.</td>
      <td class="green">&lt; 1.0 προτιμητέο για Graham</td>
    </tr>
    <tr>
      <td style="font-weight:700">R&amp;D %</td>
      <td>R&amp;D / Revenue. Informational flag — δεν είναι filter. Υψηλό R&amp;D σημαίνει growth bet (pharma, tech, semiconductors). Χαμηλό σημαίνει mature/stable business (Graham-friendly). N/A για banks &amp; energy.</td>
      <td>&lt; 3% χαμηλό ✓ Graham &nbsp;·&nbsp; 3-12% μέτριο &nbsp;·&nbsp; &gt;12% υψηλό ⚠</td>
    </tr>
    <tr style="background:#fafafa">
      <td style="font-weight:700">Risk (Overall)</td>
      <td>Σύνθετος δείκτης από 4 διαστάσεις: Επιχειρηματικός (D/E + Beta) + Αποτίμησης (P/E + P/B) + Μακρο (ευαισθησία σε οικονομικό κύκλο) + Sector (κλαδικός κίνδυνος).</td>
      <td class="green">Χαμηλός + MoS &gt; 20% = ideal combo</td>
    </tr>
  </table>
</div>

<div class="footer">
  Παράγεται αυτόματα κάθε 2η Κυριακή μέσω GitHub Actions &nbsp;·&nbsp;
  Φίλτρα: P/E &lt;20 · P/B &lt;2.5 · DCF Base MoS &gt;15% &nbsp;·&nbsp;
  Δεν αποτελεί επενδυτική συμβουλή
</div>

</body>
</html>
"""

def build_html(df_all, df_short, summary=""):
    env = Environment()
    env.globals["sparkline"]   = sparkline_svg
    env.globals["risk_badge"]  = risk_badge
    env.globals["mos_badge"]   = mos_badge
    env.globals["rd_badge"]    = rd_badge
    env.globals["roic_badge"]  = roic_badge
    t = env.from_string(TEMPLATE)
    return t.render(
        date       = datetime.date.today().isoformat(),
        total      = len(df_all),
        shortlist  = df_short.to_dict("records") if not df_short.empty else [],
        all_stocks = df_all.to_dict("records"),
        summary    = summary,
    )
