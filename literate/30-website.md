The website
===========

An OpenSheaf archive is a folder of static files, and it is meant to be
served as a website: the storage root, the discovery document
`opensheaf.json`, and pages for readers. This chapter describes the
pages, written by `src/opensheaf/html.py` for archives that follow the
*website profile* (appendix C of the specification): a home page listing
the members of the main collection, one landing page for each document
of the archive, and a sitemap. The pages are filled into templates,
which are described in the [next chapter](31-templates.md).

The pages are a presentation, never a source of truth. They are
regenerated from the archive by `osheaf index` (in the chapters on the
core), whenever the archive changes, and never edited by hand; a
verifier does not trust them. Their job is to be read by people and
found by search engines, and to link every claim to the files that
support it: each version to its inventory, each member to its pin.

The members shown are those of the main collection: the archive's own
documents, built by the core, or a curated list with members of other
archives ([collections](20-collections.md)). A member of this archive
gets a landing page; a member of another archive gets an entry on the
home page only, linking to its own archive, which has its own landing
pages.

The module
----------

    # in src/opensheaf/html.py:
    <<the documentation of html.py>>

    import datetime
    import html
    import json
    import shutil
    from pathlib import Path

    from . import core as P

    DEFAULTS = Path(__file__).resolve().parent / "templates"


    <<escaping text for HTML>>


    <<reading and filling the templates>>


    <<dates, authors and file links on the website>>


    <<a version on a landing page>>


    <<the tags for search engines>>


    <<an abstract in HTML>>


    <<writing the website>>


    <<the path of a template>>


    <<a member of another archive on the home page>>

The documentation of the module is a summary of this chapter.

    # in the documentation of html.py:
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

Templates
---------

The look of the pages belongs to the archive, not to the tools: each
archive has its own templates, in the folder named by
`index.html.templates` in `osheaf.json` (`osheaf init` copies the
defaults there, to be edited). A template missing from that folder is
taken from the package's defaults, `DEFAULTS`, the folder `templates`
next to the module.

    # in reading and filling the templates:
    def template(name):
        d = P.INDEX.get("html", {}).get("templates")
        p = P.ROOT / d / name if d else None
        return (p if p and p.exists() else DEFAULTS / name).read_text(encoding="utf-8")

The style sheet is copied rather than filled, so its path is needed
rather than its text. The lookup is the same.

    # in the path of a template:
    def template_path(name):
        d = P.INDEX.get("html", {}).get("templates")
        p = P.ROOT / d / name if d else None
        return p if p and p.exists() else DEFAULTS / name

A template is HTML with placeholders `{{name}}`, replaced by plain
string substitution. There is no template language, and no package to
install: an archive's curator can edit a template knowing only HTML. The
values are HTML already, escaped by the code that makes them. The
replacement is made value after value, so a value that contained the
placeholder of a later one would see it filled too; titles and abstracts
do not contain double braces in practice.

    # in reading and filling the templates:
    def fill(text, values):
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", v)
        return text

Every text from the metadata is escaped, quotes included, since it may
end up in an attribute. A missing value becomes the empty string.

    # in escaping text for HTML:
    def esc(s):
        return html.escape(s or "", quote=True)

Mathematics in titles and abstracts is written in LaTeX between dollar
signs (section 8) and is left as it is: MathJax, loaded by the
templates, typesets it in the reader's browser.

Small pieces
------------

Dates are shown in words (`3 June 2026`), by the function of the core,
which also understands approximate dates; a missing date shows nothing.
Authors are shown by their display names, given name first. A link to a
file of a version goes through the inventory: the logical path is
translated into the content path where OCFL stores the file, which may
lie in the folder of an earlier version. A file the version does not
have gives no link. The PDF of a version is the one its `object.json`
names among the renditions ([document versions](11-versions.md)), and
its address is `None` when there is none.

    # in dates, authors and file links on the website:
    def fmt_date(d):
        return P.fmt_date(d) if d else ""


    def authors(dc):
        return ", ".join(P.display_name(c) for c in dc["creators"])


    def file_link(root, obj_id, inv, ver, logical, label):
        cp = P.content_path(inv, ver, logical)
        return f'<a href="{root}ocfl/{obj_id}/{esc(cp)}">{esc(label)}</a>' if cp else ""


    def pdf_address(root, obj_id, inv, ver, obj):
        lp = P.pdf_of(obj)
        cp = P.content_path(inv, ver, lp) if lp else None
        return f"{root}ocfl/{obj_id}/{cp}" if cp else None

