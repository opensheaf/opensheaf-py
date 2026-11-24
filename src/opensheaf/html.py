# Generated from literate/30-website.md by opensheaf-literate: edit the document, not this file.
"""The website of an archive in plain HTML (the website profile, appendix A.3 of the
specification 0.2): a home page presenting the latest signed version of the main
catalogue, one landing page per line held here at paper/<label>/ (its full sheaf: URI,
its owner, its current version, every signed document version in the order of the
history with its status, notices, files, pins and DOI, the withdrawal if any, and the
metadata read by Google Scholar and other services), a page per owner at owner/<owner>/
(a summary of its key log), and a sitemap.

Pages are made from templates with {{name}} placeholders: templates/index.html,
templates/paper.html, templates/collection.html, templates/owner.html and
templates/style.css of the archive (osheaf.json: index.html.templates or
index.templates, else the folder templates/ if there is one), or the package's
defaults. Mathematics in titles and abstracts ($...$) is left to MathJax, loaded by
the templates. With a TeXmacs index the home page is TeXmacs', and only the landing
pages, the owner pages and the sitemap are written here.
"""

import datetime
import html
import json
import re
import shutil
from pathlib import Path

from . import core as P, names, owners, remote, sign

DEFAULTS = Path(__file__).resolve().parent / "templates"


def esc(s):
    return html.escape(s if isinstance(s, str) else str(s) if s else "", quote=True)


def safe_url(u):
    """U if it is an http or https URL, which a page may link to; else ""."""
    return u if isinstance(u, str) and u.lower().startswith(("https://", "http://")) else ""


def link(u, label, cls=""):
    """LABEL (HTML, escaped already) linked to the URL U if it is safe_url, else LABEL alone."""
    u = safe_url(u)
    attr = f' class="{cls}"' if cls else ""
    if u:
        return f'<a{attr} href="{esc(u)}">{label}</a>'
    return f'<span{attr}>{label}</span>' if cls else label


PIN = re.compile(r"[0-9a-f]{128}\Z")
OBJECT_VERSION = re.compile(r"v[1-9][0-9]*\Z")
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def number(n):
    """The document version N as text if it is a positive integer, else "?"."""
    return str(n) if isinstance(n, int) and not isinstance(n, bool) and n > 0 else "?"


def pin_html(pin):
    """The pin PIN shown by its beginning, the whole as its title; a note if it is not a pin."""
    if isinstance(pin, str) and PIN.match(pin):
        return f'<span class="pin" title="{pin}">pin {pin[:32]}…</span>'
    return '<span class="contested">no valid pin</span>'


def pins_ok(m, line=None):
    """Whether every pin of member M is a digest and an object version (of LINE, if given)."""
    try:
        pins = P.member_pins(m)
        return bool(pins) and all(
            isinstance(v, str) and OBJECT_VERSION.match(v) and isinstance(d, str) and PIN.match(d)
            and (line is None or v in line.inv["versions"]) for v, d, _ in pins)
    except (TypeError, AttributeError, KeyError):
        return False


def template(name):
    return template_path(name).read_text(encoding="utf-8")


PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")


def fill(text, values):
    return PLACEHOLDER.sub(lambda mo: values.get(mo.group(1), mo.group(0)), text)


def fmt_date(d):
    return P.fmt_date(d) if d else ""


def authors(dc):
    return P.authors_of(dc)


def file_url(root, line, ver, logical):
    cp = P.content_path(line.inv, ver, logical) if logical else None
    return f"{root}ocfl/{P.path_of(line.id)}/{cp}" if cp else None


def file_link(root, line, ver, logical, label):
    u = file_url(root, line, ver, logical)
    return f'<a href="{esc(u)}">{esc(label)}</a>' if u else ""


def pdf_address(root, line, ver, obj):
    return file_url(root, line, ver, P.pdf_of(obj))


def withdrawal_html(state, where=""):
    if state.get("status") != "withdrawn":
        return ""
    w = state.get("withdrawal", {})
    return (f'<div class="withdrawn"><strong>Withdrawn{where} ({esc(fmt_date(w.get("date")))}):</strong> '
            f'{esc(w.get("reason", {}).get("text", ""))}</div>')


def owner_tag(owner, root=""):
    """The owner OWNER, named by the label of its key log or its short name, linked to its page."""
    name = esc(P.label_of(names.object_id(owner, owner)) or names.short(owner))
    return f'<a class="owner" href="{root}owner/{owner}/">{name}</a>' if P.key_log(owner) else name


def versions_line(m, obj):
    """'version 3', or for a member of a selection 'vetted: versions 2, 3'."""
    if m.get("revisions"):
        ns = [number(r.get("documentVersion")) for r in m["revisions"]]
        return f"vetted: version{'s' if len(ns) > 1 else ''} {', '.join(ns)}"
    return f"version {number(obj.get('documentVersion'))}"


LINES = {}


