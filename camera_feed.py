#!/usr/bin/env python3
"""
Feed RSS della Commissione VI Finanze della Camera dei deputati.

Ogni esecuzione:
  1. legge la pagina "Resoconti delle Giunte e Commissioni" filtrata sulla
     Commissione VI per il mese corrente e per quello precedente;
  2. separa le interrogazioni (numerate 5-xxxxx) da tutto il resto;
  3. aggiorna l'archivio docs/stato.json (cosi' le voci dei mesi passati
     restano nel feed anche quando la pagina cambia mese);
  4. scrive due feed:
       docs/interrogazioni.xml  -> una voce per ogni interrogazione
       docs/sedute.xml          -> una voce per seduta, con tutto il resto
                                   (sede referente, consultiva, atti del
                                   Governo, audizioni, ecc.)

Dipendenze: requests, beautifulsoup4
"""

import json
import re
import sys
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

COMMISSIONE = "06"
BASE = "https://www.camera.it/leg19/210?commissione={c}&annomese={am}&view=filtered"
OUT = Path(__file__).resolve().parent / "docs"
STATO = OUT / "stato.json"
MAX_VOCI = 150          # quante voci tenere in ciascun feed
HEADERS = {
    "User-Agent": "Mozilla/5.0 (feed personale Commissione VI Finanze; NetNewsWire)",
    "Accept-Language": "it-IT,it;q=0.9",
}
RE_INTERROGAZIONE = re.compile(r"^\s*(5-\d{4,6})\s+([^:]+):\s*(.+?)\s*;?\s*$", re.S)
RE_DATA = re.compile(r"anno=(\d{4})&mese=(\d{2})&giorno=(\d{2})")
RE_IDCOMM = re.compile(r"idCommissione=(\d+)")


# ------------------------------------------------------------------ utilita'
def pulisci(testo: str) -> str:
    return re.sub(r"\s+", " ", testo or "").strip()


def assoluto(href: str) -> str:
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://www.camera.it" + href
    return href


def mesi_da_controllare(oggi: date) -> list[str]:
    corrente = f"{oggi.year}{oggi.month:02d}"
    if oggi.month == 1:
        precedente = f"{oggi.year - 1}12"
    else:
        precedente = f"{oggi.year}{oggi.month - 1:02d}"
    return [precedente, corrente]


# ------------------------------------------------------------------ parsing
def analizza_pagina(html: str) -> list[dict]:
    """Restituisce l'elenco delle sedute presenti nella pagina."""
    soup = BeautifulSoup(html, "html.parser")
    contenitore = soup.find(id="sedute")
    if contenitore is None:
        return []

    sedute = []
    for li in contenitore.find_all("li"):
        p = li.find("p", class_="seduta")
        if p is None:
            continue
        a_data = p.select_one("span.dataseduta a")
        if a_data is None:
            continue
        href_indice = assoluto(a_data.get("href", ""))
        m = RE_DATA.search(href_indice)
        if not m:
            continue
        data_iso = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        idc = RE_IDCOMM.search(href_indice)
        id_comm = idc.group(1) if idc else COMMISSIONE

        riunite = p.find("span", class_="commissioniRiunite")
        a_all = p.select_one("span.allegato a")
        a_pdf = p.select_one("span.linkPdf a")

        punti = []                     # (sede, testo)
        sede_corrente = ""
        box = li.find("div", class_="sommariettoCommissioni")
        if box is not None:
            for div in box.find_all("div", recursive=False):
                classi = div.get("class") or []
                if "sede" in classi:
                    sede_corrente = pulisci(div.get_text(" ")).rstrip(":").strip()
                elif "titolo" in classi:
                    testo = pulisci(div.get_text(" "))
                    if testo:
                        punti.append((sede_corrente, testo))

        sedute.append({
            "data": data_iso,
            "etichetta": pulisci(a_data.get_text(" ")),
            "riunite": pulisci(riunite.get_text(" ")) if riunite else "",
            "id_comm": id_comm,
            "indice": href_indice,
            "allegato": assoluto(a_all["href"]) if a_all else "",
            "pdf": assoluto(a_pdf["href"]) if a_pdf else "",
            "punti": punti,
        })
    return sedute


