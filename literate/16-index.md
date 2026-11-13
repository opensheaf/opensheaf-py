The discovery document and the index
====================================

After deposits and a new version of the [main collection](15-main-collection.md),
`osheaf index` writes what the outside world reads: the *discovery
document* `opensheaf.json`, the entry point of the archive for programs,
and an index for people. The index is made in one of two ways. An archive
with a website (the website profile, appendix C) has it written by the
[website](30-website.md) module, with a landing page per document. An
archive kept inside a TeXmacs website (as the first OpenSheaf archive is)
instead has an index written as a TeXmacs document, from a template, and
exported to HTML by TeXmacs. This chapter is the discovery document and the
TeXmacs index.

The discovery document
----------------------

The discovery document (section 6.1) says what the archive is and where
its objects are: its identifier, name and contact, the storage root and
its layout, the main collection, the profiles, and a list of every object
of the storage root with its kind, head version, the digest of its head
inventory and its status. The list is a map, not a witness: a reader can
check every entry against the storage root, and
[verification](17-verify.md) does. The digest is read from the sidecar
file, as the specification says ("as written in its checksum file").

The discovery document is rewritten whole every time, from the storage
root, so that it cannot drift. A [mirror](21-mirrors.md) of another
archive's object is listed like the others, with `mirrorOf`, the
identifier of the archive whose object it copies (sections 6.1 and 10.4),
recognised as in the [main collection](15-main-collection.md) by the
archive its head names. The optional parts (`mirrors`, `tombstones`,
`keys`, `feed`) are not written: an archive that has them adds them by
other means.

    # in write the discovery document of the archive:
    def discovery():
        objs = []
        for obj_id, d, inv in objects():
            obj = read_json(d, inv, OBJ)
            entry = {"id": obj_id, "kind": obj["kind"], "head": inv["head"],
                     "inventorySha512": (d / "inventory.json.sha512").read_text().split()[0],
                     "status": obj["status"]}
            if mirror_of(d, inv):
                entry["mirrorOf"] = mirror_of(d, inv)
            objs.append(entry)
        return {"format": "opensheaf-archive/0.1", "specification": SPEC,
                "archiveId": ARCHIVE["archiveId"], "name": ARCHIVE["name"],
                "contact": ARCHIVE["contact"], "storageRoot": "ocfl/", "storageLayout": LAYOUT,
                "mainCollection": ARCHIVE["mainCollection"], "profiles": ARCHIVE["profiles"],
                "objects": objs}

The TeXmacs index
-----------------

The TeXmacs index is a TeXmacs document, `index.tm`, made from a template
of the archive (`index.template` in the configuration) by replacing its
paragraph `<paper-index>` with one entry per member of the main
collection, in the order of the collection. The entries use the `notes`
plugin's news items, so the template must use that style. Each entry shows
the title (linking the TeXmacs source in TeXmacs, the HTML version on the
web), the authors, the links to the renditions and sources, the abstract,
the dates, and the pin: the beginning of the digest of the inventory,
linked to that inventory, so that a reader can check what the collection
pins.

    # in write the TeXmacs index of the archive:
    <<TeX accents and special letters as Unicode>>


    <<convert TeX accents in a text to Unicode>>


    <<plain text as a TeXmacs string>>


    <<text with LaTeX mathematics as TeXmacs markup>>


    <<a date as readers write it>>


    <<the line saying which version of a document readers see>>


    <<a foldable abstract in TeXmacs and HTML>>


    <<the TeXmacs index entry of a member>>


    <<write the discovery document and the index>>

### The command

`osheaf index` always writes the discovery document. Then, with a website
configured, it hands the members to the [website](30-website.md); with a
TeXmacs template, it writes `index.tm` and, unless `--no-html`, exports it
to `index.html` with TeXmacs (the PDF export, needed to typeset it, goes to
a scratch folder). The empty file `.texmacs-noconvert` tells TeXmacs'
website converter not to touch the archive's files (appendix B).

Only members of the archive itself can be shown this way: the entries are
read from the local storage root. A curated main collection with members
of other archives needs the website.

    # in write the discovery document and the index:
    def index(args):
        write_json(ROOT / "opensheaf.json", discovery())
        coll_dir = OCFL / ARCHIVE["mainCollection"]
        inv = load_inventory(coll_dir)
        members = json.loads(read_logical(coll_dir, inv, "members.json").read_text())["members"]
        if INDEX.get("html"):
            from . import html
            html.render(members)
            local = sum(1 for m in members if m.get("archive") == ARCHIVE["archiveId"])
            print(f"opensheaf.json, index.html, {local} landing pages and sitemap.xml written")
            return
        if not INDEX.get("template"):
            print("opensheaf.json written (no index configured)")
            return
        template = (ROOT / INDEX["template"]).read_text(encoding="latin-1")
        line = "  <paper-index>\n"
        if template.count(line) != 1:
            sys.exit(f"{INDEX['template']} must contain one paragraph <paper-index>")
        entries = "\n\n".join(index_entry(m) for m in members)
        with open(ROOT / "index.tm", "w", encoding="latin-1", newline="") as f:
            f.write(template.replace(line, entries + "\n"))
        (ROOT / ".texmacs-noconvert").touch()
        if not args.no_html:
            scratch = Path(tempfile.mkdtemp())
            run_texmacs(export_calls(ROOT / "index.tm", pdf=scratch / "index.pdf",
                                     html=ROOT / "index.html"))
            shutil.rmtree(scratch, ignore_errors=True)
        print("opensheaf.json, index.tm" + ("" if args.no_html else " and index.html") + " written")

