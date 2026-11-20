Importing from arXiv: fetching
==============================

Many archives will start from papers already on arXiv. arXiv keeps every
version of a paper, with its PDF and, usually, the sources the authors
submitted; an OpenSheaf archive can hold the same versions, byte for byte,
as the signed document versions of a line. This chapter and the two after it
describe how opensheaf-py does it. This one describes the module as a
whole and the first step, downloading; [the next](41-arxiv-metadata.md)
turns arXiv's metadata into DataCite; [the third](42-arxiv-import.md)
seals a line for each paper and adds its versions, each signed by the
owner of the archive. They use the core of the package (the storage
root, lines, deposits, signatures) through the module `core`, imported as `P`, and
the chapters on the core explain what those functions do.

Two steps
---------

Importing is done in two steps, by two commands:

```
osheaf arxiv fetch DOWNLOADS --author gubinelli_m_1
osheaf arxiv import DOWNLOADS
```

The first only downloads, into a folder of its own, and needs no archive.
The second reads that folder and deposits, and touches nothing on the
network. Separating them has several advantages. Downloading from arXiv is
slow, since arXiv asks robots to be patient, and may fail half-way; the
download can be resumed, and the import repeated, with `--dry-run` or after
`--rebuild`, as often as needed without asking arXiv again. The folder is
also a record of what was received from arXiv, with the digests of every
file, independent of what the archive made of it.

The downloads folder looks like this:

```
DOWNLOADS/
  download.json              what was fetched, when, from where, with SHA-256
  version-licences.json      the licence and the comments of every version
  identifiers.json           arXiv identifier -> label (by the depositor)
  papers/
    2303.18112/
      record.xml             the OAI-PMH record, in the arXivRaw format
      v1.pdf  v1-source.tar.gz
      v2.pdf  v2-source.gz
      v3.pdf  v3-source.pdf
    math_0601001/            old identifiers have a slash, written _
      ...
```

Only `identifiers.json` is written by hand: it gives each paper its
*label*, the readable name of its line in the archive and of its landing
page, `paper/<label>/` (section 3.1 of the specification). Labels should be
chosen by the depositor, not derived from the title, and the import stops,
with a proposal, when one is missing. The line itself is named by the
digest of a genesis record sealed at the import (section 5), as a deposit
with `--new` names it.

The module
----------

Everything lives in one module, `arxiv.py`. Its docstring, shown by
`osheaf arxiv import --help`, summarises what an imported version holds.

    # in arXiv: what the importer does:
    """Import papers downloaded from arXiv into the archive (specification 0.2): one
    line per paper, sealed at its first import, and one signed object version per
    arXiv version.

        osheaf arxiv fetch DOWNLOADS --author AUTHOR-ID | ARXIV-ID ...
        osheaf arxiv import DOWNLOADS [ARXIV-ID ...] [--dry-run]

    DOWNLOADS is the folder written by `osheaf arxiv fetch`: papers/<id>/ for each
    paper (the arXiv identifier, with / replaced by _) holding record.xml
    (OAI-PMH arXivRaw), vN.pdf and vN-source.{tar.gz,gz,pdf}; download.json (what
    was fetched, with SHA-256); version-licences.json (the licence and comments of
    each version, from its abstract page); identifiers.json (arXiv identifier ->
    label of the line in the archive, written by the depositor).

    Each object version holds, byte for byte as served by arXiv:

        paper.pdf          the PDF of that arXiv version
        source/...         the source files, unpacked from arXiv's e-print
                           (absent when arXiv has only a PDF)
        datacite.json      from the arXiv record; IsIdenticalTo the arXiv version
        object.json        the line (name, owner), previous, and `external` (role
                           source) naming the arXiv version and the SHA-512 of the
                           files received from arXiv
        genesis.json       the genesis record of the line, sealed at its first import

    and is signed by the owner of the archive. Papers already in the archive (by
    their label, an arXiv relation in their datacite.json or an arXiv record in
    external) are skipped, or get their new versions with --update. Nothing is
    typeset: the PDF is arXiv's.
    """

