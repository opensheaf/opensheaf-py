The discovery document and the index
====================================

After deposits and a new version of the [main collection](15-main-collection.md),
`osheaf index` writes what the outside world reads: the *discovery
document* `opensheaf.json`, the entry point of the archive for programs,
and an index for people. The index is made in one of two ways. An archive
with a website (the website profile, appendix A.3) has it written by the
[website](30-website.md) module, with a landing page per document. An
archive kept inside a TeXmacs website (as the first OpenSheaf archive is)
instead has an index written as a TeXmacs document, from a template, and
exported to HTML by TeXmacs. This chapter is the discovery document and the
TeXmacs index.

The discovery document
----------------------

The discovery document (section 3.1) says what the archive is and where
its objects are: its name and contact, the storage root and its layout,
the main catalogue, the profiles, the owners it hosts, and a list of every
object of the storage root but drafts, with its kind, its line (`name` and
`owner`), its head version, the digest of its head inventory, its status
and, if the archive gives it one, its label. The list is a map, not a
witness: a reader can check every entry against the storage root, and
[verification](17-verify.md) does. The digest is read from the checksum
file, as the specification says ("as its checksum file states it").

The status is the line's, read from its latest signed version, whatever
document version that holds (section 13.1); a copy without a signed version
gives that of its head. A key log is always `active`. Drafts
([chapter 24](24-drafts.md)) are listed apart, in `drafts`, with their kind
and head, as unfinished work on which nothing may rely (section 10.1).

The discovery document is rewritten whole every time, from the storage
root, so that it cannot drift, by every command that adds or changes an
object (section 3.1: "rewritten whenever an object is added or changed").
Two things in it are not in the storage root, and are carried from the
document it replaces: the labels, which `LABELS` holds, and the tombstones
of objects taken down (section 13.3), which `TOMBSTONES` holds, never
removed but when the line returns ([takedowns](25-takedown.md)). Version
0.1 had `archiveId`, `mirrorOf` and `mirrors`; version 0.2 names no
archive, and a mirror is listed like any line (section 11). `indexes`
declares the three indexes, which are written with the discovery document
(below); `feed` is not written yet.

`extensions` lists the extensions the objects use (section 2): the names
of the data of extensions in the key logs, as of their latest version (or
their genesis record), and in the `object.json` of the heads.

    # in write the discovery document of the archive:
    def line_status(d, inv, head):
        """The status of the object in D (section 13.1): that of its latest signed version, or
        else of its head; always active for a key log."""
        if head.get("kind") == "owner":
            return "active"
        signed = latest_signed(d, inv)
        return (read_json(d, inv, OBJ, signed) if signed else head).get("status", "active")


    def discovery():
        objs, drafts, used = [], [], set()
        for obj_id, d, inv in objects():
            if inv is None or obj_id is None:
                continue
            head = read_json(d, inv, OBJ) or {}
            used.update(head.get("extensions") or {})
            if obj_id.startswith("sheaf:draft:"):
                drafts.append({"id": obj_id, "kind": head.get("kind"), "head": inv["head"]})
                continue
            if head.get("kind") == "owner":
                try:
                    used.update(owners.load_key_log(d).extensions() or {})
                except owners.OwnerError:
                    pass
            status = line_status(d, inv, head)
            entry = {"id": obj_id, "kind": head.get("kind"), "name": head.get("name"),
                     "owner": head.get("owner"), "head": inv["head"],
                     "inventorySha512": owners.sidecar_digest((d / "inventory.json.sha512").read_bytes()),
                     "status": status}
            if label_of(obj_id):
                entry["label"] = label_of(obj_id)
            objs.append(entry)
        doc = {"format": "opensheaf-archive/0.2", "specification": SPEC, "name": ARCHIVE["name"],
               "contact": ARCHIVE["contact"], "storageRoot": "ocfl/", "storageLayout": LAYOUT}
        if ARCHIVE["mainCollection"] in LABELS:
            doc["mainCollection"] = LABELS[ARCHIVE["mainCollection"]]
        doc.update(profiles=ARCHIVE["profiles"], extensions=sorted(used), owners=archive_owners(),
                   indexes=dict(INDEXES), objects=objs)
        if drafts:
            doc["drafts"] = drafts
        if TOMBSTONES:
            doc["tombstones"] = TOMBSTONES
        return doc


    def write_discovery():
        """Write the discovery document opensheaf.json and the indexes from the storage root."""
        write_indexes()
        write_json(ROOT / "opensheaf.json", discovery())