class Line:
    """A line held in the storage root, as the pages present it."""

    def __init__(self, obj_id):
        self.id = obj_id
        _, self.name, self.owner = obj_id.split(":")
        self.dir = P.obj_dir(obj_id)
        self.inv = P.load_inventory(self.dir)
        self.slug = P.page_address(obj_id)
        self.home = P.name_address(obj_id)
        g = P.read_logical(self.dir, self.inv, P.GENESIS, "v1")
        try:
            self.originator = names.read_genesis(g.read_bytes()).get("originator") if g else None
        except ValueError:
            self.originator = None
        self.log = P.key_log(self.owner)
        self.statuses = P.line_statuses(self.dir, self.inv, self.log)[1]
        n = sign.latest_signed(self.statuses)
        self.signed = f"v{n}" if n else None
        self.state = self.json(P.OBJ, self.signed)

    def json(self, logical, ver=None):
        return P.read_json(self.dir, self.inv, logical, ver)

    def status(self, ver):
        return self.statuses[int(ver[1:]) - 1]

    def digest(self, ver):
        return P.digest(self.dir / ver / "inventory.json")

    @property
    def withdrawn(self):
        return self.state.get("status") == "withdrawn"


def removed(m):
    """Whether the line of member M was taken down here: it has a tombstone (section 13.3)."""
    return any(t.get("id") == f"sheaf:{m.get('name')}:{m.get('owner')}" for t in P.TOMBSTONES)


def held(m):
    """The Line of member M if its line is held in this archive, else None."""
    try:
        obj_id = names.object_id(m["name"], m["owner"])
        if not (P.obj_dir(obj_id) / "inventory.json").is_file():
            return None
    except (KeyError, ValueError):
        return None
    if obj_id not in LINES:
        LINES[obj_id] = Line(obj_id)
    return LINES[obj_id]


def full_uri(line):
    return names.SheafURI(line.name, line.owner).canonical(line.originator)


def short_uri(line):
    return f"sheaf:{line.name[:16]}" + ("" if line.owner == line.originator else f":{line.owner[:16]}")


def pin_uri(line, ver):
    n = line.json(P.OBJ, ver)["documentVersion"]
    return f"{full_uri(line)}/v{n}?sha512={line.digest(ver)}"


def version_block(line, ver, shown, notices, root, vetted=None):
    """One version of a line: its number, labels, stage, status, date, changes, files,
    DOI, pin and the notices about it."""
    obj = line.json(P.OBJ, ver)
    dc = line.json("datacite.json", ver)
    n = obj["documentVersion"]
    labels = [f"{e['service']} {e['label']}" for e in obj.get("external", [])
              if e.get("role") == "source" and e.get("label")]
    vs = list(line.inv["versions"])
    first = next(v for v in vs if line.json(P.OBJ, v).get("documentVersion") == n)
    par = line.json(P.OBJ, first).get("parent")
    if par and (vs.index(first) == 0 or line.json(P.OBJ, vs[vs.index(first) - 1]).get("parent") != par):
        labels.insert(0, f"the parent's version {par.get('documentVersion')}")
    head = f"Version {number(n)}" + (f" ({esc(', '.join(labels))})" if labels else "")
    if obj.get("stage"):
        head += f' <span class="stage">{esc(obj["stage"]["value"])}</span>'
    if vetted is not None and n in vetted:
        head += ' <span class="current">vetted</span>'
    elif vetted is None and n == shown:
        head += ' <span class="current">current</span>'
    status = line.status(ver)
    if status == sign.VOUCHED:
        head += ' <span class="stage">vouched for</span>'
    elif status != sign.SIGNED:
        head += f' <span class="contested">{esc(status)}</span>'
    when = ""
    if P.date_of(dc, "Available"):
        when = fmt_date(P.date_of(dc, "Available"))
    elif P.date_of(dc, "Created"):
        when = f"written {fmt_date(P.date_of(dc, 'Created'))}, not public at the time"
    files = [file_link(root, line, ver, r["path"], "PDF") for r in obj.get("renditions", [])]
    if obj.get("mainSource"):
        kind = {"application/x-tex": "LaTeX source", "application/x-texmacs": "TeXmacs source"} \
            .get(obj.get("sourceFormat"), "source")
        files.append(file_link(root, line, ver, obj["mainSource"], kind))
    elif obj.get("sourcesMissing"):
        files.append(f'<span class="missing">sources not available: '
                     f'{esc(obj["sourcesMissing"].get("text", ""))}</span>')
    files.append(f'<a href="{root}ocfl/{P.path_of(line.id)}/{ver}/inventory.json">files and digests</a>')
    arxiv = P.arxiv_id(obj, dc)
    for e in obj.get("external", []):
        if e.get("record"):
            label = f"arXiv:{arxiv}" if e.get("service") == "arXiv" and arxiv else e["service"]
            files.append(link(e["record"], esc(label)))
    if arxiv and not any(e.get("service") == "arXiv" for e in obj.get("external", [])):
        files.append(f'<a href="https://arxiv.org/abs/{esc(arxiv)}">arXiv:{esc(arxiv)}</a>')
    if dc.get("doi"):
        files.append(f'<a href="https://doi.org/{esc(dc["doi"])}">doi:{esc(dc["doi"])}</a>')
    out = [f'<li class="version{" is-current" if n == shown else ""}" id="v{number(n)}">',
           f'<div class="version-head">{head}</div>']
    if when:
        out.append(f'<div class="version-date">{esc(when)}</div>')
    withdrawn = P.withdrawn_versions(line.dir, line.inv, line.signed or line.inv["head"])
    if n in withdrawn:
        out.append(withdrawal_html(line.json(P.OBJ, withdrawn[n])))
    if P.changes_note(obj):
        out.append(f'<div class="changes">{esc(P.changes_note(obj))}</div>')
    out.append(f'<div class="files">{" · ".join(f for f in files if f)}</div>')
    uri = pin_uri(line, ver)
    out.append(f'<div class="pin" title="{esc(uri)}">{ver} · pin <code class="copy" data-copy="{esc(uri)}">'
               f'{line.digest(ver)[:32]}…</code> (<a href="{root}ocfl/{P.path_of(line.id)}/'
               f'{ver}/inventory.json">inventory</a>)</div>')
    replaced = {x.get("replaces") for x in notices}
    for k, x in enumerate(notices, 1):
        if x["documentVersion"] == n and k not in replaced:
            src = line.signed or line.inv["head"]
            statement = f' {file_link(root, line, src, x["path"], "statement")}' if x.get("path") else ""
            repl = f', replacing notice {x["replaces"]}' if x.get("replaces") else ""
            out.append(f'<div class="notice"><strong>Notice {k} ({esc(fmt_date(x["date"]))}{repl}):</strong> '
                       f'{esc(x.get("text", ""))}{statement}</div>')
    out.append("</li>")
    return "\n".join(out)


