"""HTML-Vorlage der Oberfläche im Unzer-Corporate-Design.

Zwei Betriebsarten: ein Shop oder eine Liste. Letzteres ist der eigentliche
Zweck dieses Projekts.

**Lehre aus einem Fehler:** Die erste Fassung fragte `/api/scan/{id}` ab,
während die API `/api/job/{id}` anbietet. Der Klick auf "Analysieren" tat
daraufhin scheinbar nichts — der Scan lief im Hintergrund korrekt, aber die
404-Antwort landete stillschweigend im Nichts. Deshalb gilt hier jetzt:

1. Jeder Fehler wird **sichtbar** angezeigt, mit Statuscode und Meldung.
2. `tests/test_web_api_vertrag.py` prüft, dass jeder `fetch()`-Aufruf in
   dieser Datei einer real registrierten Route entspricht.

Ein stiller Fehler ist schlimmer als ein laute Fehlermeldung — er kostet
Vertrauen in alles andere.
"""

from __future__ import annotations

from . import theme

_CSS = f"""
:root {{
  --raspberry: {theme.RASPBERRY};
  --raspberry-dark: {theme.RASPBERRY_DARK};
  --navy: {theme.NAVY};
  --navy-70: rgba(12,19,50,.70);
  --navy-45: rgba(12,19,50,.45);
  --navy-12: rgba(12,19,50,.12);
  --navy-06: rgba(12,19,50,.06);
  --mist: {theme.MIST};
  --blue: {theme.LINK_BLUE};
  --surface:#fff; --canvas:#f4f6f8;
  --pill:{theme.RADIUS_PILL}; --card:{theme.RADIUS_CARD};
  --font:{theme.FONT_STACK}; --tracking:{theme.HEADING_TRACKING};
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--canvas);color:var(--navy);font-family:var(--font);
font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}}

.topbar{{background:var(--navy);color:#fff;padding:18px 24px}}
.topbar-inner{{max-width:960px;margin:0 auto;display:flex;align-items:center;
justify-content:space-between;gap:16px}}
.wordmark{{font-weight:700;font-size:19px;letter-spacing:var(--tracking)}}
.wordmark span{{color:var(--raspberry)}}
.topbar-meta{{font-size:13px;color:rgba(255,255,255,.6)}}

.wrap{{max-width:960px;margin:0 auto;padding:44px 24px 96px}}
h1{{font-size:40px;line-height:1.1;font-weight:700;letter-spacing:var(--tracking);margin:0 0 14px}}
.lede{{font-size:17px;color:var(--navy-70);margin:0 0 30px;max-width:64ch}}
.card{{background:var(--surface);border-radius:var(--card);padding:26px;margin-bottom:18px;
box-shadow:0 1px 2px rgba(12,19,50,.05),0 8px 28px rgba(12,19,50,.06)}}

.tabs{{display:inline-flex;padding:4px;background:var(--canvas);border-radius:var(--pill);
margin-bottom:22px}}
.tabs button{{padding:9px 22px;border:0;background:transparent;border-radius:var(--pill);
font:inherit;font-weight:600;font-size:14.5px;color:var(--navy-70);cursor:pointer}}
.tabs button.on{{background:var(--navy);color:#fff}}

form{{display:flex;gap:12px;flex-wrap:wrap}}
input[type=url]{{flex:1 1 340px;min-width:0;padding:15px 22px;font-size:16px;
font-family:inherit;color:var(--navy);background:var(--canvas);
border:1.5px solid transparent;border-radius:var(--pill)}}
textarea{{width:100%;min-height:140px;padding:16px 20px;font-size:14.5px;
font-family:ui-monospace,Menlo,monospace;color:var(--navy);background:var(--canvas);
border:1.5px solid transparent;border-radius:16px;resize:vertical}}
input:focus,textarea:focus{{outline:none;background:#fff;border-color:var(--raspberry)}}
input::placeholder,textarea::placeholder{{color:var(--navy-45)}}

button.primary{{padding:15px 34px;font-size:16px;font-weight:700;font-family:inherit;
background:var(--raspberry);color:#fff;border:0;border-radius:var(--pill);cursor:pointer}}
button.primary:hover:not(:disabled){{background:var(--raspberry-dark)}}
button.primary:disabled{{background:rgba(12,19,50,.25);cursor:not-allowed}}
button.ghost{{padding:11px 22px;font-size:14.5px;font-weight:600;font-family:inherit;
background:transparent;color:var(--raspberry);border:1.5px solid var(--raspberry);
border-radius:var(--pill);cursor:pointer}}

.modes{{display:inline-flex;margin-top:18px;padding:4px;background:var(--canvas);
border-radius:var(--pill);flex-wrap:wrap}}
.modes label{{padding:8px 18px;border-radius:var(--pill);cursor:pointer;font-size:14px;
font-weight:600;color:var(--navy-70);white-space:nowrap}}
.modes label:has(input:checked){{background:var(--navy);color:#fff}}
.modes input{{position:absolute;opacity:0;pointer-events:none}}
.modes .dur{{font-weight:400;opacity:.6}}
.hint{{font-size:14px;color:var(--navy-70);margin-top:18px;padding-left:15px;
border-left:3px solid var(--mist)}}
.rowline{{display:flex;gap:16px;align-items:center;margin-top:16px;flex-wrap:wrap;
font-size:14.5px;color:var(--navy-70)}}
.rowline input[type=number]{{width:76px;padding:9px 14px;border-radius:var(--pill);
border:1.5px solid var(--navy-12);font:inherit;text-align:center}}

.bar{{height:6px;background:var(--navy-06);border-radius:var(--pill);overflow:hidden;margin:4px 0 14px}}
.bar>div{{height:100%;width:0;background:var(--raspberry);border-radius:var(--pill);
transition:width .5s ease}}
.stage{{display:flex;justify-content:space-between;gap:14px;font-size:14.5px;color:var(--navy-70)}}
.clock{{font-variant-numeric:tabular-nums;color:var(--navy-45)}}

.result-domain{{font-size:13px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;
color:var(--navy-45);margin-bottom:16px}}
.headline-row{{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}}
.answer{{font-size:33px;font-weight:700;letter-spacing:var(--tracking);line-height:1.15}}
.answer.none{{color:var(--raspberry)}}
.under{{font-size:14.5px;color:var(--navy-70);margin-top:6px}}
.row{{display:flex;gap:18px;padding:15px 0;border-top:1px solid var(--navy-12);align-items:baseline}}
.k{{flex:0 0 132px;font-size:13px;font-weight:600;letter-spacing:.04em;
text-transform:uppercase;color:var(--navy-45)}}
.v{{flex:1;min-width:0}}

.pill{{display:inline-block;padding:3px 12px;border-radius:var(--pill);font-size:12.5px;
font-weight:700;vertical-align:3px;white-space:nowrap}}
.p-sicher{{background:var(--navy);color:#fff}}
.p-wahrscheinlich{{background:rgba(27,106,215,.12);color:var(--blue)}}
.p-moeglich{{background:rgba(134,137,154,.18);color:#5d6072}}
.p-schwach{{background:var(--navy-06);color:var(--navy-45)}}
.tier{{display:inline-block;padding:2px 10px;border-radius:var(--pill);font-size:11.5px;
font-weight:700;letter-spacing:.04em;text-transform:uppercase;
background:var(--navy-06);color:var(--navy-45)}}
.tags{{display:flex;flex-wrap:wrap;gap:8px}}
.tag{{padding:5px 14px;border-radius:var(--pill);background:var(--canvas);font-size:14px}}

details{{margin-top:12px}}
summary{{cursor:pointer;font-size:14px;font-weight:600;color:var(--raspberry);list-style:none}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"▸ "}}
details[open] summary::before{{content:"▾ "}}

table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13.5px}}
th{{text-align:left;padding:9px 10px;color:var(--navy-45);font-size:11.5px;font-weight:700;
letter-spacing:.05em;text-transform:uppercase;border-bottom:1px solid var(--navy-12)}}
td{{padding:10px;border-bottom:1px solid var(--navy-06);vertical-align:top}}
td.mono{{font-family:ui-monospace,Menlo,monospace;font-size:12px;word-break:break-all;
color:var(--navy-70)}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}

.ok{{color:var(--navy);font-weight:600}}
.attention{{color:var(--raspberry);font-weight:600}}
.notice{{display:flex;gap:12px;padding:14px 0;font-size:14.5px;color:var(--navy-70);
border-top:1px solid var(--navy-12)}}
.notice:first-child{{border-top:0;padding-top:0}}
.notice .mark{{flex:0 0 auto;width:20px;height:20px;border-radius:50%;
background:var(--raspberry);color:#fff;font-size:13px;font-weight:700;
display:grid;place-items:center;margin-top:1px}}
.notice code{{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:var(--navy-45)}}
.fehler{{background:#fff;border-left:5px solid var(--raspberry)}}
.fehler h3{{margin:0 0 8px;font-size:17px;letter-spacing:-.01em}}
.fehler pre{{margin:10px 0 0;padding:12px 14px;background:var(--canvas);border-radius:12px;
font-size:12.5px;overflow-x:auto;color:var(--navy-70)}}

#feld-liste{{flex:1 1 100%}}
.foot{{margin-top:38px;text-align:center;font-size:13px;color:var(--navy-45)}}
/* !important, weil ein Inline-display die Klasse sonst überstimmt — genau
   dieser Fehler liess im Listen-Modus das Einzelfeld stehen. */
.hidden{{display:none !important}}
@media (max-width:620px){{
  h1{{font-size:30px}} .answer{{font-size:25px}}
  .row{{flex-direction:column;gap:4px}} .k{{flex-basis:auto}}
}}
"""


