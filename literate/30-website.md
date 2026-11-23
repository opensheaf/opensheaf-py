The website
===========

An OpenSheaf archive is a folder of static files, and it is meant to be
served as a website: the discovery document `opensheaf.json`, the storage
root, the indexes, and pages for readers, the *presentation files* of
section 3 of the specification. This chapter describes the pages, written
by `src/opensheaf/html.py` for archives that follow the *website profile*
(appendix A.3): a home page presenting the owner catalogues, one landing page
for each line, a page for each owner, and a sitemap. The pages are filled
into templates, which are described in the [next chapter](31-templates.md).

An archive whose home page is a [TeXmacs index](16-index.md) gets the
same landing pages, owner pages and sitemap from this module, without the
home page: `render` is then called with `home=False`. The landing pages are
what appendix A.3 asks for, and what search engines read, whatever makes
the home page.

The pages are a presentation, never a source of truth (section 3). They are
regenerated from the storage root by `osheaf index`, and after every
command that changes the archive ([the command line](60-command-line.md)),
a takedown included, as appendix A.3 asks; they are never edited by hand,
and a verifier does not trust them. Their job is to be read by people and
found by search engines, and to link every claim to the files that support
it: each version to its inventory, each member to its pin, each line to its
owner's key log.

What the pages show
-------------------

Specification 0.2 changed what a page is about. A work is a *line*,
`sheaf:<name>:<owner>` (section 4): its name, the digest of a genesis
record (section 5), and its owner, the keyed identity that signs its
versions (sections 6 and 7). An archive may give a line a *label*, a short
readable name for its URLs (section 3.1); the labels stay the addresses of
the pages, `paper/<label>/`, as before, but they are the archive's choice
and may change, and the permanent name of the line is its `sheaf:` URI,
which every landing page gives in full and in canonical form, with a short
form for people (section 12.2). A line held here without a label (a mirror
copied without one) has its page at `paper/<name>/`, or, when the archive
holds several lines of that name (the originator's line and a branch, say),
at `paper/<name>-<owner>/`, so that each line has its own (appendix A.3).

Only signed versions count (section 7.3): a landing page lists the document
versions of the history read from the latest signed version of the line
(section 4.2), each with its status: signed, vouched for by a later signed
version, or contested, when the key that signed it was exposed by its owner
(section 6.3), which the page marks. The status of the line, active or
withdrawn, is read from the same version (section 13.1), and a withdrawal
is shown on every page that shows the line, whatever version that page
presents, as section 13.1 requires.

The members shown are those of the latest signed version of each owner
catalogue, the catalogues in the order of `owners` in the discovery
document and the members of each in its order, which is authoritative
(section 8.2; appendix A.3): the documents of the lines each owner writes
here, or, for a curated catalogue, the members its curator chose, from any
archive. A member
whose line is held here, written here or copied here as a mirror, gets a
landing page; a member held elsewhere gets an entry on the home page only,
linking to its own archive, which has its own landing pages. Each member is
presented in one version (section 8.3): a member of a catalogue in its
current version, read from the history of the version pinned; a member of a
selection in the last revision of its set (section 8.4), with the list of
the revisions vetted.

Every line held here with a label gets a landing page too, also when no
collection reaches it (an accepted copy, a collection of the archive), in
the current version of its latest signed version: a label is an address,
and an address leads somewhere.

An archive may also **feature** one of its collections on the home page
(`index.html.featured` in `osheaf.json`: the label of a collection of the
archive): a reading list, a journal's issues, the papers of a seminar. Its
members are listed first, under its title, and its description becomes the
lead paragraph; the owner catalogues follow, so that the home page still
presents the archive's own documents and the pin of every member. Curation
lives in the collections of the archive, which are lines of their own
(section 8.1).

Each owner of a line with a landing page whose key log is held here
(section 6.5) gets a page, `owner/<owner>/`, summarising its key log: the
current keys, how many times they were rotated, the keys exposed, an end,
a fork, a successor, the keeper. A landing page names the owner of its line
and links that page: a signature means something only with the key log it
is checked against.

The module
----------

    # in src/opensheaf/html.py:
    <<the documentation of html.py>>

    import datetime
    import html
    import json
    import shutil
    from pathlib import Path

    from . import core as P, names, owners, remote, sign

    DEFAULTS = Path(__file__).resolve().parent / "templates"


    <<escaping text for HTML>>


    <<reading and filling the templates>>


    <<dates, authors and file links on the website>>


    <<a line held in this archive>>


    <<the sheaf: URIs of a line>>


    <<a version on a landing page>>


    <<the tags for search engines>>


    <<an abstract in HTML>>


    <<writing the website>>


    <<the path of a template>>


    <<a member of another archive on the home page>>


    <<the home-page entry of a line of this archive>>


    <<the owner of a line, on a landing page and on its own>>

The documentation of the module is a summary of this chapter.

    # in the documentation of html.py:
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

Templates
---------

The look of the pages belongs to the archive, not to the tools: each
archive has its own templates, in the folder named by
`index.html.templates` in `osheaf.json` (`osheaf init` copies the
defaults there, to be edited). An archive with a TeXmacs index has no
`index.html` settings, and names the folder `index.templates`; without
either setting, the folder `templates` of the archive is used if it
exists, so that an archive needs no setting to give its landing pages
its own look. A template missing from that folder is taken from the
package's defaults, `DEFAULTS`, the folder `templates` next to the
module: an archive made before the owner page existed gets the default
one. The style sheet is copied rather than filled, so its path is needed
rather than its text; `template` reads the file `template_path` finds.

    # in the path of a template:
    def template_path(name):
        d = P.INDEX.get("html", {}).get("templates") or P.INDEX.get("templates") or "templates"
        p = P.ROOT / d / name
        return p if p.exists() else DEFAULTS / name

A template to be filled is read as UTF-8 text.

    # in reading and filling the templates:
    def template(name):
        return template_path(name).read_text(encoding="utf-8")

A template is HTML with placeholders `{{name}}`, replaced by plain
string substitution. There is no template language, and no package to
install: an archive's curator can edit a template knowing only HTML. The
values are HTML already, escaped by the code that makes them. The
replacement is made value after value, so a value that contained the
placeholder of a later one would see it filled too; titles and abstracts
do not contain double braces in practice. A placeholder that a template
does not use is simply not shown, so that templates written before a
placeholder existed keep working.

    # in reading and filling the templates:
    def fill(text, values):
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", v)
        return text

Every text from the files of objects is escaped, quotes included, since it
may end up in an attribute: section 15.2 asks that titles, abstracts,
notes and reasons be shown as text, never as HTML. A missing value becomes
the empty string.

    # in escaping text for HTML:
    def esc(s):
        return html.escape(s or "", quote=True)

Escaping is not enough for an address. A URL read from the files, ours or
another archive's (the `url` of a member's DataCite record, its `at`, the
`record` of an external entry, a `rightsUri`, a keeper), becomes a link
only if it is an `http` or `https` URL: a `javascript:` or `data:` URL,
escaped, is still a script that runs when the reader clicks it. Plain
`http` is let through because the licences of arXiv are named by `http`
URIs (`http://creativecommons.org/licenses/by/4.0/`); the bases in `at`,
which are fetched, are held to `https` where they are recorded. Any other
value is shown as text, without a link.

    # in escaping text for HTML:
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

