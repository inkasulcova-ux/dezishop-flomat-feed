# Nasazení na GitHub — krok za krokem

Cílem je, aby se XML feed sám každou noc přegeneroval z aktuálních dat FLOMATu
a byl dostupný na veřejné URL, odkud si ho Shoptet stáhne. Běží to na GitHub
Actions, takže nepotřebujete žádný server ani webhosting. Zdarma.

---

## 1. Vytvořit repozitář

Na <https://github.com/new>:

- **Repository name:** např. `dezishop-flomat-feed`
- **Public** ← musí být veřejný, jinak GitHub Pages na free účtu nefunguje
- Nezaškrtávat „Add a README file"

> **Pozor na veřejnost:** v repozitáři budou ceny a popisy produktů, což jsou
> veřejné informace. Klíč k feedu FLOMATu se tam **nedostane** — uloží se jako
> šifrovaný secret (krok 3) a `.gitignore` hlídá, aby se `.env` nikdy
> nenacommitoval.

## 2. Nahrát soubory

Buď přes web (tlačítko *Add file → Upload files*), nebo z terminálu:

```bash
cd "cesta/k/flomat-shoptet-sync"
git init
git add .
git commit -m "Prvni verze"
git branch -M main
git remote add origin https://github.com/VASE-JMENO/dezishop-flomat-feed.git
git push -u origin main
```

Nahrát se musí: `generate_import.py`, `requirements.txt`, `popis_filtry.txt`,
`shoptet_export.xlsx`, složka `.github/` a složka `docs/`.

## 3. Uložit klíč k feedu

V repozitáři: *Settings → Secrets and variables → Actions*

Na záložce **Secrets** → *New repository secret*:
- **Name:** `FLOMAT_FEED_URL`
- **Secret:** celá URL feedu včetně `id` a `klic`

Na záložce **Variables** → *New repository variable*:
- **Name:** `EXCLUDE_CODES`
- **Value:** `99005`

(To je WD70, u kterého si držíte vlastní cenu. Další kódy oddělte čárkou.)

## 4. Zapnout GitHub Pages

*Settings → Pages*:
- **Source:** Deploy from a branch
- **Branch:** `main`, složka `/docs`
- Uložit

Za chvíli bude feed dostupný na:

```
https://VASE-JMENO.github.io/dezishop-flomat-feed/shoptet_import.xml
```

Tuhle URL dejte do Shoptetu. Report je vedle na `.../report.csv`.

## 5. Vyzkoušet generování

*Actions → Aktualizace feedu pro Shoptet → Run workflow*

Projde to zeleně? Pak se podívejte na tu URL výše — mělo by se načíst XML.
Od teď poběží samo každou noc ve 3:00 (v zimním čase; workflow je nastavený
na 2:00 UTC).

## 6. Nastavit import v Shoptetu

*Produkty → Automatické importy → Přidat import*:

| Pole | Hodnota |
|---|---|
| Jméno | FLOMAT rohože |
| Import kód | `flomat-rohoze` |
| Typ dodavatele | Shoptet |
| URL adresa XML feedu | vaše GitHub Pages URL |
| Párovat produkty podle | **Kód produktu** |
| Aktualizovat produkty | **Pouze existující** |
| Produkty chybějící ve feedu | **Ponechat nezměněné** |
| Cenový koeficient | 1 |

V **Položkách importu** zaškrtnout jen **Cena** a **Popis**.

V **Rozvrhu** nastavit **úplný import** (jen ten umí popis) na některou hodinu
mezi 04:00 a 07:00 — tedy až potom, co GitHub feed přegeneruje.

---

## Co dělat, když přibydou produkty

1. V Shoptetu doplnit novému produktu `partNumber` (katalogové číslo FLOMATu).
2. Vyexportovat produkty (*Produkty → Export produktů*) a nahradit v repozitáři
   soubor `shoptet_export.xlsx`.
3. Hotovo — při dalším běhu se produkt napojí sám.

## Co dělat, když se objeví další věta „od FLOMATu"

Přidat řádek s regulárním výrazem do `popis_filtry.txt` a nacommitovat.
Co filtr odstranil, je vidět ve výpisu běhu v záložce Actions.
