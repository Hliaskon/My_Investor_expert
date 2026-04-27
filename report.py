from jinja2 import Environment
import datetime

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
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <span class="ticker-big">{{ r.ticker }}</span>
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
  <div class="sec">Πλήρης Λίστα Batch</div>
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
</div>

<!-- Οδηγός Δεικτών -->
<div class="card" style="background:#f9f9f9">
  <div class="sec">Οδηγός Δεικτών</div>
  <table>
    <tr>
      <th style="width:130px">Δείκτης</th>
      <th style="width:90px">Πηγή</th>
      <th>Τι μετράει & γιατί χρησιμοποιείται</th>
      <th style="width:200px">Threshold</th>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">P/E Ratio</td>
      <td><span class="guide-source">Benjamin Graham</span></td>
      <td>Τιμή μετοχής διαιρεμένη με κέρδη ανά μετοχή (EPS). Δείχνει πόσα € πληρώνεις για κάθε € κέρδους. Χαμηλό P/E = η αγορά δεν περιμένει μεγάλη ανάπτυξη — ευκαιρία για value investor. Αδυναμία: αγνοεί χρέος και ποιότητα κερδών.</td>
      <td style="color:#1a7a4a">&lt; 15 ιδανικό<br>&lt; 20 αποδεκτό</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">P/B Ratio</td>
      <td><span class="guide-source">Benjamin Graham</span></td>
      <td>Τιμή προς Λογιστική Αξία (Book Value = assets minus liabilities). Αν P/B &lt; 1 η μετοχή κοστίζει λιγότερο από τα καθαρά assets της εταιρείας — σπάνια αλλά ισχυρό signal. Χρήσιμο για banks και industrials, λιγότερο για tech όπου τα assets είναι άυλα.</td>
      <td style="color:#1a7a4a">&lt; 1.5 ιδανικό<br>&lt; 2.5 αποδεκτό</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">DCF MoS<br><small>(Base / Bear / Bull)</small></td>
      <td><span class="guide-source">Graham + Buffett</span></td>
      <td>Discounted Cash Flow — υπολογίζει εσωτερική αξία βάσει μελλοντικών ταμειακών ροών (5ετής ορίζοντας + terminal value). Margin of Safety = πόσο % κάτω από αυτή την αξία είναι η τρέχουσα τιμή. Bear case χρησιμοποιεί fat tail assumptions (Taleb): growth -3%, WACC +2%. Το πιο ολοκληρωμένο valuation tool.</td>
      <td style="color:#1a7a4a">MoS &gt; 20% = buying zone<br>MoS &gt; 30% = ισχυρό</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Graham Formula</td>
      <td><span class="guide-source">Benjamin Graham</span></td>
      <td>Απλοποιημένη αποτίμηση: EPS × (8.5 + 2×growth%) × (4.4 / bond yield). Γρήγορη, διαχρονική, χρήσιμη ως δεύτερη γνώμη δίπλα στο DCF. Προσοχή: τείνει να υπερτιμά growth stocks και δεν λαμβάνει υπόψη χρέος.</td>
      <td style="color:#1a7a4a">MoS &gt; 30% ισχυρό<br>Χρήση ως confirmation</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">EV/EBITDA</td>
      <td><span class="guide-source">Hedge Funds<br>Citadel / D.E. Shaw</span></td>
      <td>Enterprise Value (market cap + χρέος - cash) διαιρεμένο με EBITDA. Καλύτερο από P/E για εταιρείες με υψηλό χρέος ή διαφορετικές κεφαλαιακές δομές. Χρησιμοποιείται για cross-sector σύγκριση. Ο πιο δημοφιλής δείκτης σε M&A αποτιμήσεις.</td>
      <td style="color:#1a7a4a">&lt; 8x φθηνό<br>8-12x μέτριο<br>&gt; 12x ακριβό</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">ROE Quality<br><small>(Buffett)</small></td>
      <td><span class="guide-source">Warren Buffett</span></td>
      <td>Return on Equity — πόσο αποδοτικά χρησιμοποιεί η εταιρεία τα κεφάλαια των μετόχων. Ο Buffett απαιτεί ROE &gt; 15% για να θεωρήσει μια εταιρεία ποιοτική. Αξιόπιστο metric — λαμβάνεται απευθείας από Alpha Vantage. Αδυναμία: εταιρείες με υψηλό leverage εμφανίζουν τεχνητά υψηλό ROE.</td>
      <td style="color:#1a7a4a">≥ 15% ισχυρό ✓<br>10-15% αποδεκτό<br>&lt; 10% ανησυχητικό</td>
    </tr>
    <tr class="guide-row">
      <td class="guide-name">ROIC est.<br><small>(proxy)</small></td>
      <td><span class="guide-source">Graham +<br>Buffett</span></td>
      <td>Εκτιμώμενο Return on Invested Capital = ROE × (1 / (1 + D/E)). Αφαιρεί το leverage effect από το ROE για πιο ρεαλιστική εικόνα. <strong>Σημαντικό:</strong> αυτό είναι proxy, όχι ακριβής υπολογισμός NOPAT/InvestedCapital. Χρήσιμο για σύγκριση vs WACC αλλά με επιφύλαξη. Εταιρείες με υγιές υψηλό χρέος (consumer staples) υποεκτιμώνται.</td>
      <td>Proxy &gt; WACC = πιθανή αξία<br><span style="color:#888;font-size:10px">Χρήση ως ένδειξη μόνο</span></td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">52-Week Low<br>Proximity</td>
      <td><span class="guide-source">Behavioral Finance<br>Kahneman / Thaler</span></td>
      <td>Πόσο % πάνω από το 52-εβδομαδιαίο χαμηλό βρίσκεται η τιμή. Βασίζεται στο behavioral finance: οι επενδυτές υπεραντιδρούν σε bad news και πουλάνε πανικόβλητα, δημιουργώντας ευκαιρίες. Αν μια μετοχή είναι κοντά στο low αλλά τα fundamentals είναι υγιή, είναι ισχυρό contrarian signal.</td>
      <td style="color:#1a7a4a">&lt; 15% από low = strong signal<br>15-30% = neutral<br>&gt; 30% = απομακρύνθηκε</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Fragility Score</td>
      <td><span class="guide-source">Nassim Taleb<br>Antifragility</span></td>
      <td>Μέτρο ευαισθησίας σε απρόβλεπτα events (Black Swans). Βάσει D/E και Beta. Antifragile = χαμηλό χρέος, χαμηλή μεταβλητότητα — η εταιρεία επιβιώνει ή ενισχύεται σε κρίσεις. Fragile = υψηλό leverage + υψηλή volatility — επικίνδυνο σε market crashes. Informational flag, όχι filter.</td>
      <td style="color:#1a7a4a">Antifragile = D/E&lt;1 + Beta&lt;1<br>Fragile = D/E&gt;2 + Beta&gt;1.3</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Risk Overall<br><small>(4 διαστάσεις)</small></td>
      <td><span class="guide-source">Multi-framework</span></td>
      <td>Σύνθετος δείκτης από: (1) Επιχειρηματικός — D/E και Beta, (2) Αποτίμησης — P/E και P/B, (3) Μακροοικονομικός — ευαισθησία κλάδου στον οικονομικό κύκλο, (4) Sector risk — ιστορική μεταβλητότητα κλάδου. Ο συνδυασμός Χαμηλού Risk + DCF MoS &gt; 20% είναι το ιδανικό setup.</td>
      <td style="color:#1a7a4a">Χαμηλός + MoS &gt; 20%<br>= ideal combo</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Beta</td>
      <td><span class="guide-source">CAPM / Graham</span></td>
      <td>Μέτρο μεταβλητότητας σχετικά με την αγορά. Beta = 1.0: κινείται ακριβώς με τον S&P 500. Beta &lt; 1: πιο σταθερή (defensive stocks). Beta &gt; 1: πιο ευμετάβλητη (amplifies market moves). Χρησιμοποιείται στον υπολογισμό WACC — υψηλότερο Beta = υψηλότερο discount rate = χαμηλότερη DCF αξία.</td>
      <td style="color:#1a7a4a">&lt; 1.0 Graham-friendly<br>χρησιμοποιείται στο WACC</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">WACC</td>
      <td><span class="guide-source">Corporate Finance</span></td>
      <td>Weighted Average Cost of Capital = Risk-Free Rate (4.2%) + Beta × Equity Risk Premium (5.5%). Είναι το "discount rate" του DCF — ο ελάχιστος ρυθμός απόδοσης που πρέπει να παράγει η εταιρεία για να δικαιολογεί την τιμή της. Υψηλό WACC = χαμηλότερη DCF αξία.</td>
      <td>Τυπικά 7-12%<br>Χαμηλό Beta = χαμηλό WACC<br>= υψηλότερη αξία</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Analyst Target<br>& Upside</td>
      <td><span class="guide-source">Consensus</span></td>
      <td>Μέσος στόχος τιμής από sell-side analysts. Χρήσιμο ως third opinion μετά από DCF και Graham. Προσοχή: οι analysts έχουν συστηματική ανοδική προκατάληψη (bias). Χρήσιμο όταν συγκλίνει με το DCF base case — αν και οι δύο δείχνουν upside &gt; 20%, ισχυρότερο signal.</td>
      <td style="color:#1a7a4a">&gt; 15% upside = ενισχύει thesis<br>Χρήση ως confirmation μόνο</td>
    </tr>

    <tr class="guide-row">
      <td class="guide-name">Dividend Yield</td>
      <td><span class="guide-source">Graham / Income</span></td>
      <td>Ετήσιο μέρισμα διαιρεμένο με τρέχουσα τιμή. Παρέχει "floor" στην αξία μιας μετοχής — ακόμα κι αν δεν υπάρχει capital gain, λαμβάνεις εισόδημα. Ο Graham απαιτούσε ιστορικό σταθερών μερισμάτων. Προσοχή: πολύ υψηλό yield (&gt; 8%) μπορεί να σημαίνει ότι η αγορά περιμένει μείωσή του.</td>
      <td style="color:#1a7a4a">2-4% υγιές<br>&gt; 4% υψηλό<br>&gt; 8% suspicious</td>
    </tr>

  </table>