### Text in TeXmacs

Titles and abstracts are plain text with LaTeX mathematics (section 8), and
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

Dates are shown as people write them, also when approximate (section 8
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
often our version 3, section 7.3), and when it became public, or when it
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
(section 10.2): the current version as of the pinned head, for a member of
an archive collection, or the last revision, for a member of a selection.
The pin shown is that of the presented version for a selection, and the
member's own pin (the head) for an archive collection. A TeXmacs document has an HTML
version, and its source is linked twice: TeXmacs' HTML export rewrites
links to `.tm` files into links to `.html` files, so the web gets a link
to a `.texmacs` name, which the export turns back into `.tm`. A LaTeX
source is linked as such, and the PDF is the one named among the
renditions, if any. An arXiv identifier, from the record the
version was imported from or else from the relations, gives a link to
arXiv. The change note of the version follows the dates.

    # in the TeXmacs index entry of a member:
    def index_entry(member):
        obj_id = member["id"]
        d = OCFL / obj_id
        inv = load_inventory(d)
        ver = presented_version(member, d, inv)
        pin_ver, pin = member_pins(member)[-1][:2]
        obj = read_json(d, inv, OBJ, ver)
        dc = read_json(d, inv, "datacite.json", ver)
        pdf = content_path(inv, ver, pdf_of(obj)) if pdf_of(obj) else None
        src = f"ocfl/{obj_id}/" + content_path(inv, ver, obj["mainSource"]) if obj.get("mainSource") else None
        html = f"site/{obj_id}/{obj_id}.html"
        texmacs = obj.get("sourceFormat") == "application/x-texmacs"
        title = tm_with_math(dc["titles"][0]["title"])
        authors = tm_escape(", ".join(display_name(c) for c in dc["creators"]))
        links = [f"<hlink|PDF|ocfl/{obj_id}/{pdf}>"] if pdf else []
        if texmacs:
            # links to .tm files become .html links in the HTML export; the source
            # is linked once for TeXmacs and once (.texmacs, exported as .tm) for HTML
            links = [f"<hlink|HTML|{html}>"] + links + [
                f"<specific|texmacs|<hlink|TeXmacs source|{src}>><specific|html*|<hlink|TeXmacs"
                f" source|{src[:-3]}.texmacs>>"]
        elif src:
            links.append(f"<hlink|LaTeX source|{src}>")
        arxiv = None
        for e in obj.get("external", []):
            if e.get("service") == "arXiv":
                arxiv = e["record"].rsplit("/abs/", 1)[1]
        for r in dc.get("relatedIdentifiers", []):
            if not arxiv and r["relatedIdentifierType"] == "arXiv":
                arxiv = r["relatedIdentifier"].split(":", 1)[1]
        if arxiv:
            links.append(f"<hlink|arXiv:{arxiv}|https://arxiv.org/abs/{arxiv}>")
        paras = []
        for desc in dc.get("descriptions", []):
            if desc["descriptionType"] == "Abstract":
                paras = [tm_with_math(" ".join(p.split())) for p in desc["description"].split("\n\n")]
        abstract = abstract_block(paras) if paras else ""
        first = date_of(dc, "Issued")
        when = (f"first issued {fmt_date(first)}; " if first else "") + version_line(obj, dc, inv, ver)
        if obj.get("changes", {}).get("text"):
            when += f"<next-line>{tm_escape(obj['changes']['text'])}"
        sep = " \\<cdot\\> "
        head = (f"<specific|texmacs|<hlink|{title}|{src}>><specific|html*|<hlink|{title}|{html}>>"
                if texmacs else title)
        return f"""  <\\notes-news-item>
        <with|font-series|bold|{head}>

        By {authors}.

        {sep.join(links)}

    {abstract}    <with|font-size|0.84|par-mode|left|{when}<next-line>pin:
        <hlink|<verbatim|{pin[:32]}...>|ocfl/{obj_id}/{pin_ver}/inventory.json>>
      </notes-news-item>"""