def dividi(seduta: dict) -> tuple[list[dict], list[tuple[str, str]]]:
    """Separa le interrogazioni (5-xxxxx) dagli altri punti della seduta."""
    interrogazioni, altro = [], []
    for sede, testo in seduta["punti"]:
        m = RE_INTERROGAZIONE.match(testo)
        if m:
            interrogazioni.append({
                "numero": m.group(1),
                "deputato": pulisci(m.group(2)),
                "oggetto": pulisci(m.group(3)).rstrip(";").strip(),
                "sede": sede,
            })
        elif "INTERROG" in sede.upper():
            # es. "Rinvio dell'interrogazione n. 5-05081": non e' una risposta
            continue
        else:
            altro.append((sede, testo))
    return interrogazioni, altro


# ------------------------------------------------------------------ archivio
def carica_stato() -> dict:
    if STATO.exists():
        return json.loads(STATO.read_text(encoding="utf-8"))
    return {"interrogazioni": {}, "sedute": {}}


def aggiorna_stato(stato: dict, sedute: list[dict], adesso: str) -> tuple[int, int]:
    nuove_i = nuove_s = 0
    for s in sedute:
        interrogazioni, altro = dividi(s)
        for i in interrogazioni:
            guid = f"{i['numero']}@{s['data']}"
            if guid not in stato["interrogazioni"]:
                nuove_i += 1
                stato["interrogazioni"][guid] = {
                    **i,
                    "data": s["data"],
                    "etichetta": s["etichetta"],
                    "allegato": s["allegato"],
                    "indice": s["indice"],
                    "pdf": s["pdf"],
                    "visto": adesso,
                }
        if altro:
            guid = f"seduta-{s['data']}-com{s['id_comm']}"
            vecchia = stato["sedute"].get(guid)
            voce = {
                "data": s["data"],
                "etichetta": s["etichetta"],
                "riunite": s["riunite"],
                "indice": s["indice"],
                "allegato": s["allegato"],
                "pdf": s["pdf"],
                "punti": altro,
                "visto": vecchia["visto"] if vecchia else adesso,
            }
            if vecchia is None:
                nuove_s += 1
            stato["sedute"][guid] = voce
    return nuove_i, nuove_s


# ------------------------------------------------------------------ RSS
def rfc822(data_iso: str) -> str:
    y, m, d = map(int, data_iso.split("-"))
    return format_datetime(datetime(y, m, d, 16, 0, tzinfo=timezone.utc))


def scrivi_feed(percorso: Path, titolo: str, descrizione: str, link: str, voci: list[str],
                aggiornato: str):
    # data dell'ultima novita' (non "adesso"): cosi' il file cambia solo
    # quando ci sono voci nuove e non si crea un salvataggio a ogni controllo
    try:
        adesso = format_datetime(datetime.fromisoformat(aggiornato))
    except (TypeError, ValueError):
        adesso = format_datetime(datetime.now(timezone.utc))
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0">\n<channel>\n'
        f"<title>{escape(titolo)}</title>\n"
        f"<link>{escape(link)}</link>\n"
        f"<description>{escape(descrizione)}</description>\n"
        "<language>it-it</language>\n"
        f"<lastBuildDate>{adesso}</lastBuildDate>\n"
        "<ttl>360</ttl>\n"
        + "".join(voci)
        + "</channel>\n</rss>\n"
    )
    percorso.write_text(xml, encoding="utf-8")


def voce_rss(titolo: str, link: str, guid: str, pub: str, html_descr: str) -> str:
    return (
        "<item>\n"
        f"<title>{escape(titolo)}</title>\n"
        f"<link>{escape(link)}</link>\n"
        f'<guid isPermaLink="false">{escape(guid)}</guid>\n'
        f"<pubDate>{pub}</pubDate>\n"
        f"<description>{escape(html_descr)}</description>\n"
        "</item>\n"
    )


def link_html(seduta: dict) -> str:
    parti = []
    if seduta.get("allegato"):
        parti.append(f'<a href="{seduta["allegato"]}">Testo delle risposte / documenti di seduta</a>')
    if seduta.get("indice"):
        parti.append(f'<a href="{seduta["indice"]}">Resoconto sommario</a>')
    if seduta.get("pdf"):
        parti.append(f'<a href="{seduta["pdf"]}">PDF</a>')
    return " · ".join(parti)


