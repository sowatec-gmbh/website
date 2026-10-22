"""Baut die SOWATEC-Website aus Vorlage + Projektregister + Auswahlliste.

Aufruf:
  python bauen.py <projektregister.md> <ausgabeordner>            -> fertige Seite (index.html, img/, fonts/)
  python bauen.py <projektregister.md> <datei.html> --vorschau    -> eine Datei, alles eingebettet

Die Auswahlliste `website-referenzen.md` wird neben dem Register gesucht.

Regeln für die Referenzliste (Datenschutz fest eingebaut):
  - Gezeigt werden Projekte aus Block 1xx (Kommunen) und 2xx (Wohnungsbau, Gewerbe).
  - Standard ist AN. Abgewählt wird in der Auswahlliste mit „nein“.
    Ein Projekt, das neu ins Register kommt, erscheint automatisch.
  - Private Bauherren (3xx) und Eigenes (9xx) erscheinen NIE mit Namen,
    auch nicht über die Auswahlliste – sie gehen nur in die Zahlen ein.
  - Titel und Ort werden aus dem Registernamen gebildet; die Auswahlliste kann beides
    überschreiben.
"""
import re, sys, json, base64, os, shutil, datetime

HIER = os.path.dirname(os.path.abspath(__file__))
LEISTUNGEN = [("Brandschutz", "Brandschutz"), ("TGA", "TGA-Planung"), ("Energieberatung", "Energieberatung"),
              ("Wärmenetz", "Wärmenetze"), ("Studie", "Studien und Wärmeplanung")]
# Gesetzte Untergrenzen, solange das Projektarchiv unvollständig ist
# (Patrick Eger, 2026-10-22: TGA-Projekte seit 1988 deutlich mehr als im Register).
# Zählt das Register mehr, gilt die gezählte Zahl. Prüfen, sobald ältere Archive erfasst sind.
MINDESTWERTE = {"TGA": 151}
BLOCKNAME = {1: "Kommunen, öffentliche Hand", 2: "Wohnungsbau, Gewerbe", 3: "Private Bauherren"}
KUERZEL = {"WEN": "Weiden", "NEW": "Neustadt a.d. Waldnaab", "TIR": "Tirschenreuth", "ESB": "Eschenbach",
           "VOH": "Vohenstrauß", "DD": "Dresden", "WIN": "Wunsiedel", "AM": "Amberg", "Neustadt": "Neustadt a.d. Waldnaab"}


def tabelle_lesen(pfad, block_regel=True):
    """Liest Markdown-Tabellen. Mit block_regel nur Zeilen unter '## 1xx' usw."""
    zeilen, block = [], None
    for line in open(pfad, encoding="utf-8"):
        m = re.match(r"^## (\d)xx", line)
        if m:
            block = int(m.group(1)); continue
        if line.startswith("## "):
            block = None; continue
        if line.startswith("|") and (block or not block_regel):
            zeilen.append((block, [z.strip() for z in line.strip().strip("|").split("|")]))
    return zeilen


def register_lesen(pfad):
    out = []
    for block, z in tabelle_lesen(pfad):
        if len(z) >= 6 and re.match(r"^\d{3}-\d{3}$", z[0]):
            out.append(dict(nr=z[0], kreis=z[1], projekt=z[2], leistung=z[3], ablage=z[4],
                            belegt=z[5].startswith("✓"), block=block))
    return out


def auswahl_lesen(pfad):
    """Auswahlliste: | Projekt im Register | Auf Website | Titel | Ort |"""
    aus = {}
    if not os.path.exists(pfad):
        return aus
    for _, z in tabelle_lesen(pfad, block_regel=False):
        if len(z) < 2 or z[0].startswith("Projekt im Register") or set(z[0]) <= set("-: "):
            continue
        z += [""] * (4 - len(z))
        aus[z[0]] = dict(an=not z[1].lower().startswith("nein"), titel=z[2], ort=z[3])
    return aus


def titel_ort(projekt):
    t = re.sub(r"\*\(.*?\)\*", "", projekt)
    t = re.sub(r"\(B\)|\s-\s*(Fa\.\s*)?(Bauer|Kreutzer)\b|^AKTE\s+|^\d\d-\d\d\s+", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" -")
    teile = t.split(" ", 1)
    ort = KUERZEL.get(teile[0], teile[0])
    rest = teile[1] if len(teile) > 1 else ""
    if "-" in ort and not rest:
        ort, rest = ort.split("-", 1)
    return (rest or t).strip(), ort


def leistung_anzeige(l):
    return " + ".join(n for k, n in LEISTUNGEN if k in l)