def meta_tags(line, cur, obj, dc):
    """Google Scholar's citation_* tags, schema.org JSON-LD and FAIR Signposting."""
    base = P.ARCHIVE["baseUrl"]
    landing = f"{base}paper/{line.slug}/"
    pdf = pdf_address(base, line, cur, obj)
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
    def rel(r, href, media=None):
        return f'<link rel="{r}" href="{esc(href)}"' + (f' type="{esc(media)}"' if media else "") + ">"
    cite = f"https://doi.org/{dc['doi']}" if dc.get("doi") else landing
    kind = schema_type(obj, dc)
    tags += [rel("canonical", landing), rel("cite-as", cite),
             rel("describedby", file_url(base, line, cur, "datacite.json"), "application/vnd.datacite.datacite+json")]
    for path, media in content_items(obj):
        u = file_url(base, line, cur, path)
        if u:
            tags.append(rel("item", u, media))
    tags += [rel("license", u) for u in licence_urls(dc)]
    tags.append(rel("type", f"https://schema.org/{kind}"))
    tags += [rel("author", o) for o in (orcid_of(c) for c in dc["creators"]) if o]
    ld = {"@context": "https://schema.org", "@type": kind,
          "name": dc["titles"][0]["title"], "url": landing,
          "author": [person_ld(c) for c in dc["creators"]],
          "datePublished": date, "version": dc["version"],
          "identifier": [full_uri(line)] + [f"https://doi.org/{d}" for d in
                                            [dc.get("doi"), concept_doi(dc)] if d]}
    encodings = [{"@type": "MediaObject", "contentUrl": u, "encodingFormat": media}
                 for u, media in ((file_url(base, line, cur, r["path"]), r.get("mediaType"))
                                  for r in obj.get("renditions", [])) if u]
    if encodings:
        ld["encoding"] = encodings
    licences = licence_urls(dc) + [r["rights"] for r in dc.get("rightsList", [])
                                   if r.get("rights") and not (r.get("rightsUri") or r.get("rightsIdentifier"))]
    if licences:
        ld["license"] = licences[0] if len(licences) == 1 else licences
    same = same_as(dc)
    if same:
        ld["sameAs"] = same
    if abstract:
        ld["abstract"] = abstract
    keywords = [x["subject"] for x in dc.get("subjects", []) if x.get("subject")]
    if keywords:
        ld["keywords"] = keywords
    if obj.get("kind") == "collection":
        ld["hasPart"] = collection_parts(line, cur)
    if obj.get("status") == "withdrawn":
        ld["creativeWorkStatus"] = "Withdrawn"
    tags.append('<script type="application/ld+json">' + json_in_script(ld) + "</script>")
    return "\n".join(tags)


def json_in_script(data):
    """DATA as JSON to write inside a <script> element: no <, > or & is left for HTML to read."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def content_items(obj):
    """(logical path, media type) of the renditions and the main source of OBJ."""
    out = [(r["path"], r.get("mediaType")) for r in obj.get("renditions", [])]
    if obj.get("mainSource"):
        out.append((obj["mainSource"], obj.get("sourceFormat")))
    elif obj.get("kind") == "collection":
        out.append(("members.json", "application/json"))
    return list(dict.fromkeys(out))


def licence_urls(dc):
    """The URLs of the licences of DC's rightsList (section 4.4)."""
    out = []
    for r in dc.get("rightsList", []):
        if safe_url(r.get("rightsUri")):
            out.append(r["rightsUri"])
        elif r.get("rightsIdentifier"):
            out.append(f"https://spdx.org/licenses/{r['rightsIdentifier']}.html")
    return out