Mathematics in titles and abstracts is written in LaTeX between dollar
signs (section 4.4) and is left as it is: MathJax, loaded by the
templates, typesets it in the reader's browser, without running scripts
of the archive's files.

Small pieces
------------

Dates are shown in words (`3 June 2026`), by the function of the core,
which also understands approximate dates; a missing date shows nothing.
Authors are shown by their display names, given name first, joined as
in prose, `A, B and C`, by the rule the TeXmacs index follows too
(`authors_of`, with the names of creators in the
[deposit](13-deposit.md)).

    # in dates, authors and file links on the website:
    def fmt_date(d):
        return P.fmt_date(d) if d else ""


    def authors(dc):
        return P.authors_of(dc)

A link to a file of a version goes through the inventory: the logical path
is translated into the content path where OCFL stores the file, which may
lie in the folder of an earlier version, below the folder of the object,
which the storage layout gives (section 3.2: `<owner>/<name>/` in the
owner-name layout). A file the version does not have gives no link. The
PDF of a version is the one its `object.json` names among the renditions
([document versions](11-versions.md)), and its address is `None` when
there is none. The links go to the files; no file of an object is ever
included in a page (section 15.3).

    # in dates, authors and file links on the website:
    def file_url(root, line, ver, logical):
        cp = P.content_path(line.inv, ver, logical) if logical else None
        return f"{root}ocfl/{P.path_of(line.id)}/{cp}" if cp else None


    def file_link(root, line, ver, logical, label):
        u = file_url(root, line, ver, logical)
        return f'<a href="{esc(u)}">{esc(label)}</a>' if u else ""


    def pdf_address(root, line, ver, obj):
        return file_url(root, line, ver, P.pdf_of(obj))

An abstract may have several paragraphs, separated by blank lines in
`datacite.json`; the line breaks inside a paragraph are only those of the
text as it was typed, and are collapsed.

    # in an abstract in HTML:
    def abstract_html(dc):
        for x in dc.get("descriptions", []):
            if x["descriptionType"] == "Abstract":
                return "\n".join(f"<p>{esc(' '.join(p.split()))}</p>" for p in x["description"].split("\n\n"))
        return ""

A line held in this archive
---------------------------

A `Line` gathers what the pages need of a line held in the storage root:
its folder and inventory, the key log of its owner held beside it (section
6.5), the status of each of its versions against that key log (section
7.3), its latest signed version and the `object.json` of that version, from
which its status, withdrawal and notices are read (sections 4.2 and 13.1).
A line without a signed version (all its versions contested) is read from
its head instead. Statuses take a little work, so each line is read once
per run of `render`, and kept in `LINES`.

Its page is written at `home`, the address built from its name, which
fixed files record and which never changes, and, for a line with a label,
also at `slug`, its label, the address the pages link to and the
canonical one: the same page at both, so that the readable address and the
permanent one both work (`name_address` and `page_address`, in the chapter
on the [archive](10-archive.md); appendix A.3).
The originator of its work, read from its genesis record, tells whether
its `sheaf:` URI needs an owner part (below).

    # in a line held in this archive:
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

A line taken down here has a tombstone (section 13.3), and section 13.2
asks that the takedown delete it from the presentation files: the pages
leave out every member whose line has one, without an entry, since even its
cached citation may be what had to go. A collection that pins it keeps its
member until its curator decides otherwise.

The `sheaf:` URIs of a line
---------------------------