def referenzen(reg, auswahl):
    liste, gesehen = [], set()
    for r in reg:
        if r["block"] not in (1, 2):
            continue
        a = auswahl.get(r["projekt"], dict(an=True, titel="", ort=""))
        if not a["an"]:
            continue
        titel, ort = titel_ort(r["projekt"])
        titel, ort = a["titel"] or titel, a["ort"] or ort
        ort = "" if ort == "-" else ort
        schluessel = (titel.lower(), ort.lower())
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        liste.append(dict(titel=titel, ort=ort, leistung=leistung_anzeige(r["leistung"]),
                          laufend=r["ablage"] == "aktiv"))
    liste.sort(key=lambda p: (not p["laufend"],))
    return liste


def daten(reg, auswahl):
    heute = datetime.date.today()
    n = len([r for r in reg if r["block"] in (1, 2, 3)])
    oeff = len({r["kreis"] for r in reg if r["block"] == 1})
    zaehl = {k: sum(1 for r in reg if k in r["leistung"]) for k, _ in LEISTUNGEN}
    for k, mindest in MINDESTWERTE.items():
        zaehl[k] = max(zaehl[k], mindest)
    n = max(n, sum(zaehl.values()))
    zahlen = [
        dict(wert=str(heute.year - 1988), text="Jahre Erfahrung, gegründet 1988"),
        dict(wert=f"über {(n // 10) * 10}", text="Projekte seit 1988"),
        dict(wert=str(oeff), text="Kommunen und öffentliche Auftraggeber"),
        dict(wert=str(zaehl["Brandschutz"]), text="Brandschutzprojekte"),
        dict(wert=str(zaehl["Energieberatung"]), text="Energieberatungen"),
        dict(wert=str(zaehl["Wärmenetz"]), text="Wärmenetze"),
    ]
    privat = sum(1 for r in reg if r["block"] == 3 and "Energieberatung" in r["leistung"])
    return dict(stand=heute.strftime("%d.%m.%Y"), zahlen=zahlen,
                leistungen=[dict(name=nm, anzahl=zaehl[k]) for k, nm in LEISTUNGEN],
                auftraggeber=[dict(name=BLOCKNAME[b], anzahl=sum(1 for r in reg if r["block"] == b)) for b in (1, 2, 3)],
                aktuell=referenzen(reg, auswahl),
                historie=json.load(open(os.path.join(HIER, "historie.json"), encoding="utf-8")),
                privatHinweis=f"Private Bauherren nennen wir nicht namentlich – darunter {privat} Energieberatungen.")


def quelle(ordner, datei):
    """Bild/Schrift im Unterordner oder – im GitHub-Repository – flach daneben."""
    p = os.path.join(HIER, ordner, datei)
    return p if os.path.exists(p) else os.path.join(HIER, datei)


def bauen(register, ziel, vorschau=False):
    reg = register_lesen(register)
    auswahl = auswahl_lesen(os.path.join(os.path.dirname(os.path.abspath(register)), "website-referenzen.md"))
    d = daten(reg, auswahl)
    html = open(os.path.join(HIER, "vorlage.html"), encoding="utf-8").read()
    html = html.replace("/*DATEN*/", json.dumps(d, ensure_ascii=False).replace("</", "<\\/"))
    if vorschau:
        html = html.replace("<!--VORSCHAU-->", '<div class="vorschau"><div class="wrap"><b>Entwurf</b>'
                            '<span>Zahlen und Referenzen live aus Projektregister und Auswahlliste</span></div></div>')
        def einbetten(m):
            p = quelle(m.group(1), m.group(2))
            mime = {"png": "image/png", "jpg": "image/jpeg", "woff2": "font/woff2"}[p.rsplit(".", 1)[1]]
            return "data:%s;base64,%s" % (mime, base64.b64encode(open(p, "rb").read()).decode())
        html = re.sub(r"(img|fonts)/([\w\-]+\.(?:jpg|png|woff2))", einbetten, html)
        open(ziel, "w", encoding="utf-8").write(html)
    else:
        os.makedirs(ziel, exist_ok=True)
        open(os.path.join(ziel, "index.html"), "w", encoding="utf-8").write(html.replace("<!--VORSCHAU-->", ""))
        for ordner, datei in set(re.findall(r"(img|fonts)/([\w\-]+\.(?:jpg|png|woff2))", html)):
            os.makedirs(os.path.join(ziel, ordner), exist_ok=True)
            shutil.copy(quelle(ordner, datei), os.path.join(ziel, ordner, datei))
    return d


if __name__ == "__main__":
    d = bauen(sys.argv[1], sys.argv[2], "--vorschau" in sys.argv)
    print("Stand", d["stand"], "| Referenzen", len(d["aktuell"]), "| Zahlen", [z["wert"] for z in d["zahlen"]])
