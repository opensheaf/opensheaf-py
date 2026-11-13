Description-only versions and completions
=========================================

A document version, once deposited, never changes: its files are fixed by
their digests, and anyone who pinned it can check that. Yet much of what
one wants to say about a version comes later: that it was published in a
journal (a DOI), that its licence was opened, that a theorem in it is
wrong, that the whole paper is retracted. OpenSheaf says these things with
*description-only versions* (section 7.3): new object versions that hold
the same document version, with the same files, and change only
`datacite.json`, the state of the object, or its notices.

This chapter defines the general mechanism and the commands built on it:
`osheaf notice`, `withdraw`, `relate` and `relicense`. It ends with
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

The mechanism
-------------

A description-only version starts from the head: its files are taken over
unchanged, as they are stored (no copy is made, since `add_version()` finds
their digests in the manifest). The command changes the two descriptions
through a function `change(dc, obj)` it passes in, which may also stop with
a message (a document withdrawn twice). The document version stays, and
the `Updated` date says when its description last changed (section 8).
Files may be added, but only new ones: the file of a notice, the statement
of a withdrawal.

The head holds the current version except after an earlier version was
deposited later, or completed; the specification allows a description-only
version of any document version, and tools otherwise hold the current one
(section 7.3). These tools always describe the version of the head.

    # in add a description-only version of a document:
    def description_version(obj_id, change, message, add_files=None):
        """Add a description-only version of document OBJ_ID: the files of the
        head (and ADD_FILES, {logical path: file}, such as the file of a notice),
        with datacite.json and object.json changed by CHANGE(dc, obj). The
        document version stays; datacite.json gets the Updated date."""
        obj_dir = OCFL / obj_id
        inv = load_inventory(obj_dir)
        if inv is None:
            sys.exit(f"no object {obj_id}")
        state = {p: d for d, ps in inv["versions"][inv["head"]]["state"].items() for p in ps}
        dc = read_json(obj_dir, inv, "datacite.json")
        prev = read_json(obj_dir, inv, OBJ)
        if prev["kind"] != "document":
            sys.exit(f"{obj_id} is not a document")
        obj = json.loads(json.dumps(prev))
        change(dc, obj)
        set_date(dc, "Updated", TODAY)
        carry_forward(prev, obj, inv, next_object_version(inv))
        tmp = Path(tempfile.mkdtemp())
        write_json(tmp / "datacite.json", dc)
        write_json(tmp / OBJ, obj)
        files = {p: obj_dir / inv["manifest"][d][0] for p, d in state.items()}
        for lp, f in (add_files or {}).items():
            if lp in files:
                sys.exit(f"{obj_id} has a file {lp} already")
            files[lp] = Path(f)
        files["datacite.json"], files[OBJ] = tmp / "datacite.json", tmp / OBJ
        inv = add_version(obj_id, files, message)
        shutil.rmtree(tmp, ignore_errors=True)
        return inv

Notices, withdrawals and change notes are *notes* (section 9): a short text,
for feeds, indexes and services, or a file of the content with the full
statement (with mathematics, or a PDF), or both. The file is stored under a
folder named after its use (`notices/`, `withdrawal/`) to keep it apart
from the sources.

    # in a note from a text and a file:
    def note_from(text, file, folder):
        """A note (section 9): a text, a file of the content, or both."""
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
keeps unchanged (section 7.3): a notice is never edited, only followed by
another that corrects it.

    # in add a notice about a document version:
    def notice(args):
        """A notice about a document version (section 7.3), by a description-only
        version: kept, unchanged, in every later object version."""
        d = OCFL / args.id
        inv = load_inventory(d)
        if inv is None:
            sys.exit(f"no object {args.id}")
        numbers = {doc_version_of(d, inv, v) for v in inv["versions"]}
        if args.about not in numbers:
            sys.exit(f"{args.id} has no document version {args.about}")
        note, add = note_from(args.text, args.file, "notices")
        note.update(documentVersion=args.about, date=args.date or TODAY)

        def change(dc, obj):
            obj["notices"] = obj.get("notices", []) + [note]
        inv = description_version(args.id, change, args.message or
                                  f"Notice about document version {args.about} (description-only version)", add)
        print(f"{args.id}: {inv['head']} (notice about version {args.about})")

### Withdrawal