A landing page gives the full `sheaf:` URI of its line (appendix A.3,
section 12.2), with complete parts, in canonical form (section 12.1): the
originator's line is `sheaf:<name>`, without an owner part, and any other
line, a branch, `sheaf:<name>:<owner>`. The citation and the metadata for
search engines give the same form, so that a citation compares byte for
byte with the relations recorded in files, which use the canonical form
too. Section 12.2 allows a short form for people, a prefix of each part,
and asks for at least 16 characters in each part of a short form printed
where it cannot be corrected; the pages, which may be printed, give that
one. The pin of a version is written as the URI naming exactly that object
version (section 12.1), the document version with the digest of the
inventory, which is what a citation of a fixed version should carry.

    # in the sheaf: URIs of a line:
    def full_uri(line):
        return names.SheafURI(line.name, line.owner).canonical(line.originator)


    def short_uri(line):
        return f"sheaf:{line.name[:16]}" + ("" if line.owner == line.originator else f":{line.owner[:16]}")


    def pin_uri(line, ver):
        n = line.json(P.OBJ, ver)["documentVersion"]
        return f"{full_uri(line)}/v{n}?sha512={line.digest(ver)}"

Writing the website
-------------------

`render` writes everything from the member lists of the owner catalogues.
It first decides which lines get a landing page, and in which version
(below); then it writes the landing pages; then the home page, from the
members in the catalogue's order: an entry for each, from its landing page
here or from its own archive; then the owner pages, the style sheet and the
sitemap; and it removes the pages of lines that no longer have one. The
list `urls` collects the pages for the sitemap, starting with the home
page; `written` the lines that got a landing page, whose number `render`
returns.

With `home=False`, for an archive whose home page is a TeXmacs index,
the home page is not written, and the members of other archives are not
read (their entries would be read over the network for nothing); the
style sheet is copied only if the landing page refers to it, as the
default one does, so that an archive whose template uses its own style
sheets gets no stray `style.css`.

    # in writing the website:
    def render(members, home=True, featured=None, keeper_fetch=None, groups=None):
        """Write index.html, paper/<label>/index.html for every line presented, owner/<owner>/,
        style.css and sitemap.xml; with home=False (a TeXmacs index is the home page),
        everything but index.html. FEATURED: the identifier of a collection of the archive
        whose members the home page lists first. KEEPER_FETCH: how the places of keepers are
        read (owners.fetch_json by default). GROUPS: [(owner, members)], the members by owner
        catalogue, for an archive with several owners."""
        global KEEPER_FETCH
        LINES.clear()
        KEEPERS.clear()
        KEEPER_FETCH = keeper_fetch
        members = [m for m in members if not removed(m)]
        root_out = P.ROOT
        base = P.ARCHIVE["baseUrl"]
        urls, written, seen_owners = [(base, None)], [], []
        page_t = template("paper.html")
        <<the lines that get a landing page>>
        for obj_id, m in pages.items():
            line = LINES[obj_id]
            <<write the landing page of a line of this archive>>
        if home:
            <<the entries of the home page, together or by owner>>
            <<the featured collection of the home page>>
            <<the lead paragraph of the home page>>
            <<write the home page and the style sheet>>
        elif "style.css" in page_t:
            shutil.copyfile(template_path("style.css"), root_out / "style.css")
        <<write the pages of the owners>>
        <<write the sitemap>>
        <<the pages at the former addresses of lines>>
        <<remove the pages of former lines>>
        return len(written)

### Which lines get a page

A member of an owner catalogue held here gets a landing page, in the
version the catalogue presents; so does a member held here of the featured
collection; and so, further down, does every member held here of a
collection that gets a landing page, since that page lists its members, in
the version that collection presents. The first collection to reach a line
decides its version: the owner catalogues first, so that a line of the
archive is presented in its current version (appendix A.3) even when a
featured selection vetted an earlier revision of it. Collections are
followed once each, so a collection that includes itself, directly or not,
ends the walk. Finally every labelled line held here that nothing reached
gets a page too, presented as a catalogue following it would present it:
the current version of its latest signed version. A key log is not a work,
and gets an owner page instead; a line without a signed version gets no
page.

    # in the lines that get a landing page:
    fmembers = []
    if featured:
        fline = held({"name": featured.split(":")[1], "owner": featured.split(":")[2]})
        fmembers = (fline.json("members.json", fline.signed) or {}).get("members", [])
    pages, followed = {}, set()

    def walk(queue):
        while queue:
            qm = queue.pop(0)
            line = held(qm)
            if line is None:
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

The PDF of a document is found from its renditions, whatever its name:
deposits by these tools call it `paper.pdf`, but an accepted copy keeps
the name its source gave it.

### The landing page of a line

A landing page is at `paper/<label>/` and presents the version the member
that reached it presents (`presented_version`, in the chapter on the
[owner catalogues](15-owner-catalogues.md)): the current version, as of the
version pinned, for a catalogue (section 8.3), or the last revision for a
selection, whose vetted document versions are marked in the list of
versions (section 8.4). Three things are read from the latest signed
version of the line instead (`ref`), which may be a later object version (a
description-only version, a notice, a withdrawal): the notices, the status
and the list of versions. Notices about any version are kept in every later
object version (section 4.2), and the status belongs to the line, whatever
version is shown (section 13.1). The versions are listed from the last of
the history to the first. The pin shown is the member's, or for a
selection that of the revision presented.

