"""Liest die tatsächlich verwendeten Marken-Farben und Schriften einer Website aus.

Einmalig genutzt, um die Oberfläche an ein Corporate Design anzupassen,
statt Farbwerte zu raten. Rendert die Seite und wertet die berechneten
Stile aus — CSS-Variablen, Flächen, Schrift, Buttons.

    python scripts/extract_brand.py https://www.unzer.com/de/
"""

from __future__ import annotations

import asyncio
import json
import sys

from playwright.async_api import async_playwright

SCRIPT = """
() => {
  const out = {vars: {}, bg: {}, color: {}, fonts: {}, buttons: [], borderRadius: {}};

  // 1. CSS-Custom-Properties aus :root — dort stehen Markenfarben meist explizit
  for (const sheet of Array.from(document.styleSheets)) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    for (const rule of Array.from(rules || [])) {
      if (!rule.style || !rule.selectorText) continue;
      if (!/:root|^html$|^body$/.test(rule.selectorText)) continue;
      for (const prop of Array.from(rule.style)) {
        if (prop.startsWith('--')) out.vars[prop] = rule.style.getPropertyValue(prop).trim();
      }
    }
  }

  // 2. Tatsächlich gerenderte Farben zählen
  const count = (obj, key) => { if (key) obj[key] = (obj[key] || 0) + 1; };
  const skip = /rgba\\(0, 0, 0, 0\\)|transparent/;

  for (const el of Array.from(document.querySelectorAll('*')).slice(0, 4000)) {
    const cs = getComputedStyle(el);
    if (!skip.test(cs.backgroundColor)) count(out.bg, cs.backgroundColor);
    count(out.color, cs.color);
    count(out.fonts, cs.fontFamily);
    if (parseFloat(cs.borderRadius) > 0) count(out.borderRadius, cs.borderRadius);
  }

  // 3. Buttons und Call-to-Action-Links separat — dort sitzt die Primärfarbe
  const cta = document.querySelectorAll('button, a[class*="button" i], a[class*="btn" i], [class*="cta" i]');
  for (const el of Array.from(cta).slice(0, 40)) {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 20) continue;
    out.buttons.push({
      text: (el.textContent || '').trim().slice(0, 40),
      bg: cs.backgroundColor,
      color: cs.color,
      border: cs.borderColor,
      radius: cs.borderRadius,
      font: cs.fontFamily.split(',')[0].replace(/["']/g, ''),
      weight: cs.fontWeight,
    });
  }

  // 4. Überschriften
  out.headings = Array.from(document.querySelectorAll('h1, h2')).slice(0, 6).map(h => {
    const cs = getComputedStyle(h);
    return {
      text: (h.textContent || '').trim().slice(0, 45),
      color: cs.color,
      font: cs.fontFamily.split(',')[0].replace(/["']/g, ''),
      weight: cs.fontWeight,
      size: cs.fontSize,
      spacing: cs.letterSpacing,
    };
  });

  return out;
}
"""


def top(mapping: dict[str, int], n: int = 12) -> list[tuple[str, int]]:
    return sorted(mapping.items(), key=lambda kv: -kv[1])[:n]


def to_hex(css: str) -> str:
    """rgb(a)-Notation in Hex umwandeln, damit sich Werte vergleichen lassen."""
    nums = [int(float(x)) for x in css.replace("rgba(", "").replace("rgb(", "").rstrip(")").split(",")[:3]]
    return "#" + "".join(f"{v:02x}" for v in nums) if len(nums) == 3 else css


async def main(url: str) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        data = await page.evaluate(SCRIPT)
        await browser.close()

    print("=== CSS-VARIABLEN MIT FARBWERT ===")
    for name, value in data["vars"].items():
        if any(k in value.lower() for k in ("#", "rgb", "hsl")):
            print(f"  {name}: {value}")

    print("\n=== HÄUFIGSTE FLÄCHENFARBEN ===")
    for value, n in top(data["bg"]):
        print(f"  {to_hex(value):>10}  {value:<28} {n}x")

    print("\n=== HÄUFIGSTE TEXTFARBEN ===")
    for value, n in top(data["color"], 8):
        print(f"  {to_hex(value):>10}  {value:<28} {n}x")

    print("\n=== SCHRIFTEN ===")
    for value, n in top(data["fonts"], 6):
        print(f"  {n:>5}x  {value}")

    print("\n=== ECKENRADIEN ===")
    for value, n in top(data["borderRadius"], 6):
        print(f"  {n:>5}x  {value}")

    print("\n=== BUTTONS ===")
    seen: set[str] = set()
    for b in data["buttons"]:
        key = f"{b['bg']}|{b['color']}"
        if key in seen:
            continue
        seen.add(key)
        print(f"  {to_hex(b['bg']):>10} auf Text {to_hex(b['color']):>10}  r={b['radius']:<12} "
              f"{b['font']} {b['weight']}  \"{b['text']}\"")

    print("\n=== ÜBERSCHRIFTEN ===")
    for h in data["headings"]:
        print(f"  {to_hex(h['color']):>10}  {h['font']:<22} {h['weight']:<5} {h['size']:<8} "
              f"ls={h['spacing']:<8} \"{h['text']}\"")

    with open("/tmp/brand.json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "https://www.unzer.com/de/"))
