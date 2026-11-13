# Generated from literate/30-website.md by tools/tangle.py: edit the document, not this file.
"""The website of an archive in plain HTML (the website profile, appendix C of
the specification): a home page listing the documents of the main collection,
one landing page per document (its current version, every version in the
order of the history, notices, files, DOI, and the metadata read by Google
Scholar and other services), and a sitemap.

Pages are made from templates with {{name}} placeholders: templates/index.html,
templates/paper.html and templates/style.css of the archive (osheaf.json:
index.html.templates), or the package's defaults. Mathematics in titles and
abstracts ($...$) is left to MathJax, loaded by the templates.
"""

import datetime
import html
import json
import shutil
from pathlib import Path

from . import core as P

DEFAULTS = Path(__file__).resolve().parent / "templates"


def esc(s):
    return html.escape(s or "", quote=True)


def template(name):
    d = P.INDEX.get("html", {}).get("templates")
    p = P.ROOT / d / name if d else None
    return (p if p and p.exists() else DEFAULTS / name).read_text(encoding="utf-8")


def fill(text, values):
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def fmt_date(d):
    return P.fmt_date(d) if d else ""


def authors(dc):
    return ", ".join(P.display_name(c) for c in dc["creators"])


def file_link(root, obj_id, inv, ver, logical, label):
    cp = P.content_path(inv, ver, logical)
    return f'<a href="{root}ocfl/{obj_id}/{esc(cp)}">{esc(label)}</a>' if cp else ""


def version_block(obj_id, d, inv, ver, current, notices, root):
    """One version of a document: its number, labels, stage, date, changes,
    files, DOI and the notices about it."""
    obj = P.read_json(d, inv, P.OBJ, ver)
    dc = P.read_json(d, inv, "datacite.json", ver)
    n = obj["documentVersion"]
    labels = [f"{e['service']} {e['label']}" for e in obj.get("external", [])
              if e.get("role") == "source" and e.get("label")]
    head = f"Version {n}" + (f" ({esc(', '.join(labels))})" if labels else "")
    if obj.get("stage"):
        head += f' <span class="stage">{esc(obj["stage"]["value"])}</span>'
    if ver == current:
        head += ' <span class="current">current</span>'
    when = ""
    if P.date_of(dc, "Available"):
        when = fmt_date(P.date_of(dc, "Available"))
    elif P.date_of(dc, "Created"):
        when = f"written {fmt_date(P.date_of(dc, 'Created'))}, not public at the time"
    files = [file_link(root, obj_id, inv, ver, r["path"], "PDF") for r in obj.get("renditions", [])]
    if obj.get("mainSource"):
        kind = {"application/x-tex": "LaTeX source", "application/x-texmacs": "TeXmacs source"} \
            .get(obj.get("sourceFormat"), "source")
        files.append(file_link(root, obj_id, inv, ver, obj["mainSource"], kind))
    elif obj.get("sourcesMissing"):
        files.append(f'<span class="missing">sources not available: '
                     f'{esc(obj["sourcesMissing"].get("text", ""))}</span>')
    files.append(f'<a href="{root}ocfl/{obj_id}/{ver}/inventory.json">files and digests</a>')
    for e in obj.get("external", []):
        if e.get("record"):
            files.append(f'<a href="{esc(e["record"])}">{esc(e["service"])}</a>')
    if dc.get("doi"):
        files.append(f'<a href="https://doi.org/{esc(dc["doi"])}">doi:{esc(dc["doi"])}</a>')
    out = [f'<li class="version{" is-current" if ver == current else ""}" id="v{n}">',
           f'<div class="version-head">{head}</div>']
    if when:
        out.append(f'<div class="version-date">{esc(when)}</div>')
    if obj.get("changes", {}).get("text"):
        out.append(f'<div class="changes">{esc(obj["changes"]["text"])}</div>')
    out.append(f'<div class="files">{" · ".join(f for f in files if f)}</div>')
    for x in notices:
        if x["documentVersion"] == n:
            link = f' {file_link(root, obj_id, inv, inv["head"], x["path"], "statement")}' if x.get("path") else ""
            out.append(f'<div class="notice"><strong>Notice ({esc(fmt_date(x["date"]))}):</strong> '
                       f'{esc(x.get("text", ""))}{link}</div>')
    out.append("</li>")
    return "\n".join(out)