Links in the page are relative to the root of the archive (`../../`), so
that the website also works from a copy on the local disk or at another
address; only the tags for search engines, which must be absolute, use
the base URL.

    # in write the landing page of a line of this archive:
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
    <<the withdrawal and the contested mark of a landing page>>
    <<the licence and citation of a landing page>>
    <<the HTML version of a document, if any>>
    common = {
        "root": root, "archive_name": esc(P.ARCHIVE["name"]), "base_url": esc(base),
        "head": meta_tags(line, cur, obj, dc), "title": esc(dc["titles"][0]["title"]),
        "issued": esc(fmt_date(issued)), "withdrawn": withdrawn, "contested": contested,
        "versions": versions, "licence": licence, "cite": cite,
        "pin": pin, "pin_url": f"{root}ocfl/{P.path_of(line.id)}/{pin_ver}/inventory.json",
        "sheaf_uri": esc(full_uri(line)), "sheaf_short": esc(short_uri(line)),
        "owner": owner_html(line.owner, root),
    }
    if line.owner not in seen_owners:
        seen_owners.append(line.owner)
    if obj.get("kind") == "collection":
        <<the landing page of a collection>>
    else:
        page = fill(page_t, dict(common, **{
            "authors": esc(authors(dc)), "abstract": abstract_html(dc),
            "pdf": esc(pdf_address(root, line, cur, obj) or f"#v{obj['documentVersion']}"),
            "html_link": html_link}))
    for address in dict.fromkeys([line.home, line.slug]):
        out = root_out / "paper" / address / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        written.append(address)
    lastmod = line.inv["versions"][line.inv["head"]]["created"][:10]
    urls.append((f"{base}paper/{line.slug}/", lastmod))
    if html_link:
        urls.append((f"{base}site/{line.slug}/{line.slug}.html", lastmod))

A TeXmacs document deposited here has an HTML version, made by TeXmacs at
the deposit (appendix A.2) and kept outside the storage root, in
`site/<label>/<label>.html`. The landing page links it, next to the PDF,
and the sitemap lists it after the landing page: it is the full text,
which search engines index. The landing pages are in `paper/<label>/`, so
the two never meet. The link is the placeholder `{{html_link}}`, empty for
a document without an HTML version; a template written before it existed
simply does not show the link.

    # in the HTML version of a document, if any:
    html_link = ""
    if (P.SITE / line.slug / f"{line.slug}.html").exists():
        html_link = f' · <a href="{root}site/{line.slug}/{line.slug}.html">HTML</a>'

A withdrawn line keeps its page, its files and its history (section
13.1); the page shows the withdrawal notice, with its date and reason,
above the abstract, whatever version the page presents: presentations must
show it. A line whose presented version is contested, signed only with
keys its owner has since exposed (section 6.3), is marked so above the
abstract too: what it holds may have been signed by whoever stole the key.

    # in the withdrawal and the contested mark of a landing page:
    withdrawn = withdrawal_html(line.state)
    contested = ""
    if line.status(cur) == sign.CONTESTED or line.status(pin_ver) == sign.CONTESTED:
        contested = ('<div class="contested"><strong>Contested:</strong> this version is signed only with '
                     'keys its owner has since exposed (sections 6.3 and 7.3 of the specification); '
                     'what it holds may not be the owner\'s.</div>')

The withdrawal is the same on landing pages and on the entries of the home
page; for a member of another archive it is said to come from the member's
owner, since for a selection it is not part of what was vetted (section
8.4).

    # in dates, authors and file links on the website:
    def withdrawal_html(state, where=""):
        if state.get("status") != "withdrawn":
            return ""
        w = state.get("withdrawal", {})
        return (f'<div class="withdrawn"><strong>Withdrawn{where} ({esc(fmt_date(w.get("date")))}):</strong> '
                f'{esc(w.get("reason", {}).get("text", ""))}</div>')

The licence is named, and linked when it has a URL. The suggested
citation names the archive, the year of first appearance and the document
version, then the `sheaf:` URI of the version presented, with its digest,
which names it in every archive and over time (section 12.1), and ends
with the DOI when there is one, the landing page otherwise. The URI is
set as an identifier, which may break anywhere and is copied on a click,
and the last address is a link, so that neither runs out of the box of
the citation.

    # in the licence and citation of a landing page:
    rights = (dc.get("rightsList") or [{}])[0]
    licence = esc(rights.get("rights", ""))
    if rights.get("rightsUri"):
        licence = link(rights["rightsUri"], licence)
    cite_url = f"https://doi.org/{dc['doi']}" if dc.get("doi") else f"{base}paper/{line.slug}/"
    cite = esc(f"{authors(dc)}. {dc['titles'][0]['title']}. {P.ARCHIVE['name']}, "
               f"{(issued or '')[:4]}, version {obj['documentVersion']}.") \
        + f' <code class="copy">{esc(pin_uri(line, cur))}</code>.' \
        + f' <a href="{esc(cite_url)}">{esc(cite_url)}</a>'

### The landing page of a collection

A collection held here (a reading list, a journal issue, the main
catalogue itself) has a landing page at the same place, `paper/<label>/`,
but from its own template, `collection.html`, since what a reader looks
for there is its members, not a PDF. The page names its type and curator,
gives its description, and lists its members as the home page does: each
with its title linked to its landing page (here, or in its own archive),
its authors, the versions vetted for a selection, and its pin. Its members
are read from `members.json` alone, by their `kind`, `name`, `owner` and
`at` (section 8.2), never by a label. Then come its versions, its
citation and licence (CC0, section 8.6), and the pin of the collection
itself. An archive whose `templates/` folder has no `collection.html`
uses the default one.

    # in the landing page of a collection:
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

### A version