The indexes
-----------

An archive SHOULD keep three indexes of its objects, next to its discovery
document (section 12.5): `names/`, by name, `owners/`, by owner name, and
`sha512/`, by inventory digest. A resolver that knows a name, an owner or
a pin finds what it looks for by fetching one small file, without reading
the whole discovery document or any object; and since `names/` holds the
text of every genesis record, the lines of a work can be searched for from
the indexes alone (section 12.4). Each index is a folder of files
`<p>.json`, one per prefix `<p>` of the keys, of the length the discovery
document declares in `indexes`: these tools use two characters, so that
`names/` and `owners/` (base32) have at most 1024 files and `sha512/`
(hexadecimal) 256. A file without entries is omitted.

The indexes are maps, like the discovery document, and are rewritten with
it, whole, from the storage root, by every command that adds or changes an
object. The entries:

- in `names/`, for each object with a genesis record, its `name`, `owner`,
  `id` and `status`, its `originator` (for a key log, the owner itself),
  the text of its `genesis.json` and its label, if any;
- in `owners/`, for each owner with lines in the storage root, its owner
  name and the names of those lines, its key log among them;
- in `sha512/`, for each sealed object version, and each key-log version
  carried by a fork record (section 6.3), its `inventorySha512`, `id`,
  `version` and `status`, a carried version having the identifier of its
  key log and its own number.

