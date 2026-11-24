Description-only versions and completions
=========================================

A document version, once deposited, never changes: its files are fixed by
their digests, and anyone who pinned it can check that. Yet much of what
one wants to say about a version comes later: that it was published in a
journal (a DOI), that its licence was opened, that a theorem in it is
wrong, that the whole paper is retracted. OpenSheaf says these things with
*description-only versions* (section 4.2): new object versions that hold
the same document version, with the same files, and change only
`datacite.json`, the state of the object, or its notices.

This chapter defines the general mechanism and the commands built on it:
`osheaf notice`, `withdraw`, `relate`, `relicense` and `describe`. It ends with
`osheaf complete`, which is not description-only (it adds files) but is
the other way a document version changes without getting a new number.
The functions rely on the [history and notices](11-versions.md) being
carried forward, as in a [deposit](13-deposit.md).

    # in description-only versions and the commands that make them:
    <<add a description-only version of a document>>


    <<a note from a text and a file>>


    <<add a notice about a document version>>


    <<withdraw a document>>


    <<complete a document version deposited without sources>>


    <<relate a document to the same work elsewhere>>


    <<change the licence of a document>>


    <<correct the title, abstract, keywords or authors of a document>>

The mechanism
-------------

A description-only version starts from the head: its files are taken over
unchanged, as they are stored (no copy is made, since `add_version()` finds
their digests in the manifest). The command changes the two descriptions
through a function `change(dc, obj)` it passes in, which may also stop with
a message (a document withdrawn twice). The document version stays, and
the `Updated` date says when its description last changed (section 4.4).
Files may be added, but only new ones: the file of a notice, the statement
of a withdrawal. The message of the inventory may be a function, called
after the change, for a command whose message depends on what changed.

The head holds the current version except after an earlier version was
deposited later, or completed; the specification allows a description-only
version of any document version, and tools otherwise hold the current one
(section 4.2). These tools always describe the version of the head. The
document is named by its label; the genesis record goes over with the other
files of the head, byte for byte, and `previous` is set when the version is
added. Like every new version, it is signed, and stops before extending
versions that are not signed unless `acknowledged` (`--i-know`,
section 7.3); the discovery document is then rewritten (section 3.1).

    # in add a description-only version of a document:
    def description_version(label, change, message, add_files=None, acknowledged=False):
        """Add a description-only version of the document LABEL: the files of the
        head (and ADD_FILES, {logical path: file}, such as the file of a notice),
        with datacite.json and object.json changed by CHANGE(dc, obj). The
        document version stays; datacite.json gets the Updated date."""
        obj_id = resolve(label)
        d = obj_dir(obj_id)
        inv = load_inventory(d)
        if inv is None:
            sys.exit(f"no object {label}")
        state = {p: dg for dg, ps in inv["versions"][inv["head"]]["state"].items() for p in ps}
        dc = read_json(d, inv, "datacite.json")
        prev = read_json(d, inv, OBJ)
        if prev["kind"] != "document":
            sys.exit(f"{label} is not a document")
        obj = json.loads(json.dumps(prev))
        change(dc, obj)
        set_date(dc, "Updated", TODAY)
        carry_forward(prev, obj, inv, next_object_version(inv))
        files = {p: content_file(d, inv["manifest"][dg][0]) for p, dg in state.items() if p not in ("datacite.json", OBJ)}
        for lp, f in (add_files or {}).items():
            if lp in files:
                sys.exit(f"{label} has a file {lp} already")
            files[lp] = Path(f)
        files["datacite.json"] = json_bytes(dc)
        inv = add_version(obj_id, files, obj, message() if callable(message) else message,
                          acknowledged=acknowledged)
        write_discovery()
        return inv

The commands pass on whether the depositor gave `--i-know`.

    # in add a description-only version of a document:
    def ack(args):
        return bool(getattr(args, "i_know", False))

Notices, withdrawals and change notes are *notes* (section 4.3): a short text,
for feeds, indexes and services, or a file of the content with the full
statement (with mathematics, or a PDF), or both. The file is stored under a
folder named after its use (`notices/`, `withdrawal/`) to keep it apart
from the sources.

    # in a note from a text and a file:
    def note_from(text, file, folder):
        """A note (section 4.3): a text, a file of the content, or both."""
        note, add = {}, {}
        if text:
            note["text"] = text
        if file:
            f = Path(file)
            lp = f"{folder}/{f.name}"
            note["path"] = lp
            note["mediaType"] = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain",
                                 ".html": "text/html"}.get(f.suffix.lower(), "application/octet-stream")
            add[lp] = f
        if not note:
            sys.exit("a note needs a text, a file, or both")
        return note, add