Every document version of the history gets an item in the list of
versions, as appendix A.3 asks: its number and the labels services gave
it, its stage, its status, its date, its change note, its files, its DOI,
its pin and the notices about it. The change note is labelled as in the
TeXmacs index (`changes_note`): `arXiv comments: 61 pages` for a version
imported from arXiv, whose comments are not always about a change,
`changes: ...` otherwise. The version presented, the document version
`shown`, is marked, and has an anchor `#vN` like the others. The pin of a
version is shown by the beginning of the digest, followed by a link to
the inventory; the `sheaf:` URI naming exactly that object version is its
title, shown when the pointer rests on it, and is what a click on the
digest copies ([the templates](31-templates.md)). For a member
of a selection, `vetted` is the set of the document versions vetted, each
marked as such; the version presented is then the selection's, not
necessarily the document's current version, and is not called current.

    # in a version on a landing page:
    def version_block(line, ver, shown, notices, root, vetted=None):
        """One version of a line: its number, labels, stage, status, date, changes, files,
        DOI, pin and the notices about it."""
        obj = line.json(P.OBJ, ver)
        dc = line.json("datacite.json", ver)
        n = obj["documentVersion"]
        <<the heading and date of a version>>
        <<the links of a version>>
        out = [f'<li class="version{" is-current" if n == shown else ""}" id="v{n}">',
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
        <<the notices about a version>>
        out.append("</li>")
        return "\n".join(out)

The heading is the document version, with the labels of the records it
was imported from: `Version 3 (arXiv v3)`. A version signed only through a
later signed version is *vouched for* (section 7.3), which the heading
says in small type; a contested version is marked, in the colour of
warnings, and so is a version whose signatures cannot be checked here, when
the owner's key log is missing (`unchecked`). The date is the `Available`
date, when the version became public; a version written but never public at
the time (an old manuscript deposited later) shows its `Created` date and
says so.

A branch numbers its own document versions from 1, and a version that
holds a branch point (the first, and each new branch point) also shows the
number of the parent version, which `parent.documentVersion` keeps:
"Version 1 (the parent's version 3)" (section 9.4).

    # in the number in the parent line of a version of a branch:
    vs = list(line.inv["versions"])
    first = next(v for v in vs if line.json(P.OBJ, v).get("documentVersion") == n)
    par = line.json(P.OBJ, first).get("parent")
    if par and (vs.index(first) == 0 or line.json(P.OBJ, vs[vs.index(first) - 1]).get("parent") != par):
        labels.insert(0, f"the parent's version {par.get('documentVersion')}")

The heading then gives the number, the labels, the stage, and the status
of the version.

    # in the heading and date of a version:
    labels = [f"{e['service']} {e['label']}" for e in obj.get("external", [])
              if e.get("role") == "source" and e.get("label")]
    <<the number in the parent line of a version of a branch>>
    head = f"Version {n}" + (f" ({esc(', '.join(labels))})" if labels else "")
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

The links are the renditions (PDF), the main source named by its
format, or the reason why the sources are missing, never a rendition
passed off as a source (section 4.3); then the inventory of the version,
which lists every file with its digest; then the external records and
the DOI. A record of arXiv is shown as the TeXmacs index shows it, by its
identifier without version (`arXiv:2607.08385`), since the heading
already names arXiv's version (`Version 1 (arXiv v1)`); the link goes to
the record of that very version. A version not imported from arXiv but
related to it (section 4.4) links arXiv's abstract page the same way. A
deposit with Zenodo (appendix A.1) is shown by its record.

    # in the links of a version:
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

The notices come from the latest signed version, and each current one is
shown under the version it is about, with its number; a notice replaced by
a later one is not, and the one replacing it says so (section 4.2). A
notice with a file (a full statement, with mathematics or as a PDF) links
to it, as stored in that version.

    # in the notices about a version:
    replaced = {x.get("replaces") for x in notices}
    for k, x in enumerate(notices, 1):
        if x["documentVersion"] == n and k not in replaced:
            src = line.signed or line.inv["head"]
            statement = f' {file_link(root, line, src, x["path"], "statement")}' if x.get("path") else ""
            repl = f', replacing notice {x["replaces"]}' if x.get("replaces") else ""
            out.append(f'<div class="notice"><strong>Notice {k} ({esc(fmt_date(x["date"]))}{repl}):</strong> '
                       f'{esc(x.get("text", ""))}{statement}</div>')

### Tags for search engines

A landing page carries in its head the metadata that services read
(appendix A.3). Google Scholar reads `citation_*` meta tags, and requires
the title, one tag per author, the date of publication (with slashes)
and the address of the PDF. The date is the first appearance of the
work, `Issued`, or else the date the version became public.

    # in the tags for search engines:
    def meta_tags(line, cur, obj, dc):
        """Google Scholar's citation_* tags, schema.org JSON-LD and FAIR Signposting."""
        base = P.ARCHIVE["baseUrl"]
        landing = f"{base}paper/{line.slug}/"
        pdf = pdf_address(base, line, cur, obj)
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
Google Scholar requires (appendix A.3 asks that it be served with
`Content-Security-Policy: sandbox`, which is the server's business). A
version without a PDF gets no tag for it, here and in the links and the
record below.

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
             f'<link rel="describedby" href="{esc(file_url(base, line, cur, "datacite.json"))}"'
             ' type="application/vnd.datacite.datacite+json">']
    if pdf:
        tags.append(f'<link rel="item" href="{esc(pdf)}" type="application/pdf">')
    if safe_url(rights.get("rightsUri")):
        tags.append(f'<link rel="license" href="{esc(rights["rightsUri"])}">')

The schema.org `ScholarlyArticle` record, in JSON-LD, says the same for
general search engines, with the `sheaf:` URI of the line among its
identifiers. It is written into a `<script>` element, where the sequence
`</` would end the element early: it is escaped as `<\/`, which JSON reads
as the same string.

    # in the schema.org record of a landing page:
    ld = {"@context": "https://schema.org", "@type": "ScholarlyArticle",
          "name": dc["titles"][0]["title"], "url": landing,
          "author": [{"@type": "Person", "name": P.display_name(c)} for c in dc["creators"]],
          "datePublished": date, "version": dc["version"],
          "identifier": ([f"https://doi.org/{dc['doi']}"] if dc.get("doi") else []) + [full_uri(line)]}
    if pdf:
        ld["encoding"] = {"@type": "MediaObject", "contentUrl": pdf, "encodingFormat": "application/pdf"}
    if abstract:
        ld["abstract"] = abstract
    if safe_url(rights.get("rightsUri")):
        ld["license"] = rights["rightsUri"]
    tags.append('<script type="application/ld+json">'
                + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")

### The home page

Each member held here has an entry on the home page: its title, linked to
its landing page, its authors, its year and version (the versions vetted,
for a selection), a link to the PDF, and its pin. The pin is shown on
purpose: the home page is the presentation of a version of the main
catalogue, and the beginning of each member's digest lets a reader compare
it with `members.json`. The verification of an archive declaring the
website profile ([chapter 17](17-verify.md)) checks that the home page
shows the pin of every member. A withdrawn line is marked, and so is a
member whose version is contested. The abstract is folded in a `<details>`
element, so that the list stays short.

    # in the home-page entry of a line of this archive:
    def local_entry(m, root="", show_owner=False):
        """The entry of a member held here, in the version its collection presents (the main
        catalogue's, the featured one's, or that of the collection whose landing page lists it);
        root: the way to the root of the archive from the page ("../../" on a landing page);
        SHOW_OWNER: the owner of its line named after the year."""
        line = held(m)
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
            + f' · <span class="pin" title="{pin}">pin {pin[:32]}…</span></div>',
            f"<details><summary>{summary}</summary>{abstract}</details>" if abstract else "",
            "</li>"])

