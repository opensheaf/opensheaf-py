Accepted copies
===============

A journal, a series or a curated archive does not take a document whole:
it vets one version, and that version is what it stands behind. A
[mirror](21-mirrors.md) would copy every version, including those the
authors write after acceptance; a reference in a
[collection](20-collections.md) would leave the vetted version in the
authors' hands. An *accepted copy* is the third way (section 10.5 of the
specification): a document of the accepting archive whose first version
holds exactly the files of the vetted version of another archive's
document, byte for byte, with a record of where they come from. This
chapter describes `src/opensheaf/accept.py`, which makes such copies.

What an accepted copy records
-----------------------------

An accepted copy is a document of this archive, under this archive's
identifier, and its later versions are acts of this archive's curator:
a corrected version accepted after a further review, a notice, a
withdrawal. The authors' later versions change nothing in it. What makes
it a copy, rather than a new document, is in its first document version:

- its content files are those of the vetted version, each checked
  against the digest of the source's inventory;
- its `object.json` names the source under `external`, with `role`
  `source` and `service` `OpenSheaf`: the `record` is the address of the
  source object version, the `label` the source's object identifier and
  object version (`paper v2`), and `files` has a single entry,
  `inventory.json`, whose `sha512` is the pin of the source version. A
  reader can thus fetch the source version and check, by the same
  digest a collection would use, that the copy is what was vetted;
- its `datacite.json` takes the description of the source, with this
  archive as publisher, the relations of the source, and one more
  relation, `IsIdenticalTo` the source version.

Accepted copies belong to *selections*, the kind of collection that vets
particular revisions (section 10.1): the selection lists the accepted
copy as a member of its own archive, with the copy's first document
version as its revision. A journal's issue is then a selection of its
own documents, written with [`osheaf collection sync`](20-collections.md)
from a file such as:

```yaml
id: issue-2026-1
type: selection
title: Volume 1, issue 1
members:
  - {archive: ., id: network-discrimination, revisions: [1]}
  - {archive: ., id: stabiliser-codes, revisions: [1]}
```

When the editors accept a correction, a new document version of the
copy, the issue changes only when they add it to the revision set
(`revisions: [1, 2]`) and synchronise again: a new version of the issue,
recorded as their act. The specification also allows the other form, the
original revision set with the copy's archive among the member's
`mirrors`; these tools do not write it, since a reader resolving the
original pin at that archive would find there the copy, a different
object with its own inventory, and not the pinned version.

The module
----------

    # in src/opensheaf/accept.py:
    <<the documentation of accept.py>>


    <<accepting a vetted version>>

The documentation of the module is that of the command.

    # in the documentation of accept.py:
    """Accepting a vetted version (a journal, a series, a curated archive):

        osheaf accept ARCHIVE-URL ID --version vN [--as NEW-ID] [--stage VoR]
                      [--available DATE] [--agreement METHOD] [--licence-checked]

    copies the files of exactly one version of another archive's object (the
    version that was vetted) into a document of this archive: its first document
    version, or, for a document accepted before, a new document version (a
    correction, which is an editorial act of this archive: the authors' later
    versions change nothing here). The files are copied byte for byte, each
    checked against the digest of the source's inventory; object.json records the
    source under `external` (role source: the archive's address, the object and
    its version as the label, and the SHA-512 of that version's inventory, its
    pin), and datacite.json takes the source's description, with this archive as
    publisher and a relation to the source version.

    Copying needs the right to redistribute: the version's licence must be an open
    one (CC BY, CC BY-SA, CC0, GPL), or --licence-checked states that it is
    allowed (for instance by the authors' agreement, which --agreement records).
    """

    import hashlib
    import json
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    from . import core as P
    from .collections import Remote, get
    from .mirror import is_open

Accepting a version
-------------------

The command reads the source archive as collections do, checks the
version and the right to copy it, finds out whether the copy is a new
document or a correction of one accepted before, copies and checks the
files, describes the copy, and deposits it as a new object version.

    # in accepting a vetted version:
    def accept(args):
        P.init_storage_root()
        r = Remote(args.url)
        <<check the vetted version and the right to copy it>>
        <<find the document that receives the accepted copy>>
        pin = r.pin(args.id, ver)
        tmp = Path(tempfile.mkdtemp())
        files = {}
        <<copy the files of the vetted version, checking each>>
        available = args.available or P.TODAY
        <<the description of an accepted copy>>
        <<the object record of an accepted copy>>
        <<deposit the accepted copy>>