An abstract may have several paragraphs, separated by blank lines in
`datacite.json`; the line breaks inside a paragraph are only those of the
text as it was typed, and are collapsed.

    # in an abstract in HTML:
    def abstract_html(dc):
        for x in dc.get("descriptions", []):
            if x["descriptionType"] == "Abstract":
                return "\n".join(f"<p>{esc(' '.join(p.split()))}</p>" for p in x["description"].split("\n\n"))
        return ""

Writing the website
-------------------

`render` writes everything from the member list of the main collection.
It goes through the members in the collection's order, which is
authoritative (section 10.2): a member of another archive gets an entry
on the home page; a document of this archive gets a landing page and an
entry. Then come the home page, the style sheet and the sitemap, and the
landing pages of documents that are no longer members are removed. The
list `urls` collects the pages for the sitemap, starting with the home
page.

    # in writing the website:
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
            <<write the landing page of a document of this archive>>
            <<the home-page entry of a document of this archive>>
        <<the lead paragraph of the home page>>
        <<write the home page and the style sheet>>
        <<write the sitemap>>
        <<remove the landing pages of former members>>

The PDF of a document is found from its renditions, whatever its name:
deposits by these tools call it `paper.pdf`, but an accepted copy keeps
the name its source gave it.

### The landing page of a document

A landing page is at `paper/<id>/` and presents the document version
pinned by the collection, which for the main collection is the current
version (section 7.3). Two things are read from the head instead, which
may be a later object version (a description-only version, a notice, a
withdrawal): the notices and the status. Notices about any version are
kept in every later object version, and the status belongs to the
object, whatever version is shown. The versions are listed from the last
of the history to the first.

Links in the page are relative to the root of the archive (`../../`), so
that the website also works from a copy on the local disk or at another
address; only the tags for search engines, which must be absolute, use
the base URL.

    # in write the landing page of a document of this archive:
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
    <<the withdrawal notice of a landing page>>
    <<the licence and citation of a landing page>>
    page = fill(page_t, {
        "root": root, "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base),
        "head": meta_tags(obj_id, d, inv, cur, obj, dc),
        "title": esc(dc["titles"][0]["title"]), "authors": esc(authors(dc)),
        "issued": esc(fmt_date(issued)), "abstract": abstract_html(dc),
        "withdrawn": withdrawn, "versions": versions, "licence": licence,
        "pdf": esc(pdf_address(root, obj_id, inv, cur, obj) or f"#v{obj['documentVersion']}"),
        "cite": esc(cite), "pin": m["inventorySha512"], "pin_url": f"{root}ocfl/{obj_id}/{cur}/inventory.json",
    })
    out = root_out / "paper" / obj_id / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    urls.append((f"{base}paper/{obj_id}/", inv["versions"][inv["head"]]["created"][:10]))

A withdrawn document keeps its page, its files and its history (section
11.1); the page shows the withdrawal notice, with its date and reason,
above the abstract. Presentations must show it.

    # in the withdrawal notice of a landing page:
    withdrawn = ""
    if head.get("status") == "withdrawn":
        w = head.get("withdrawal", {})
        withdrawn = (f'<div class="withdrawn"><strong>Withdrawn ({esc(fmt_date(w.get("date")))}):</strong> '
                     f'{esc(w.get("reason", {}).get("text", ""))}</div>')

The licence is named, and linked when it has a URL. The suggested
citation names the archive, the year of first appearance and the
document version, and ends with the DOI when there is one, the landing
page otherwise.

    # in the licence and citation of a landing page:
    rights = (dc.get("rightsList") or [{}])[0]
    licence = esc(rights.get("rights", ""))
    if rights.get("rightsUri"):
        licence = f'<a href="{esc(rights["rightsUri"])}">{licence}</a>'
    cite = f"{authors(dc)}. {dc['titles'][0]['title']}. {P.ARCHIVE['name']}, " \
           f"{(issued or '')[:4]}, version {obj['documentVersion']}. " \
           + (f"https://doi.org/{dc['doi']}" if dc.get("doi") else f"{base}paper/{obj_id}/")

