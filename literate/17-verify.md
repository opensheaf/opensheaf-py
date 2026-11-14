Verifying an archive
====================

An OpenSheaf archive is meant to be checkable by anyone, from its files
alone: the digests fix every file, the pins fix every collection, and the
rules of the specification can be checked against the descriptions.
`osheaf verify` is the verifier of section 14, run on an archive on disk.
It checks what the previous chapters write: the [storage root](10-archive.md),
the [document versions and their history](11-versions.md), the
descriptions written by [deposits](13-deposit.md) and
[description-only versions](14-description.md), the
[main collection](15-main-collection.md) and the
[discovery document](16-index.md). With `--remote` it also resolves the
members of other archives, and the sources of accepted copies (see
[collections](20-collections.md)).

The verifier reports every problem it finds, as a line naming the place
(`ocfl/<id>: v3 ...`), rather than stopping at the first.

    # in verify an archive:
    <<check the document versions of a document>>


    <<check an archive and list its problems>>


    <<the verify command>>

The command
-----------

The command prints the problems and their number, or `OK`, and its exit
status says which, so that it can run in continuous integration. With
`--remote`, the members of other archives of the head of every collection
are resolved and their pins checked, and every accepted copy is compared
with its source (section 14). Mirrors of other archives' collections are
left out: their members are the original archive's to check. Earlier
versions of a collection are not resolved, since the pins of its head are
what the archive presents now; a verifier that wants them all can follow
the inventories.

    # in the verify command:
    def verify(args):
        errors = verify_errors()
        if getattr(args, "remote", False):
            from . import collections
            for obj_id, d, inv in objects():
                if read_json(d, inv, OBJ)["kind"] == "collection" and not mirror_of(d, inv):
                    errors += [f"{obj_id}: {e}" for e in
                               collections.check_remote(read_json(d, inv, "members.json")["members"])]
            errors += collections.check_accepted_copies()
        for e in errors:
            print(e)
        print("OK" if not errors else f"{len(errors)} problem(s)")
        sys.exit(1 if errors else 0)

The checks
----------

The checks follow the order of the archive: the discovery document, then
each object and each of its versions, then two independent checks.

    # in check an archive and list its problems:
    def verify_errors():
        errors = []
        <<check against the JSON Schemas of the specification, when jsonschema is installed>>

        <<check the discovery document of an archive against its storage root>>

        for obj_id, (d, inv) in found.items():
            <<check the inventory and the stored files of an object>>
            <<check every version of an object>>
            errors += document_version_errors(obj_id, d, inv)

        <<check the storage root with an independent OCFL validator>>

        <<check that the index shows the pins of the main collection>>
        return errors

### Schemas

The JSON files defined by the specification are validated against its JSON
Schemas (appendix D), with their formats (dates, URIs) checked as
assertions, as section 14 asks. `jsonschema` is optional: without it this
check is skipped, silently. `datacite.json` has no JSON Schema (DataCite
publishes only an XML Schema); its required properties are checked by hand
below.

    # in check against the JSON Schemas of the specification, when jsonschema is installed:
    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    def check_schema(where, data, name):
        if jsonschema is None:
            return
        schema = json.loads((SCHEMAS / name).read_text())
        v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for e in v.iter_errors(data):
            errors.append(f"{where}: {e.message}")

### The discovery document

Without a discovery document there is nothing more to check. With one, it
must state the required layout, and list exactly the objects of the storage
root: the verifier reads the files, so it can also check that none is
missing (section 14). An object listed with `mirrorOf` must be a mirror of
that archive, and a mirror must be listed so (sections 6.1 and 10.4);
whether it is one is read from its head, as everywhere in these tools.

    # in check the discovery document of an archive against its storage root:
    disc_path = ROOT / "opensheaf.json"
    if not disc_path.exists():
        return ["opensheaf.json is missing"]
    disc = json.loads(disc_path.read_text())
    check_schema("opensheaf.json", disc, "opensheaf-archive-0.1.schema.json")
    if disc.get("storageLayout") != LAYOUT or not (OCFL / "0=ocfl_1.1").exists():
        errors.append("storage root missing or with another layout")
    listed = {o["id"]: o for o in disc.get("objects", [])}
    found = {obj_id: (d, inv) for obj_id, d, inv in objects()}
    for obj_id in set(listed) ^ set(found):
        errors.append(f"opensheaf.json and the storage root disagree about {obj_id}")
    for obj_id, (d, inv) in found.items():
        if obj_id in listed and listed[obj_id].get("mirrorOf") != mirror_of(d, inv):
            errors.append(f"opensheaf.json: {obj_id} " + (f"is a mirror of {mirror_of(d, inv)}, without mirrorOf"
                          if mirror_of(d, inv) else "is listed as a mirror, and is not one"))