Drafts are never indexed. An object taken down
([takedowns](25-takedown.md)) keeps its entries in `names/` and `sha512/`,
with the status `removed`: since its files are gone, they are carried from
the index files being replaced (the takedown writes them just before
deleting), and the tombstone's own pin is added if it is missing. A
takedown removes the name from `owners/`.

    # in write the discovery document of the archive:
    INDEXES = {"names": 2, "owners": 2, "sha512": 2}
    INDEX_FORMAT = "opensheaf-index/0.2"
    INDEX_KEY = {"names": "name", "owners": "owner", "sha512": "inventorySha512"}


    def index_entries():
        """{index: [entries]} of the storage root and of its tombstones (section 12.5)."""
        out = {"names": [], "owners": [], "sha512": []}
        lines = {}
        for obj_id, d, inv in objects():
            if inv is None or obj_id is None or obj_id.startswith("sheaf:draft:"):
                continue
            head = read_json(d, inv, OBJ) or {}
            gpath = read_logical(d, inv, GENESIS)
            if gpath is None or len(obj_id.split(":")) != 3:
                continue
            genesis = gpath.read_bytes()
            try:
                rec = names.read_genesis(genesis)
            except ValueError:
                continue
            _, nm, owner = obj_id.split(":")
            status = line_status(d, inv, head)
            entry = {"name": nm, "owner": owner, "id": obj_id, "status": status,
                     "originator": owner if rec["kind"] == "owner" else rec.get("originator"),
                     "genesis": genesis.decode("utf-8")}
            if label_of(obj_id):
                entry["label"] = label_of(obj_id)
            out["names"].append(entry)
            lines.setdefault(owner, []).append(nm)
            for n in range(1, int(inv["head"][1:]) + 1):
                sc = d / f"v{n}" / "inventory.json.sha512"
                if sc.exists():
                    out["sha512"].append({"inventorySha512": owners.sidecar_digest(sc.read_bytes()),
                                          "id": obj_id, "version": f"v{n}", "status": status})
            if head.get("kind") == "owner":
                try:
                    log = owners.load_key_log(d)
                except owners.OwnerError:
                    continue
                for v in log.versions:
                    for c in (v.carried if v.fork_record else []):
                        out["sha512"].append({"inventorySha512": c.digest, "id": obj_id,
                                              "version": f"v{c.number}", "status": "active"})
        out["owners"] = [{"owner": o, "names": sorted(ns)} for o, ns in sorted(lines.items())]
        out["names"] += removed_entries("names")
        out["sha512"] += removed_entries("sha512")
        return out


    def removed_entries(index):
        """The entries of the lines taken down, kept from the index files of INDEX with the status
        removed, and the tombstones' own entries when the files lack them (sections 12.5 and 13.3)."""
        gone = {t["id"]: t for t in TOMBSTONES}
        kept = [dict(e, status="removed") for e in read_index(index) if e.get("id") in gone]
        for t in gone.values():
            if index == "names" and not any(e["id"] == t["id"] for e in kept):
                kept.append({"name": t["name"], "owner": t["owner"], "id": t["id"], "status": "removed"})
            if index == "sha512" and not any(e["id"] == t["id"] and e["version"] == t["lastVersion"]
                                             for e in kept):
                kept.append({"inventorySha512": t["inventorySha512"], "id": t["id"],
                             "version": t["lastVersion"], "status": "removed"})
        return kept


    def read_index(index):
        """Every entry of the files of the index INDEX held next to the discovery document."""
        out = []
        for p in sorted((ROOT / index).glob("*.json")) if (ROOT / index).is_dir() else []:
            try:
                out += json.loads(p.read_text(encoding="utf-8")).get("entries", [])
            except (ValueError, AttributeError):
                pass
        return out


    def index_files(entries):
        """{index: {prefix: file contents}} of ENTRIES, by the prefixes INDEXES declares."""
        out = {}
        for index, es in entries.items():
            files = out.setdefault(index, {})
            key = INDEX_KEY[index]
            for e in sorted(es, key=lambda e: (e[key], e.get("id", ""), int(e.get("version", "v0")[1:]))):
                p = e[key][:INDEXES[index]]
                files.setdefault(p, {"format": INDEX_FORMAT, "index": index, "entries": []})["entries"].append(e)
        return out


    def write_indexes():
        """Write the files of the three indexes, replacing those of the folders."""
        files = index_files(index_entries())
        for index in INDEXES:
            folder = ROOT / index
            want = files.get(index, {})
            for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
                if p.stem not in want:
                    p.unlink()
            for prefix, data in want.items():
                write_json(folder / f"{prefix}.json", data)


The TeXmacs index
-----------------

The TeXmacs index is a TeXmacs document, `index.tm`, made from a template
of the archive (`index.template` in the configuration) by replacing its
paragraph `<paper-index>` with one entry per member of the main
collection, in the order of the collection. The entries use the `notes`
plugin's news items, so the template must use that style. Each entry shows
the title, linking the landing page of the document, the authors, the
links to the renditions and sources, the abstract, the dates, and the pin:
the beginning of the digest of the inventory, linked to that inventory, so
that a reader can check what the collection pins.

The landing pages, with the tags read by search engines, and the sitemap
are those of the [website](30-website.md), written by the same code: a
TeXmacs index is a home page, nothing more, and the website profile
(appendix A.3) asks for the rest whatever makes the home page.

    # in write the TeXmacs index of the archive:
    <<TeX accents and special letters as Unicode>>


    <<convert TeX accents in a text to Unicode>>


    <<plain text as a TeXmacs string>>


    <<text with LaTeX mathematics as TeXmacs markup>>


    <<a date as readers write it>>


    <<the line saying which version of a document readers see>>


    <<the arXiv identifier of a document version>>


    <<the change note of a version, with what it is>>


    <<a foldable abstract in TeXmacs and HTML>>


    <<the TeXmacs index entry of a member>>


    <<write the discovery document and the index>>