### A version

Every document version gets an item in the list of versions, as
appendix C asks: its number and the labels services gave it, its stage,
its date, its change note, its files, its DOI and the notices about it.
The current version is marked, and has an anchor `#vN` like the others.

    # in a version on a landing page:
    def version_block(obj_id, d, inv, ver, current, notices, root):
        """One version of a document: its number, labels, stage, date, changes,
        files, DOI and the notices about it."""
        obj = P.read_json(d, inv, P.OBJ, ver)
        dc = P.read_json(d, inv, "datacite.json", ver)
        n = obj["documentVersion"]
        <<the heading and date of a version>>
        <<the links of a version>>
        out = [f'<li class="version{" is-current" if ver == current else ""}" id="v{n}">',
               f'<div class="version-head">{head}</div>']
        if when:
            out.append(f'<div class="version-date">{esc(when)}</div>')
        if obj.get("changes", {}).get("text"):
            out.append(f'<div class="changes">{esc(obj["changes"]["text"])}</div>')
        out.append(f'<div class="files">{" · ".join(f for f in files if f)}</div>')
        <<the notices about a version>>
        out.append("</li>")
        return "\n".join(out)

The heading is the document version, with the labels of the records it
was imported from: `Version 3 (arXiv v3)`, or, for an
[accepted copy](22-accepted-copies.md), `Version 1 (OpenSheaf paper v2)`.
The date is the `Available` date, when the version became public; a
version written but never public at the time (an old manuscript
deposited later) shows its `Created` date and says so.

    # in the heading and date of a version:
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

The links are the renditions (PDF), the main source named by its
format, or the reason why the sources are missing, never a rendition
passed off as a source (section 9); then the inventory of the version,
which lists every file with its digest; then the external records and
the DOI.

    # in the links of a version:
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

The notices come from the head, and each is shown under the version it
is about. A notice with a file (a full statement, with mathematics or as
a PDF) links to it, as stored in the head.

    # in the notices about a version:
    for x in notices:
        if x["documentVersion"] == n:
            link = f' {file_link(root, obj_id, inv, inv["head"], x["path"], "statement")}' if x.get("path") else ""
            out.append(f'<div class="notice"><strong>Notice ({esc(fmt_date(x["date"]))}):</strong> '
                       f'{esc(x.get("text", ""))}{link}</div>')

### Tags for search engines

A landing page carries in its head the metadata that services read
(appendix C). Google Scholar reads `citation_*` meta tags, and requires
the title, one tag per author, the date of publication (with slashes)
and the address of the PDF. The date is the first appearance of the
work, `Issued`, or else the date the version became public.

    # in the tags for search engines:
    def meta_tags(obj_id, d, inv, cur, obj, dc):
        """Google Scholar's citation_* tags, schema.org JSON-LD and FAIR Signposting."""
        base = P.ARCHIVE["baseUrl"]
        landing = f"{base}paper/{obj_id}/"
        pdf = pdf_address(base, obj_id, inv, cur, obj)
        date = P.date_of(dc, "Issued") or P.date_of(dc, "Available") or P.date_of(dc, "Created") or ""
        <<the citation tags of Google Scholar>>
        abstract = next((x["description"] for x in dc.get("descriptions", [])
                         if x["descriptionType"] == "Abstract"), "")
        if abstract:
            tags.append(f'<meta name="description" content="{esc(" ".join(abstract.split())[:300])}">')
        <<the Signposting links of a landing page>>
        <<the schema.org record of a landing page>>
        return "\n".join(tags)

