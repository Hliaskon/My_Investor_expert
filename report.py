from jinja2 import Template
import datetime

def sparkline_svg(prices, width=90, height=28):
    """Generates inline SVG sparkline from price list"""
    if not prices or len(prices) < 2:
        return "<span style='color:#888;font-size:10px'>n/a</span>"
    mn, mx = min(prices), max(prices)
    rng    = mx - mn or 1
    pts    = []
    for i, p in enumerate(prices):
        x = i / (len(prices) - 1) * width
        y = height - ((p - mn) / rng) * height
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    color = "#2ecc71" if prices[-1] >= prices[0] else "#e74c3c"
    return (
        f'<svg width="{width}" height="{height}" style="vertical-align:middle">'
        f'<polyline points="{poly}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round"/></svg>'
    )

def risk_badge(level):
    colors = {
        "low":    ("background:#e6f9ef;color:#1a7a4a", "Χαμηλός"),
        "medium": ("background:#fff8e1;color:#8a6000", "Μέτριος"),
        "high":   ("background:#fdecea;color:#c0392b", "Υψηλός"),
    }
    style, label = colors.get(level, colors["medium"])
    return f'<span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;{style}">{label}</span>'

def mos_badge(val):
    if val is None: return "<span style='color:#aaa'>—</span>"
    if val > 20:
        return f'<span style="background:#e6f9ef;color:#1a7a4a;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'
    elif val > 0:
        return f'<span style="background:#fff8e1;color:#8a6000;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'
    else:
        return f'<span style="background:#fdecea;color:#c0392b;font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px">{val:+.0f}%</span>'

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto;
         padding: 20px; color: #222; background: #f9f9f9; }
  .card { background:#fff; border-radius:10px; border:1px solid #eee;
          padding:22px 26px; margin-bottom:20px; }
  .header { background:#1a1a2e; color:#fff; padding:20px 26px;
             border-radius:10px; display:flex; align-items:center; gap:14px; }
  .header h1 { margin:0; font-size:17px; font-weight:700; }
  .header p  { margin:3px 0 0; font-size:11px; color:#aaa; }
  .stats { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
  .stat { background:#f5f5f5; border-radius:8px; padding:12px 14px; }
  .stat-label { font-size:10px; color:#888; text-transform:uppercase; letter-spacing:.5px; }
  .stat-value { font-size:22px; font-weight:700; color:#1a1a2e; margin:3px 0; }
  .stat-sub   { font-size:10px; color:#1a7a4a; }
  .section-title { font-size:13px; font-weight:700; color:#1a1a2e; margin:0 0 14px;
                   padding-bottom:8px; border-bottom:2px solid #f0f0f0; }
  .summary-box { background:#f0f4ff; border-left:4px solid #3a5bd9;
                 padding:14px 18px; border-radius:0 6px 6px 0; }
  .summary-box p { font-size:13px; color:#2d2d4e; margin:5px 0; line-height:1.65; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th { background:#1a1a2e; color:#ccc; font-weight:500; padding:8px 10px;
       text-align:left; font-size:10px; letter-spacing:.3px; }
  td { padding:9px 10px; border-bottom:1px solid #f5f5f5; vertical-align:middle; }
  tr:nth-child(even) td { background:#fafafa; }
  tr:hover td { background:#f0f4ff; }
  .ticker { font-weight:700; color:#1a1a2e; font-size:13px; }
  .muted  { color:#888; }
  .green  { color:#1a7a4a; font-weight:600; }
  .risk-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
  .risk-item { font-size:10px; text-align:center; }
  .risk-item .label { color:#888; margin-bottom:2px; }
  .dcf-trio { display:flex; gap:4px; align-items:center; }
  .footer { font-size:10px; color:#aaa; text-align:center;
             padding-top:14px; border-top:1px solid #eee; margin-top:10px; }
</style>
</head>
<body>

<div class="header">
  <div style="width:40px;height:40px;background:#3a5bd9;border-radius:8px;
              display:flex;align-items:center;justify-content:center;font-size:20px">📊</div>
  <div>
    <h1>Weekly Stock Screener — DCF &amp; Risk Report</h1>
    <p>{{ date }} &nbsp;·&nbsp; Graham + DCF (Bear/Base/Bull) + Risk Analysis &nbsp;·&nbsp; {{ total }} μετοχές</p>
  </div>
</div>

<div class="card" style="margin-top:16px">
  <div class="stats">
    <div class="stat">
      <div class="stat-label">Screened</div>
      <div class="stat-value">{{ total }}</div>
      <div class="stat-sub">watchlist</div>
    </div>
    <div class="stat">
      <div class="stat-label">Shortlist</div>
      <div class="stat-value" style="color:#1a7a4a">{{ shortlist|length }}</div>
      <div class="stat-sub">passes all filters</div>
    </div>
    <div class="stat">
      <div class="stat-label">Best DCF MoS</div>
      <div class="stat-value" style="color:#1a7a4a">
        {% if shortlist %}{{ shortlist[0].dcf_base_mos }}%{% else %}—{% endif %}
      </div>
      <div class="stat-sub">{% if shortlist %}{{ shortlist[0].ticker }}{% endif %}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Avg WACC</div>
      <div class="stat-value">
        {% if shortlist %}{{ (shortlist | map(attribute='wacc') | list | sum / shortlist|length) | round(1) }}%{% else %}—{% endif %}
      </div>
      <div class="stat-sub">shortlist</div>
    </div>
  </div>
</div>

{% if summary %}
<div class="card">
  <div class="section-title">Claude Summary</div>
  <div class="summary-box">
    {% for line in summary.split('\n') %}
      {% if line.strip() %}<p>{{ line }}</p>{% endif %}
    {% endfor %}
  </div>
</div>
{% endif %}

{% if shortlist %}
<div class="card">
  <div class="section-title">Shortlist — DCF &amp; Risk Detail</div>
  {% for r in shortlist %}
  <div style="border:1px solid #eee;border-radius:8px;padding:16px 18px;margin-bottom:14px">

    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
      <div style="display:flex;align-items:center;gap:12px">
        <span class="ticker">{{ r.ticker }}</span>
        <span style="font-size:11px;color:#888">{{ r.sector }}</span>
        {{ risk_badge(r.risk.overall) }}
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        {{ sparkline(r.sparkline) }}
        <span style="font-size:14px;font-weight:700">${{ r.price }}</span>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">

      <!-- DCF scenarios -->
      <div>
        <div style="font-size:10px;color:#888;margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.4px">DCF Analysis (WACC {{ r.wacc }}%, g {{ r.g_base_pct }}%)</div>
        <table>
          <tr>
            <th>Σενάριο</th><th>DCF Value</th><th>MoS vs τιμή</th>
          </tr>
          <tr>
            <td>🐻 Bear</td>
            <td>${{ r.dcf_bear or '—' }}</td>
            <td>{{ mos_badge(r.dcf_bear_mos) }}</td>
          </tr>
          <tr>
            <td><strong>📊 Base</strong></td>
            <td class="green">${{ r.dcf_base or '—' }}</td>
            <td>{{ mos_badge(r.dcf_base_mos) }}</td>
          </tr>
          <tr>
            <td>🚀 Bull</td>
            <td>${{ r.dcf_bull or '—' }}</td>
            <td>{{ mos_badge(r.dcf_bull_mos) }}</td>
          </tr>
          <tr>
            <td>Graham</td>
            <td>${{ r.graham_value or '—' }}</td>
            <td>{{ mos_badge(r.graham_mos) }}</td>
          </tr>
        </table>
      </div>

      <!-- Risk breakdown -->
      <div>
        <div style="font-size:10px;color:#888;margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.4px">Risk Analysis</div>
        <table>
          <tr><th>Διάσταση</th><th>Επίπεδο</th></tr>
          <tr><td>Επιχειρηματικός</td><td>{{ risk_badge(r.risk.business) }}</td></tr>
          <tr><td>Αποτίμησης</td><td>{{ risk_badge(r.risk.valuation) }}</td></tr>
          <tr><td>Μακρο</td><td>{{ risk_badge(r.risk.macro) }}</td></tr>
          <tr><td>Κλάδου</td><td>{{ risk_badge(r.risk.sector) }}</td></tr>
        </table>
        <div style="margin-top:8px;font-size:11px;color:#555">
          P/E {{ r.pe }} &nbsp;·&nbsp; P/B {{ r.pb }} &nbsp;·&nbsp;
          Beta {{ r.beta }} &nbsp;·&nbsp; D/E {{ r.de or '—' }} &nbsp;·&nbsp;
          ROE {{ r.roe }}%
          {% if r.analyst_target %}
          &nbsp;·&nbsp; Analyst Target ${{ r.analyst_target | round(0) | int }}
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endif %}

<div class="card">
  <div class="section-title">Πλήρης Λίστα</div>
  <table>
    <tr>
      <th>Ticker</th><th>1Y Chart</th><th>Τιμή</th><th>P/E</th><th>P/B</th>
      <th>DCF Base MoS</th><th>Graham MoS</th><th>Beta</th><th>Risk</th>
    </tr>
    {% for r in all_stocks %}
    <tr>
      <td class="ticker">{{ r.ticker }}</td>
      <td>{{ sparkline(r.sparkline) }}</td>
      <td>${{ r.price }}</td>
      <td>{{ r.pe or '—' }}</td>
      <td>{{ r.pb or '—' }}</td>
      <td>{{ mos_badge(r.dcf_base_mos) }}</td>
      <td>{{ mos_badge(r.graham_mos) }}</td>
      <td>{{ r.beta }}</td>
      <td>{{ risk_badge(r.risk.overall) }}</td>
    </tr>
    {% endfor %}
  </table>
</div>

<div class="footer">
  Παράγεται αυτόματα κάθε Κυριακή &nbsp;·&nbsp;
  Φίλτρα: P/E &lt;20 · P/B &lt;2.5 · DCF Base MoS &gt;15% &nbsp;·&nbsp;
  Δεν αποτελεί επενδυτική συμβουλή
</div>

</body>
</html>
"""

def build_html(df_all, df_short, summary=""):
    from jinja2 import Environment
    env = Environment()
    env.globals["sparkline"]  = sparkline_svg
    env.globals["risk_badge"] = risk_badge
    env.globals["mos_badge"]  = mos_badge
    t = env.from_string(TEMPLATE)
    return t.render(
        date      = datetime.date.today().isoformat(),
        total     = len(df_all),
        shortlist = df_short.to_dict("records") if not df_short.empty else [],
        all_stocks= df_all.to_dict("records"),
        summary   = summary,
    )
