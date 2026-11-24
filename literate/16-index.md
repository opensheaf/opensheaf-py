The discovery document and the index
====================================

After deposits and new versions of the [owner catalogues](15-owner-catalogues.md),
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
the profiles, the owners it hosts, each with its owner catalogue (section
8.1), in the order in which the index presents them, and a list of every
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
Three things in it are not in the storage root, and are carried from the
document it replaces: the labels, which `LABELS` holds, the owner
catalogues, which `CATALOGUES` holds, and the tombstones
of objects taken down (section 13.3), which `TOMBSTONES` holds, never
removed but when the line returns ([takedowns](25-takedown.md)). Version
0.1 had `archiveId`, `mirrorOf` and `mirrors`; version 0.2 names no
archive, and a mirror is listed like any line (section 11). The first
drafts of 0.2 had `mainCollection`, the one catalogue of the archive,
which `owners`, naming each owner with its catalogue, has replaced (#72);
`owners` is always written (section 3.1 requires it); an owner whose
catalogue is not made yet (between its key log and its
catalogue, when it is set up) is left out of `owners` until it is. `indexes`
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
        hosted = [{"owner": o, "catalogue": CATALOGUES[o]} for o in archive_owners() if o in CATALOGUES]
        doc.update(profiles=ARCHIVE["profiles"], extensions=sorted(used), owners=hosted,
                   indexes=dict(INDEXES), objects=objs)
        if drafts:
            doc["drafts"] = drafts
        if TOMBSTONES:
            doc["tombstones"] = TOMBSTONES
        return doc


    def write_discovery():
        """Write the discovery document opensheaf.json, its pages of objects and the indexes from the
        storage root."""
        refuse_unread_pages()
        write_indexes()
        doc = discovery()
        pages = object_pages(doc["objects"])
        folder = ROOT / OBJECT_PAGES
        if folder.is_dir():
            for f in folder.glob("*.json"):
                if f"{OBJECT_PAGES}/{f.name}" not in pages:
                    unlinked(f).unlink()
            if not any(folder.iterdir()):
                folder.rmdir()
        if pages:
            for path, entries in pages.items():
                write_json(ROOT / path, {"format": "opensheaf-objects/0.2", "objects": entries})
            doc = {("objectPages" if k == "objects" else k): (list(pages) if k == "objects" else v)
                   for k, v in doc.items()}
        write_json(ROOT / "opensheaf.json", doc)

Pages
-----

An archive with many objects lists them in pages (section 3.1): in place
of `objects`, `objectPages` lists the paths of page files, each with
`format` `"opensheaf-objects/0.2"` and its entries. These tools page
beyond `OBJECTS_PER_PAGE` objects, a thousand, as the specification
advises, in `objects/<p>.json`, `<p>` being the shortest prefix of the
names that keeps every page within a thousand entries, as far as the names
allow: names are digests, so objects spread evenly, and a deposit rewrites
one page. Pages no longer written are removed.

    # in write the discovery document of the archive:
    OBJECTS_PER_PAGE = 1000
    OBJECT_PAGES = "objects"


    def object_pages(objs):
        """The pages of the entries OBJS (section 3.1), {path: entries}; {} when they are not paged."""
        if len(objs) <= OBJECTS_PER_PAGE:
            return {}
        for k in range(1, 53):
            groups = {}
            for o in objs:
                groups.setdefault(o["name"][:k], []).append(o)
            if max(len(g) for g in groups.values()) <= OBJECTS_PER_PAGE:
                break
        return {f"{OBJECT_PAGES}/{p}.json": groups[p] for p in sorted(groups)}

Every reader of a discovery document takes its entries through
`listed_objects`, which reads the pages when it has them, with `read`
giving the bytes of a path relative to the document (or None); a page
missing, or not a page, is a `ValueError`. A path of a page stays below
the document: relative, without `.`, `..` or a scheme.

    # in write the discovery document of the archive:
    def page_path_ok(path):
        return (owners.safe_relative(path) and path.endswith(".json")
                and ":" not in path.split("/")[0])


    def listed_objects(disc, read):
        """The entries of objects of the discovery document DISC (section 3.1), from its pages if it
        pages them, READ(path) giving the bytes of a page or None; ValueError if a page is not found."""
        if "objectPages" not in disc:
            return [o for o in disc.get("objects") or [] if isinstance(o, dict)]
        out = []
        for path in disc.get("objectPages") or []:
            if not page_path_ok(path):
                raise ValueError(f"{path!r} is not the path of a page below the discovery document (section 3.1)")
            data = read(path)
            if data is None:
                raise ValueError(f"the page of objects {path} is missing (section 3.1)")
            try:
                page = json.loads(data)
            except ValueError:
                raise ValueError(f"the page of objects {path} is not JSON") from None
            if not isinstance(page, dict) or not isinstance(page.get("objects"), list):
                raise ValueError(f"{path} is not a page of objects (section 3.1)")
            out += [o for o in page["objects"] if isinstance(o, dict)]
        return out


    def local_page(path):
        f = ROOT / path
        return f.read_bytes() if page_path_ok(path) and f.is_file() else None

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
                    unlinked(p).unlink()
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

`osheaf index` writes the discovery document and the indexes, and then the
readable index, if one is configured. With a website, it hands the members
of the owner catalogues to the [website](30-website.md); with a TeXmacs
template, it has the website write the landing pages, the owner pages and
the sitemap without a home page (`home=False`), writes `index.tm` and,
unless `--no-html`, exports it to `index.html` with TeXmacs (the PDF export,
needed to typeset it, goes to a scratch folder). The landing pages are at
`paper/<label>/`, apart from the HTML versions of TeXmacs documents in
`site/<label>/`, and the `index.html` of TeXmacs is never overwritten by
the website. The empty file `.texmacs-noconvert` tells TeXmacs' website
converter not to touch the archive's files (appendix A.2).

    # in write the discovery document and the index:
    def index(args):
        write_discovery()
        if INDEX.get("html") or INDEX.get("template"):
            readable_index(args)
            return
        print("opensheaf.json and the indexes written (no readable index configured)")

The members presented are those of the owner catalogues, in the order of
the owners (appendix A.3), each read from the latest signed version of its
catalogue, not from its head: nothing relies on a version that is not
signed (section 7.3). An owner catalogue without a signed version (its
owner's keys all exposed since) presents none of its members, and the
command says so; an archive none of whose catalogues has a signed version
presents nothing. The members are given by owner, for a home page that
groups them so (`catalogue_groups`), or in one list.

    # in write the discovery document and the index:
    def catalogue_groups():
        """[(owner, members of the latest signed version of its owner catalogue)], in the order of the
        owners, or None when no owner catalogue has a signed version."""
        out = []
        for owner in archive_owners():
            cid = CATALOGUES.get(owner)
            d = obj_dir(cid) if cid else None
            inv = load_inventory(d) if d else None
            if inv is None:
                continue
            ver = latest_signed(d, inv)
            if ver is None:
                print(f"warning: the owner catalogue of {names.short(owner)} has no signed version "
                      "(section 7.3): none of its members is presented", file=sys.stderr)
                continue
            out.append((owner, read_json(d, inv, "members.json", ver)["members"]))
        return out or None


    def catalogue_members():
        """The members of the owner catalogues in one list, in the order of the owners, or None."""
        groups = catalogue_groups()
        return None if groups is None else [m for _, ms in groups for m in ms]

With `index.html.featured` set to the label of a collection of the
archive, the home page lists that collection first (a reading list, a
journal's issues), then the owner catalogues; a setting that names something
else stops the command. `index.owners` says how the home page of an
archive with several owners presents the owner catalogues (appendix A.3):
`together` (the default), in one list, or `by-owner`, under a heading for
each owner ([website](30-website.md)); another value stops the command. A
TeXmacs index lists them together, in the order of the owners.

Only members held here can be shown in a TeXmacs index: its entries are
read from the local storage root. A curated owner catalogue with members of
other archives needs the website, and the members held elsewhere are left
out of `index.tm`, with a warning.

    # in write the discovery document and the index:
    def readable_index(args):
        """The website, or the TeXmacs index with the landing pages of the website."""
        from . import html
        groups = catalogue_groups()
        if groups is None:
            return
        members = [m for _, ms in groups for m in ms]
        if INDEX.get("owners", "together") not in ("together", "by-owner"):
            sys.exit(f"osheaf.json: index.owners is together or by-owner, not {INDEX['owners']}")
        if INDEX.get("html"):
            featured = INDEX["html"].get("featured") if isinstance(INDEX["html"], dict) else None
            fid = None
            if featured:
                fid = LABELS.get(featured)
                if fid is None:
                    sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not a label of this "
                             "archive")
                fd = obj_dir(fid)
                if (read_json(fd, load_inventory(fd), OBJ) or {}).get("kind") != "collection":
                    sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not a collection")
            pages = html.render(members, featured=fid, groups=groups)
            print(f"Done: opensheaf.json, index.html, {plural(pages, 'landing page')} and sitemap.xml written.")
            return
        template = (ROOT / INDEX["template"]).read_text(encoding="latin-1")
        line = "  <paper-index>\n"
        if template.count(line) != 1:
            sys.exit(f"{INDEX['template']} must contain one paragraph <paper-index>")
        pages = html.render(members, home=False)
        here = [m for m in members if html.held(m)]
        if len(here) < len(members):
            print(f"Warning: {plural(len(members) - len(here), 'member')} held in other archives "
                  f"{'is' if len(members) - len(here) == 1 else 'are'} left out of index.tm (the website shows "
                  "them).", file=sys.stderr)
        entries = "\n\n".join(index_entry(m) for m in here)
        with open(unlinked(ROOT / "index.tm"), "w", encoding="latin-1", newline="") as f:
            f.write(template.replace(line, entries + "\n"))
        unlinked(ROOT / ".texmacs-noconvert").touch()
        if not getattr(args, "no_html", False):
            unlinked(ROOT / "index.html")
            scratch = Path(tempfile.mkdtemp())
            run_texmacs(export_calls(ROOT / "index.tm", pdf=scratch / "index.pdf",
                                     html=ROOT / "index.html"))
            shutil.rmtree(scratch, ignore_errors=True)
        print("Done: opensheaf.json, index.tm" + ("" if getattr(args, "no_html", False) else ", index.html")
              + f", {plural(pages, 'landing page')} and sitemap.xml written.")

The presentation files are regenerated after every change (appendix A.3),
not only by `osheaf index`: the [command line](60-command-line.md) calls
`present` after each command that changes the archive. It writes what is
quick to write: the whole website, or, for a TeXmacs index, the landing
pages, the owner pages and the sitemap, leaving `index.tm` and its export,
which need TeXmacs, to `osheaf index`. A failure there does not undo the
change, which is already made, and does not make the command fail: it is
reported, and `osheaf index` writes the pages again.

    # in write the discovery document and the index:
    def present():
        """Regenerate the presentation files after a change (appendix A.3), if any are configured."""
        if not (INDEX.get("html") or INDEX.get("template")) or OLD:
            return
        from . import html
        try:
            members = catalogue_members()
            if members is None:
                return
            if INDEX.get("html"):
                readable_index(argparse_namespace(no_html=True))
            else:
                html.render(members, home=False)
        except (Exception, SystemExit) as e:  # noqa: BLE001 - the change is made; index writes the pages again
            print(f"warning: the website was not regenerated ({e}); run osheaf index", file=sys.stderr)

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
allows `2019-03`, or a range, of which the start is shown). DataCite also
allows a date with a time (`2026-06-03T10:00:00Z`), of which the date is
shown; a date in no form it knows is shown as it is written, never
stopping the page that shows it.

    # in a date as readers write it:
    DATE_SHOWN = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2})(?:T.*)?)?)?", re.S)


    def fmt_date(iso):
        """'2026-06-03' -> '3 June 2026' (approximate dates: '2019-03' -> 'March 2019'; with a
        time, its date; in another form, as it is)."""
        text = str(iso)
        m = DATE_SHOWN.fullmatch(text.split("/")[0].strip())
        if not m:
            return text
        year, month, day = m.groups()
        try:
            if day:
                d = datetime.date(int(year), int(month), int(day))
                return f"{d.day} {d.strftime('%B %Y')}"
            if month:
                return datetime.date(int(year), int(month), 1).strftime("%B %Y")
        except ValueError:
            return text
        return year


    def iso_date(text, option="--date"):
        """The date TEXT, given with OPTION, as YYYY-MM-DD (default: today); stops on any other."""
        if text is None or text == "":
            return TODAY
        if isinstance(text, datetime.date) and not isinstance(text, datetime.datetime):
            return text.isoformat()
        try:
            if isinstance(text, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return datetime.date.fromisoformat(text).isoformat()
        except ValueError:
            pass
        sys.exit(f"{option}: a date, YYYY-MM-DD, not {text!r}")

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
        d, at, label = obj_dir(obj_id), path_of(obj_id), page_address(obj_id)
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