### Objects

For each object: its identifier, the digest algorithm, the sidecar of the
inventory, the entry of the discovery document (its head and digest must be
those of the storage root, or the discovery document is stale, which
happens when `osheaf index` was not run after a change), and every stored
file against its digest. This last check reads every file of the archive,
and is what makes the verifier slow on large archives.

    # in check the inventory and the stored files of an object:
    where = f"ocfl/{obj_id}"
    if inv.get("id") != obj_id or not ID_RE.match(obj_id) or len(obj_id) > 64:
        errors.append(f"{where}: bad identifier")
    if inv.get("digestAlgorithm") != "sha512":
        errors.append(f"{where}: digest algorithm is not sha512")
    side = (d / "inventory.json.sha512").read_text().split()[0]
    if side != digest(d / "inventory.json"):
        errors.append(f"{where}: inventory checksum file does not match")
    lst = listed.get(obj_id)
    if lst and (lst["head"] != inv["head"] or lst["inventorySha512"] != side):
        errors.append(f"opensheaf.json: stale entry for {obj_id}")
    for dig, paths in inv["manifest"].items():
        for cp in paths:
            if not (d / cp).exists():
                errors.append(f"{where}: missing {cp}")
            elif digest(d / cp) != dig:
                errors.append(f"{where}: digest mismatch for {cp}")

Then each version of the object, in three groups of checks.

    # in check every version of an object:
    for ver, vinfo in inv["versions"].items():
        <<check the inventory copy, the user and the logical paths of an object version>>
        <<check the two descriptions of an object version>>
        <<check the files of a document version or the members of a collection version>>

Section 7.1: each version has its own copy of the inventory (to be pinned
on its own), a user and a message, logical paths that do not leave the
object, and the two descriptions. A version without them cannot be checked
further. The rule that logical paths be in Unicode normalisation form C is
not checked.