Withdrawal (section 11.1) retracts a document: it is not a deletion. The
content stays, the history remains verifiable, and readers see the
withdrawal with the document. The status belongs to the object, whatever
version its head holds; the date is written twice, in `object.json` and as
the `Withdrawn` date of `datacite.json`, and the two must agree. A
withdrawn document gets no new document versions (see the
[deposit](13-deposit.md)), but may still get notices or relations.

    # in withdraw a document:
    def withdraw(args):
        """Withdraw a document (section 11.1): a description-only version with the
        status withdrawn, the reason, and the Withdrawn date in datacite.json. The
        content stays."""
        reason, add = note_from(args.reason, args.file, "withdrawal")
        date = args.date or TODAY

        def change(dc, obj):
            if obj.get("status") == "withdrawn":
                sys.exit(f"{args.id} is withdrawn already")
            obj["status"] = "withdrawn"
            obj["withdrawal"] = {"date": date, "reason": reason}
            set_date(dc, "Withdrawn", date)
        inv = description_version(args.id, change, args.message or "Withdrawal (description-only version)", add)
        print(f"{args.id}: {inv['head']} (withdrawn)")

### Relations

A link to the same work elsewhere, added after the deposit: most often the
published article (`IsVersionOf` its DOI, as section 8.1 recommends for a
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
                                  f"Related: {args.relation} {rel['relatedIdentifier']} (description-only version)")
        print(f"{args.id}: {inv['head']} ({args.relation} {rel['relatedIdentifier']})")

### Licences

Changing the licence of a document (typically from "All rights reserved"
to a Creative Commons licence) changes no file: the content is the same,
and only its terms change. The authors' agreement is recorded with it, in
`object.json` (section 9), with the names of the creators. Only the
licences known by name may be chosen here.

    # in change the licence of a document:
    def relicense(args):
        """A description-only version with a new licence in datacite.json and the
        authors' agreement in object.json."""
        new = RIGHTS[args.rights]

        def change(dc, obj):
            if dc.get("rightsList") == [new]:
                sys.exit(f"{args.id} already has {args.rights}")
            dc["rightsList"] = [new]
            obj["agreement"] = {"by": [c["name"] for c in dc["creators"]],
                                "date": args.date or TODAY, "method": args.method}
        inv = description_version(args.id, change, args.message or
                                  f"Licence: {new['rights']} (description-only version; content unchanged)")
        print(f"{args.id}: {inv['head']} ({new['rights']})")

Completing a version without sources
------------------------------------

A version deposited without its sources (from arXiv, which keeps only the
PDF of some versions, say) may get them later, keeping its number
(section 7.3, "Completion"). The completing object version starts from the
*last object version holding that document version*, not from the head,
since the head may hold another document version; it adds the sources and
changes nothing else, so that [verification](17-verify.md) can check that
only files were added. `sourcesMissing` gives way to the main source and
its format, which is also added to the `formats` of `datacite.json`.

The notices and the history are those of the head: the old `object.json`
loses its own, and `carry_forward` puts back the current ones, replacing
the history's entry for the completed version. The other parts of the
state come from the completed version, not from the head: completing an
earlier version of a withdrawn document would therefore lose the
withdrawal, a case these tools do not guard against. And the new object
version becomes the head without a history if the document had none, which
the [current version](11-versions.md) does not handle when the completed
version is not the latest.

Completion only adds files: the PDF received is kept, and the archive does
not typeset the added sources.

    # in complete a document version deposited without sources:
    def complete(args):
        """Add the sources of a document version recorded without them
        (sourcesMissing, section 7.3): a new object version holding the files of
        that document version and the sources; its number stays."""
        d = OCFL / args.id
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
        files = {p: d / inv["manifest"][dg][0] for p, dg in state.items() if p not in ("datacite.json", OBJ)}
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
        set_date(dc, "Updated", TODAY)
        fmt = obj["sourceFormat"]
        if fmt not in dc.get("formats", []):
            dc["formats"] = [fmt] + dc.get("formats", [])
        tmp = Path(tempfile.mkdtemp())
        write_json(tmp / "datacite.json", dc)
        write_json(tmp / OBJ, obj)
        files["datacite.json"], files[OBJ] = tmp / "datacite.json", tmp / OBJ
        for lp, f in carried_files(args.id, inv).items():     # notice files are kept
            files.setdefault(lp, f)
        inv = add_version(args.id, files, args.message or
                          f"Sources of document version {args.version} added (sourcesMissing completed)")
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"{args.id}: {inv['head']} (sources of version {args.version})")