The version is given as an object version (`--version v2`), which is
what a pin fixes, and must exist in the source. It must be a version of a
document: section 10.5 defines accepted copies of revisions of
documents, and a collection's members would not be copied with it. As for mirrors, copying
is redistribution; but only the one version copied needs a licence that
allows it, since the other versions stay where they are. When the
licence is not open, the curator states that copying is allowed with
`--licence-checked`, and records the authors' agreement with
`--agreement`.

    # in check the vetted version and the right to copy it:
    if r.archive_id == P.ARCHIVE["archiveId"]:
        sys.exit(f"{args.id} is an object of this archive")
    inv = r.inventory(args.id)
    ver = args.version
    if ver not in inv["versions"]:
        sys.exit(f"{args.id} has no object version {ver} (versions: {', '.join(inv['versions'])})")
    src_obj = json.loads(r.file(args.id, inv, ver, P.OBJ))
    if src_obj.get("kind") != "document":
        sys.exit(f"{args.id} is a {src_obj.get('kind')}: only a revision of a document is accepted (section 10.5)")
    src_dc = json.loads(r.file(args.id, inv, ver, "datacite.json"))
    if not is_open(src_dc.get("rightsList")) and not args.licence_checked:
        sys.exit(f"{args.id} {ver} is not under an open licence "
                 f"({(src_dc.get('rightsList') or [{}])[0].get('rights', 'none')}): copying it needs "
                 "the right to redistribute (--licence-checked, with --agreement to record it)")

### A new document, or a correction

The copy keeps the source's identifier unless `--as` gives another (a
journal may name its articles its own way). If a document of that
identifier exists, the copy is a correction of it: a new document
version, numbered after the highest present. Only an active document of
this archive can be corrected; a mirror, a collection, or a withdrawn
document cannot.

    # in find the document that receives the accepted copy:
    obj_id = args.as_id or args.id
    d = P.OCFL / obj_id
    have = P.load_inventory(d)
    doc_version = 1
    prev_obj = prev_dc = None
    if have:
        prev_obj, prev_dc = P.read_json(d, have, P.OBJ), P.read_json(d, have, "datacite.json")
        if prev_obj.get("archiveId") != P.ARCHIVE["archiveId"] or prev_obj["kind"] != "document":
            sys.exit(f"{obj_id} is not a document of this archive")
        if prev_obj.get("status") == "withdrawn":
            sys.exit(f"{obj_id} is withdrawn")
        doc_version = max(P.doc_version_of(d, have, v) for v in have["versions"]) + 1

### Copying the files

The files are those of the state of the source version: every logical
path, with the digest of its content. Each is fetched once, through the
first content path the manifest gives for its digest, checked against
the digest, and written into a temporary folder under its logical path.
`datacite.json` and `object.json` are not copied: the copy has its own,
written below. A file that does not match stops everything before
anything is deposited. The notice files of the source version are copied
too: section 10.5 asks for exactly the files of the vetted version, every
file but the two descriptions. In the copy they are files of its first
document version like the others, since the copy does not take over the
source's `notices` (a statement of the source's archive, not of this
one); the source version, which the copy links, explains them.

    # in copy the files of the vetted version, checking each:
    base = r.root + args.id + "/"
    state = {p: dg for dg, ps in inv["versions"][ver]["state"].items() for p in ps}
    for logical, dg in sorted(state.items()):
        if logical in ("datacite.json", P.OBJ):
            continue
        data = get(base + inv["manifest"][dg][0])
        if hashlib.sha512(data).hexdigest() != dg:
            sys.exit(f"{args.id} {ver}: {logical} does not match its digest; nothing accepted")
        f = tmp / "files" / logical
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
        files[logical] = f

### The description

The description of the copy is that of the source, less what belongs to
the source's record: its DOI, its address, its dates, its relations and
its version number. The copy is published by this archive, has the
document version it has here, and its address is its landing page here.
`--type` may change the kind of content, for instance from `Preprint` to
`JournalArticle`.

    # in the description of an accepted copy:
    dc = {k: v for k, v in src_dc.items() if k not in ("doi", "url", "dates", "relatedIdentifiers", "version")}
    dc["publisher"] = {"name": P.ARCHIVE["name"]}
    dc["version"] = str(doc_version)
    dc["url"] = P.landing_url(obj_id)
    if args.type:
        dc["types"] = {"resourceTypeGeneral": args.type}
    <<the dates of an accepted copy>>
    <<the relations of an accepted copy>>