def genera_feed(stato: dict):
    pagina = "https://www.camera.it/leg19/210"

    # --- interrogazioni
    voci = []
    ordinate = sorted(stato["interrogazioni"].items(),
                      key=lambda kv: (kv[1]["data"], kv[1]["numero"]), reverse=True)
    for guid, i in ordinate[:MAX_VOCI]:
        titolo = f"{i['numero']} {i['deputato']}: {i['oggetto']}"
        descr = (
            f"<p><b>{escape(i['sede'] or 'Interrogazione')}</b> — seduta di {escape(i['etichetta'])}</p>"
            f"<p><b>{escape(i['numero'])}</b> {escape(i['deputato'])}: {escape(i['oggetto'])}</p>"
            f"<p>{link_html(i)}</p>"
        )
        link = i["allegato"] or i["indice"]
        voci.append(voce_rss(titolo, link, guid, rfc822(i["data"]), descr))
    scrivi_feed(OUT / "interrogazioni.xml",
                "Camera – VI Finanze: interrogazioni",
                "Interrogazioni in Commissione Finanze (VI) con risposta del Governo",
                pagina, voci,
                max((i["visto"] for i in stato["interrogazioni"].values()), default=""))

    # --- sedute (tutto il resto)
    voci = []
    ordinate = sorted(stato["sedute"].items(), key=lambda kv: kv[0], reverse=True)
    for guid, s in ordinate[:MAX_VOCI]:
        sedi = []
        for sede, _ in s["punti"]:
            if sede and sede not in sedi:
                sedi.append(sede)
        etichetta_sedi = ", ".join(x.capitalize() if x.isupper() else x for x in sedi) or "Seduta"
        prefisso = f"{s['riunite']} – " if s.get("riunite") else ""
        titolo = f"{prefisso}{s['etichetta']} – {etichetta_sedi}"

        righe, sede_prec = [], None
        for sede, testo in s["punti"]:
            if sede != sede_prec:
                if righe:
                    righe.append("</ul>")
                righe.append(f"<p><b>{escape(sede or 'Altro')}</b></p><ul>")
                sede_prec = sede
            righe.append(f"<li>{escape(testo)}</li>")
        if righe:
            righe.append("</ul>")
        descr = "".join(righe) + f"<p>{link_html(s)}</p>"
        voci.append(voce_rss(titolo, s["indice"], guid, rfc822(s["data"]), descr))
    scrivi_feed(OUT / "sedute.xml",
                "Camera – VI Finanze: sedute",
                "Lavori della Commissione Finanze (VI): sede referente, consultiva, atti del Governo, audizioni",
                pagina, voci,
                max((x["visto"] for x in stato["sedute"].values()), default=""))


# ------------------------------------------------------------------ main
def main():
    OUT.mkdir(exist_ok=True)
    stato = carica_stato()
    adesso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    sessione = requests.Session()
    sessione.headers.update(HEADERS)
    errori = 0
    totale_i = totale_s = 0
    for am in mesi_da_controllare(date.today()):
        url = BASE.format(c=COMMISSIONE, am=am)
        try:
            r = sessione.get(url, timeout=60)
            r.raise_for_status()
            r.encoding = "utf-8"
        except Exception as e:
            print(f"ERRORE nel leggere {url}: {e}", file=sys.stderr)
            errori += 1
            continue
        sedute = analizza_pagina(r.text)
        ni, ns = aggiorna_stato(stato, sedute, adesso)
        totale_i += ni
        totale_s += ns
        print(f"{am}: {len(sedute)} sedute lette, {ni} interrogazioni nuove, {ns} sedute nuove")

    if errori == 2:
        sys.exit("Nessuna pagina letta: il feed non viene modificato.")

    STATO.write_text(json.dumps(stato, ensure_ascii=False, indent=1), encoding="utf-8")
    genera_feed(stato)
    # Una modifica al mese anche senza novita': GitHub sospende le
    # attivita' programmate dopo 60 giorni senza modifiche al repository
    # (succederebbe, per esempio, durante la pausa estiva dei lavori).
    (OUT / "ultimo-controllo.txt").write_text(date.today().strftime("%Y-%m") + "\n")
    (OUT / ".nojekyll").touch()
    print(f"Fatto: {totale_i} interrogazioni e {totale_s} sedute aggiunte.")


if __name__ == "__main__":
    main()