The PDF is the one of this archive, on the same host as the page, as
Google Scholar requires. A version without a PDF gets no tag for it, here
and in the links and the record below.

    # in the citation tags of Google Scholar:
    tags = [f'<meta name="citation_title" content="{esc(dc["titles"][0]["title"])}">']
    tags += [f'<meta name="citation_author" content="{esc(c["name"])}">' for c in dc["creators"]]
    if date:
        tags.append(f'<meta name="citation_publication_date" content="{esc(date.replace("-", "/"))}">')
    if pdf:
        tags.append(f'<meta name="citation_pdf_url" content="{esc(pdf)}">')
    if dc.get("doi"):
        tags.append(f'<meta name="citation_doi" content="{esc(dc["doi"])}">')

[FAIR Signposting](https://signposting.org/FAIR/) links tell a program,
from the landing page alone, how to cite the document (`cite-as`: the
DOI, or the page), where its metadata are (`describedby`: the
`datacite.json` of the version), where the content is (`item`) and
under what licence. `canonical` gives search engines the one address of
the page.

    # in the Signposting links of a landing page:
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

The schema.org `ScholarlyArticle` record, in JSON-LD, says the same for
general search engines. It is written into a `<script>` element, where
the sequence `</` would end the element early: it is escaped as `<\/`,
which JSON reads as the same string.

    # in the schema.org record of a landing page:
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

### The home page

Each document of this archive has an entry on the home page: its title,
linked to its landing page, its authors, its year and version, a link
to the PDF, and its pin. The pin is shown on purpose: the home page is
the presentation of a collection version, and the beginning of each
member's digest lets a reader compare it with `members.json`. The
verification of the archive (in the chapters on the core) checks that
the home page shows the pin of every member. The abstract is folded in a
`<details>` element, so that the list stays short.

    # in the home-page entry of a document of this archive:
    pdf = pdf_address("", obj_id, inv, cur, obj)
    abstract = abstract_html(dc)
    entries.append("\n".join([
        f'<li class="paper{" withdrawn" if withdrawn else ""}">',
        f'<a class="paper-title" href="paper/{obj_id}/">{esc(dc["titles"][0]["title"])}</a>',
        f'<div class="paper-authors">{esc(authors(dc))}</div>',
        f'<div class="paper-meta">{esc((issued or "")[:4])} · version {obj["documentVersion"]}'
        + (f' · <a href="{esc(pdf)}">PDF</a>' if pdf else "")
        + f' · <span class="pin" title="{m["inventorySha512"]}">'
        f'pin {m["inventorySha512"][:32]}…</span></div>',
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"]))

The lead paragraph of the home page says what the archive is. An
archive of one's own documents gets a fixed text; a curated collection
(order `manual`) gets its description, and a sentence saying that its
members are kept in their own archives.

    # in the lead paragraph of the home page:
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

The home page is at the root of the archive, next to `opensheaf.json`,
so its links need no prefix. The empty file `.nojekyll` tells GitHub
Pages to serve the files as they are, without passing them through
Jekyll.

    # in write the home page and the style sheet:
    index = fill(template("index.html"), {
        "root": "", "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base), "lead": lead,
        "papers": "\n".join(entries) if entries else '<li class="empty">No documents yet.</li>',
        "count": str(len(entries)), "updated": esc(fmt_date(datetime.date.today().isoformat())),
    })
    (root_out / "index.html").write_text(index, encoding="utf-8")
    shutil.copyfile(template_path("style.css"), root_out / "style.css")
    (root_out / ".nojekyll").touch()

### The sitemap and the removed pages

The sitemap lists the home page and the landing pages, each with the
date of the last object version of its document, so that a harvester
revisits only what changed.

    # in write the sitemap:
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, last in urls:
        sm.append(f"  <url><loc>{esc(url)}</loc>" + (f"<lastmod>{last}</lastmod>" if last else "") + "</url>")
    sm.append("</urlset>")
    (root_out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")

A document that left the collection loses its landing page, which is
generated output like the rest; the document itself stays in the
storage root.

    # in remove the landing pages of former members:
    # remove landing pages of documents no longer in the collection
    for p in (root_out / "paper").glob("*") if (root_out / "paper").exists() else []:
        if p.name not in {m["id"] for m in members if m.get("archive") == P.ARCHIVE["archiveId"]}:
            shutil.rmtree(p)

Members of other archives
-------------------------

A member of another archive appears on the home page with what can be
learnt about it, from the best source at hand. The specification forbids
embedding other archives' HTML (appendix C, "Separation"): only their
metadata are read, and the entry is written here. The starting point is
the citation cached in the collection, which needs no network. If this
archive holds a mirror of the member, its copy gives the title, the
authors, the abstract and a PDF served from here. The member's archive,
if it answers, gives its name, a link to its landing page and, when
there is no mirror, the title, authors, abstract and PDF. If it does not
answer, the entry says so, and shows the copy or the cached citation.

    # in a member of another archive on the home page:
    def remote_entry(m):
        """The home-page entry of a member of another archive: its metadata read
        from that archive, or else the cached citation."""
        from . import collections
        cite = m.get("cite", {})
        title, by, year = cite.get("title", m["id"]), ", ".join(cite.get("creators", [])), cite.get("year", "")
        links, abstract, archive_name = [], "", m.get("archiveUrl", "")
        here = P.ARCHIVE["baseUrl"] in m.get("mirrors", []) and (P.OCFL / m["id"]).exists()
        if here:
            <<read a mirrored member from the copy in this archive>>
        try:
            <<read a member from its own archive>>
        except Exception:  # noqa: BLE001 - the copy or the cached citation is shown
            links.append('<span class="missing">'
                         + ("its archive is unavailable" if here else "archive unavailable: cached citation")
                         + "</span>")
        <<the home-page entry of a member of another archive>>

The mirror is read at the pinned version. The code assumes that the
mirror holds it: after `osheaf collection update` has moved a member to
a version not yet mirrored, `osheaf mirror` must be run again before the
pages are written.

    # in read a mirrored member from the copy in this archive:
    # a mirror in this archive: its copy is read and linked locally
    inv = P.load_inventory(P.OCFL / m["id"])
    dc = P.read_json(P.OCFL / m["id"], inv, "datacite.json", m["version"])
    title, by, abstract = dc["titles"][0]["title"], authors(dc), abstract_html(dc)
    pdf = pdf_address("", m["id"], inv, m["version"], P.read_json(P.OCFL / m["id"], inv, P.OBJ, m["version"]))
    if pdf:
        links.append(f'<a href="{esc(pdf)}">PDF (mirrored here)</a>')

The member's archive is read with the `Remote` of the collections
module, at the pinned version. Any failure, from the network to a
missing file, falls back on what is already known.

    # in read a member from its own archive:
    r = collections.Remote(m["archiveUrl"])
    archive_name = r.disc.get("name", archive_name)
    rinv = r.inventory(m["id"])
    rdc = json.loads(r.file(m["id"], rinv, m["version"], "datacite.json"))
    if not here:
        title, by, abstract = rdc["titles"][0]["title"], authors(rdc), abstract_html(rdc)
        lp = P.pdf_of(json.loads(r.file(m["id"], rinv, m["version"], P.OBJ)))
        cp = P.content_path(rinv, m["version"], lp) if lp else None
        if cp:
            links.append(f'<a href="{esc(r.root + m["id"] + "/" + cp)}">PDF</a>')
    if rdc.get("url"):
        links.insert(0, f'<a href="{esc(rdc["url"])}">landing page</a>')

The entry has the same form as that of a document of this archive, with
the archive named and linked, and the pin; the title is not a link,
since the landing page, if any, is in the other archive.

    # in the home-page entry of a member of another archive:
    return "\n".join([
        '<li class="paper member">',
        f'<span class="paper-title">{esc(title)}</span>',
        f'<div class="paper-authors">{esc(by)}</div>',
        f'<div class="paper-meta">{esc(str(year))} · in <a href="{esc(m["archiveUrl"])}">{esc(archive_name)}</a>'
        + (" · " + " · ".join(links) if links else "")
        + f' · <span class="pin" title="{m["inventorySha512"]}">pin {m["inventorySha512"][:32]}…</span></div>',
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])

The specification now also has selections, whose members pin revisions
rather than an object version (section 10.2); the website, like the
rest of these tools, knows only members with a single pinned version.