In the module the metadata come first, then the import, the import
command, and downloading at the end; the three chapters present the same
definitions grouped by subject, in the order in which they are used.

    # in src/opensheaf/arxiv.py:
    #!/usr/bin/env python3
    <<arXiv: what the importer does>>

    import argparse
    import email.utils
    import gzip
    import hashlib
    import io
    import json
    import re
    import shutil
    import sys
    import tarfile
    import tempfile
    import unicodedata
    import xml.etree.ElementTree as ET
    from pathlib import Path

    from . import core as P

    <<arXiv: the namespaces of the OAI record>>

    <<arXiv: TeX accents>>

    <<arXiv: licences known by name>>


    <<arXiv: plain names from TeX>>


    <<arXiv: reading the arXivRaw record>>


    <<arXiv: the names in the list of authors>>


    <<arXiv: the standard mathematical commands>>


    <<arXiv: separating text and mathematics>>


    <<arXiv: the authors' macros from the preamble>>


    <<arXiv: the contents of balanced braces>>


    <<arXiv: titles and abstracts as plain text>>


    <<arXiv: changes of font as plain text>>


    <<arXiv: spaces and dashes written the TeX way>>


    <<arXiv: macros left unknown>>


    <<arXiv: proposing an identifier from the title>>


    <<arXiv: a creator from an author's name>>


    <<arXiv: safe logical paths>>


    <<arXiv: unpacking an e-print>>


    <<arXiv: finding the main TeX file>>


    <<arXiv: papers already in the archive>>


    <<arXiv: digests of the received files>>


    <<arXiv: the files of a TeXmacs source>>


    <<arXiv: the TeXmacs version of a source>>


    <<arXiv: the rights of a licence>>


    <<arXiv: versions already in an object>>


    <<arXiv: importing a paper>>


    <<arXiv: the import command>>


    <<arXiv: downloading politely>>


    <<arXiv: one request at a time>>


    <<arXiv: the kind of an e-print>>


    <<arXiv: the papers of an author>>


    <<arXiv: fetching papers>>


    <<arXiv: the fetch command>>

Downloading
-----------

### Politely

arXiv asks automated clients to make at most one request every three
seconds, and to say who they are. Every request goes through one function,
which waits until three seconds have passed since the previous one and
sends a `User-Agent` naming opensheaf-py. The time of the last request is
kept in a list, so that the function can change it without a `global`
statement.

    # in arXiv: downloading politely:
    UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}
    _last = [0.0]

A request that fails is tried again, up to four times, waiting 15, 30, 45
and 60 seconds: arXiv answers a busy moment with an error, and networks
fail. An answer 403 (forbidden) or 404 (not found) is final, and is raised
at once: trying again would not change it. After four failures we give up
on that address.

    # in arXiv: one request at a time:
    def _get(url):
        import time
        import urllib.error
        import urllib.request
        wait = 3 - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        for attempt in range(4):
            try:
                _last[0] = time.time()
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code in (403, 404):
                    raise
                time.sleep(15 * (attempt + 1))
            except OSError:
                time.sleep(15 * (attempt + 1))
        raise RuntimeError("giving up on " + url)

### What is fetched for each paper

For each paper we fetch three kinds of things.

The **record**, by OAI-PMH, the protocol by which arXiv offers its metadata
for harvesting. Of its formats, `arXivRaw` is the one we need: it is the
closest to what arXiv itself stores, and lists every version of the paper
with its date and the type of its source, where the other formats describe
only the paper as it is now. A record is fetched once; with `--refresh` it
is fetched again, which is how new versions of a paper are found.

