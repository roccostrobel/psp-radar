"""HTML-Vorlage der Oberfläche im Unzer-Corporate-Design.

Bewusst als eigene Datei: In app.py gehört die Anwendungslogik, nicht 500
Zeilen Markup. Die Farbwerte stammen aus theme.py und damit aus einer
Messung, nicht aus einer Schätzung.
"""

from __future__ import annotations

from . import theme

_CSS = f"""
:root {{
  --raspberry: {theme.RASPBERRY};
  --raspberry-dark: {theme.RASPBERRY_DARK};
  --navy: {theme.NAVY};
  --navy-70: rgba(12, 19, 50, .70);
  --navy-45: rgba(12, 19, 50, .45);
  --navy-25: rgba(12, 19, 50, .25);
  --navy-12: rgba(12, 19, 50, .12);
  --navy-06: rgba(12, 19, 50, .06);
  --mist: {theme.MIST};
  --grey: {theme.GREY};
  --blue: {theme.LINK_BLUE};
  --surface: #ffffff;
  --canvas: #f4f6f8;
  --pill: {theme.RADIUS_PILL};
  --card: {theme.RADIUS_CARD};
  --font: {theme.FONT_STACK};
  --tracking: {theme.HEADING_TRACKING};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--canvas);
  color: var(--navy);
  font-family: var(--font);
  font-size: 16px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
}}

/* ---------- Kopfleiste ---------- */

.topbar {{
  background: var(--navy);
  color: #fff;
  padding: 18px 24px;
}}
.topbar-inner {{
  max-width: 880px; margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
}}
.wordmark {{
  font-weight: 700; font-size: 19px; letter-spacing: var(--tracking);
}}
.wordmark span {{ color: var(--raspberry); }}
.topbar-meta {{ font-size: 13px; color: rgba(255,255,255,.6); }}

/* ---------- Layout ---------- */

.wrap {{ max-width: 880px; margin: 0 auto; padding: 48px 24px 96px; }}

h1 {{
  font-size: 42px; line-height: 1.1; font-weight: 700;
  letter-spacing: var(--tracking); margin: 0 0 14px;
}}
.lede {{ font-size: 17px; color: var(--navy-70); margin: 0 0 34px; max-width: 62ch; }}

.card {{
  background: var(--surface); border-radius: var(--card);
  padding: 26px; margin-bottom: 20px;
  box-shadow: 0 1px 2px rgba(12,19,50,.05), 0 8px 28px rgba(12,19,50,.06);
}}

/* ---------- Formular ---------- */

form {{ display: flex; gap: 12px; flex-wrap: wrap; }}

input[type=url] {{
  flex: 1 1 340px; min-width: 0;
  padding: 15px 22px; font-size: 16px; font-family: inherit;
  color: var(--navy); background: var(--canvas);
  border: 1.5px solid transparent; border-radius: var(--pill);
  transition: border-color .15s, background .15s;
}}
input[type=url]::placeholder {{ color: var(--navy-45); }}
input[type=url]:focus {{
  outline: none; background: #fff; border-color: var(--raspberry);
}}

button.primary {{
  padding: 15px 34px; font-size: 16px; font-weight: 700; font-family: inherit;
  letter-spacing: -.01em;
  background: var(--raspberry); color: #fff;
  border: 0; border-radius: var(--pill); cursor: pointer;
  transition: background .15s, transform .06s;
}}
button.primary:hover:not(:disabled) {{ background: var(--raspberry-dark); }}
button.primary:active:not(:disabled) {{ transform: translateY(1px); }}
button.primary:disabled {{ background: var(--navy-25); cursor: not-allowed; }}

/* Segmentierte Umschaltung, Pill-Form wie die Buttons auf unzer.com */
.modes {{
  display: inline-flex; margin-top: 18px; padding: 4px;
  background: var(--canvas); border-radius: var(--pill);
}}
.modes label {{
  padding: 8px 18px; border-radius: var(--pill); cursor: pointer;
  font-size: 14px; font-weight: 600; color: var(--navy-70);
  transition: background .15s, color .15s; white-space: nowrap;
}}
.modes label:has(input:checked) {{ background: var(--navy); color: #fff; }}
.modes input {{ position: absolute; opacity: 0; pointer-events: none; }}
.modes .dur {{ font-weight: 400; opacity: .6; }}

.hint {{
  font-size: 14px; color: var(--navy-70); margin-top: 18px;
  padding-left: 15px; border-left: 3px solid var(--mist);
}}

/* ---------- Fortschritt ---------- */

.bar {{
  height: 6px; background: var(--navy-06);
  border-radius: var(--pill); overflow: hidden; margin: 4px 0 14px;
}}
.bar > div {{
  height: 100%; width: 0; background: var(--raspberry);
  border-radius: var(--pill); transition: width .6s ease;
}}
.stage {{
  display: flex; justify-content: space-between; gap: 14px;
  font-size: 14.5px; color: var(--navy-70);
}}
.clock {{ font-variant-numeric: tabular-nums; color: var(--navy-45); }}

/* ---------- Ergebnis ---------- */

.headline-row {{
  display: flex; align-items: baseline; gap: 14px;
  flex-wrap: wrap; margin-bottom: 4px;
}}
.result-domain {{
  font-size: 14px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; color: var(--navy-45); margin-bottom: 18px;
}}
.answer {{
  font-size: 34px; font-weight: 700; letter-spacing: var(--tracking);
  line-height: 1.15;
}}
.answer.none {{ color: var(--raspberry); }}
.under {{ font-size: 14.5px; color: var(--navy-70); margin-top: 6px; }}

.row {{
  display: flex; gap: 18px; padding: 15px 0;
  border-top: 1px solid var(--navy-12); align-items: baseline;
}}
.k {{
  flex: 0 0 132px; font-size: 13px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; color: var(--navy-45);
}}
.v {{ flex: 1; min-width: 0; font-size: 16px; }}

.pill {{
  display: inline-block; padding: 3px 12px; border-radius: var(--pill);
  font-size: 12.5px; font-weight: 700; letter-spacing: .01em;
  vertical-align: 3px; white-space: nowrap;
}}
.p-sicher {{ background: var(--navy); color: #fff; }}
.p-wahrscheinlich {{ background: rgba(27,106,215,.12); color: var(--blue); }}
.p-moeglich {{ background: rgba(134,137,154,.18); color: #5d6072; }}
.p-schwach {{ background: var(--navy-06); color: var(--navy-45); }}

.tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.tag {{
  padding: 5px 14px; border-radius: var(--pill);
  background: var(--canvas); font-size: 14px; font-weight: 500;
}}

details {{ margin-top: 12px; }}
summary {{
  cursor: pointer; font-size: 14px; font-weight: 600; color: var(--raspberry);
  list-style: none;
}}
summary::-webkit-details-marker {{ display: none; }}
summary::before {{ content: "▸ "; display: inline-block; transition: transform .15s; }}
details[open] summary::before {{ content: "▾ "; }}

table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 13px; }}
th {{
  text-align: left; padding: 8px 10px; color: var(--navy-45);
  font-size: 11.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  border-bottom: 1px solid var(--navy-12);
}}
td {{ padding: 9px 10px; border-bottom: 1px solid var(--navy-06); vertical-align: top; }}
td.mono {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px; word-break: break-all; color: var(--navy-70);
}}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}

.ok {{ color: var(--navy); font-weight: 600; }}
.attention {{ color: var(--raspberry); font-weight: 600; }}

.notice {{
  display: flex; gap: 12px; padding: 14px 0; font-size: 14.5px;
  color: var(--navy-70); border-top: 1px solid var(--navy-12);
}}
.notice:first-child {{ border-top: 0; padding-top: 0; }}
.notice .mark {{
  flex: 0 0 auto; width: 20px; height: 20px; border-radius: 50%;
  background: var(--raspberry); color: #fff; font-size: 13px; font-weight: 700;
  display: grid; place-items: center; margin-top: 1px;
}}
.notice code {{
  font-family: ui-monospace, Menlo, monospace; font-size: 12.5px;
  color: var(--navy-45);
}}

.foot {{
  margin-top: 40px; text-align: center;
  font-size: 13px; color: var(--navy-45);
}}
.hidden {{ display: none; }}

@media (max-width: 620px) {{
  h1 {{ font-size: 32px; }}
  .answer {{ font-size: 26px; }}
  .row {{ flex-direction: column; gap: 4px; }}
  .k {{ flex-basis: auto; }}
}}
"""