### The command

`readable_index` was `osheaf index` under specification 0.1. Then, with a website
configured, it hands the members to the [website](30-website.md); with a
TeXmacs template, it has the website write the landing pages and the
sitemap without a home page (`home=False`), writes `index.tm` and, unless
`--no-html`, exports it to `index.html` with TeXmacs (the PDF export,
needed to typeset it, goes to a scratch folder). The landing pages are at
`paper/<id>/`, apart from the HTML versions of TeXmacs documents in
`site/<id>/`, and the `index.html` of TeXmacs is never overwritten. The
empty file `.texmacs-noconvert` tells TeXmacs' website converter not to
touch the archive's files (appendix A.2).

With `index.html.featured` set to a collection of the archive, the home
page lists that collection first (a reading list, a journal's issues),
then the main collection; a setting that names something else stops the
command.

Only members of the archive itself can be shown this way: the entries are
read from the local storage root. A curated main collection with members
of other archives needs the website.

Version 0.2 of the specification changed what the pages must show (labels
and `sheaf:` URIs instead of identifiers, the statuses of versions, the
owners), and the [website](30-website.md) has not been ported yet. Until
it is, `osheaf index` writes the discovery document and the indexes only,
and says so when a website or a TeXmacs index is configured; the code that writes them stays,
as `readable_index`, for the port, with its entries read from the lines of
the members (`index_entry`, below).

    # in write the discovery document and the index:
    def index(args):
        write_discovery()
        if INDEX.get("html") or INDEX.get("template"):
            print("opensheaf.json and the indexes written; the website and the TeXmacs index are not yet "
                  "available for specification 0.2")
            return
        print("opensheaf.json and the indexes written (no readable index configured)")


    def readable_index(args):
        """The website or the TeXmacs index (specification 0.1; to be ported to 0.2)."""
        coll_dir = OCFL / ARCHIVE["mainCollection"]
        inv = load_inventory(coll_dir)
        members = json.loads(read_logical(coll_dir, inv, "members.json").read_text())["members"]
        if INDEX.get("html"):
            from . import html
            featured = INDEX["html"].get("featured") if isinstance(INDEX["html"], dict) else None
            if featured and not (OCFL / featured / "inventory.json").exists():
                sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not an object of this archive")
            if featured and read_json(OCFL / featured, load_inventory(OCFL / featured), OBJ).get("kind") != "collection":
                sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not a collection")
            html.render(members, featured=featured)
            local = sum(1 for m in members if m.get("archive") == ARCHIVE["archiveId"])
            print(f"opensheaf.json, index.html, {local} landing pages and sitemap.xml written")
            return
        template = (ROOT / INDEX["template"]).read_text(encoding="latin-1")
        line = "  <paper-index>\n"
        if template.count(line) != 1:
            sys.exit(f"{INDEX['template']} must contain one paragraph <paper-index>")
        from . import html
        pages = html.render(members, home=False)
        entries = "\n\n".join(index_entry(m) for m in members)
        with open(ROOT / "index.tm", "w", encoding="latin-1", newline="") as f:
            f.write(template.replace(line, entries + "\n"))
        (ROOT / ".texmacs-noconvert").touch()
        if not args.no_html:
            scratch = Path(tempfile.mkdtemp())
            run_texmacs(export_calls(ROOT / "index.tm", pdf=scratch / "index.pdf",
                                     html=ROOT / "index.html"))
            shutil.rmtree(scratch, ignore_errors=True)
        print("opensheaf.json, index.tm" + ("" if args.no_html else ", index.html")
              + f", {pages} landing pages and sitemap.xml written")

### Text in TeXmacs

Titles and abstracts are plain text with LaTeX mathematics (section 4.4), and
some, imported from arXiv, still have TeX accents (`It\^o`). The accents
become Unicode letters: an accent command is a combining character, and
normalising to NFC composes it with its letter. A few letters are commands
of their own (`\o`, `\ss`, `\l`). The [arXiv import](41-arxiv-metadata.md) uses the
same conversion.

    # in TeX accents and special letters as Unicode:
    TEX_ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303",
                   "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "=": "\u0304"}
    TEX_LETTERS = {"o": "\u00f8", "O": "\u00d8", "ss": "ss", "aa": "\u00e5", "AA": "\u00c5",
                   "l": "\u0142", "L": "\u0141", "ae": "\u00e6", "oe": "\u0153", "i": "i"}

An accent applies to a letter written with or without braces (`\'e`,
`\'{e}`, `{\'e}`); the accents written with a letter (`\c`, `\v`) need the
braces, since `\cc` would be another command.

    # in convert TeX accents in a text to Unicode:
    def tex_text(s):
        """Text with TeX accents (It\\^o, H{\\o}egh) as Unicode text."""
        acc = lambda m: unicodedata.normalize("NFC", m.group(2) + TEX_ACCENTS[m.group(1)])
        s = re.sub(r"\{?\\([\'`\"^~=])\s*\{?([A-Za-z])\}?\}?", acc, s)
        s = re.sub(r"\{?\\([cvuH])\s*\{([A-Za-z])\}\}?", acc, s)
        s = re.sub(r"\{\\(o|O|ss|aa|AA|l|L|ae|oe)\}|\\(o|O|ss|aa|AA|l|L|ae|oe)\b",
                   lambda m: TEX_LETTERS[m.group(1) or m.group(2)], s)
        return s

TeXmacs strings have their own escapes (`<less>`, `\|`) and their own
encoding. The file is written as Latin-1 bytes (see
[TeXmacs](12-texmacs.md)), and TeXmacs reads those bytes as the Cork
encoding of TeX, which agrees with Latin-1 for the accented letters from
`0xC0`, with four exceptions. Every other character is written as a
TeXmacs symbol with its code point.

    # in plain text as a TeXmacs string:
    def tm_escape(s):
        """Plain text as a TeXmacs string. Accented Latin letters are written as
        their Cork bytes (the same as Latin-1 from 0xC0, except 0xD7, 0xDF, 0xF7
        and 0xFF); other characters as the symbol \\<#17A\\> (a bare <#17A> is
        read as raw data)."""
        esc = {"\\": "\\\\", "<": "<less>", ">": "<gtr>", "|": "\\|"}
        s = re.sub(r"[\\<>|]", lambda m: esc[m.group(0)], s)
        out = []
        for c in unicodedata.normalize("NFC", s):
            o = ord(c)
            if o < 128 or (0xC0 <= o <= 0xFF and o not in (0xD7, 0xDF, 0xF7, 0xFF)):
                out.append(c)
            elif c == "\u00df":
                out.append("ss")
            else:
                out.append(f"\\<#{o:X}\\>")
        return "".join(out)

The mathematics is not converted to TeXmacs: it stays LaTeX, shown as
typewriter text in TeXmacs, and passed to the HTML export as `\(...\)` for
MathJax, the same text marked for each output with `specific`. Dollars
escaped with a backslash are not delimiters.

    # in text with LaTeX mathematics as TeXmacs markup:
    def tm_with_math(s):
        """TeXmacs markup for text with LaTeX math ($...$): the math is kept as
        LaTeX, set in TeXmacs as typewriter text and in HTML as \\(...\\) for
        MathJax."""
        out = []
        for i, part in enumerate(re.split(r"(?<!\\)\$", s)):
            if i % 2 == 0 or not part:
                out.append(tm_escape(tex_text(part)))
            else:
                out.append(f"<specific|texmacs|<verbatim|{tm_escape(part)}>>"
                           f"<specific|html*|\\\\({tm_escape(part)}\\\\)>")
        return "".join(out)

### Dates and versions

Dates are shown as people write them, also when approximate (section 4.4
allows `2019-03`, or a range, of which the start is shown).

    # in a date as readers write it:
    def fmt_date(iso):
        """'2026-06-03' -> '3 June 2026' (approximate dates: '2019-03' -> 'March 2019')."""
        parts = iso.split("/")[0].split("-")
        if len(parts) == 3:
            d = datetime.date.fromisoformat("-".join(parts))
            return f"{d.day} {d.strftime('%B %Y')}"
        if len(parts) == 2:
            return datetime.date(int(parts[0]), int(parts[1]), 1).strftime("%B %Y")
        return parts[0]

The version line tells the reader which version this is: the document
version, its label on the service it was imported from (arXiv's `v4` is
often our version 3, section 4.2), and when it became public, or when it
was written if it was not public at the time; without either date, when it
was deposited, from the inventory.

    # in the line saying which version of a document readers see:
    def version_line(obj, dc, inv, ver):
        """'version 3 (arXiv v4), 27 November 2025'; a version not public at the
        time shows when it was written."""
        label = ""
        for e in obj.get("external", []):
            if e.get("role") == "source" and e.get("label"):
                label = f" ({e['service']} {e['label']})"
        line = f"version {obj['documentVersion']}{label}"
        if date_of(dc, "Available"):
            line += f", {fmt_date(date_of(dc, 'Available'))}"
        elif date_of(dc, "Created"):
            line += f", written {fmt_date(date_of(dc, 'Created'))}, not public at the time"
        else:
            line += f", deposited {fmt_date(inv['versions'][ver]['created'][:10])}"
        return line

Both presentations link a document to arXiv by one identifier, without
version: `arXiv:2607.08385`, linking arXiv's abstract page, which lists
every version. The arXiv version a document version comes from is named
by the version line (`version 1 (arXiv v1)`), so the identifier needs no
version of its own; before, the index showed `arXiv:2607.08385v1` for an
imported paper next to `arXiv:2611.17119` for a related one. The
identifier is that of the record the version was imported from, or else
of a relation to arXiv (section 4.4), as for a paper deposited here and
also posted on arXiv.

    # in the arXiv identifier of a document version:
    def arxiv_id(obj, dc):
        """The arXiv identifier of a version, without version: '2607.08385'."""
        for e in obj.get("external", []):
            if e.get("service") == "arXiv" and "/abs/" in e.get("record", ""):
                return re.sub(r"v\d+$", "", e["record"].rsplit("/abs/", 1)[1])
        for r in dc.get("relatedIdentifiers", []):
            if r["relatedIdentifierType"] == "arXiv":
                return re.sub(r"v\d+$", "", r["relatedIdentifier"].split(":", 1)[1])
        return None

The change note of a version (section 4.3, `changes`) is what the authors
wrote about it. For a version imported from arXiv it is arXiv's comments
on the version, which are often not about a change at all (`61 pages`):
shown bare, they read as a change note. So the note is labelled by what it
is, `arXiv comments: 61 pages`, or `changes: ...` for a note written with
a deposit, in both presentations.

    # in the change note of a version, with what it is:
    def changes_note(obj):
        """'arXiv comments: 61 pages', 'changes: typos corrected', or None."""
        text = obj.get("changes", {}).get("text")
        if not text:
            return None
        arxiv = any(e.get("role") == "source" and e.get("service") == "arXiv" for e in obj.get("external", []))
        return f"{'arXiv comments' if arxiv else 'changes'}: {text}"

The abstract is folded: in TeXmacs a fold, on the web an HTML `details`
element, since the HTML export does not render folds.

    # in a foldable abstract in TeXmacs and HTML:
    def abstract_block(paras):
        # a fold in TeXmacs, a details element in HTML (the exporter has no
        # rendering of folded text)
        body = "\n\n".join(f"        {p}" for p in paras)
        return ("    <specific|texmacs|<\\folded>\n      Abstract\n    <|folded>\n"
                f"{body}\n    </folded>>"
                "<specific|html*|<html-tag|details|<html-tag|summary|Abstract>"
                f"<\\html-div-class|paper-abstract>\n{body}\n    </html-div-class>>>\n\n")

### An entry

An entry is made from the version the collection presents
(section 8.2): the current version as of the pinned head, for a member of
a catalogue, or the last revision, for a member of a selection.
The pin shown is that of the presented version for a selection, and the
member's own pin (the head) for a catalogue. The title links
the landing page, for every document; before, the title of a TeXmacs
document linked its HTML version and the others linked nothing. The
authors are written by the rule of every presentation, `A, B and C`
(`authors_of`, with the names of creators in the
[deposit](13-deposit.md)), and end with a full stop, unless the last
name already ends with one. A TeXmacs document has an HTML
version, and its source is linked twice: TeXmacs' HTML export rewrites
links to `.tm` files into links to `.html` files, so the web gets a link
to a `.texmacs` name, which the export turns back into `.tm`. A LaTeX
source is linked as such, and the PDF is the one named among the
renditions, if any. The arXiv identifier gives a link to arXiv. The
change note of the version, labelled, follows the dates.

    # in the TeXmacs index entry of a member:
    def index_entry(member):
        obj_id = names.object_id(member["name"], member["owner"])
        d, at, label = obj_dir(obj_id), path_of(obj_id), label_of(obj_id) or member["name"]
        inv = load_inventory(d)
        ver = presented_version(member, d, inv)
        pin_ver, pin = member_pins(member)[-1][:2]
        obj = read_json(d, inv, OBJ, ver)
        dc = read_json(d, inv, "datacite.json", ver)
        pdf = content_path(inv, ver, pdf_of(obj)) if pdf_of(obj) else None
        src = f"ocfl/{at}/" + content_path(inv, ver, obj["mainSource"]) if obj.get("mainSource") else None
        html = f"site/{label}/{label}.html"
        texmacs = obj.get("sourceFormat") == "application/x-texmacs"
        title = tm_with_math(dc["titles"][0]["title"])
        authors = tm_escape(authors_of(dc))
        if not authors.endswith("."):
            authors += "."
        links = [f"<hlink|PDF|ocfl/{at}/{pdf}>"] if pdf else []
        if texmacs:
            # links to .tm files become .html links in the HTML export; the source
            # is linked once for TeXmacs and once (.texmacs, exported as .tm) for HTML
            links = [f"<hlink|HTML|{html}>"] + links + [
                f"<specific|texmacs|<hlink|TeXmacs source|{src}>><specific|html*|<hlink|TeXmacs"
                f" source|{src[:-3]}.texmacs>>"]
        elif src:
            links.append(f"<hlink|LaTeX source|{src}>")
        arxiv = arxiv_id(obj, dc)
        if arxiv:
            links.append(f"<hlink|arXiv:{arxiv}|https://arxiv.org/abs/{arxiv}>")
        paras = []
        for desc in dc.get("descriptions", []):
            if desc["descriptionType"] == "Abstract":
                paras = [tm_with_math(" ".join(p.split())) for p in desc["description"].split("\n\n")]
        abstract = abstract_block(paras) if paras else ""
        first = date_of(dc, "Issued")
        when = (f"first issued {fmt_date(first)}; " if first else "") + version_line(obj, dc, inv, ver)
        if changes_note(obj):
            when += f"<next-line>{tm_escape(changes_note(obj))}"
        sep = " \\<cdot\\> "
        head = f"<hlink|{title}|paper/{label}/>"
        return f"""  <\\notes-news-item>
        <with|font-series|bold|{head}>

        By {authors}

        {sep.join(links)}

    {abstract}    <with|font-size|0.84|par-mode|left|{when}<next-line>pin:
        <hlink|<verbatim|{pin[:32]}...>|ocfl/{at}/{pin_ver}/inventory.json>>
      </notes-news-item>"""