def orcid_of(creator):
    """The ORCID iD of CREATOR as https://orcid.org/..., if datacite.json gives one."""
    for x in creator.get("nameIdentifiers", []):
        if (x.get("nameIdentifierScheme") or "").upper() == "ORCID" and x.get("nameIdentifier"):
            iD = x["nameIdentifier"].rsplit("/", 1)[-1]
            return f"https://orcid.org/{iD}"
    return None


SCHEMA_TYPES = {"Collection": "Collection", "Dataset": "Dataset", "Software": "SoftwareSourceCode",
                "Book": "Book", "BookChapter": "Chapter", "Audiovisual": "MediaObject",
                "Image": "ImageObject", "Text": "ScholarlyArticle", "Preprint": "ScholarlyArticle",
                "JournalArticle": "ScholarlyArticle", "ConferencePaper": "ScholarlyArticle",
                "Report": "Report", "Dissertation": "Thesis", "Presentation": "PresentationDigitalDocument"}


def schema_type(obj, dc):
    if obj.get("kind") == "collection":
        return "Collection"
    return SCHEMA_TYPES.get(dc.get("types", {}).get("resourceTypeGeneral"), "CreativeWork")


def person_ld(c):
    p = {"@type": "Person" if c.get("nameType", "Personal") == "Personal" else "Organization",
         "name": P.display_name(c)}
    if orcid_of(c):
        p["@id"] = orcid_of(c)
    return p


def concept_doi(dc):
    return next((r["relatedIdentifier"] for r in dc.get("relatedIdentifiers", [])
                 if r.get("relationType") == "IsVersionOf" and r.get("relatedIdentifierType") == "DOI"), None)


def same_as(dc):
    """The URLs of the same work elsewhere: the IsIdenticalTo relations of DC."""
    out = []
    for r in dc.get("relatedIdentifiers", []):
        if r.get("relationType") != "IsIdenticalTo":
            continue
        ident, kind = r.get("relatedIdentifier", ""), r.get("relatedIdentifierType")
        url = {"DOI": f"https://doi.org/{ident}", "arXiv": f"https://arxiv.org/abs/{ident.removeprefix('arXiv:')}",
               "URL": ident}.get(kind)
        if safe_url(url):
            out.append(url)
    return out


def collection_parts(line, ver):
    """The members of the collection LINE in VER: their landing pages here, or else their DOIs."""
    base = P.ARCHIVE["baseUrl"]
    out = []
    for m in (line.json("members.json", ver) or {}).get("members", []):
        h = held(m)
        if h:
            out.append({"@id": f"{base}paper/{h.slug}/"})
        elif m.get("doi"):
            out.append({"@id": f"https://doi.org/{m['doi']}"})
    return out


def abstract_html(dc):
    for x in dc.get("descriptions", []):
        if x["descriptionType"] == "Abstract":
            return "\n".join(f"<p>{esc(' '.join(p.split()))}</p>" for p in x["description"].split("\n\n"))
    return ""