_JS = """
const $ = (id) => document.getElementById(id);
let timer = null;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const LABEL = {sicher:"sicher", wahrscheinlich:"wahrscheinlich",
               moeglich:"möglich", schwach:"schwach"};

const pill = (d) =>
  `<span class="pill p-${esc(d.confidence_label)}">${d.confidence}% ${LABEL[d.confidence_label] || ""}</span>`;

function evidenceTable(items) {
  if (!items || !items.length) return "";
  const rows = items.map(e => `<tr>
    <td>${esc(e.signal_type)}</td>
    <td class="mono">${esc(e.matched_value)}</td>
    <td>${esc(e.stage)}</td>
    <td class="num">${e.weight}</td></tr>`).join("");
  return `<details><summary>${items.length} Belege</summary>
    <table><thead><tr><th>Signal</th><th>Gefunden</th><th>Stufe</th><th>Gewicht</th></tr></thead>
    <tbody>${rows}</tbody></table></details>`;
}

function render(r) {
  const gateways = (r.psps || []).filter(d => d.role === "gateway" || d.role === "orchestrator");
  const main = gateways.length ? gateways.reduce((a, b) => b.confidence > a.confidence ? b : a) : null;
  const methods = [...(r.wallets || []), ...(r.payment_methods || [])];

  let h = `<div class="card">`;
  h += `<div class="result-domain">${esc(r.final_domain || r.url)}</div>`;

  if (main) {
    h += `<div class="headline-row"><div class="answer">${esc(main.name)}</div>${pill(main)}</div>`;
    if (main.underlying) {
      h += `<div class="under">Technischer Unterbau: ${esc(main.underlying_name || main.underlying)} —
            abgerechnet wird aber über ${esc(main.name)}.</div>`;
    }
    h += evidenceTable(main.evidence);
    const others = gateways.filter(d => d.id !== main.id);
    if (others.length) {
      h += `<div class="under">Ebenfalls erkannt: ${others.map(d => esc(d.name) + " (" + d.confidence + "%)").join(", ")}</div>`;
    }
  } else {
    h += `<div class="answer none">Kein Zahlungsdienstleister ermittelt</div>`;
    h += `<div class="under">${r.checkout_reached
      ? "Der Checkout wurde erreicht, aber kein bekannter Anbieter erkannt — vermutlich fehlt eine Signatur."
      : "Der Checkout wurde nicht erreicht. Ohne ihn bleibt der Zahlungsdienstleister in der Regel unsichtbar."}</div>`;
  }

  h += `<div class="row"><div class="k">Shop-System</div><div class="v">`;
  h += r.platform
    ? `${esc(r.platform.name)} ${pill(r.platform)}` + evidenceTable(r.platform.evidence)
    : `<span style="color:var(--navy-45)">unbekannt</span>`;
  h += `</div></div>`;

  if (methods.length) {
    h += `<div class="row"><div class="k">Zahlungsarten</div><div class="v"><div class="tags">`;
    h += methods.map(d => `<span class="tag">${esc(d.name)}</span>`).join("");
    h += `</div></div></div>`;
  }

  if ((r.fraud_tools || []).length) {
    h += `<div class="row"><div class="k">Fraud / Risk</div><div class="v"><div class="tags">`;
    h += r.fraud_tools.map(d => `<span class="tag">${esc(d.name)}</span>`).join("");
    h += `</div></div></div>`;
  }

  h += `<div class="row"><div class="k">Checkout</div><div class="v">`;
  h += r.checkout_reached
    ? `<span class="ok">erreicht</span>`
    : `<span class="attention">nicht erreicht</span>`;
  h += ` <span style="color:var(--navy-45)">· ${r.duration_s} s · Signaturstand ${esc(r.signature_version || "")}</span>`;
  h += `</div></div></div>`;

  if ((r.warnings || []).length) {
    h += `<div class="card">`;
    h += r.warnings.map(w =>
      `<div class="notice"><span class="mark">!</span><span>${esc(w.message)}
       <code>${esc(w.code)}</code></span></div>`).join("");
    h += `</div>`;
  }

  $("out").innerHTML = h;
}

async function poll(id) {
  const j = await (await fetch(`/api/scan/${id}`)).json();

  $("fill").style.width = (j.progress * 100).toFixed(1) + "%";
  $("stage").textContent = j.stage;
  const m = Math.floor(j.elapsed / 60), s = Math.floor(j.elapsed % 60);
  $("clock").textContent = m ? `${m}:${String(s).padStart(2, "0")} min` : `${s} s`;

  if (j.status === "laeuft") return;

  clearInterval(timer);
  $("progress").classList.add("hidden");
  $("go").disabled = false;
  $("go").textContent = "Analysieren";

  if (j.status === "fehler") {
    $("out").innerHTML = `<div class="card"><div class="notice"><span class="mark">!</span>
      <span>Der Scan ist fehlgeschlagen: ${esc(j.error)}</span></div></div>`;
  } else {
    render(j.result);
  }
}

$("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("url").value.trim();
  const mode = document.querySelector('input[name=mode]:checked').value;

  $("out").innerHTML = "";
  $("go").disabled = true;
  $("go").textContent = "läuft …";
  $("fill").style.width = "0%";
  $("stage").textContent = "wird gestartet";
  $("clock").textContent = "0 s";
  $("progress").classList.remove("hidden");

  const {id} = await (await fetch("/api/scan", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({url, mode})
  })).json();

  clearInterval(timer);
  timer = setInterval(() => poll(id), 1200);
  poll(id);
});
"""


INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>psp-detector</title>
<style>__CSS__</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="wordmark">psp<span>-</span>detector</div>
    <div class="topbar-meta">{{SIGNATUREN}} Signaturen · {{GATEWAYS}} Zahlungsdienstleister</div>
  </div>
</header>

<div class="wrap">
  <h1>Wer wickelt die Zahlung ab?</h1>
  <p class="lede">
    Shop-URL eingeben und erfahren, welcher Zahlungsdienstleister dahintersteht —
    dazu die angebotenen Zahlungsarten, das Shop-System und zu jedem Fund ein Beleg.
  </p>

  <div class="card">
    <form id="f">
      <input id="url" type="url" placeholder="https://beispielshop.de" required autofocus>
      <button id="go" class="primary" type="submit">Analysieren</button>
    </form>

    <div class="modes">
      <label><input type="radio" name="mode" value="voll" checked>
        Volle Tiefe <span class="dur">2–4 min</span></label>
      <label><input type="radio" name="mode" value="schnell">
        Ohne Checkout <span class="dur">40 s</span></label>
    </div>

    <p class="hint">
      Der Zahlungsdienstleister lädt erst im Checkout. Ohne Checkout-Simulation
      bleibt er meist unerkannt — das ist keine Fehlfunktion, sondern der Grund,
      warum die volle Tiefe so lange dauert.
    </p>
  </div>

  <div id="progress" class="card hidden">
    <div class="bar"><div id="fill"></div></div>
    <div class="stage"><span id="stage">…</span><span id="clock" class="clock"></span></div>
  </div>

  <div id="out"></div>

  <div class="foot">Läuft lokal auf diesem Rechner · keine Bestellung, keine Zahlungsdaten</div>
</div>

<script>__JS__</script>
</body>
</html>
"""


def render_index(signature_count: int, gateway_count: int) -> str:
    """Baut die fertige Seite. CSS und JS werden erst hier eingesetzt,
    damit die geschweiften Klammern im JavaScript keine f-String-Fallen sind."""
    return (
        INDEX_HTML.replace("__CSS__", _CSS)
        .replace("__JS__", _JS)
        .replace("{{SIGNATUREN}}", str(signature_count))
        .replace("{{GATEWAYS}}", str(gateway_count))
    )