An archive with one owner has one owner catalogue, whose members the home
page lists in their order. An archive with several owners presents them as
`index.owners` of the configuration says (appendix A.3). With `together`,
the default, they are in one list, ordered as an owner catalogue is
(newest first, section 8.2, `member_order`), each entry naming the owner of
its line after its year. With `by-owner`, each owner's members are under a
heading naming the owner, in the order of the owners, each catalogue in
its own order. The owner is named by the label of its key log, or else by
the beginning of its name, and linked to its page. The template has one
list, `<ol class="papers">`, with `{{papers_heading}}` before it: the
first owner's heading goes there, and each later one closes the list and
opens another, so that templates written before keep working.

    # in the entries of the home page, together or by owner:
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

The owner of a line, on the home page: the label of its key log or the
beginning of its name, linked to its page when its key log is held here.

    # in dates, authors and file links on the website:
    def owner_tag(owner, root=""):
        """The owner OWNER, named by the label of its key log or its short name, linked to its page."""
        name = esc(P.label_of(names.object_id(owner, owner)) or names.short(owner))
        return f'<a class="owner" href="{root}owner/{owner}/">{name}</a>' if P.key_log(owner) else name

The featured collection is read from its latest signed version, as the main
catalogue is. Its title heads its section, and each member gets an entry,
from this archive or another, in the version the featured collection
presents (the revisions its curator vetted, for a selection).

    # in the featured collection of the home page:
    featured_html = ""
    if featured:
        fdc = fline.json("datacite.json", fline.signed)
        items = [local_entry(fm) if held(fm) else remote_entry(fm) for fm in fmembers]
        featured_html = ('<section class="featured">\n'
                         f'<h2>{esc(fdc["titles"][0]["title"])}</h2>\n<ol class="papers">\n'
                         + ("\n".join(items) if items else '<li class="empty">No members yet.</li>')
                         + "\n</ol>\n</section>")

The version line of an entry names the version presented or, for a member
of a selection, the versions vetted, the last of which is presented.

    # in dates, authors and file links on the website:
    def versions_line(m, obj):
        """'version 3', or for a member of a selection 'vetted: versions 2, 3'."""
        if m.get("revisions"):
            ns = [str(r["documentVersion"]) for r in m["revisions"]]
            return f"vetted: version{'s' if len(ns) > 1 else ''} {', '.join(ns)}"
        return f"version {obj['documentVersion']}"

The lead paragraph of the home page says what the archive is. An archive
of its owners' documents gets a fixed text; an archive with one owner
catalogue, curated (order `manual`), or the featured collection, gets its
description, and a
sentence saying that its members are kept in their own archives, and, for
a selection, that each is shown in the version its curator vetted.

    # in the lead paragraph of the home page:
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

The home page is at the root of the archive, next to `opensheaf.json`,
so its links need no prefix. The empty file `.nojekyll` tells GitHub
Pages to serve the files as they are, without passing them through
Jekyll.

    # in write the home page and the style sheet:
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

### The sitemap and the removed pages

The sitemap lists the home page, the landing pages, the HTML versions and
the owner pages, each landing page with the date of the last object
version of its line, so that a harvester revisits only what changed. No
`robots.txt` is written: it names the sitemap for a whole host, and only
counts at the root of the host (`https://example.org/robots.txt`), which is
the archive's only when the archive is the whole site. An archive served in
a folder of a larger site, as `https://mgubi.org/papers/`, has the line
`Sitemap: https://mgubi.org/papers/sitemap.xml` added to the site's
`robots.txt`, or submits the sitemap to the search engines directly.

    # in write the sitemap:
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, last in urls:
        sm.append(f"  <url><loc>{esc(url)}</loc>" + (f"<lastmod>{last}</lastmod>" if last else "") + "</url>")
    sm.append("</urlset>")
    (root_out / "sitemap.xml").write_text("\n".join(sm) + "\n", encoding="utf-8")