</div>

<div class="footer">
  Παράγεται αυτόματα κάθε Κυριακή μέσω GitHub Actions &nbsp;·&nbsp;
  Φίλτρα: P/E &lt; 20 · P/B &lt; 2.5 · DCF Base MoS &gt; 15% &nbsp;·&nbsp;
  Bear case: fat tail assumptions (Taleb) &nbsp;·&nbsp;
  Δεν αποτελεί επενδυτική συμβουλή
</div>

</body>
</html>
"""

def build_html(df_all, df_short, summary="", macro_html="", alignment_map=None, batch_idx=1, n_batches=5):
    if alignment_map is None:
        alignment_map = {}
    env = Environment()
    env.globals["risk_badge"]      = risk_badge
    env.globals["mos_badge"]       = mos_badge
    env.globals["w52_badge"]       = w52_badge
    env.globals["fragility_badge"] = fragility_badge
    env.globals["roic_badge"]      = roic_badge
    env.globals["roe_quality_badge"] = roe_quality_badge
    t = env.from_string(TEMPLATE)
    return t.render(
        date          = datetime.date.today().isoformat(),
        total         = len(df_all),
        batch_idx     = batch_idx,
        n_batches     = n_batches,
        shortlist     = df_short.to_dict("records") if not df_short.empty else [],
        all_stocks    = df_all.to_dict("records"),
        summary       = summary,
        macro_html    = macro_html,
        alignment_map = alignment_map,
    )
