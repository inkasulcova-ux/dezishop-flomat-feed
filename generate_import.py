#!/usr/bin/env python3
"""
Generator aktualizacniho XML feedu pro Shoptet (dezishop.cz)
=============================================================
Vezme velkoobchodni CSV feed FLOMAT + export produktu ze Shoptetu a vyrobi
XML soubor ve formatu Shoptetu, ktery obsahuje JEN vase produkty a u nich
novou cenu a popis. Ten soubor pak Shoptet stahuje pres
Produkty -> Automaticke importy.

Parovani: partNumber v Shoptetu  ==  ITEM_CODE ve feedu FLOMAT.

Pouziti:
    python generate_import.py                      # vygeneruje XML + report
    python generate_import.py --report-only        # jen ukaze zmeny, nic nezapisuje
    python generate_import.py --out /cesta/feed.xml

Konfigurace: .env (vzor v .env.example)
"""
import argparse
import csv
import datetime
import html
import os
import re
import sys
from xml.sax.saxutils import escape

from dotenv import load_dotenv

load_dotenv()

FEED_URL = os.getenv("FLOMAT_FEED_URL", "")
SHOPTET_EXPORT = os.getenv("SHOPTET_EXPORT_PATH", "shoptet_export.xlsx")
OUT_PATH = os.getenv("OUTPUT_XML_PATH", "shoptet_import.xml")
REPORT_PATH = os.getenv("REPORT_PATH", "report.csv")
FILTERS_PATH = os.getenv("FILTERS_PATH", "popis_filtry.txt")
SYNC_DESCRIPTION = os.getenv("SYNC_DESCRIPTION", "true").lower() == "true"
PRICE_COEFFICIENT = float(os.getenv("PRICE_COEFFICIENT", "1.0"))
MAX_DESCRIPTION_CHARS = 32767  # limit Shoptetu

# Produkty, ktere se NIKDY nemaji aktualizovat (drzite si u nich vlastni cenu).
# Kody oddelte carkou, napr. EXCLUDE_CODES=99005,99008
EXCLUDE_CODES = {
    c.strip() for c in os.getenv("EXCLUDE_CODES", "").split(",") if c.strip()
}


# ------------------------------------------------------------------ nacitani

def load_flomat_feed(path_or_url: str):
    """Vrati {ITEM_CODE: radek} z CSV feedu FLOMAT."""
    if path_or_url.startswith("http"):
        import requests
        resp = requests.get(path_or_url, timeout=120)
        resp.raise_for_status()
        lines = resp.content.decode("utf-8").splitlines()
    else:
        with open(path_or_url, encoding="utf-8") as f:
            lines = f.read().splitlines()
    reader = csv.DictReader(lines, delimiter=";")
    return {r["ITEM_CODE"].strip(): r for r in reader if r.get("ITEM_CODE")}


def load_shoptet_export(path: str):
    """Nacte export produktu ze Shoptetu (.xlsx nebo .csv) -> seznam dictu."""
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows)]
        return [dict(zip(header, r)) for r in rows]

    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(4096)
        f.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        return list(csv.DictReader(f, delimiter=delim))


def get_field(row: dict, *names):
    """Tolerantni cteni sloupce (ruzne exporty maji ruzne velikosti pismen)."""
    lowered = {str(k).strip().lower(): v for k, v in row.items() if k}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


# -------------------------------------------------------------------- vystup

def load_filters(path: str):
    """Nacte regularni vyrazy pro filtrovani vet z popisu."""
    if not os.path.exists(path):
        return []
    rules = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rules.append(re.compile(line, re.IGNORECASE))
            except re.error as exc:
                print(f"  VAROVANI: neplatny filtr '{line}' ({exc}) - preskakuji")
    return rules