_JS = r"""
const $ = (id) => document.getElementById(id);
let timer = null, jobId = null;

const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const LABEL = {sicher:"sicher", wahrscheinlich:"wahrscheinlich",
               moeglich:"möglich", schwach:"schwach"};

const pill = (d) => `<span class="pill p-${esc(d.confidence_label)}">${d.confidence}% ${LABEL[d.confidence_label] || ""}</span>`;

/* Jeder Fehler wird sichtbar. Die erste Fassung dieser Datei schluckte eine
   404-Antwort stillschweigend, wodurch der Knopf scheinbar nichts tat. */
function zeigeFehler(titel, details) {
  stopp();
  $("out").innerHTML = `<div class="card fehler">
    <h3>${esc(titel)}</h3>
    <div style="color:var(--navy-70);font-size:14.5px">
      Der Scan wurde nicht abgeschlossen. Details unten helfen bei der Ursache.
    </div>
    <pre>${esc(details)}</pre></div>`;
}

function stopp() {
  clearInterval(timer);
  $("progress").classList.add("hidden");
  $("go").disabled = false;
  $("go").textContent = "Analysieren";
}

async function holen(pfad, optionen) {
  const antwort = await fetch(pfad, optionen);
  if (!antwort.ok) {
    let text = "";
    try { text = JSON.stringify(await antwort.json()); } catch (e) { text = await antwort.text(); }
    throw new Error(`${optionen?.method || "GET"} ${pfad} → HTTP ${antwort.status}\n${text}`);
  }
  return antwort.json();
}

function evidenceTable(items) {
  if (!items || !items.length) return "";
  const rows = items.map(e => `<tr><td>${esc(e.signal_type)}</td>
    <td class="mono">${esc(e.matched_value)}</td><td>${esc(e.stage)}</td>
    <td class="num">${e.weight}</td></tr>`).join("");
  return `<details><summary>${items.length} Belege</summary><table>
    <thead><tr><th>Signal</th><th>Gefunden</th><th>Stufe</th><th>Gewicht</th></tr></thead>
    <tbody>${rows}</tbody></table></details>`;
}

function karteEinzel(r) {
  const gw = (r.psps || []).filter(d => d.role === "gateway" || d.role === "orchestrator");
  const main = gw.length ? gw.reduce((a, b) => b.confidence > a.confidence ? b : a) : null;
  const methoden = [...(r.wallets || []), ...(r.payment_methods || [])];

  let h = `<div class="card"><div class="result-domain">${esc(r.final_domain || r.url)}</div>`;

  if (main) {
    h += `<div class="headline-row"><div class="answer">${esc(main.name)}</div>${pill(main)}
          <span class="tier">${esc(r.tier)}</span></div>`;
    if (main.underlying) {
      h += `<div class="under">Technischer Unterbau: ${esc(main.underlying_name || main.underlying)}
            — abgerechnet wird aber über ${esc(main.name)}.</div>`;
    }
    h += evidenceTable(main.evidence);
    const rest = gw.filter(d => d.id !== main.id);
    if (rest.length) {
      h += `<div class="under">Ebenfalls erkannt: ${rest.map(d => esc(d.name)+" ("+d.confidence+"%)").join(", ")}</div>`;
    }
  } else {
    h += `<div class="answer none">Kein Zahlungsdienstleister ermittelt</div>
          <div class="under">${r.checkout_reached
            ? "Der Checkout wurde erreicht, aber kein bekannter Anbieter erkannt — vermutlich fehlt eine Signatur."
            : "Der Checkout wurde nicht erreicht. Ohne ihn bleibt der Zahlungsdienstleister meist unsichtbar."}</div>`;
  }

  h += `<div class="row"><div class="k">Shop-System</div><div class="v">`;
  h += r.platform ? `${esc(r.platform.name)} ${pill(r.platform)}` + evidenceTable(r.platform.evidence)
                  : `<span style="color:var(--navy-45)">unbekannt</span>`;
  h += `</div></div>`;

  if (methoden.length) {
    h += `<div class="row"><div class="k">Zahlungsarten</div><div class="v"><div class="tags">${
      methoden.map(d => `<span class="tag">${esc(d.name)}</span>`).join("")}</div></div></div>`;
  }
  if ((r.fraud_tools || []).length) {
    h += `<div class="row"><div class="k">Fraud / Risk</div><div class="v"><div class="tags">${
      r.fraud_tools.map(d => `<span class="tag">${esc(d.name)}</span>`).join("")}</div></div></div>`;
  }

  h += `<div class="row"><div class="k">Checkout</div><div class="v">${
    r.checkout_reached ? `<span class="ok">erreicht</span>` : `<span class="attention">nicht erreicht</span>`
  } <span style="color:var(--navy-45)">· ${r.duration_s} s · Stufe ${esc(r.tier)} · Signaturen ${esc(r.signature_version || "")}</span></div></div></div>`;

  if ((r.warnings || []).length) {
    h += `<div class="card">` + r.warnings.map(w =>
      `<div class="notice"><span class="mark">!</span><span>${esc(w.message)}
       <code>${esc(w.code)}</code></span></div>`).join("") + `</div>`;
  }
  return h;
}

function tabelleListe(daten) {
  const rows = (daten.results || []).map(r => {
    const gw = (r.psps || []).filter(d => d.role === "gateway" || d.role === "orchestrator");
    const main = gw.length ? gw.reduce((a, b) => b.confidence > a.confidence ? b : a) : null;
    return `<tr>
      <td class="mono">${esc(r.final_domain || r.url)}</td>
      <td>${main ? esc(main.name) + " " + pill(main) : '<span class="attention">nicht ermittelt</span>'}</td>
      <td>${r.platform ? esc(r.platform.name) : "—"}</td>
      <td><span class="tier">${esc(r.tier)}</span></td>
      <td class="num">${r.duration_s} s</td></tr>`;
  }).join("");

  const stufen = Object.entries(daten.nach_stufe || {})
    .map(([k, v]) => `${esc(k)}: ${v}`).join(" · ");

  return `<div class="card">
    <div class="headline-row"><div class="answer">${daten.done} von ${daten.total} Shops</div></div>
    <div class="under">${stufen || "&nbsp;"}</div>
    <table><thead><tr><th>Shop</th><th>Zahlungsdienstleister</th><th>Shop-System</th>
      <th>Stufe</th><th>Dauer</th></tr></thead><tbody>${rows}</tbody></table>
    <div style="margin-top:18px">
      <button class="ghost" onclick="location.href='/api/job/${esc(daten.id)}/csv'">Als CSV herunterladen</button>
    </div></div>`;
}

async function abfragen() {
  try {
    const j = await holen(`/api/job/${jobId}`);

    $("fill").style.width = (j.progress * 100).toFixed(1) + "%";
    $("stage").textContent = j.stage;
    const m = Math.floor(j.elapsed / 60), s = Math.floor(j.elapsed % 60);
    $("clock").textContent = m ? `${m}:${String(s).padStart(2,"0")} min` : `${s} s`;

    /* Zwischenstand bei Listen: Ergebnisse laufend anzeigen statt am Ende */
    if (j.kind === "batch" && (j.results || []).length) $("out").innerHTML = tabelleListe(j);

    if (j.status === "laeuft") return;
    stopp();

    if (j.status === "fehler") {
      zeigeFehler("Scan fehlgeschlagen", j.error || "Kein Grund übermittelt");
    } else if (j.kind === "batch") {
      $("out").innerHTML = tabelleListe(j);
    } else if (j.result) {
      $("out").innerHTML = karteEinzel(j.result);
    } else {
      zeigeFehler("Kein Ergebnis erhalten", JSON.stringify(j, null, 2));
    }
  } catch (fehler) {
    zeigeFehler("Verbindung zur Auswertung fehlgeschlagen", String(fehler.message || fehler));
  }
}

function starten(id) {
  jobId = id;
  clearInterval(timer);
  timer = setInterval(abfragen, 1200);
  abfragen();
}

function vorbereiten(text) {
  $("out").innerHTML = "";
  $("go").disabled = true;
  $("go").textContent = "läuft …";
  $("fill").style.width = "0%";
  $("stage").textContent = text;
  $("clock").textContent = "0 s";
  $("progress").classList.remove("hidden");
}

$("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const mode = document.querySelector('input[name=mode]:checked').value;
  const liste = $("tab-liste").classList.contains("on");

  try {
    if (liste) {
      const urls = $("urls").value.split(/[\n,;]+/).map(u => u.trim()).filter(Boolean);
      if (!urls.length) { zeigeFehler("Keine URLs eingegeben", "Bitte eine URL pro Zeile."); return; }
      vorbereiten(`${urls.length} Shops werden vorbereitet`);
      const {id} = await holen("/api/batch", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({urls, mode, concurrency: Number($("par").value) || 6})
      });
      starten(id);
    } else {
      const url = $("url").value.trim();
      if (!url) { zeigeFehler("Keine URL eingegeben", "Bitte eine Shop-URL angeben."); return; }
      vorbereiten("Shop wird geprüft");
      const {id} = await holen("/api/scan", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url, mode})
      });
      starten(id);
    }
  } catch (fehler) {
    zeigeFehler("Auftrag konnte nicht gestartet werden", String(fehler.message || fehler));
  }
});

function tab(welcher) {
  const istListe = welcher === "liste";
  $("tab-liste").classList.toggle("on", istListe);
  $("tab-einzel").classList.toggle("on", !istListe);
  $("feld-liste").classList.toggle("hidden", !istListe);
  $("url").classList.toggle("hidden", istListe);
  $("par-zeile").classList.toggle("hidden", !istListe);
  (istListe ? $("urls") : $("url")).focus();
}
$("tab-einzel").addEventListener("click", () => tab("einzel"));
$("tab-liste").addEventListener("click", () => tab("liste"));
"""


