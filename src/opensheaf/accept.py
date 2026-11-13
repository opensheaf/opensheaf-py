# Generated from literate/22-accepted-copies.md by tools/tangle.py: edit the document, not this file.
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


def accept(args):
    P.init_storage_root()
    r = Remote(args.url)
    if r.archive_id == P.ARCHIVE["archiveId"]:
        sys.exit(f"{args.id} is an object of this archive")
    inv = r.inventory(args.id)
    ver = args.version
    if ver not in inv["versions"]:
        sys.exit(f"{args.id} has no object version {ver} (versions: {', '.join(inv['versions'])})")
    src_obj = json.loads(r.file(args.id, inv, ver, P.OBJ))
    src_dc = json.loads(r.file(args.id, inv, ver, "datacite.json"))
    if not is_open(src_dc.get("rightsList")) and not args.licence_checked:
        sys.exit(f"{args.id} {ver} is not under an open licence "
                 f"({(src_dc.get('rightsList') or [{}])[0].get('rights', 'none')}): copying it needs "
                 "the right to redistribute (--licence-checked, with --agreement to record it)")
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
    pin = r.pin(args.id, ver)
    tmp = Path(tempfile.mkdtemp())
    files = {}
    base = r.root + args.id + "/"
    state = {p: dg for dg, ps in inv["versions"][ver]["state"].items() for p in ps}
    received = []
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
    for n in src_obj.get("notices", []):      # notices of the source are its archive's, not ours
        if n.get("path"):
            files.pop(n["path"], None)
    available = args.available or P.TODAY
    dc = {k: v for k, v in src_dc.items() if k not in ("doi", "url", "dates", "relatedIdentifiers", "version")}
    dc["publisher"] = {"name": P.ARCHIVE["name"]}
    dc["version"] = str(doc_version)
    dc["url"] = P.landing_url(obj_id)
    if args.type:
        dc["types"] = {"resourceTypeGeneral": args.type}
    issued = P.date_of(src_dc, "Issued") or (P.date_of(prev_dc, "Issued") if prev_dc else None)
    dc["dates"] = []
    if issued:
        P.set_date(dc, "Issued", issued)
    P.set_date(dc, "Available", available)
    # the files are those of the source version: its relations stay true
    rel = list(src_dc.get("relatedIdentifiers", []))
    rel.append({"relatedIdentifier": f"{r.url}ocfl/{args.id}/{ver}/", "relatedIdentifierType": "URL",
                "relationType": "IsIdenticalTo"})
    dc["relatedIdentifiers"] = rel
    obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
           "archiveId": P.ARCHIVE["archiveId"], "objectId": obj_id, "documentVersion": doc_version}
    for k in ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain"):
        if k in src_obj:
            obj[k] = src_obj[k]
    obj["changes"] = {"text": args.changes or (
        f"Accepted: version {src_obj['documentVersion']} of {args.id} in {r.disc.get('name', r.archive_id)}"
        if doc_version == 1 else f"Correction: version {src_obj['documentVersion']} of {args.id} accepted "
        "by this archive in place of the earlier one")}
    if args.stage:
        obj["stage"] = {"scheme": "NISO-JAV", "value": args.stage}
    if args.agreement:
        obj["agreement"] = {"by": [c["name"] for c in src_dc["creators"]], "date": available,
                            "method": args.agreement}
    obj["external"] = [{"role": "source", "service": "OpenSheaf", "record": f"{r.url}ocfl/{args.id}/{ver}/",
                        "label": f"{args.id} {ver}",
                        "files": [{"name": "inventory.json", "sha512": pin}]}]
    obj["status"] = "active"
    P.carry_forward(prev_obj, obj, have, P.next_object_version(have))
    for lp, f in P.carried_files(obj_id, have).items():
        files.setdefault(lp, f)
    P.write_json(tmp / "datacite.json", dc)
    P.write_json(tmp / P.OBJ, obj)
    files["datacite.json"], files[P.OBJ] = tmp / "datacite.json", tmp / P.OBJ
    msg = args.message or (f"Accepted from {r.archive_id}: {args.id} {ver} (pin {pin[:16]}...)")
    new = P.add_version(obj_id, files, msg)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{obj_id}: {new['head']} (document version {doc_version}, from {args.id} {ver})")
