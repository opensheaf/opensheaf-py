# Generated from literate/30-website.md by opensheaf-literate: edit the document, not this file.
"""The website of an archive in plain HTML (the website profile, appendix C of
the specification): a home page listing the documents of the main collection,
one landing page per document (its current version, every version in the
order of the history, notices, files, DOI, and the metadata read by Google
Scholar and other services), and a sitemap.

Pages are made from templates with {{name}} placeholders: templates/index.html,
templates/paper.html and templates/style.css of the archive (osheaf.json:
index.html.templates or index.templates, else the folder templates/ if there
is one), or the package's defaults. Mathematics in titles and abstracts
($...$) is left to MathJax, loaded by the templates. With a TeXmacs index
the home page is TeXmacs', and only the landing pages and the sitemap are
written here.
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
    return template_path(name).read_text(encoding="utf-8")


def fill(text, values):
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def fmt_date(d):
    return P.fmt_date(d) if d else ""


def authors(dc):
    return P.authors_of(dc)


def file_link(root, obj_id, inv, ver, logical, label):
    cp = P.content_path(inv, ver, logical)
    return f'<a href="{root}ocfl/{obj_id}/{esc(cp)}">{esc(label)}</a>' if cp else ""


def pdf_address(root, obj_id, inv, ver, obj):
    lp = P.pdf_of(obj)
    cp = P.content_path(inv, ver, lp) if lp else None
    return f"{root}ocfl/{obj_id}/{cp}" if cp else None


def versions_line(m, obj):
    """'version 3', or for a member of a selection 'vetted: versions 2, 3'."""
    if m.get("revisions"):
        ns = [str(r["documentVersion"]) for r in m["revisions"]]
        return f"vetted: version{'s' if len(ns) > 1 else ''} {', '.join(ns)}"
    return f"version {obj['documentVersion']}"


def version_block(obj_id, d, inv, ver, shown, notices, root, vetted=None):
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
    if vetted is not None and n in vetted:
        head += ' <span class="current">vetted</span>'
    elif vetted is None and n == shown:
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
    arxiv = P.arxiv_id(obj, dc)
    for e in obj.get("external", []):
        if e.get("record"):
            label = f"arXiv:{arxiv}" if e.get("service") == "arXiv" and arxiv else e["service"]
            files.append(f'<a href="{esc(e["record"])}">{esc(label)}</a>')
    if arxiv and not any(e.get("service") == "arXiv" for e in obj.get("external", [])):
        files.append(f'<a href="https://arxiv.org/abs/{esc(arxiv)}">arXiv:{esc(arxiv)}</a>')
    if dc.get("doi"):
        files.append(f'<a href="https://doi.org/{esc(dc["doi"])}">doi:{esc(dc["doi"])}</a>')
    out = [f'<li class="version{" is-current" if n == shown else ""}" id="v{n}">',
           f'<div class="version-head">{head}</div>']
    if when:
        out.append(f'<div class="version-date">{esc(when)}</div>')
    if P.changes_note(obj):
        out.append(f'<div class="changes">{esc(P.changes_note(obj))}</div>')
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
    pdf = pdf_address(base, obj_id, inv, cur, obj)
    date = P.date_of(dc, "Issued") or P.date_of(dc, "Available") or P.date_of(dc, "Created") or ""
    tags = [f'<meta name="citation_title" content="{esc(dc["titles"][0]["title"])}">']
    tags += [f'<meta name="citation_author" content="{esc(c["name"])}">' for c in dc["creators"]]
    if date:
        tags.append(f'<meta name="citation_publication_date" content="{esc(date.replace("-", "/"))}">')
    if pdf:
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
             ' type="application/vnd.datacite.datacite+json">']
    if pdf:
        tags.append(f'<link rel="item" href="{esc(pdf)}" type="application/pdf">')
    if rights.get("rightsUri"):
        tags.append(f'<link rel="license" href="{esc(rights["rightsUri"])}">')
    ld = {"@context": "https://schema.org", "@type": "ScholarlyArticle",
          "name": dc["titles"][0]["title"], "url": landing,
          "author": [{"@type": "Person", "name": P.display_name(c)} for c in dc["creators"]],
          "datePublished": date, "version": dc["version"]}
    if pdf:
        ld["encoding"] = {"@type": "MediaObject", "contentUrl": pdf, "encodingFormat": "application/pdf"}
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


def render(members, home=True, featured=None):
    """Write index.html, paper/<id>/index.html for every member, style.css
    and sitemap.xml; with home=False (a TeXmacs index is the home page),
    everything but index.html. featured: a collection of the archive whose
    members the home page lists first."""
    root_out = P.ROOT
    base = P.ARCHIVE["baseUrl"]
    entries, urls, written = [], [(base, None)], []
    page_t = template("paper.html")
    fmembers = []
    if featured:
        fdir = P.OCFL / featured
        finv = P.load_inventory(fdir)
        fmembers = P.read_json(fdir, finv, "members.json")["members"]
    listed = {m["id"] for m in members if m.get("archive") == P.ARCHIVE["archiveId"]}
    extra = [fm for fm in fmembers if fm.get("archive") == P.ARCHIVE["archiveId"] and fm["id"] not in listed]
    for k, m in enumerate(members + extra):
        if m.get("archive") != P.ARCHIVE["archiveId"]:
            if home:
                entries.append(remote_entry(m))
            continue
        obj_id = m["id"]
        d = P.OCFL / obj_id
        inv = P.load_inventory(d)
        cur = P.presented_version(m, d, inv)
        pin_ver, pin = P.member_pins(m)[-1][:2]
        vetted = {r["documentVersion"] for r in m["revisions"]} if m.get("revisions") else None
        obj = P.read_json(d, inv, P.OBJ, cur)
        dc = P.read_json(d, inv, "datacite.json", cur)
        head = P.read_json(d, inv, P.OBJ)
        notices = head.get("notices", [])
        root = "../../"
        versions = "\n".join(version_block(obj_id, d, inv, v, obj["documentVersion"], notices, root, vetted)
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
        html_link = ""
        if (P.SITE / obj_id / f"{obj_id}.html").exists():
            html_link = f' · <a href="{root}site/{obj_id}/{obj_id}.html">HTML</a>'
        page = fill(page_t, {
            "root": root, "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base),
            "head": meta_tags(obj_id, d, inv, cur, obj, dc),
            "title": esc(dc["titles"][0]["title"]), "authors": esc(authors(dc)),
            "issued": esc(fmt_date(issued)), "abstract": abstract_html(dc),
            "withdrawn": withdrawn, "versions": versions, "licence": licence,
            "pdf": esc(pdf_address(root, obj_id, inv, cur, obj) or f"#v{obj['documentVersion']}"),
            "cite": esc(cite), "pin": pin, "pin_url": f"{root}ocfl/{obj_id}/{pin_ver}/inventory.json",
            "html_link": html_link,
        })
        out = root_out / "paper" / obj_id / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        written.append(obj_id)
        urls.append((f"{base}paper/{obj_id}/", inv["versions"][inv["head"]]["created"][:10]))
        if html_link:
            urls.append((f"{base}site/{obj_id}/{obj_id}.html", inv["versions"][inv["head"]]["created"][:10]))
        if k < len(members):
            entries.append(local_entry(m))
    if home:
        featured_html = ""
        if featured:
            fdc = P.read_json(fdir, finv, "datacite.json")
            items = [local_entry(fm) if fm.get("archive") == P.ARCHIVE["archiveId"] else remote_entry(fm)
                     for fm in fmembers]
            featured_html = ('<section class="featured">\n'
                             f'<h2>{esc(fdc["titles"][0]["title"])}</h2>\n<ol class="papers">\n'
                             + ("\n".join(items) if items else '<li class="empty">No members yet.</li>')
                             + "\n</ol>\n</section>")
        lead = ('Papers with their sources, every version, fixed by digests. An '
                '<a href="https://opensheaf.org">OpenSheaf</a> archive: programs start from '
                '<a href="opensheaf.json">opensheaf.json</a>.')
        cdir = P.OCFL / (featured or P.ARCHIVE["mainCollection"])
        cinv = P.load_inventory(cdir)
        cmem = P.read_json(cdir, cinv, "members.json") if cinv else {}
        if featured or cmem.get("order") == "manual":
            cdc = P.read_json(cdir, cinv, "datacite.json")
            desc = next((x["description"] for x in cdc.get("descriptions", [])), "")
            lead = (esc(desc) + ' A collection in the <a href="https://opensheaf.org">OpenSheaf</a> format: each '
                    'member is kept in its own archive and pinned by a digest'
                    + (', in the versions its curator vetted' if cmem.get("type") == "selection" else '')
                    + '; programs start from <a href="opensheaf.json">opensheaf.json</a>.')
        index = fill(template("index.html"), {
            "root": "", "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base), "lead": lead,
            "papers": "\n".join(entries) if entries else '<li class="empty">No documents yet.</li>',
            "featured": featured_html,
            "papers_heading": "<h2>In this archive</h2>" if featured else "",
            "count": str(len(entries)), "updated": esc(fmt_date(datetime.date.today().isoformat())),
        })
        (root_out / "index.html").write_text(index, encoding="utf-8")
        shutil.copyfile(template_path("style.css"), root_out / "style.css")
        (root_out / ".nojekyll").touch()
    elif "style.css" in page_t:
        shutil.copyfile(template_path("style.css"), root_out / "style.css")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, last in urls:
        sm.append(f"  <url><loc>{esc(url)}</loc>" + (f"<lastmod>{last}</lastmod>" if last else "") + "</url>")
    sm.append("</urlset>")
    (root_out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    # remove landing pages of documents no longer in the collection
    for p in (root_out / "paper").glob("*") if (root_out / "paper").exists() else []:
        if p.is_dir() and p.name not in {m["id"] for m in members if m.get("archive") == P.ARCHIVE["archiveId"]}:
            shutil.rmtree(p)
    return len(written)


def template_path(name):
    d = P.INDEX.get("html", {}).get("templates") or P.INDEX.get("templates") or "templates"
    p = P.ROOT / d / name
    return p if p.exists() else DEFAULTS / name


def remote_entry(m):
    """The home-page entry of a member of another archive: its metadata read
    from that archive, or else the cached citation."""
    from . import collections
    cite = m.get("cite", {})
    title, by, year = cite.get("title", m["id"]), P.names_joined(cite.get("creators", [])), cite.get("year", "")
    links, abstract, archive_name, status = [], "", m.get("archiveUrl", ""), {}
    pin = P.member_pins(m)[-1][1]
    minv = P.load_inventory(P.OCFL / m["id"])
    here = P.ARCHIVE["baseUrl"] in m.get("mirrors", []) and minv is not None \
        and all(v in minv["versions"] for v, _, _ in P.member_pins(m))
    if here:
        # a mirror in this archive: its copy is read and linked locally
        shown = P.presented_version(m, P.OCFL / m["id"], minv)
        dc = P.read_json(P.OCFL / m["id"], minv, "datacite.json", shown)
        title, by, abstract = dc["titles"][0]["title"], authors(dc), abstract_html(dc)
        pdf = pdf_address("", m["id"], minv, shown, P.read_json(P.OCFL / m["id"], minv, P.OBJ, shown))
        status = P.read_json(P.OCFL / m["id"], minv, P.OBJ)
        if pdf:
            links.append(f'<a href="{esc(pdf)}">PDF (mirrored here)</a>')
    try:
        r = collections.Remote(m["archiveUrl"])
        archive_name = r.disc.get("name", archive_name)
        rinv = r.inventory(m["id"])
        shown = m["revisions"][-1]["version"] if m.get("revisions") else r.current(m["id"], m["version"])
        rdc = json.loads(r.file(m["id"], rinv, shown, "datacite.json"))
        status = json.loads(r.file(m["id"], rinv, rinv["head"], P.OBJ))
        if not here:
            title, by, abstract = rdc["titles"][0]["title"], authors(rdc), abstract_html(rdc)
            lp = P.pdf_of(json.loads(r.file(m["id"], rinv, shown, P.OBJ)))
            cp = P.content_path(rinv, shown, lp) if lp else None
            if cp:
                links.append(f'<a href="{esc(r.root + m["id"] + "/" + cp)}">PDF</a>')
        if rdc.get("url"):
            links.insert(0, f'<a href="{esc(rdc["url"])}">landing page</a>')
    except Exception:  # noqa: BLE001 - the copy or the cached citation is shown
        links.append('<span class="missing">'
                     + ("its archive is unavailable" if here else "archive unavailable: cached citation")
                     + "</span>")
    withdrawn = ""
    if status.get("status") == "withdrawn":
        w = status.get("withdrawal", {})
        withdrawn = (f'<div class="withdrawn"><strong>Withdrawn in its archive ({esc(fmt_date(w.get("date")))}):'
                     f'</strong> {esc(w.get("reason", {}).get("text", ""))}</div>')
    return "\n".join([
        f'<li class="paper member{" withdrawn" if withdrawn else ""}">',
        f'<span class="paper-title">{esc(title)}</span>',
        f'<div class="paper-authors">{esc(by)}</div>',
        f'<div class="paper-meta">{esc(str(year))} · in <a href="{esc(m["archiveUrl"])}">{esc(archive_name)}</a>'
        + (f' · {versions_line(m, {})}' if m.get("revisions") else "")
        + (" · " + " · ".join(links) if links else "")
        + f' · <span class="pin" title="{pin}">pin {pin[:32]}…</span></div>',
        withdrawn,
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])


def local_entry(m):
    """The home-page entry of a member of this archive, in the version its
    collection presents (the main collection's or the featured one's)."""
    obj_id = m["id"]
    d = P.OCFL / obj_id
    inv = P.load_inventory(d)
    cur = P.presented_version(m, d, inv)
    pin = P.member_pins(m)[-1][1]
    obj = P.read_json(d, inv, P.OBJ, cur)
    dc = P.read_json(d, inv, "datacite.json", cur)
    withdrawn = P.read_json(d, inv, P.OBJ).get("status") == "withdrawn"
    issued = P.date_of(dc, "Issued")
    pdf = pdf_address("", obj_id, inv, cur, obj)
    abstract = abstract_html(dc)
    return "\n".join([
        f'<li class="paper{" withdrawn" if withdrawn else ""}">',
        f'<a class="paper-title" href="paper/{obj_id}/">{esc(dc["titles"][0]["title"])}</a>',
        f'<div class="paper-authors">{esc(authors(dc))}</div>',
        f'<div class="paper-meta">{esc((issued or "")[:4])} · {versions_line(m, obj)}'
        + (f' · <a href="{esc(pdf)}">PDF</a>' if pdf else "")
        + f' · <span class="pin" title="{pin}">pin {pin[:32]}…</span></div>',
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])