A line whose label changed (`osheaf label`, in the chapter on the
[archive](10-archive.md)) had its page at another address, which
descriptions already deposited give and readers have kept. `osheaf.json`
records these addresses in `formerAddresses`, each mapped to its line; at
each one that no page of a line now takes, the website writes a small page
that sends the reader to the line's page, by a link and by the `refresh`
of HTML (a static site has no other redirect), with the new address as
canonical and nothing for search engines to index. It is not listed in the
sitemap. A former address of a line that has no page any more gets
nothing, and is removed below like any page.

    # in the pages at the former addresses of lines:
    moved = []
    for address, obj_id in sorted((P.ARCHIVE.get("formerAddresses") or {}).items()):
        if address in written or obj_id not in pages or not P.LABEL_RE.match(address):
            continue
        slug = LINES[obj_id].slug
        out = root_out / "paper" / address / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(redirect_page(f"../{slug}/", f"{base}paper/{slug}/"), encoding="utf-8")
        moved.append(address)

The page is the same for the HTML version of a document, which `osheaf
label` leaves at its old place in `site/`. It is marked, so that the tools
tell it from a page of their own: a page at a former address may be
replaced, a page of the curator's may not.

    # in writing the website:
    def redirect_page(href, canonical):
        """A page sending its reader to HREF (relative), whose address is now CANONICAL."""
        return (f"<!DOCTYPE html>\n{P.REDIRECT_MARK}\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
                f"<title>Moved</title>\n<link rel=\"canonical\" href=\"{esc(canonical)}\">\n"
                f"<meta name=\"robots\" content=\"noindex\">\n"
                f"<meta http-equiv=\"refresh\" content=\"0; url={esc(href)}\">\n</head>\n"
                f"<body><p>This page has moved to <a href=\"{esc(href)}\">{esc(canonical)}</a>.</p></body>\n</html>\n")

A line that has no page any more loses it: one taken down (section 13.2
asks that a takedown delete it from the presentation files), one that left
every collection and lost its label, one whose label changed. Its page is
generated output like the rest; the line itself, if it is still held, stays
in the storage root. The same holds for the pages of owners. Only folders
are pages: files left in `paper/` or `owner/` by others (the `.DS_Store`
of macOS) are not touched.

    # in remove the pages of former lines:
    for folder, keep in (("paper", set(written) | set(moved)), ("owner", set(owner_pages))):
        for p in (root_out / folder).glob("*") if (root_out / folder).exists() else []:
            if p.is_dir() and p.name not in keep:
                shutil.rmtree(p)

Members of other archives
-------------------------

A member of another archive appears on the home page, or on the page of
a collection, with what can be learnt about it, from its own archive. The
specification forbids including other archives' pages, or the files of
objects, in the presentation files (section 15.3): only their metadata
are read, as data, and the entry is written here. The starting point is
the citation cached in the collection (section 8.2), which needs no
network. Then the member's `at`, the base URLs where copies of its line
may be found, are tried in turn, as a `Source` of the
[resolver](20-resolution.md), which reads an archive over HTTP, or from a
folder through the locations configured (`OPENSHEAF_LOCATIONS`).

At the first archive that answers, the inventory of the version pinned is
fetched and its digest compared with the pin: a copy that does not match
is not used, and the entry says so (a *mismatch*, section 8.5). A copy
that matches gives the title, the authors, the abstract, the PDF and the
landing page of the version presented, the archive's name, and the
line's status, as the archive's discovery document states it (section
3.1), with the withdrawal read from the head of the line. The signatures
are not checked here: that is the work of `osheaf verify --remote`
(section 14.5) and of the Explorer, which the page links; the page only
avoids showing a copy that is not the one the collection pins. A member
whose archives do not answer shows the cached citation, and says so.

    # in a member of another archive on the home page:
    def remote_entry(m, root="", show_owner=False):
        """The entry of a member held elsewhere: its metadata read from the first of its at
        that answers, checked against the pin, or else the cached citation."""
        cite = m.get("cite", {})
        title, by, year = cite.get("title") or m["name"], P.names_joined(cite.get("creators", [])), \
            cite.get("year", "")
        pin = P.member_pins(m)[-1][1]
        links, abstract, landing, withdrawn = [], "", "", ""
        at = (m.get("at") or [""])[0]
        archive_name = at
        view = remote_view(m)
        if view is None:
            links.append('<span class="missing">archive unavailable: cached citation</span>')
        elif view.get("mismatch"):
            archive_name, at = view["archive"], view["at"]
            links.append('<span class="contested">mismatch: its archive holds another version under this '
                         'pin</span>')
        else:
            archive_name, at = view["archive"], view["at"]
            dc = view["dc"]
            title, by, abstract = dc["titles"][0]["title"], authors(dc), abstract_html(dc)
            if view.get("pdf"):
                links.append(link(view["pdf"], "PDF"))
            landing = safe_url(dc.get("url"))
            if landing:
                links.insert(0, link(landing, "landing page"))
            withdrawn = withdrawal_html(view.get("state", {}), " by its owner")
        <<the entry of a member of another archive>>