INDEX_HTML = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>psp-radar</title>
<style>__CSS__</style>
</head>
<body>

<header class="topbar">
  <div class="topbar-inner">
    <div class="wordmark">psp<span>-</span>radar</div>
    <div class="topbar-meta">{{SIGNATUREN}} Signaturen · {{GATEWAYS}} Zahlungsdienstleister</div>
  </div>
</header>

<div class="wrap">
  <h1>Wer wickelt die Zahlung ab?</h1>
  <p class="lede">
    Shop-URL oder ganze Liste eingeben und erfahren, welcher Zahlungsdienstleister
    dahintersteht — dazu Zahlungsarten, Shop-System und zu jedem Fund ein Beleg.
  </p>

  <div class="card">
    <div class="tabs">
      <button type="button" id="tab-einzel" class="on">Ein Shop</button>
      <button type="button" id="tab-liste">Liste</button>
    </div>

    <form id="f">
      <input id="url" type="url" placeholder="https://beispielshop.de" autofocus>
      <div id="feld-liste" class="hidden">
        <textarea id="urls" placeholder="https://shop-eins.de&#10;https://shop-zwei.de&#10;https://shop-drei.de"></textarea>
      </div>
      <button id="go" class="primary" type="submit">Analysieren</button>
    </form>

    <div class="modes">
      <label><input type="radio" name="mode" value="trichter" checked>
        Trichter <span class="dur">empfohlen</span></label>
      <label><input type="radio" name="mode" value="voll">
        Volle Tiefe <span class="dur">langsam</span></label>
      <label><input type="radio" name="mode" value="schnell">
        Ohne Checkout <span class="dur">schnell</span></label>
      <label><input type="radio" name="mode" value="statisch">
        Nur statisch <span class="dur">Sekunden</span></label>
    </div>

    <div class="rowline hidden" id="par-zeile">
      <span>Shops parallel</span>
      <input id="par" type="number" min="1" max="16" value="6">
      <span style="color:var(--navy-45)">höher ist schneller, belastet aber mehr</span>
    </div>

    <p class="hint">
      <strong>Trichter</strong> prüft erst billig ohne Browser und geht nur dann in den
      Checkout, wenn das Ergebnis sonst unklar bliebe. Für Listen die richtige Wahl.
      <strong>Volle Tiefe</strong> simuliert immer den Checkout — genauer bei Shops mit
      mehreren Anbietern, aber deutlich langsamer.
    </p>
  </div>

  <div id="progress" class="card hidden">
    <div class="bar"><div id="fill"></div></div>
    <div class="stage"><span id="stage">…</span><span id="clock" class="clock"></span></div>
  </div>

  <div id="out"></div>

  <div class="foot">Keine Bestellung, keine Zahlungsdaten · Rate-Limit pro Domain</div>
</div>

<script>__JS__</script>
</body>
</html>
"""


def render_index(signature_count: int, gateway_count: int) -> str:
    """Baut die fertige Seite.

    CSS und JS werden erst hier eingesetzt, damit die geschweiften Klammern
    im JavaScript nicht als f-String-Platzhalter gelesen werden.
    """
    return (
        INDEX_HTML.replace("__CSS__", _CSS)
        .replace("__JS__", _JS)
        .replace("{{SIGNATUREN}}", str(signature_count))
        .replace("{{GATEWAYS}}", str(gateway_count))
    )