The copy of the inventory is the inventory as of its version (OCFL 1.1,
section 3.5.3): its head is that version, and it records exactly the
versions `v1` to `vN` of the root inventory, each as the root records it.
A copy listing fewer versions than its name, or with another head, would
otherwise pass, and a pin of it, which is the digest of the copy, would fix
a history other than the object's. The messages are those of the
[explorer](https://opensheaf.org/explorer/source/17-verify.html), which
makes the same check.

    # in check the inventory copy, the user and the logical paths of an object version:
    if not (d / ver / "inventory.json").exists() or not (d / ver / "inventory.json.sha512").exists():
        errors.append(f"{where}: {ver} has no inventory copy")
    else:
        copy = json.loads((d / ver / "inventory.json").read_text())
        upto = [v for v in inv["versions"] if int(v[1:]) <= int(ver[1:])]
        if copy.get("head") != ver:
            errors.append(f"{where}: {ver} the inventory copy has the head {copy.get('head')}")
        if sorted(copy.get("versions") or {}) != sorted(upto):
            errors.append(f"{where}: {ver} the inventory copy does not record exactly the versions v1 to {ver}")
        elif any(copy["versions"][v] != inv["versions"][v] for v in upto):
            errors.append(f"{where}: {ver} the inventory copy disagrees with the inventory"
                          " about the versions it records")
    if not vinfo.get("user", {}).get("name") or not vinfo.get("message"):
        errors.append(f"{where}: {ver} lacks a user name or a message")
    logical = {p for ps in vinfo["state"].values() for p in ps}
    for p in logical:
        parts = p.split("/")
        if p.startswith("/") or ".." in parts or "." in parts:
            errors.append(f"{where}: bad logical path {p}")
    missing = [n for n in ("datacite.json", OBJ) if n not in logical]
    for n in missing:
        errors.append(f"{where}: {ver} has no {n}")
    if missing:
        continue

The descriptions are checked against each other and against sections 8 and
9. `object.json` must name its object, and its archive: this archive, or,
in a mirror, the archive it copies, which every version of the mirror must
name (section 14: "for each mirror, check that its `object.json` files
name that archive"). The two files must agree on the document version and
the date of a withdrawal. `datacite.json` must
have the required properties; a Creative Commons or arXiv licence must be
identified, by SPDX or by URL, so that archives record the same licence the
same way (section 8). Every note with a file must find that file in the
version.

    # in check the two descriptions of an object version:
    obj = read_json(d, inv, OBJ, ver)
    dc = read_json(d, inv, "datacite.json", ver)
    check_schema(f"{where}/{ver}/{OBJ}", obj, "opensheaf-object-0.1.schema.json")
    if obj.get("objectId") != obj_id:
        errors.append(f"{where}: {ver} object.json names another object")
    elif obj.get("archiveId") != (mirror_of(d, inv) or disc.get("archiveId")):
        errors.append(f"{where}: {ver} object.json names another archive")
    if str(obj.get("documentVersion")) != dc.get("version"):
        errors.append(f"{where}: {ver} datacite.json and object.json disagree on the version")
    if obj.get("status") == "withdrawn" and date_of(dc, "Withdrawn") != obj.get("withdrawal", {}).get("date"):
        errors.append(f"{where}: {ver} withdrawal dates disagree")
    for k in ("titles", "creators", "publicationYear", "types", "version", "publisher"):
        if k not in dc:
            errors.append(f"{where}: {ver} datacite.json lacks {k}")
    for r in dc.get("rightsList", []):
        if r.get("rightsIdentifier") is None and r.get("rights", "").lower().startswith(("creative", "arxiv")) \
                and not r.get("rightsUri"):
            errors.append(f"{where}: {ver} licence without SPDX identifier and without rightsUri")
    for note in [obj.get("changes"), obj.get("sourcesMissing"), obj.get("licence")] + \
            obj.get("notices", []) + [obj.get("withdrawal", {}).get("reason")]:
        if note and note.get("path") and note["path"] not in logical:
            errors.append(f"{where}: {ver} note file {note['path']} not in the version")

A document version must hold its main source and its renditions, and
cannot both name a main source and say that its sources are missing. A
collection version must hold `members.json`, valid against its schema,
with the checks of the member list described next.

    # in check the files of a document version or the members of a collection version:
    if obj.get("kind") == "document":
        if obj.get("mainSource") and obj["mainSource"] not in logical:
            errors.append(f"{where}: {ver} main source not in the version")
        if obj.get("sourcesMissing") and obj.get("mainSource"):
            errors.append(f"{where}: {ver} sourcesMissing together with a main source")
        for r in obj.get("renditions", []):
            if r["path"] not in logical:
                errors.append(f"{where}: {ver} rendition {r['path']} not in the version")
    elif "members.json" not in logical:
        errors.append(f"{where}: {ver} collection without members.json")
    else:
        mem = read_json(d, inv, "members.json", ver)
        check_schema(f"{where}/{ver}/members.json", mem, "opensheaf-collection-0.1.schema.json")
        <<check the type of a member list and the keys of its members>>
        <<check the pins of the members of this archive>>

The schema says much of this already, but `jsonschema` is optional, and the
rules of section 10.2 that section 14 names are checked by hand: the member
list has a `type`, `catalogue` or `selection`; a member of a catalogue has `version` and `inventorySha512` and no revisions; a member
of a selection has a non-empty list of `revisions`, each with its three
fields, of distinct document versions, and none of `version`,
`inventorySha512` or `follow`. A collection of a mirror is checked the
same way: it is another archive's object, but the format is the same.

    # in check the type of a member list and the keys of its members:
    kind = mem.get("type")
    if kind not in ("catalogue", "selection"):
        errors.append(f"{where}: {ver} members.json has no valid type (catalogue or selection)")
    for m in mem.get("members", []):
        who = f"{where}: {ver} member {m.get('id')}"
        if kind == "catalogue" and (not m.get("version") or not m.get("inventorySha512") or "revisions" in m):
            errors.append(f"{who}: a member of a catalogue needs version and inventorySha512, "
                          "and no revisions")
        if kind == "selection":
            revs = m.get("revisions")
            if any(k in m for k in ("version", "inventorySha512", "follow")):
                errors.append(f"{who}: a member of a selection has no version, inventorySha512 or follow")
            if not isinstance(revs, list) or not revs or any(
                    not all(r.get(k) for k in ("documentVersion", "version", "inventorySha512")) for r in revs):
                errors.append(f"{who}: a member of a selection needs revisions, each with documentVersion, "
                              "version and inventorySha512")
            elif len({r["documentVersion"] for r in revs}) != len(revs):
                errors.append(f"{who}: a document version is vetted twice")

Every pin of a member of this archive must be right: the pinned object
version exists, its inventory has the pinned digest and, for a revision,
it holds the stated document version. A revision set must also be in the
order of the document's history (section 10.2), which for a member of
this archive is read from the head. Members of other archives are
resolved only with `--remote`; members of a mirrored collection belong to
the archive it copies.

    # in check the pins of the members of this archive:
    for m in mem.get("members", []):
        if m.get("archive") != disc.get("archiveId") or mirror_of(d, inv):
            continue  # members of other archives: resolved as in section 6.4
        for pv, pin, n in member_pins(m):
            md = OCFL / str(m.get("id")) / str(pv) / "inventory.json"
            if not md.exists():
                errors.append(f"{where}: {ver} member {m['id']} {pv}: unavailable")
            elif digest(md) != pin:
                errors.append(f"{where}: {ver} member {m['id']} {pv}: mismatch")
            elif n is not None and doc_version_of(OCFL / m["id"], load_inventory(OCFL / m["id"]), pv) != n:
                errors.append(f"{where}: {ver} member {m['id']} {pv} does not hold document version {n}")
        if kind == "selection" and (OCFL / str(m.get("id"))).exists():
            md = OCFL / m["id"]
            order = [doc_version_of(md, load_inventory(md), h) for h in history_of(md, load_inventory(md))]
            vetted = [r.get("documentVersion") for r in m.get("revisions") or []]
            pos = [order.index(x) for x in vetted if x in order]
            if pos != sorted(pos):
                errors.append(f"{where}: {ver} member {m['id']}: revisions not in the order of the history")

### Document versions

The rules of section 7.3 concern the sequence of object versions of a
document, and are checked in one pass over them, remembering for each
document version its own files, its change note, and whether its sources
were missing.

    # in check the document versions of a document:
    def document_version_errors(obj_id, d, inv):
        """Section 7.3: numbering without gaps, the same files for the same
        document version (a version with sourcesMissing may be completed by adding
        files), the history, and notices kept unchanged."""
        errors, where = [], f"ocfl/{obj_id}"
        seen, files_of, missing_of, highest = {}, {}, {}, 0
        had_history, notices = False, []
        for ver, vinfo in inv["versions"].items():
            <<the files of an object version that belong to its document version>>
            <<check the number and the files of a document version>>
            <<check the history recorded in an object version>>
            <<check that an object version keeps the earlier notices>>
        return errors

A document version is its *own* files: everything except the two
descriptions and the files of notices and of a withdrawal, which
description-only versions add, and the file of the licence terms
(`licence`, section 9), which "any object MAY contain": licence terms
describe the object, like `rightsList` in `datacite.json`, not the document
version, so a description-only version may add or replace them (sections
7.3 and 9). Its change note belongs to the document version, since it was
written and deposited with it (section 9), and so does the note of missing
sources (a completion "changes or removes no file of the version", section
7.3).

    # in the files of an object version that belong to its document version:
    obj = read_json(d, inv, OBJ, ver)
    if obj is None or obj.get("kind") != "document":
        return errors
    n = obj["documentVersion"]
    notes = {x["path"] for x in obj.get("notices", []) if x.get("path")}
    if obj.get("withdrawal", {}).get("reason", {}).get("path"):
        notes.add(obj["withdrawal"]["reason"]["path"])
    if (obj.get("licence") or {}).get("path"):
        notes.add(obj["licence"]["path"])
    own = {p: dig for dig, ps in vinfo["state"].items() for p in ps
           if p not in ("datacite.json", OBJ) and p not in notes}
    change = (obj.get("changes") or {}).get("text")

A document version seen before must have the same own files and change
note, except while its sources are missing: then files may be added (a
[completion](14-description.md)), never changed or removed. A document
version not seen before must have the next number.

    # in check the number and the files of a document version:
    if n in seen:
        before, mis = files_of[n], missing_of[n]
        if mis:
            if any(before.get(p) not in (None, dig) for p, dig in own.items()) or not set(before) <= set(own):
                errors.append(f"{where}: {ver} changes files of document version {n} (only additions allowed)")
        elif own != before or change != seen[n]:
            errors.append(f"{where}: {ver} has other files than document version {n}")
        missing_of[n] = bool(obj.get("sourcesMissing"))
        files_of[n] = own
    else:
        if n != highest + 1:
            errors.append(f"{where}: {ver} document version {n} breaks the numbering (expected {highest + 1})")
        highest = max(highest, n)
        seen[n], files_of[n], missing_of[n] = change, own, bool(obj.get("sourcesMissing"))

The history, once present, must stay present; it may name only object
versions that exist at that point; it must list each document version
known so far exactly once; and each entry must be the last object version
holding its document version, as known when the history was written.

    # in check the history recorded in an object version:
    hist = obj.get("history")
    if had_history and hist is None:
        errors.append(f"{where}: {ver} lacks the history of earlier versions")
    if hist is not None:
        had_history = True
        known = [v for v in inv["versions"] if int(v[1:]) <= int(ver[1:])]
        if any(h not in known for h in hist):
            errors.append(f"{where}: {ver} history names unknown object versions")
        else:
            docs = [read_json(d, inv, OBJ, h)["documentVersion"] for h in hist]
            if len(set(docs)) != len(docs) or set(docs) != set(range(1, highest + 1)):
                errors.append(f"{where}: {ver} history does not list each document version once")
            for h, k in zip(hist, docs):
                later = [v for v in known if int(v[1:]) > int(h[1:])
                         and read_json(d, inv, OBJ, v)["documentVersion"] == k]
                if later:
                    errors.append(f"{where}: {ver} history entry {h} is not the last object version of {k}")

Every notice of an object version must be present, unchanged, in the next
one, and so in every later one.

    # in check that an object version keeps the earlier notices:
    cur = obj.get("notices", [])
    if any(x not in cur for x in notices):
        errors.append(f"{where}: {ver} drops or changes an earlier notice")
    notices = cur

### Independent checks

An independent OCFL validator, `ocfl-py`, checks each object and the
storage root when it is installed: the tools write OCFL themselves, and a
second implementation catches what they might get wrong in the same way
twice. It may warn that our identifiers are not URIs, which OCFL
recommends and OpenSheaf does not use (section 7.1); warnings are not
reported.

    # in check the storage root with an independent OCFL validator:
    # an independent OCFL validator, when installed
    try:
        import ocfl
        from ocfl.validator import Validator
    except ImportError:
        ocfl = None
    if ocfl is not None:
        for obj_id, (d, inv) in found.items():
            v = Validator(log_warnings=False, log_errors=True)
            if not v.validate_object(str(d)):
                errors.append(f"ocfl/{obj_id}: OCFL validator: {v.status_str()}")
        if not ocfl.StorageRoot(root=str(OCFL)).validate(log_warnings=False):
            errors.append("ocfl: the OCFL validator rejects the storage root")

The presentation is never authoritative, but it should not lie: the TeXmacs
index (or the website's index page) must show the pin of every member of
the main collection, so that an index left behind after `osheaf collect`
is noticed. For a member of a selection, the pin of the revision
presented, the last, is required.

The specification requires an index page only of archives declaring the
profile `website` (appendix C: "the website has an index page generated
from the head version of the main collection"); other archives may serve
any page there, or one made by other tools. So a pin missing from the
index is a problem only for an archive declaring `website`; for the
others it is printed as a note, which does not count among the problems,
in the words of the [explorer](https://opensheaf.org/explorer/source/17-verify.html).

    # in check that the index shows the pins of the main collection:
    # the presentation shows the current pins (appendix C, for the profile website)
    coll = found.get(disc.get("mainCollection"))
    if coll and (ROOT / "index.html").exists():
        website = "website" in (disc.get("profiles") or [])
        html = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
        mem = json.loads(read_logical(coll[0], coll[1], "members.json").read_text())
        for m in mem["members"]:
            if (member_pins(m)[-1][1] or "")[:32] not in html:
                if website:
                    errors.append(f"index.html does not show the pin of {m['id']}")
                else:
                    print(f"  index.html does not show the pin of {m['id']}"
                          " (the archive does not declare the profile website)")