The entry has the same form as that of a line held here, with the archive
named and linked, the versions vetted for a member of a selection, and the
pin (of the last revision, for a selection); the title links to the
landing page in the other archive, as the title of a line held here links
to its own. A member withdrawn in its archive stays, and its entry shows
the withdrawal (section 8.3), said to come from its owner (section 8.4).

    # in the entry of a member of another archive:
    return "\n".join([
        f'<li class="paper member{" withdrawn" if withdrawn else ""}">',
        (f'<a class="paper-title" href="{esc(landing)}">{esc(title)}</a>' if landing
         else f'<span class="paper-title">{esc(title)}</span>'),
        f'<div class="paper-authors">{esc(by)}</div>',
        f'<div class="paper-meta">{esc(str(year))}'
        + (f' · {owner_tag(m["owner"], root)}' if show_owner else "")
        + f' · in {link(at, esc(archive_name))}'
        + (f' · {versions_line(m, {})}' if m.get("revisions") else "")
        + (" · " + " · ".join(links) if links else "")
        + f' · <span class="pin" title="{pin}">pin {pin[:32]}…</span></div>',
        withdrawn,
        f"<details><summary>Abstract</summary>{abstract}</details>" if abstract else "",
        "</li>"])

What is read of a member elsewhere is read through `Source.get`, which
returns the bytes of a file below the base, or `None`. Every path comes
from the other archive's files, and is untrusted (section 15.2): a content
path must be a safe relative path (`remote.safe_path`), or it is not
followed. The version presented is that of section 8.3: the last revision,
for a selection; for a catalogue, the current version as of the version
pinned, the last of its `history` or, without one, the last object version
holding the highest document version up to the pin (section 4.2), which
needs the `object.json` of each of those versions, small files (below). Anything
that fails, from the network to a file that is not JSON, makes the
archive count as not answering, and the next one in `at` is tried.

    # in a member of another archive on the home page:
    def remote_view(m):
        """{archive, at, dc, pdf, state} of member M, read at the first of its at that answers
        and whose copy matches the pin; {archive, at, mismatch} for a copy that does not
        match; None if none answers."""
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
                view = {"archive": disc.get("name") or at, "at": src.at or at}
                if names.sha512_hex(data) != pin:
                    return dict(view, mismatch=True)
                inv = json.loads(data)

                def read(ver, logical, inv=inv):
                    cp = P.content_path(inv, ver, logical)
                    raw = src.get(f"{path}/{cp}") if cp and remote.safe_path(cp) else None
                    return json.loads(raw) if raw else None
                <<the version of a member elsewhere that is presented>>
                view["dc"] = read(shown, "datacite.json")
                lp = P.pdf_of(read(shown, P.OBJ) or {})
                cp = P.content_path(inv, shown, lp) if lp else None
                if cp and remote.safe_path(cp) and src.at:
                    view["pdf"] = f"{src.at}{path}/{cp}"
                <<the status of a member elsewhere>>
                if not view["dc"]:
                    continue
                return view
            except (remote.Unavailable, ValueError, KeyError, TypeError, AttributeError):
                continue
        return None

The version presented of a member of a selection is its last revision, the
version pinned; that of a member of a catalogue is computed from the files
of the versions up to the pin, as the core computes it for a line held
here (`current_version`).

    # in the version of a member elsewhere that is presented:
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

The status is the one the archive's discovery document gives the line
(section 3.1), which a verifier checks against the storage root; for a
withdrawn line, the withdrawal and its reason are read from the head of the
line, whose root inventory names it.

    # in the status of a member elsewhere:
    entry = next((o for o in disc.get("objects", []) if isinstance(o, dict) and o.get("id") == obj_id), {})
    if entry.get("status") == "withdrawn":
        root_inv = json.loads(src.get(f"{path}/inventory.json") or b"{}")
        state = read(root_inv.get("head", pin_ver), P.OBJ, root_inv) if root_inv.get("versions") else None
        view["state"] = state if state and state.get("status") == "withdrawn" else {"status": "withdrawn"}

The owners
----------

A landing page names the owner of its line by its owner name, the digest
of its genesis record (section 6), which identifies no one (section 15.5):
a person is tied to it only by what its versions say, and by its keeper
(section 6.6), named here when the owner has one. When the owner's key log
is held here, as it must be beside every line of the archive (section
6.5), the name links its page, and what a reader must know at once is said
next to it: that the owner has ended, or exposed keys, which makes what
those keys signed contested (sections 6.3 and 7.3).

The keeper is followed by "(confirmed)" when its place, its ORCID record or
its domain, confirmed the link when the pages were written (section 6.6;
`keeper_link`, in the chapter on [owners](06-owners.md)); a link claimed
only, or not checked (no network), shows nothing more, since a page cannot
tell a reader more than the claim the genesis record makes. Each keeper is
read once per run of `render`, and `render` is given the function that
reads, so that the tests write the same pages from the same files.

    # in the owner of a line, on a landing page and on its own:
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

The page of an owner, `owner/<owner>/`, from the template `owner.html`,
summarises its key log as held here (section 6.1): the owner name and the
`sheaf:` URI of its key log, `sheaf:<owner>` (section 12.1), with the pin
of its latest version; the keeper, marked when it confirms the link, and
the successor it names, if any (section 6.6); the current keys and how many sign; the
number of rotation keys committed to and how many sign the next version;
how many versions the key log has, every version after the first being a
rotation, an exposure or an end; the keys exposed; the end, the fork point
and the successor, if any. Then the lines of the owner that have a landing
page here. It shows the key log; it does not judge the person.

    # in the owner of a line, on a landing page and on its own:
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

`render` writes a page for each owner of a line with a landing page whose
key log is held here, and lists them in the sitemap.

    # in write the pages of the owners:
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