def filter_description(html_text: str, rules):
    """Vyhodi z popisu vety, ktere odpovidaji filtrum. Vraci (novy_text, vyhozene_vety).

    Pracuje jen s textem mezi HTML znackami, takze struktura popisu zustane cela.
    Pokud filtrovanim zustane prazdny <li> nebo <p>, odstrani se cely.
    """
    if not rules or not html_text:
        return html_text, []

    dropped = []

    def process_text(segment: str):
        # rozdeli na vety podle . ! ? a vrati jen ty, ktere neodpovidaji filtrum
        parts = re.split(r"(?<=[.!?])\s+", segment)
        kept = []
        for part in parts:
            if part.strip() and any(rule.search(part) for rule in rules):
                dropped.append(" ".join(part.split()))
                continue
            kept.append(part)
        return " ".join(kept)

    out, last = [], 0
    for match in re.finditer(r"<[^>]+>", html_text):
        out.append(process_text(html_text[last:match.start()]))
        out.append(match.group(0))
        last = match.end()
    out.append(process_text(html_text[last:]))
    result = "".join(out)

    # uklid po prazdnych elementech a zdvojenych mezerach
    for _ in range(3):
        result = re.sub(r"<(li|p|h[1-6])>\s*</\1>", "", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip(), dropped


def clean_description(text: str):
    text = (text or "").strip()
    if len(text) > MAX_DESCRIPTION_CHARS:
        text = text[:MAX_DESCRIPTION_CHARS]
    return text


def build_xml(items):
    """Postavi XML ve formatu Shoptet (SHOP > SHOPITEM)."""
    out = ['<?xml version="1.0" encoding="utf-8"?>', "<SHOP>"]
    for it in items:
        out.append("  <SHOPITEM>")
        out.append(f"    <CODE>{escape(it['code'])}</CODE>")
        out.append(f"    <NAME>{escape(it['name'])}</NAME>")
        out.append(f"    <PRICE_VAT>{it['price_vat']:.2f}</PRICE_VAT>")
        out.append(f"    <VAT>{it['vat']}</VAT>")
        if SYNC_DESCRIPTION:
            desc = clean_description(it["description"])
            out.append(f"    <DESCRIPTION><![CDATA[{desc}]]></DESCRIPTION>")
        out.append("  </SHOPITEM>")
    out.append("</SHOP>")
    return "\n".join(out) + "\n"


def write_report(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["kod_shoptet", "kod_flomat", "nazev", "nova_cena_s_dph",
                    "velkoobchodni_cena_s_dph", "sklad_flomat", "delka_popisu", "stav"])
        w.writerows(rows)


# ---------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Generator Shoptet import XML z feedu FLOMAT")
    parser.add_argument("--report-only", action="store_true", help="jen vypsat prehled, negenerovat XML")
    parser.add_argument("--out", help="cesta k vystupnimu XML (prebiji .env)")
    parser.add_argument("--export", help="cesta k exportu produktu ze Shoptetu (prebiji .env)")
    parser.add_argument("--feed", help="cesta nebo URL feedu FLOMAT (prebiji .env)")
    parser.add_argument("--only", help="zahrnout jen tyto kody produktu (oddelene carkou) - pro testovaci import")
    args = parser.parse_args()

    only_codes = {c.strip() for c in (args.only or "").split(",") if c.strip()}

    feed_src = args.feed or FEED_URL
    export_src = args.export or SHOPTET_EXPORT
    out_path = args.out or OUT_PATH

    if not feed_src:
        print("CHYBA: neni zadan feed FLOMAT (FLOMAT_FEED_URL v .env nebo --feed)")
        sys.exit(1)
    if not os.path.exists(export_src):
        print(f"CHYBA: export ze Shoptetu nenalezen: {export_src}")
        sys.exit(1)

    print(f"Nacitam export ze Shoptetu: {export_src}")
    products = load_shoptet_export(export_src)
    print(f"  produktu: {len(products)}")

    rules = load_filters(FILTERS_PATH)
    print(f"Filtru popisu nacteno: {len(rules)} ({FILTERS_PATH})")

    print(f"Nacitam feed FLOMAT: {feed_src}")
    feed = load_flomat_feed(feed_src)
    print(f"  polozek ve feedu: {len(feed)}")

    items, report, skipped, vyhozeno = [], [], [], []
    for p in products:
        code = get_field(p, "code", "kod")
        name = get_field(p, "name", "nazev", "název")
        part = get_field(p, "partNumber", "part_number", "číslo dílu výrobce (mpn)", "mpn")

        if not code:
            continue
        if only_codes and code not in only_codes:
            continue
        if code in EXCLUDE_CODES:
            skipped.append((code, part, name, "", "", "", "", "vyrazeno (EXCLUDE_CODES)"))
            continue
        if not part:
            skipped.append((code, "", name, "", "", "", "", "chybi partNumber"))
            continue

        row = feed.get(part)
        if not row:
            skipped.append((code, part, name, "", "", "", "", "neni ve feedu FLOMAT"))
            continue

        price_vat = round(float(row["PRICE_RECOMMENDED_VAT"]) * PRICE_COEFFICIENT, 2)
        vat = row.get("VAT", "21").split(".")[0]
        description = row.get("DESCRIPTION", "")
        description, dropped = filter_description(description, rules)
        if dropped:
            vyhozeno.append((code, dropped))

        items.append({
            "code": code,
            "name": name,
            "price_vat": price_vat,
            "vat": vat,
            "description": description,
        })
        report.append((code, part, name, f"{price_vat:.2f}", row.get("PRICE_VAT", ""),
                       row.get("STOCK", ""), len(description), "aktualizovat"))

    report.extend(skipped)

    print()
    print(f"K aktualizaci: {len(items)} produktu")
    for it in items:
        print(f"  {it['code']:8} {it['price_vat']:>10.2f} Kc  popis {len(it['description']):>5} znaku  {it['name'][:45]}")
    if vyhozeno:
        print("\nFiltr popisu odstranil tyto vety:")
        for code, vety in vyhozeno:
            for v in vety:
                print(f"  {code}: {v[:110]}")

    if skipped:
        print(f"\nPreskoceno: {len(skipped)}")
        for s in skipped:
            print(f"  {s[0]:8} {s[7]:22} {s[2][:45]}")

    if args.report_only:
        write_report(report, REPORT_PATH)
        print(f"\nReport ulozen: {REPORT_PATH} (XML se negenerovalo, bezel --report-only)")
        return

    if not items:
        print("\nNeni co generovat - zadny produkt se nespaÍroval.")
        sys.exit(1)

    xml = build_xml(items)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(xml)
    write_report(report, REPORT_PATH)

    print(f"\nXML vygenerovano: {out_path} ({len(xml)} bajtu, {len(items)} produktu)")
    print(f"Report ulozen: {REPORT_PATH}")
    print(f"Cas: {datetime.datetime.now():%d.%m.%Y %H:%M}")


if __name__ == "__main__":
    main()
