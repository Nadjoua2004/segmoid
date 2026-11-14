#!/usr/bin/env python3
"""
AstroDoc AI - download all resources into the project folders.

Usage (run from the root of your astrodoc/ project, on your own laptop):
    python download_resources.py

Needs only Python 3.8+ (no extra packages). Creates:
    backend/data/docs/        NASA / CSA / JAXA documents for the chatbot (RAG)
    backend/data/events/      donki_sep_sample.json (real solar particle events)
    backend/data/physionet/   Apple Watch heart-rate CSVs (open access, ODC-BY)
"""
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

ROOT = Path("backend/data")
DOCS, EVENTS, PHYSIO = ROOT / "docs", ROOT / "events", ROOT / "physionet"

# ---- PDFs (saved as-is) -------------------------------------------------
PDFS = [
    ("03_NASA-STD-3001_TB_Carbon_Dioxide.pdf",
     "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-004-carbon-dioxide.pdf"),
    ("04_NASA-STD-3001_TB_Radiation_Protection.pdf",
     "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-020-radiation-protection.pdf"),
    ("05_NASA-STD-3001_TB_Bone_Loss.pdf",
     "https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-030-bone-loss.pdf"),
    ("08_Exercise_countermeasures_npjMicrogravity2023.pdf",
     "https://www.nature.com/articles/s41526-023-00256-5.pdf"),
]

# ---- Web pages (converted to .txt; several URLs are joined into one file) --
PAGES = [
    ("01_NASA_Human_Body_in_Space.txt",
     ["https://www.nasa.gov/humans-in-space/the-human-body-in-space/"]),
    ("02_NASA_HRP_Five_Hazards.txt",
     ["https://www.nasa.gov/hrp/hazards"]),
    ("07_NASA_Astronaut_Exercise.txt",
     ["https://www.nasa.gov/missions/station/iss-research/astronaut-exercise/"]),
    ("09_SANS_mechanical_countermeasures_2025.txt",
     ["https://pmc.ncbi.nlm.nih.gov/articles/PMC11891356/"]),
    ("10_Red_risks_red_planet.txt",
     ["https://pmc.ncbi.nlm.nih.gov/articles/PMC7645687/"]),
    ("11_CSA_Effects_of_space_on_the_body.txt", [
        "https://www.asc-csa.gc.ca/eng/astronauts/living-in-space/effects-of-space-on-the-body.asp",
        "https://www.asc-csa.gc.ca/eng/astronauts/space-medicine/decomp.asp",
        "https://www.asc-csa.gc.ca/eng/astronauts/space-medicine/muscles.asp",
        "https://www.asc-csa.gc.ca/eng/astronauts/space-medicine/bones.asp",
        "https://www.asc-csa.gc.ca/eng/astronauts/space-medicine/radiation.asp",
    ]),
    ("12_JAXA_Health_management_for_astronauts.txt", [
        "https://humans-in-space.jaxa.jp/en/biz-lab/med-in-space/healthcare/",
        "https://humans-in-space.jaxa.jp/en/biz-lab/med-in-space/healthcare/medops/",
        "https://humans-in-space.jaxa.jp/en/biz-lab/med-in-space/healthcare/food/",
    ]),
]

# ---- NASA DONKI solar particle events (May 2024 storm) -------------------
DONKI_URL = ("https://api.nasa.gov/DONKI/SEP?startDate=2024-05-01"
             "&endDate=2024-05-31&api_key=DEMO_KEY")

# ---- PhysioNet: Apple Watch heart rate, night 1 of 5 participants --------
PHYSIO_BASE = "https://physionet.org/files/bidsleep-dataset/1.0.1/"
PHYSIO_FILES = [(f"{s}_night1_hr.csv", f"{s}/1/hr.csv")
                for s in ["Bidslab00", "Bidslab01", "Bidslab02", "Bidslab06", "Bidslab07"]]
PHYSIO_FILES += [("physionet_LICENSE.txt", "LICENSE.txt"), ("physionet_README.md", "README.md")]


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


class TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "noscript", "svg", "aside", "form"}
    BLOCK = {"p", "div", "section", "article", "li", "br", "tr",
             "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip, self.title, self._in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in self.BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and not self.skip:
            self.parts.append("## " if tag != "h1" else "# ")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)

    def text(self):
        t = "".join(self.parts)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
        return t.strip()


def page_to_text(url):
    raw, _ = fetch(url)
    p = TextExtractor()
    p.feed(raw.decode("utf-8", errors="replace"))
    return f"Title: {p.title.strip()}\nSource: {url}\n\n{p.text()}"


def main():
    for d in (DOCS, EVENTS, PHYSIO):
        d.mkdir(parents=True, exist_ok=True)
    ok, failed = [], []

    def run(label, fn):
        try:
            size = fn()
            ok.append(f"{label} ({size/1024:.0f} KB)")
            print(f"  OK    {label}  ({size/1024:.0f} KB)")
        except Exception as e:  # keep going no matter what
            failed.append((label, str(e)))
            print(f"  FAIL  {label}  -> {e}")

    print("PDFs ->", DOCS)
    for name, url in PDFS:
        def f(name=name, url=url):
            data, ctype = fetch(url)
            if b"%PDF" not in data[:1024]:
                raise RuntimeError(f"not a PDF (got {ctype}) - open {url} in your browser and save it")
            (DOCS / name).write_bytes(data)
            return len(data)
        run(name, f)

    print("Web pages ->", DOCS)
    for name, urls in PAGES:
        def f(name=name, urls=urls):
            chunks = []
            for u in urls:
                try:
                    chunks.append(page_to_text(u))
                except Exception as e:
                    print(f"        (skipped {u}: {e})")
            if not chunks:
                raise RuntimeError("no page could be fetched")
            text = ("\n\n" + "=" * 40 + "\n").join(chunks)
            (DOCS / name).write_text(text, encoding="utf-8")
            return len(text.encode())
        run(name, f)

    print("NASA DONKI ->", EVENTS)
    def donki():
        data, _ = fetch(DONKI_URL)
        events = json.loads(data)
        out = json.dumps(events, indent=2)
        (EVENTS / "donki_sep_sample.json").write_text(out, encoding="utf-8")
        return len(out)
    run("donki_sep_sample.json", donki)

    print("PhysioNet ->", PHYSIO)
    for name, path in PHYSIO_FILES:
        def f(name=name, path=path):
            data, _ = fetch(PHYSIO_BASE + path)
            (PHYSIO / name).write_bytes(data)
            return len(data)
        run(name, f)

    print(f"\nDone: {len(ok)} saved, {len(failed)} failed.")
    if failed:
        print("Open these in your browser and save them by hand:")
        for label, err in failed:
            print(f"  - {label}: {err}")
    print("\nFiles are in:", ROOT.resolve())
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