def meta_tags(obj_id, d, inv, cur, obj, dc):
    """Google Scholar's citation_* tags, schema.org JSON-LD and FAIR Signposting."""
    base = P.ARCHIVE["baseUrl"]
    landing = f"{base}paper/{obj_id}/"
    pdf = f"{base}ocfl/{obj_id}/{P.content_path(inv, cur, 'paper.pdf')}"
    date = P.date_of(dc, "Issued") or P.date_of(dc, "Available") or P.date_of(dc, "Created") or ""
    tags = [f'<meta name="citation_title" content="{esc(dc["titles"][0]["title"])}">']
    tags += [f'<meta name="citation_author" content="{esc(c["name"])}">' for c in dc["creators"]]
    if date:
        tags.append(f'<meta name="citation_publication_date" content="{esc(date.replace("-", "/"))}">')
    tags.append(f'<meta name="citation_pdf_url" content="{esc(pdf)}">')
    if dc.get("doi"):
        tags.append(f'<meta name="citation_doi" content="{esc(dc["doi"])}">')
    abstract = next((x["description"] for x in dc.get("descriptions", [])
                     if x["descriptionType"] == "Abstract"), "")
    if abstract:
        tags.append(f'<meta name="description" content="{esc(" ".join(abstract.split())[:300])}">')
    rights = (dc.get("rightsList") or [{}])[0]
    cite = f"https://doi.org/{dc['doi']}" if dc.get("doi") else landing
    tags += [f'<link rel="canonical" href="{esc(landing)}">',
             f'<link rel="cite-as" href="{esc(cite)}">',
             f'<link rel="describedby" href="{base}ocfl/{obj_id}/{P.content_path(inv, cur, "datacite.json")}"'
             ' type="application/vnd.datacite.datacite+json">',
             f'<link rel="item" href="{esc(pdf)}" type="application/pdf">']
    if rights.get("rightsUri"):
        tags.append(f'<link rel="license" href="{esc(rights["rightsUri"])}">')
    ld = {"@context": "https://schema.org", "@type": "ScholarlyArticle",
          "name": dc["titles"][0]["title"], "url": landing,
          "author": [{"@type": "Person", "name": P.display_name(c)} for c in dc["creators"]],
          "datePublished": date, "version": dc["version"],
          "encoding": {"@type": "MediaObject", "contentUrl": pdf, "encodingFormat": "application/pdf"}}
    if abstract:
        ld["abstract"] = abstract
    if dc.get("doi"):
        ld["identifier"] = f"https://doi.org/{dc['doi']}"
    if rights.get("rightsUri"):
        ld["license"] = rights["rightsUri"]
    tags.append('<script type="application/ld+json">'
                + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n".join(tags)


def abstract_html(dc):
    for x in dc.get("descriptions", []):
        if x["descriptionType"] == "Abstract":
            return "\n".join(f"<p>{esc(' '.join(p.split()))}</p>" for p in x["description"].split("\n\n"))
    return ""


def render(members):
    """Write index.html, paper/<id>/index.html for every member, style.css
    and sitemap.xml."""
    root_out = P.ROOT
    base = P.ARCHIVE["baseUrl"]
    entries, urls = [], [(base, None)]
    page_t = template("paper.html")
    for m in members:
        if m.get("archive") != P.ARCHIVE["archiveId"]:
            entries.append(remote_entry(m))
            continue
        obj_id, cur = m["id"], m["version"]
        d = P.OCFL / obj_id
        inv = P.load_inventory(d)
        obj = P.read_json(d, inv, P.OBJ, cur)
        dc = P.read_json(d, inv, "datacite.json", cur)
        head = P.read_json(d, inv, P.OBJ)
        notices = head.get("notices", [])
        root = "../../"
        versions = "\n".join(version_block(obj_id, d, inv, v, cur, notices, root)
                             for v in reversed(P.history_of(d, inv)))
        issued = P.date_of(dc, "Issued")
        withdrawn = ""
        if head.get("status") == "withdrawn":
            w = head.get("withdrawal", {})
            withdrawn = (f'<div class="withdrawn"><strong>Withdrawn ({esc(fmt_date(w.get("date")))}):</strong> '
                         f'{esc(w.get("reason", {}).get("text", ""))}</div>')
        rights = (dc.get("rightsList") or [{}])[0]
        licence = esc(rights.get("rights", ""))
        if rights.get("rightsUri"):
            licence = f'<a href="{esc(rights["rightsUri"])}">{licence}</a>'
        cite = f"{authors(dc)}. {dc['titles'][0]['title']}. {P.ARCHIVE['name']}, " \
               f"{(issued or '')[:4]}, version {obj['documentVersion']}. " \
               + (f"https://doi.org/{dc['doi']}" if dc.get("doi") else f"{base}paper/{obj_id}/")
        page = fill(page_t, {
            "root": root, "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base),
            "head": meta_tags(obj_id, d, inv, cur, obj, dc),
            "title": esc(dc["titles"][0]["title"]), "authors": esc(authors(dc)),
            "issued": esc(fmt_date(issued)), "abstract": abstract_html(dc),
            "withdrawn": withdrawn, "versions": versions, "licence": licence,
            "pdf": f'{root}ocfl/{obj_id}/{P.content_path(inv, cur, "paper.pdf")}',
            "cite": esc(cite), "pin": m["inventorySha512"], "pin_url": f"{root}ocfl/{obj_id}/{cur}/inventory.json",
        })
        out = root_out / "paper" / obj_id / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        urls.append((f"{base}paper/{obj_id}/", inv["versions"][inv["head"]]["created"][:10]))
        pdf = f'ocfl/{obj_id}/{P.content_path(inv, cur, "paper.pdf")}'
        abstract = abstract_html(dc)
        entries.append("\n".join([
            f'<li class="paper{" withdrawn" if withdrawn else ""}">',
            f'<a class="paper-title" href="paper/{obj_id}/">{esc(dc["titles"][0]["title"])}</a>',
            f'<div class="paper-authors">{esc(authors(dc))}</div>',
            f'<div class="paper-meta">{esc((issued or "")[:4])} · version {obj["documentVersion"]}'
            f' · <a href="{pdf}">PDF</a> · <span class="pin" title="{m["inventorySha512"]}">'
            f'pin {m["inventorySha512"][:32]}…</span></div>',
            f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
            "</li>"]))
    lead = ('Papers with their sources, every version, fixed by digests. An '
            '<a href="https://opensheaf.org">OpenSheaf</a> archive: programs start from '
            '<a href="opensheaf.json">opensheaf.json</a>.')
    cdir = P.OCFL / P.ARCHIVE["mainCollection"]
    cinv = P.load_inventory(cdir)
    if cinv and P.read_json(cdir, cinv, "members.json").get("order") == "manual":
        desc = next((x["description"] for x in P.read_json(cdir, cinv, "datacite.json").get("descriptions", [])), "")
        lead = (esc(desc) + ' A collection in the <a href="https://opensheaf.org">OpenSheaf</a> format: each '
                'member is kept in its own archive and pinned by a digest; programs start from '
                '<a href="opensheaf.json">opensheaf.json</a>.')
    index = fill(template("index.html"), {
        "root": "", "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base), "lead": lead,
        "papers": "\n".join(entries) if entries else '<li class="empty">No documents yet.</li>',
        "count": str(len(entries)), "updated": esc(fmt_date(datetime.date.today().isoformat())),
    })
    (root_out / "index.html").write_text(index, encoding="utf-8")
    shutil.copyfile(template_path("style.css"), root_out / "style.css")
    (root_out / ".nojekyll").touch()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, last in urls:
        sm.append(f"  <url><loc>{esc(url)}</loc>" + (f"<lastmod>{last}</lastmod>" if last else "") + "</url>")
    sm.append("</urlset>")
    (root_out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    # remove landing pages of documents no longer in the collection
    for p in (root_out / "paper").glob("*") if (root_out / "paper").exists() else []:
        if p.name not in {m["id"] for m in members if m.get("archive") == P.ARCHIVE["archiveId"]}:
            shutil.rmtree(p)


def template_path(name):
    d = P.INDEX.get("html", {}).get("templates")
    p = P.ROOT / d / name if d else None
    return p if p and p.exists() else DEFAULTS / name


def remote_entry(m):
    """The home-page entry of a member of another archive: its metadata read
    from that archive, or else the cached citation."""
    from . import collections
    cite = m.get("cite", {})
    title, by, year = cite.get("title", m["id"]), ", ".join(cite.get("creators", [])), cite.get("year", "")
    links, abstract, archive_name = [], "", m.get("archiveUrl", "")
    here = P.ARCHIVE["baseUrl"] in m.get("mirrors", []) and (P.OCFL / m["id"]).exists()
    if here:
        # a mirror in this archive: its copy is read and linked locally
        inv = P.load_inventory(P.OCFL / m["id"])
        dc = P.read_json(P.OCFL / m["id"], inv, "datacite.json", m["version"])
        title, by, abstract = dc["titles"][0]["title"], authors(dc), abstract_html(dc)
        cp = P.content_path(inv, m["version"], "paper.pdf")
        if cp:
            links.append(f'<a href="ocfl/{m["id"]}/{esc(cp)}">PDF (mirrored here)</a>')
    try:
        r = collections.Remote(m["archiveUrl"])
        archive_name = r.disc.get("name", archive_name)
        rinv = r.inventory(m["id"])
        rdc = json.loads(r.file(m["id"], rinv, m["version"], "datacite.json"))
        if not here:
            title, by, abstract = rdc["titles"][0]["title"], authors(rdc), abstract_html(rdc)
            cp = P.content_path(rinv, m["version"], "paper.pdf")
            if cp:
                links.append(f'<a href="{esc(r.root + m["id"] + "/" + cp)}">PDF</a>')
        if rdc.get("url"):
            links.insert(0, f'<a href="{esc(rdc["url"])}">landing page</a>')
    except Exception:  # noqa: BLE001 - the copy or the cached citation is shown
        links.append('<span class="missing">'
                     + ("its archive is unavailable" if here else "archive unavailable: cached citation")
                     + "</span>")
    return "\n".join([
        '<li class="paper member">',
        f'<span class="paper-title">{esc(title)}</span>',
        f'<div class="paper-authors">{esc(by)}</div>',
        f'<div class="paper-meta">{esc(str(year))} · in <a href="{esc(m["archiveUrl"])}">{esc(archive_name)}</a>'
        + (" · " + " · ".join(links) if links else "")
        + f' · <span class="pin" title="{m["inventorySha512"]}">pin {m["inventorySha512"][:32]}…</span></div>',
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])