The **PDF and the e-print** of every version, from `export.arxiv.org`, the
host arXiv provides for programs. The e-print is what arXiv serves as the
source of a version, and it comes in several forms: a gzipped tar archive
(the usual case, several files), a single gzipped file (a paper submitted
as one TeX file), or a PDF (a paper submitted as PDF only, or whose source
arXiv does not distribute). The HTTP answer does not say which, so we look
at the first bytes and name the file accordingly, `vN-source.tar.gz`,
`vN-source.gz` or `vN-source.pdf`; anything else is kept as `.bin`.

    # in arXiv: the kind of an e-print:
    def _source_kind(data):
        if data[:4] == b"%PDF":
            return "pdf"
        if data[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(data)
            except OSError:
                return "gz"
            try:
                tarfile.open(fileobj=io.BytesIO(raw)).getmembers()
                return "tar.gz"
            except tarfile.TarError:
                return "gz"
        return "bin"

The **licence and comments** of every version. This is the subtle part.
The licence in the record is that of the current version only, and authors
may change it from one version to the next (for instance from arXiv's
default licence to CC BY for the version accepted by a journal that
requires it); the same holds for the comments field, where authors write
what changed ("v3: published version, typos corrected"). Each version's
own licence and comments appear only on its abstract page,
`arxiv.org/abs/IDvN`, which we read as HTML. The licence is the link in
the licence box of the page or, failing that, the first link to a Creative
Commons or arXiv licence; the comments are the text of their table cell,
with links replaced by their addresses and HTML entities decoded.

### The download

`fetch` goes through the papers in turn. It can be interrupted at any
point and started again: a file listed in `download.json` and present on
disk is not fetched again, and both JSON files are written after every
file. A failure to fetch a file is recorded in `download.json`, with the
error, and does not stop the download; since the failed entry names no
file, the next run tries again. The list of failures is printed at the end.

    # in arXiv: fetching papers:
    def fetch(downloads, ids, refresh=False):
        """Download the record, and the PDF and source of every version, of each
        paper; and the licence and comments of each version. Resumable: what is
        present is not fetched again (the records are fetched again with --refresh)."""
        import datetime
        import html as htmllib
        dl = Path(downloads)
        (dl / "papers").mkdir(parents=True, exist_ok=True)
        logf, verf = dl / "download.json", dl / "version-licences.json"
        log = json.loads(logf.read_text()) if logf.exists() else {}
        info = json.loads(verf.read_text()) if verf.exists() else {}
        for n, aid in enumerate(ids, 1):
            d = dl / "papers" / aid.replace("/", "_")
            d.mkdir(exist_ok=True)
            rec = d / "record.xml"
            if refresh or not rec.exists():
                rec.write_bytes(_get("https://oaipmh.arxiv.org/oai?verb=GetRecord&identifier="
                                     f"oai:arXiv.org:{aid}&metadataPrefix=arXivRaw"))
            versions = re.findall(r'<version version="(v\d+)">', rec.read_text(encoding="utf-8"))
            print(f"[{n}/{len(ids)}] {aid}: {', '.join(versions)}", flush=True)
            entry = log.setdefault(aid, {})
            for v in versions:
                <<arXiv: fetch the PDF and the e-print of a version>>
                <<arXiv: fetch the licence and comments of a version>>
        errs = [(a, k) for a, e in log.items() for k, x in e.items() if "error" in x]
        print("done;", len(errs), "errors", errs)

The versions of the paper are read from the record by a regular
expression: at this stage we only need their names. Each file is recorded
with its address, size, SHA-256 digest and the time it was fetched.

    # in arXiv: fetch the PDF and the e-print of a version:
    for what, url in (("pdf", f"https://export.arxiv.org/pdf/{aid}{v}"),
                      ("src", f"https://export.arxiv.org/e-print/{aid}{v}")):
        key = f"{v}.{what}"
        if key in entry and (d / entry[key].get("file", "/nonexistent")).exists():
            continue
        try:
            data = _get(url)
        except Exception as e:  # noqa: BLE001 - recorded, not fatal
            entry[key] = {"error": str(e), "url": url}
            print("   ", key, "ERROR", e, flush=True)
            continue
        name = f"{v}.pdf" if what == "pdf" else f"{v}-source.{_source_kind(data)}"
        (d / name).write_bytes(data)
        entry[key] = {"file": name, "url": url, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "fetched": datetime.datetime.now(datetime.timezone.utc)
                      .isoformat(timespec="seconds")}
        P.write_json(logf, log)

The page of a version is fetched unless both its licence and its comments
are known (comments may be known to be absent, recorded as `null`).

    # in arXiv: fetch the licence and comments of a version:
    k = aid + v
    if k in info and "comments" in info[k] and info[k].get("licence"):
        continue
    # the record gives only the current licence and comments; each
    # version's own are on its abstract page
    page = _get(f"https://arxiv.org/abs/{k}").decode("utf-8", "replace")
    m = re.search(r'class="abs-license"[^>]*>\s*<a[^>]*href="([^"]+)"', page) or \
        re.search(r'href="(https?://(?:creativecommons\.org/(?:licenses|publicdomain)/[^"]+|'
                  r'arxiv\.org/licenses/[^"]+))"', page)
    c = re.search(r'<td class="tablecell comments[^"]*"[^>]*>(.*?)</td>', page, re.S)
    comments = None
    if c:
        body = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>[^<]*</a>', r"\1", c.group(1))
        comments = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", "", body)).split())
    info[k] = {"licence": m.group(1) if m else None, "comments": comments}
    P.write_json(verf, info)

### Which papers

The papers are named by their arXiv identifiers, or by an author: arXiv
gives each author who claims their papers a page, such as
`arxiv.org/a/gubinelli_m_1`, with an Atom feed listing them. We take the
identifiers of its entries, without their version.

    # in arXiv: the papers of an author:
    def author_papers(author):
        """arXiv identifiers of an author's arXiv page (e.g. gubinelli_m_1)."""
        feed = _get(f"https://arxiv.org/a/{author}.atom2")
        ns = {"a": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(feed)
        return [re.sub(r"v\d+$", "", e.find("a:id", ns).text.rsplit("/abs/", 1)[1])
                for e in root.findall("a:entry", ns)]

The command takes identifiers, an author, or both. It is called by `osheaf
arxiv fetch` (see the chapter on the command line), with the rest of the
command line.

    # in arXiv: the fetch command:
    def fetch_main(argv=None):
        ap = argparse.ArgumentParser(prog="osheaf arxiv fetch", description=fetch.__doc__)
        ap.add_argument("downloads", metavar="DOWNLOADS", help="the folder of the downloads")
        ap.add_argument("ids", nargs="*", metavar="ARXIV-ID", help="arXiv identifiers")
        ap.add_argument("--author", help="all papers of an arXiv author page, e.g. gubinelli_m_1")
        ap.add_argument("--refresh", action="store_true", help="fetch the records again (new versions)")
        a = ap.parse_args(argv)
        ids = list(a.ids) + (author_papers(a.author) if a.author else [])
        if not ids:
            ap.error("give arXiv identifiers or --author")
        fetch(a.downloads, ids, a.refresh)