def render(members, home=True, featured=None, keeper_fetch=None, groups=None):
    """Write index.html, paper/<label>/index.html for every line presented, owner/<owner>/,
    style.css and sitemap.xml; with home=False (a TeXmacs index is the home page),
    everything but index.html. FEATURED: the identifier of a collection of the archive
    whose members the home page lists first. KEEPER_FETCH: how the places of keepers are
    read (owners.fetch_json by default). GROUPS: [(owner, members)], the members by owner
    catalogue, for an archive with several owners."""
    global KEEPER_FETCH
    P.refuse_unread_pages()
    LINES.clear()
    KEEPERS.clear()
    KEEPER_FETCH = keeper_fetch
    members = [m for m in members if not removed(m)]
    root_out = P.ROOT
    base = P.ARCHIVE["baseUrl"]
    urls, written, seen_owners = [(base, None)], [], []
    page_t = template("paper.html")
    fmembers = []
    if featured:
        fline = held({"name": featured.split(":")[1], "owner": featured.split(":")[2]})
        fmembers = (fline.json("members.json", fline.signed) or {}).get("members", [])
    pages, followed = {}, set()

    def walk(queue):
        while queue:
            qm = queue.pop(0)
            line = held(qm)
            if line is None or not pins_ok(qm, line):
                continue
            if line.id not in pages:
                pages[line.id] = qm
            if qm.get("kind") == "collection" and line.id not in followed:
                followed.add(line.id)
                ver = P.presented_version(qm, line.dir, line.inv)
                queue += (line.json("members.json", ver) or {}).get("members", [])

    fmembers = [m for m in fmembers if not removed(m)]
    walk(list(members) + list(fmembers))
    for label, obj_id in sorted(P.LABELS.items()):
        _, nm, owner = obj_id.split(":")
        line = held({"name": nm, "owner": owner})
        if obj_id not in pages and line and line.signed and line.state.get("kind") in ("document", "collection"):
            walk([{"kind": line.state["kind"], "name": nm, "owner": owner, "version": line.signed,
                   "inventorySha512": line.digest(line.signed)}])
    for obj_id, m in pages.items():
        line = LINES[obj_id]
        cur = P.presented_version(m, line.dir, line.inv)
        pin_ver, pin = P.member_pins(m)[-1][:2]
        ref = line.signed or pin_ver
        vetted = {r["documentVersion"] for r in m["revisions"]} if m.get("revisions") else None
        obj = line.json(P.OBJ, cur)
        dc = line.json("datacite.json", cur)
        notices = line.state.get("notices", [])
        root = "../../"
        versions = "\n".join(version_block(line, v, obj["documentVersion"], notices, root, vetted)
                             for v in reversed(P.history_of(line.dir, line.inv, ref)))
        issued = P.date_of(dc, "Issued")
        withdrawn = withdrawal_html(line.state)
        contested = ""
        if line.status(cur) == sign.CONTESTED or line.status(pin_ver) == sign.CONTESTED:
            contested = ('<div class="contested"><strong>Contested:</strong> this version is signed only with '
                         'keys its owner has since exposed (sections 6.3 and 7.3 of the specification); '
                         'what it holds may not be the owner\'s.</div>')
        rights = (dc.get("rightsList") or [{}])[0]
        licence = esc(rights.get("rights", ""))
        if rights.get("rightsUri"):
            licence = link(rights["rightsUri"], licence)
        cite_url = f"https://doi.org/{dc['doi']}" if dc.get("doi") else f"{base}paper/{line.slug}/"
        cite = esc(f"{authors(dc)}. {dc['titles'][0]['title']}. {P.ARCHIVE['name']}, "
                   f"{(issued or '')[:4]}, version {obj['documentVersion']}.") \
            + f' <code class="copy">{esc(pin_uri(line, cur))}</code>.' \
            + f' <a href="{esc(cite_url)}">{esc(cite_url)}</a>'
        html_link = ""
        if (P.SITE / line.slug / f"{line.slug}.html").exists():
            html_link = f' · <a href="{root}site/{line.slug}/{line.slug}.html">HTML</a>'
        common = {
            "root": root, "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base),
            "head": meta_tags(line, cur, obj, dc), "title": esc(dc["titles"][0]["title"]),
            "issued": esc(fmt_date(issued)), "withdrawn": withdrawn, "contested": contested,
            "versions": versions, "licence": licence, "cite": cite,
            "pin": esc(pin), "pin_url": f"{root}ocfl/{P.path_of(line.id)}/{pin_ver}/inventory.json",
            "sheaf_uri": esc(full_uri(line)), "sheaf_short": esc(short_uri(line)),
            "owner": owner_html(line.owner, root),
        }
        if line.owner not in seen_owners:
            seen_owners.append(line.owner)
        if obj.get("kind") == "collection":
            cmembers = line.json("members.json", cur) or {}
            kind = {"selection": "A selection", "catalogue": "A catalogue"}.get(cmembers.get("type"), "A collection")
            items = [local_entry(cm, root) if held(cm) else remote_entry(cm, root)
                     for cm in cmembers.get("members", []) if not removed(cm)]
            count = len(items)
            page = fill(template("collection.html"), dict(common, **{
                "kind": f"{kind} curated by {esc(authors(dc))}",
                "count": f"{count} member{'s' if count != 1 else ''}",
                "description": abstract_html(dc),
                "members": "\n".join(items) if items else '<li class="empty">No members yet.</li>'}))
        else:
            page = fill(page_t, dict(common, **{
                "authors": esc(authors(dc)), "abstract": abstract_html(dc),
                "pdf": esc(pdf_address(root, line, cur, obj) or f"#v{number(obj['documentVersion'])}"),
                "html_link": html_link}))
        for address in dict.fromkeys([line.home, line.slug]):
            out = root_out / "paper" / address / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page, encoding="utf-8")
            written.append(address)
        lastmod = str(line.inv["versions"][line.inv["head"]].get("created", ""))[:10]
        lastmod = lastmod if DAY.match(lastmod) else None
        urls.append((f"{base}paper/{line.slug}/", lastmod))
        if html_link:
            urls.append((f"{base}site/{line.slug}/{line.slug}.html", lastmod))
    if home:
        groups_here = [(o, [m for m in ms if not removed(m)]) for o, ms in (groups or [])]
        several = len(groups_here) > 1
        by_owner = several and P.INDEX.get("owners", "together") == "by-owner"
        entry = lambda m: (local_entry(m, show_owner=several and not by_owner) if held(m)
                           else remote_entry(m, show_owner=several and not by_owner))
        empty = '<li class="empty">No documents yet.</li>'
        papers_heading = ""
        if by_owner:
            entries, blocks = [], []
            for owner, ms in groups_here:
                items = [entry(m) for m in ms]
                entries += items
                blocks.append((f'<h2 class="owner-heading">{owner_tag(owner)}</h2>', "\n".join(items) or empty))
            papers_heading = blocks[0][0]
            papers_html = blocks[0][1] + "".join(f'\n  </ol>\n{h}\n  <ol class="papers">\n{body}'
                                                 for h, body in blocks[1:])
        else:
            entries = [entry(m) for m in (P.member_order(members) if several else members)]
            papers_html = "\n".join(entries) or empty
        featured_html = ""
        if featured:
            fdc = fline.json("datacite.json", fline.signed)
            items = [local_entry(fm) if held(fm) else remote_entry(fm) for fm in fmembers]
            featured_html = ('<section class="featured">\n'
                             f'<h2>{esc(fdc["titles"][0]["title"])}</h2>\n<ol class="papers">\n'
                             + ("\n".join(items) if items else '<li class="empty">No members yet.</li>')
                             + "\n</ol>\n</section>")
        lead = ('Papers with their sources, every version, fixed by digests and signed by their owners. An '
                '<a href="https://opensheaf.org">OpenSheaf</a> archive: programs start from '
                '<a href="opensheaf.json">opensheaf.json</a>.')
        cats = [P.CATALOGUES[o] for o in P.archive_owners() if o in P.CATALOGUES]
        main_id = cats[0] if len(cats) == 1 else None
        cline = fline if featured else (LINES.get(main_id) or (held({"name": main_id.split(":")[1],
                                                                     "owner": main_id.split(":")[2]})
                                                               if main_id else None))
        cmem = (cline.json("members.json", cline.signed) or {}) if cline else {}
        if featured or cmem.get("order") == "manual":
            cdc = cline.json("datacite.json", cline.signed)
            desc = next((x["description"] for x in cdc.get("descriptions", [])), "")
            lead = (esc(desc) + ' A collection in the <a href="https://opensheaf.org">OpenSheaf</a> format: each '
                    'member is kept in its own archive and pinned by a digest'
                    + (', in the versions its curator vetted' if cmem.get("type") == "selection" else '')
                    + '; programs start from <a href="opensheaf.json">opensheaf.json</a>.')
        index = fill(template("index.html"), {
            "root": "", "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base), "lead": lead,
            "papers": papers_html,
            "featured": featured_html,
            "papers_heading": papers_heading or ("<h2>In this archive</h2>" if featured else ""),
            "count": str(len(entries)), "updated": esc(fmt_date(datetime.date.today().isoformat())),
        })
        (root_out / "index.html").write_text(index, encoding="utf-8")
        shutil.copyfile(template_path("style.css"), root_out / "style.css")
        (root_out / ".nojekyll").touch()
    elif "style.css" in page_t:
        shutil.copyfile(template_path("style.css"), root_out / "style.css")
    owner_pages = []
    for owner in seen_owners:
        if P.key_log(owner) is None:
            continue
        lines = [LINES[i] for i in pages if LINES[i].owner == owner]
        out = root_out / "owner" / owner / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(owner_page(owner, lines), encoding="utf-8")
        owner_pages.append(owner)
        urls.append((f"{base}owner/{owner}/", None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, last in urls:
        sm.append(f"  <url><loc>{esc(url)}</loc>" + (f"<lastmod>{last}</lastmod>" if last else "") + "</url>")
    sm.append("</urlset>")
    (root_out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")
    moved = []
    for address, obj_id in sorted((P.ARCHIVE.get("formerAddresses") or {}).items()):
        if address in written or obj_id not in pages or not P.LABEL_RE.match(address):
            continue
        slug = LINES[obj_id].slug
        out = root_out / "paper" / address / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(redirect_page(f"../{slug}/", f"{base}paper/{slug}/"), encoding="utf-8")
        moved.append(address)
    for folder, keep in (("paper", set(written) | set(moved)), ("owner", set(owner_pages))):
        for p in (root_out / folder).glob("*") if (root_out / folder).exists() else []:
            if p.is_dir() and p.name not in keep:
                shutil.rmtree(p)
    return len(written)


def redirect_page(href, canonical):
    """A page sending its reader to HREF (relative), whose address is now CANONICAL."""
    return (f"<!DOCTYPE html>\n{P.REDIRECT_MARK}\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>Moved</title>\n<link rel=\"canonical\" href=\"{esc(canonical)}\">\n"
            f"<meta name=\"robots\" content=\"noindex\">\n"
            f"<meta http-equiv=\"refresh\" content=\"0; url={esc(href)}\">\n</head>\n"
            f"<body><p>This page has moved to <a href=\"{esc(href)}\">{esc(canonical)}</a>.</p></body>\n</html>\n")


def template_path(name):
    d = P.INDEX.get("html", {}).get("templates") or P.INDEX.get("templates") or "templates"
    p = P.ROOT / d / name
    return p if p.exists() else DEFAULTS / name


def remote_entry(m, root="", show_owner=False):
    """The entry of a member held elsewhere: its metadata read from the first of its at
    that answers, checked against the pin, or else the cached citation."""
    cite = m.get("cite", {})
    title, by, year = cite.get("title") or m["name"], P.names_joined(cite.get("creators", [])), \
        cite.get("year", "")
    pin = P.member_pins(m)[-1][1] if pins_ok(m) else None
    links, abstract, landing, withdrawn = [], "", "", ""
    at = (m.get("at") or [""])[0]
    at = archive_name = at if isinstance(at, str) else ""
    view = remote_view(m) if pin else None
    if view is None:
        links.append('<span class="missing">archive unavailable: cached citation</span>')
    elif view.get("mismatch"):
        archive_name, at = view["archive"], view["at"]
        links.append('<span class="contested">mismatch: its archive holds another version under this '
                     'pin</span>')
    else:
        archive_name, at = view["archive"], view["at"]
        title, by, abstract, withdrawn = view["title"], view["by"], view["abstract"], view["withdrawn"]
        if view.get("pdf"):
            links.append(link(view["pdf"], "PDF"))
        landing = view["landing"]
        if landing:
            links.insert(0, link(landing, "landing page"))
    return "\n".join([
        f'<li class="paper member{" withdrawn" if withdrawn else ""}">',
        link(landing, esc(title), "paper-title"),
        f'<div class="paper-authors">{esc(by)}</div>',
        f'<div class="paper-meta">{esc(str(year))}'
        + (f' · {owner_tag(m["owner"], root)}' if show_owner else "")
        + f' · in {link(at, esc(archive_name))}'
        + (f' · {versions_line(m, {})}' if m.get("revisions") else "")
        + (" · " + " · ".join(links) if links else "")
        + f' · {pin_html(pin)}</div>',
        withdrawn,
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])


def remote_view(m):
    """{archive, at, dc, pdf, state, title, by, abstract, landing, withdrawn} of member M,
    read at the first of its at that answers and whose copy matches the pin; {archive, at,
    mismatch} for a copy that does not match; None if none answers."""
    obj_id = names.object_id(m["name"], m["owner"])
    pin_ver, pin = P.member_pins(m)[-1][:2]
    for at in m.get("at", []):
        src = remote.Source(at)
        try:
            disc = src.discovery()
            path = src.object_path(obj_id)
            data = src.get(f"{path}/{pin_ver}/inventory.json")
            if data is None:
                continue
            name = disc.get("name")
            view = {"archive": name if isinstance(name, str) and name else at, "at": src.at or at}
            if names.sha512_hex(data) != pin:
                return dict(view, mismatch=True)
            inv = json.loads(data)

            def read(ver, logical, inv=inv):
                dig = next((dg for dg, ps in inv["versions"][ver]["state"].items() if logical in ps), None)
                cp = inv["manifest"][dig][0] if dig else None
                raw = src.get(f"{path}/{cp}") if cp and remote.safe_path(cp) else None
                if raw is not None and names.sha512_hex(raw) != dig:
                    raise ValueError(f"{cp}: not the file its inventory names")
                return json.loads(raw) if raw else None
            if m.get("revisions"):
                shown = pin_ver
            else:
                hist = (read(pin_ver, P.OBJ) or {}).get("history")
                if hist:
                    shown = hist[-1]
                else:
                    last = {}
                    for k in range(1, int(pin_ver[1:]) + 1):
                        o = read(f"v{k}", P.OBJ) if f"v{k}" in inv["versions"] else None
                        if o:
                            last[o["documentVersion"]] = f"v{k}"
                    shown = last[max(last)]
            view["dc"] = read(shown, "datacite.json")
            lp = P.pdf_of(read(shown, P.OBJ) or {})
            cp = P.content_path(inv, shown, lp) if lp else None
            if cp and remote.safe_path(cp) and src.at:
                view["pdf"] = f"{src.at}{path}/{cp}"
            entry = next((o for o in disc.get("objects", []) if isinstance(o, dict) and o.get("id") == obj_id), {})
            if entry.get("status") == "withdrawn":
                root_inv = json.loads(src.get(f"{path}/inventory.json") or b"{}")
                state = read(root_inv.get("head", pin_ver), P.OBJ, root_inv) if root_inv.get("versions") else None
                view["state"] = state if state and state.get("status") == "withdrawn" else {"status": "withdrawn"}
            if not view["dc"]:
                continue
            dc = view["dc"]
            view.update(title=dc["titles"][0]["title"], by=authors(dc), abstract=abstract_html(dc),
                        landing=safe_url(dc.get("url")),
                        withdrawn=withdrawal_html(view.get("state", {}), " by its owner"))
            if not isinstance(view["title"], str) or not isinstance(view["by"], str):
                continue
            return view
        except (remote.Unavailable, ValueError, KeyError, IndexError, TypeError, AttributeError):
            continue
    return None


def local_entry(m, root="", show_owner=False):
    """The entry of a member held here, in the version its collection presents (the main
    catalogue's, the featured one's, or that of the collection whose landing page lists it);
    root: the way to the root of the archive from the page ("../../" on a landing page);
    SHOW_OWNER: the owner of its line named after the year."""
    line = held(m)
    if not pins_ok(m, line):
        return remote_entry(m, root, show_owner)
    cur = P.presented_version(m, line.dir, line.inv)
    pin_ver, pin = P.member_pins(m)[-1][:2]
    obj = line.json(P.OBJ, cur)
    dc = line.json("datacite.json", cur)
    issued = P.date_of(dc, "Issued")
    pdf = pdf_address(root, line, cur, obj)
    abstract = abstract_html(dc)
    summary = "Description" if obj.get("kind") == "collection" else "Abstract"
    contested = sign.CONTESTED in (line.status(cur), line.status(pin_ver))
    return "\n".join([
        f'<li class="paper{" withdrawn" if line.withdrawn else ""}">',
        f'<a class="paper-title" href="{root}paper/{line.slug}/">{esc(dc["titles"][0]["title"])}</a>',
        f'<div class="paper-authors">{esc(authors(dc))}</div>',
        f'<div class="paper-meta">{esc((issued or "")[:4])}'
        + (f' · {owner_tag(m["owner"], root)}' if show_owner else "") + f' · {versions_line(m, obj)}'
        + (f' · <a href="{esc(pdf)}">PDF</a>' if pdf else "")
        + (' · <span class="contested">contested</span>' if contested else "")
        + f' · {pin_html(pin)}</div>',
        f"<details><summary>{summary}</summary>{abstract}</details>" if abstract else "",
        "</li>"])


KEEPERS = {}
KEEPER_FETCH = None


def keeper_link(log):
    """The link of the owner of LOG to its keeper, read once per run of render."""
    if log.owner not in KEEPERS:
        KEEPERS[log.owner] = owners.keeper_link(log, KEEPER_FETCH)
    return KEEPERS[log.owner]


def keeper_html(log):
    """The keeper of the owner of LOG, linked, marked (confirmed) when it confirms the link; or ""."""
    keeper = owners.keeper_of(log)
    if not keeper:
        return ""
    mark = " (confirmed)" if keeper_link(log).status == owners.CONFIRMED else ""
    return f'{link(keeper, esc(keeper))}{mark}'


def owner_html(owner, root):
    """The owner of a line, on a landing page: its name, linked to its page, its keeper and
    its state."""
    log = P.key_log(owner)
    name = f"<code>{esc(owner)}</code>"
    out = f'<a href="{root}owner/{owner}/">{name}</a>' if log else name
    keeper = keeper_html(log) if log else ""
    if keeper:
        out += f" · keeper {keeper}"
    notes = owner_notes(log)
    return out + (f' · <span class="contested">{esc("; ".join(notes))}</span>' if notes else "")


def owner_notes(log):
    """What a reader is told about an owner: an end, a fork, a successor, exposed keys."""
    if log is None:
        return []
    out = []
    if log.fork_point:
        out.append(f"ended by a fork of its key log at v{log.fork_point}")
    elif log.ended:
        out.append("ended")
    if log.successor:
        out.append(f"successor {log.successor}")
    exposed = log.exposed_keys()
    if exposed:
        out.append(f"{len(exposed)} key{'s' if len(exposed) != 1 else ''} exposed")
    return out


def owner_page(owner, lines):
    """The page of OWNER, from its key log held here, listing LINES ([Line])."""
    log = P.key_log(owner)
    side = log.side()
    last = side[-1] if side else None
    keys = (last.keys or {}) if last else {}
    facts = [f"<li>Key log <code class=\"copy\">sheaf:{esc(owner)}</code>, {len(log.versions)} version"
             f"{'s' if len(log.versions) != 1 else ''}"
             + (f"; latest <code class=\"copy\">sheaf:{esc(owner)}/v{last.number}?sha512={last.digest}</code>" if last else "")
             + "</li>"]
    keeper = keeper_html(log)
    if keeper:
        facts.append(f"<li>Keeper: {keeper}</li>")
        claim = owners.successor_claim(log, keeper_link(log))
        if claim:
            facts.append(f"<li>Successor {esc(claim)}: <code>{esc(keeper_link(log).successor)}</code></li>")
    latest = log.latest()
    if latest is not None:
        facts.append(f"<li>Current keys ({latest.keys['threshold']} of {len(latest.keys['keys'])} sign):"
                     "<ul>" + "".join(f"<li><code>{esc(k)}</code></li>" for k in latest.keys["keys"])
                     + "</ul></li>")
        facts.append(f"<li>Rotation keys committed to: {len(keys.get('next', []))}, of which "
                     f"{keys.get('nextThreshold')} sign the next version of the key log</li>")
    facts.append(f"<li>Rotations, exposures and ends: {max(len(side) - 1, 0)}</li>")
    exposed = sorted(log.exposed_keys())
    if exposed:
        facts.append('<li class="contested">Exposed keys (what they alone signed is contested):<ul>'
                     + "".join(f"<li><code>{esc(k)}</code></li>" for k in exposed) + "</ul></li>")
    if log.fork_point:
        facts.append(f'<li class="contested">Ended by a fork of its key log at v{log.fork_point}</li>')
    elif log.ended:
        facts.append('<li class="contested">Ended: it signs nothing more</li>')
    if log.successor:
        facts.append(f"<li>Successor named by its ending version: <code>{esc(log.successor)}</code></li>")
    items = [f'<li><a href="../../paper/{ln.slug}/">'
             f'{esc((ln.json("datacite.json", ln.signed) or {}).get("titles", [{}])[0].get("title", ln.slug))}'
             f'</a> <code class="small">{esc(full_uri(ln))}</code></li>' for ln in lines]
    return fill(template("owner.html"), {
        "root": "../../", "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(P.ARCHIVE["baseUrl"]),
        "owner": esc(owner), "facts": "\n".join(facts),
        "lines": "\n".join(items) if items else '<li class="empty">No lines with a page here.</li>'})