The commands
------------

### Notices

A notice is about one document version, possibly not the current one ("the
proof of Lemma 3 in version 2 is incomplete; see version 3"). It is
appended to the notices of the head, which every later object version
keeps unchanged and in order (section 4.2), so that its position is its
number: notice 1, 2, ... of the line. A notice is never edited: a later
notice corrects or withdraws it by naming its number in `replaces`
(`--replaces`), and must then be about the same document version; a notice
is replaced at most once. Its `date` is the date its author issued it,
today unless `--date` says otherwise: a date, `YYYY-MM-DD`, as the schema
requires of `notices`, `withdrawal` and `agreement`; any other value
stops the command (`iso_date`, with the [dates of the index](16-index.md)).

    # in add a notice about a document version:
    def notice(args):
        """A notice about a document version (section 4.2), by a description-only
        version: kept, unchanged, in every later object version."""
        d = obj_dir(resolve(args.id))
        inv = load_inventory(d)
        if inv is None:
            sys.exit(f"no object {args.id}")
        numbers = {doc_version_of(d, inv, v) for v in inv["versions"]}
        if args.about not in numbers:
            sys.exit(f"{args.id} has no document version {args.about}")
        note, add = note_from(args.text, args.file, "notices")
        note.update(documentVersion=args.about, date=iso_date(args.date))
        earlier = read_json(d, inv, OBJ).get("notices", [])
        r = getattr(args, "replaces", None)
        if r is not None:
            if not 1 <= r <= len(earlier):
                sys.exit(f"{args.id} has no notice {r} (it has {len(earlier)})")
            if earlier[r - 1]["documentVersion"] != args.about:
                sys.exit(f"notice {r} is about document version {earlier[r - 1]['documentVersion']}, "
                         f"not {args.about}: a notice replaces one about the same version (section 4.2)")
            if any(x.get("replaces") == r for x in earlier):
                sys.exit(f"notice {r} is already replaced (section 4.2)")
            note["replaces"] = r

        def change(dc, obj):
            obj["notices"] = obj.get("notices", []) + [note]
        inv = description_version(args.id, change, args.message or
                                  f"Notice about document version {args.about} (description-only version)", add, ack(args))
        print(f"{args.id}: {inv['head']} (notice {len(earlier) + 1}, about version {args.about}"
              + (f", replacing notice {r})" if r is not None else ")"))

### Withdrawal

Withdrawal (section 13.1) retracts a document: it is not a deletion. The
content stays, the history remains verifiable, and readers see the
withdrawal with the document. The status belongs to the object, whatever
version its head holds; the date is written twice, in `object.json` and as
the `Withdrawn` date of `datacite.json`, and the two must agree. The
withdrawal covers the versions deposited so far; the description-only
versions after it (notices, relations) keep it, and a new document version
(see the [deposit](13-deposit.md)) reinstates the document, the versions
withdrawn staying withdrawn.

    # in withdraw a document:
    def withdraw(args):
        """Withdraw a document (section 13.1): a description-only version with the
        status withdrawn, the reason, and the Withdrawn date in datacite.json. The
        content stays."""
        reason, add = note_from(args.reason, args.file, "withdrawal")
        date = iso_date(args.date)

        def change(dc, obj):
            if obj.get("status") == "withdrawn":
                sys.exit(f"{args.id} is withdrawn already")
            obj["status"] = "withdrawn"
            obj["withdrawal"] = {"date": date, "reason": reason}
            set_date(dc, "Withdrawn", date)
        inv = description_version(args.id, change, args.message or "Withdrawal (description-only version)", add, ack(args))
        print(f"{args.id}: {inv['head']} (withdrawn)")

### Relations

A link to the same work elsewhere, added after the deposit: most often the
published article (`IsVersionOf` its DOI, as section 4.4 recommends for a
preprint), or an arXiv version found later. Since the first public
appearance of the work may then turn out to be earlier than recorded, the
same version may correct the `Issued` date.

    # in relate a document to the same work elsewhere:
    def relate(args):
        """Link a document to the same work elsewhere (arXiv identifier or DOI)."""
        kind, _, value = args.to.partition(":")
        if kind not in ("arxiv", "doi") or not value:
            sys.exit("--to must be arxiv:ID or doi:DOI")
        rel = {"relatedIdentifier": f"arXiv:{value}" if kind == "arxiv" else value,
               "relatedIdentifierType": "arXiv" if kind == "arxiv" else "DOI",
               "relationType": args.relation}

        def change(dc, obj):
            rels = dc.setdefault("relatedIdentifiers", [])
            if any(r["relatedIdentifier"] == rel["relatedIdentifier"] for r in rels):
                sys.exit(f"{args.id} already relates to {rel['relatedIdentifier']}")
            rels.append(rel)
            if args.issued:
                set_date(dc, "Issued", args.issued)
        inv = description_version(args.id, change, args.message or
                                  f"Related: {args.relation} {rel['relatedIdentifier']} (description-only version)", None, ack(args))
        print(f"{args.id}: {inv['head']} ({args.relation} {rel['relatedIdentifier']})")

### Licences

Changing the licence of a document (typically from "All rights reserved"
to a Creative Commons licence) changes no file: the content is the same,
and only its terms change. The authors' agreement is recorded with it, in
`object.json` (section 4.3), with the names of the creators. The licence
is given as to a deposit: a licence known by its SPDX key, or a statement.

    # in change the licence of a document:
    def relicense(args):
        """A description-only version with a new licence in datacite.json and the
        authors' agreement in object.json."""
        new = rights_list(check_rights(args.rights))[0]

        def change(dc, obj):
            if dc.get("rightsList") == [new]:
                sys.exit(f"{args.id} already has {args.rights}")
            dc["rightsList"] = [new]
            obj["agreement"] = {"by": [c["name"] for c in dc["creators"]],
                                "date": iso_date(args.date), "method": args.method}
        inv = description_version(args.id, change, args.message or
                                  f"Licence: {new['rights']} (description-only version; content unchanged)", None, ack(args))
        print(f"{args.id}: {inv['head']} ({new['rights']})")

### Corrections of the description

A title with a typing mistake, an abstract whose TeX the arXiv import did
not understand, a name recorded with initials only: the description of a
version may be wrong where its files are right. Section 7.3 allows exactly
this: a description-only version that changes `datacite.json` and nothing
else. `osheaf describe` writes one, with the fields given replaced and
every other field kept:

- `--title`: the main title (the first of `titles`; other titles, such
  as a subtitle, stay);
- `--abstract` or `--abstract-file`: the description of type `Abstract`,
  plain text with mathematics between dollars (section 4.4), paragraphs
  separated by blank lines; the other descriptions, such as the journal
  reference of an arXiv import (`SeriesInformation`), stay;
- `--keyword`, repeated: the keywords, which replace the subjects without
  a scheme, those a deposit writes; subjects with a scheme (the arXiv
  categories of an import) are not keywords of the depositor's, and stay;
- `--author`, repeated: the creators, as in a deposit (`"Family,
  Given|Affiliation"`), replacing the list whole, so that an affiliation
  not given again is dropped.

The message of the inventory says what was corrected, which is known
only once `change` has compared the fields: it is passed as a function,
called by `description_version` after the change. A correction that
corrects nothing is refused, so that the history of the
object does not fill with versions that say nothing: each field given is
compared with the one recorded. The text is taken exactly as given, with
no conversion from TeX: what the depositor writes is what readers see.

    # in correct the title, abstract, keywords or authors of a document:
    def describe(args):
        """Correct the description of a document (title, abstract, keywords,
        authors) by a description-only version (section 4.2)."""
        if args.abstract is not None and args.abstract_file:
            sys.exit("describe: give --abstract or --abstract-file, not both")
        abstract = (Path(args.abstract_file).read_text(encoding="utf-8") if args.abstract_file
                    else args.abstract)
        abstract = abstract.strip() if abstract is not None else None
        if args.title is not None and not args.title.strip() or abstract == "":
            sys.exit("describe: a title or an abstract cannot be empty")
        changed = []

        def change(dc, obj):
            if args.title is not None and args.title.strip() != dc["titles"][0]["title"]:
                dc["titles"][0]["title"] = args.title.strip()
                changed.append("title")
            if abstract is not None:
                descs = dc.setdefault("descriptions", [])
                old = next((x for x in descs if x["descriptionType"] == "Abstract"), None)
                if old is None:
                    descs.insert(0, {"description": abstract, "descriptionType": "Abstract"})
                    changed.append("abstract")
                elif old["description"] != abstract:
                    old["description"] = abstract
                    changed.append("abstract")
            if args.keyword:
                subjects = dc.get("subjects", [])
                if [x["subject"] for x in subjects if not x.get("subjectScheme")] != args.keyword:
                    dc["subjects"] = [{"subject": k} for k in args.keyword] + \
                        [x for x in subjects if x.get("subjectScheme")]
                    changed.append("keywords")
            if args.author:
                creators = [creator(a) for a in args.author]
                if creators != dc["creators"]:
                    dc["creators"] = creators
                    changed.append("authors")
            if not changed:
                sys.exit(f"{args.id}: nothing to change in the description")
        inv = description_version(args.id, change, args.message or (
            lambda: f"Description corrected: {', '.join(changed)} (description-only version)"), None, ack(args))
        print(f"{args.id}: {inv['head']} ({', '.join(changed)} corrected)")

Completing a version without sources
------------------------------------

A version deposited without its sources (from arXiv, which keeps only the
PDF of some versions, say) may get them later, keeping its number
(section 4.2, "Completion"). The completing object version starts from the
*last object version holding that document version*, not from the head,
since the head may hold another document version; it adds the sources and
changes nothing else, so that [verification](17-verify.md) can check that
only files were added. `sourcesMissing` gives way to the main source and
its format, which is also added to the `formats` of `datacite.json`.

The notices and the history are those of the head: the old `object.json`
loses its own, and `carry_forward` puts back the current ones, replacing
the history's entry for the completed version. The state of the object is
also the head's, since it belongs to the object whatever version is held
(section 13.1): completing an earlier version of a withdrawn document keeps
the withdrawal, with its `Withdrawn` date in `datacite.json` and the file
of its reason, if any. Everything else comes from the completed version.
The new object version becomes the head without a history if the document
had none; the order of the numbers stays the order of the work, and the
[current version](11-versions.md) stays the highest document version.

Completion only adds files: the PDF received is kept, and the archive does
not typeset the added sources.

    # in complete a document version deposited without sources:
    def complete(args):
        """Add the sources of a document version recorded without them
        (sourcesMissing, section 4.2): a new object version holding the files of
        that document version and the sources; its number stays."""
        obj_id = resolve(args.id)
        d = obj_dir(obj_id)
        inv = load_inventory(d)
        if inv is None:
            sys.exit(f"no object {args.id}")
        last = None
        for v in inv["versions"]:
            if doc_version_of(d, inv, v) == args.version:
                last = v
        if last is None:
            sys.exit(f"{args.id} has no document version {args.version}")
        obj = read_json(d, inv, OBJ, last)
        if not obj.get("sourcesMissing"):
            sys.exit(f"{args.id}: document version {args.version} has its sources already")
        head = read_json(d, inv, OBJ)
        dc = read_json(d, inv, "datacite.json", last)
        state = {p: dg for dg, ps in inv["versions"][last]["state"].items() for p in ps}
        files = {p: content_file(d, inv["manifest"][dg][0]) for p, dg in state.items() if p not in ("datacite.json", OBJ)}
        source = Path(args.source)
        main = source.name
        for lp, f in [(main, source)] + [(x.partition("=")[2] or Path(x.partition("=")[0]).name,
                                          Path(x.partition("=")[0])) for x in args.extra_source or []]:
            if lp in files:
                sys.exit(f"{args.id}: version {args.version} has a file {lp} already (completing only adds files)")
            if not f.is_file():
                sys.exit(f"no file {f}")
            files[lp] = f
        obj.pop("sourcesMissing")
        obj["mainSource"] = main
        obj["sourceFormat"] = args.source_format or SOURCE_FORMATS.get(source.suffix.lower(), "application/octet-stream")
        obj.pop("notices", None)
        obj.pop("history", None)
        carry_forward(head, obj, inv, next_object_version(inv))
        obj.pop("withdrawal", None)
        obj["status"] = head["status"]           # the state of the object is the head's
        if head.get("withdrawal"):
            obj["withdrawal"] = head["withdrawal"]
            set_date(dc, "Withdrawn", head["withdrawal"]["date"])
            if head["withdrawal"]["reason"].get("path"):
                lp = head["withdrawal"]["reason"]["path"]
                files.setdefault(lp, read_logical(d, inv, lp))
        set_date(dc, "Updated", TODAY)
        fmt = obj["sourceFormat"]
        if fmt not in dc.get("formats", []):
            dc["formats"] = [fmt] + dc.get("formats", [])
        files["datacite.json"] = json_bytes(dc)
        for lp, f in carried_files(obj_id, inv).items():     # notice files are kept
            files.setdefault(lp, f)
        inv = add_version(obj_id, files, obj, args.message or
                          f"Sources of document version {args.version} added (sourcesMissing completed)",
                          acknowledged=getattr(args, "i_know", False))
        write_discovery()
        print(f"{args.id}: {inv['head']} (sources of version {args.version})")