The dates follow their meanings in section 8. `Issued`, the first public
appearance of the work anywhere, is the source's, or for a correction
that of the copy accepted before. `Available` is when this version
became public here: `--available`, or today.

    # in the dates of an accepted copy:
    issued = P.date_of(src_dc, "Issued") or (P.date_of(prev_dc, "Issued") if prev_dc else None)
    dc["dates"] = []
    if issued:
        P.set_date(dc, "Issued", issued)
    P.set_date(dc, "Available", available)

The relations of the source remain true of the copy, whose files are the
same; to them is added the link to the source object version itself,
at the storage root that the source's discovery document states.

    # in the relations of an accepted copy:
    # the files are those of the source version: its relations stay true
    rel = list(src_dc.get("relatedIdentifiers", []))
    rel.append({"relatedIdentifier": f"{r.root}{args.id}/{ver}/", "relatedIdentifierType": "URL",
                "relationType": "IsIdenticalTo"})
    dc["relatedIdentifiers"] = rel

### The object record

`object.json` takes from the source the fields that describe the
content, which is the same: the main source and its format, or the note
that the sources are missing, the renditions and the toolchain. It does
not take the source's history, notices, change note or stage, which
belong to the source's document.

    # in the object record of an accepted copy:
    obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
           "archiveId": P.ARCHIVE["archiveId"], "objectId": obj_id, "documentVersion": doc_version}
    for k in ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain"):
        if k in src_obj:
            obj[k] = src_obj[k]
    <<the change note, stage and agreement of an accepted copy>>
    <<the source record of an accepted copy>>

The change note says what was accepted, unless `--changes` gives one.
`--stage` records the stage of the version in the NISO Journal Article
Versions (`AM` for an accepted manuscript, `VoR` for a version of
record). `--agreement` records the authors' agreement as section 9
allows: the names of the source's creators, the date, and how it was
given, nothing more.

    # in the change note, stage and agreement of an accepted copy:
    obj["changes"] = {"text": args.changes or (
        f"Accepted: version {src_obj['documentVersion']} of {args.id} in {r.disc.get('name', r.archive_id)}"
        if doc_version == 1 else f"Correction: version {src_obj['documentVersion']} of {args.id} accepted "
        "by this archive in place of the earlier one")}
    if args.stage:
        obj["stage"] = {"scheme": "NISO-JAV", "value": args.stage}
    if args.agreement:
        obj["agreement"] = {"by": [c["name"] for c in src_dc["creators"]], "date": available,
                            "method": args.agreement}

The source record is what makes the copy checkable: the address of the
source version, its label, and its pin. The website shows the label in
the heading of the version ([the website](30-website.md)).

    # in the source record of an accepted copy:
    obj["external"] = [{"role": "source", "service": "OpenSheaf", "record": f"{r.root}{args.id}/{ver}/",
                        "label": f"{args.id} {ver}",
                        "files": [{"name": "inventory.json", "sha512": pin}]}]
    obj["status"] = "active"

### Depositing

The copy is deposited with the functions of the core. For a correction,
`carry_forward` keeps the notices of the document accepted before, which
persist unchanged in every later version, and its history if it has one;
`carried_files` keeps the files of those notices. Since the vetted
version may have notice files of its own, a file of a notice of this
archive at the same logical path as a different file of the vetted
version stops the command: one of the two would be lost. The message of
the OCFL version names the source and the beginning of its pin.

    # in deposit the accepted copy:
    P.carry_forward(prev_obj, obj, have, P.next_object_version(have))
    for lp, f in P.carried_files(obj_id, have).items():
        if lp in files and P.digest(files[lp]) != P.digest(f):
            sys.exit(f"{obj_id}: the file {lp} of a notice here differs from that of {args.id} {ver}")
        files.setdefault(lp, f)
    P.write_json(tmp / "datacite.json", dc)
    P.write_json(tmp / P.OBJ, obj)
    files["datacite.json"], files[P.OBJ] = tmp / "datacite.json", tmp / P.OBJ
    msg = args.message or (f"Accepted from {r.archive_id}: {args.id} {ver} (pin {pin[:16]}...)")
    new = P.add_version(obj_id, files, msg)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{obj_id}: {new['head']} (document version {doc_version}, from {args.id} {ver})")

A version that the accepting archive makes itself, such as a journal's
typeset version of record, is not an accepted copy: it is deposited as
any document of the archive, with relations to the authors' versions.
