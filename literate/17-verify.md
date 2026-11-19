Verifying an archive
====================

An OpenSheaf archive is meant to be checkable by anyone, from its files
alone: the digests fix every file, `previous` chains the inventories, the
signatures say which owner's keys made each version, the key logs check
themselves from the owner names, and the rules of the specification can be
checked against the descriptions. `osheaf verify` is the verifier of
section 14, run on an archive on disk. It checks what the previous chapters
write: the [storage root](10-archive.md) and its layout, the key logs of
the [owners](06-owners.md), the lines with their
[signatures](08-signatures.md), the
[document versions and their history](11-versions.md), the descriptions
written by [deposits](13-deposit.md) and
[description-only versions](14-description.md), the
[main catalogue](15-main-collection.md) and the
[discovery document](16-index.md).

Section 14 orders the checks: files and storage (14.2), key logs (14.3),
the other objects (14.4) with their collections (14.5), and the archive as a
whole (14.6), each step using the results of those before. This chapter
follows that order, and adds a check that section 15.4 asks of archives and
a verifier with access to the files can make: that no private key is kept
in the archive.

    # in verify an archive:
    <<the findings of a verifier>>


    <<check the document versions of a document>>


    <<check the descriptions of an object version>>


    <<check the files and the storage of an archive>>


    <<check the key logs of an archive>>


    <<check the lines of an archive>>


    <<check a branch>>


    <<check the members of a collection version>>


    <<check the indexes of the archive>>


    <<check the archive as a whole>>


    <<check the presentation files of the profile website>>


    <<look for keys left in the archive>>


    <<check an archive and list its findings>>


    <<the verify command>>

Findings
--------

A verifier reports every finding with its place, and does not stop at the
first (section 14.1). A finding is an *error*, a breach of a MUST or MUST
NOT, except where section 14 makes it a warning; a *warning*, a breach of a
SHOULD, or one the archive cannot repair, or a check not made; or a
*result*: the statuses of versions, ended owners, exposed keys, contested
versions, withdrawals and removals. An archive without errors passes. The
places are the labels of the lines when the archive gives them, or their
identifiers (`owner <name>` for a key log), followed by the object version.

    # in the findings of a verifier:
    class Findings(list):
        """The findings of a verifier (section 14.1), as dicts with severity, place and message."""

        def add(self, severity, place, message):
            self.append({"severity": severity, "place": place, "message": message})

        def error(self, place, message):
            self.add("error", place, message)

        def warning(self, place, message):
            self.add("warning", place, message)

        def result(self, place, message):
            self.add("result", place, message)

        def count(self, severity):
            return sum(1 for x in self if x["severity"] == severity)


    def where(obj_id):
        """The place of an object in findings: its label, its owner for a key log, or its identifier."""
        parts = (obj_id or "").split(":")
        if len(parts) == 3 and parts[1] == parts[2]:
            return f"owner {parts[1]}"
        return label_of(obj_id) or obj_id or "?"

The JSON files defined by the specification are validated against its JSON
Schemas (appendix B), with their formats (dates, URIs) checked as
assertions, as section 14.2 asks. `jsonschema` is optional: without it this
check is not made, and a warning says so and how to install it (a check not
made is a warning, section 14.1). `jsonschema` checks the formats `uri` and
`uri-reference` only when a URI parser is installed (`rfc3986-validator`,
which the extras `validate` and `test` bring); otherwise it accepts any
string in them, so the verifier warns that these formats are not checked
rather than pass them in silence. `datacite.json` has no JSON Schema
(DataCite publishes only an XML Schema); its required properties are
checked by hand below.

    # in the findings of a verifier:
    def schema_checker(f):
        """A function (place, data, schema name, severity) checking DATA against a schema of 0.2."""
        try:
            import jsonschema
            formats = jsonschema.FormatChecker()
        except ImportError:
            f.warning("archive", "the JSON Schemas are not checked: jsonschema is not installed"
                      " (pip install 'opensheaf[validate]')")
            return lambda *a, **k: None
        if "uri" not in formats.checkers:
            f.warning("archive", "the formats uri and uri-reference are not checked: rfc3986-validator is not"
                      " installed (pip install 'opensheaf[validate]')")
        validators = {}

        def check(place, data, name, severity="error"):
            if name not in validators:
                schema = json.loads((SCHEMAS / f"opensheaf-{name}-0.2.schema.json").read_text(encoding="utf-8"))
                validators[name] = jsonschema.Draft202012Validator(schema, format_checker=formats)
            for e in validators[name].iter_errors(data):
                f.add(severity, place, e.message)
        return check

The checks
----------

The verifier first tells an archive of version 0.1 by its configuration
or its discovery document, and reports a single error: section 16.1 says
that such an archive is rebuilt, and these tools do not read it. Then the
steps of section 14, in order.

    # in check an archive and list its findings:
    def verify_findings(remote=False):
        """The findings of the checks of section 14 on the archive, in the order of 14.2 to 14.6;
        REMOTE: also resolve the members of other archives (section 14.5)."""
        f = Findings()
        if OLD:
            f.error("archive", "specification 0.1: rebuild (section 16.1)")
            return f
        schema = schema_checker(f)
        disc_path, disc = ROOT / "opensheaf.json", {}
        if not disc_path.exists():
            f.error("opensheaf.json", "the discovery document is missing (section 3.1)")
        else:
            try:
                disc = json.loads(disc_path.read_text(encoding="utf-8"))
            except ValueError as e:
                f.error("opensheaf.json", f"not JSON: {e}")
            if disc.get("specification") == "0.1":
                f.error("archive", "specification 0.1: rebuild (section 16.1)")
                return f
            schema("opensheaf.json", disc, "archive")
        found = check_storage(f, schema, disc)
        logs = check_key_logs(f, found, schema)
        resolver = None
        if remote:
            from . import remote as remote_
            resolver = remote_.Resolver()
        try:
            statuses = check_lines(f, found, logs, schema, disc, resolver)
            if resolver is not None:
                for severity, message in resolver.notes:
                    f.add(severity, "resolution", message)
        finally:
            if resolver is not None:
                resolver.__exit__(None, None, None)
        check_archive(f, found, statuses, disc)
        check_indexes(f, schema, disc)
        check_presentation(f, disc)
        look_for_keys(f)
        return f


    def verify_errors():
        """The errors of verify_findings(), as 'place: message'."""
        return [f"{x['place']}: {x['message']}" for x in verify_findings() if x["severity"] == "error"]

Files and storage (14.2)
------------------------

### The layout

The discovery document names the layout, and is authoritative
(section 3.2); it must agree with the configuration, from which the tools
compute every path. For the owner-name layout the storage root has no
`ocfl_layout.json`, and, a breach being a warning, holds the text file that
describes the layout; for the hashed layout, `ocfl_layout.json` names it,
and a configuration file of the extension, if present, keeps its default
parameters. Every object must be at the path its identifier gives in that
layout.

    # in check the files and the storage of an archive:
    def check_storage(f, schema, disc):
        """The checks of section 14.2; returns {identifier: (folder, inventory)} of the objects."""
        if not (OCFL / "0=ocfl_1.1").exists():
            f.error("ocfl", "no OCFL 1.1 storage root (0=ocfl_1.1)")
        if disc and disc.get("storageLayout") != LAYOUT:
            f.error("opensheaf.json", f"storageLayout is {disc.get('storageLayout')}, the configuration says {LAYOUT}")
        if LAYOUT == OWNER_NAME_LAYOUT:
            if (OCFL / "ocfl_layout.json").exists():
                f.error("ocfl", "ocfl_layout.json names only registered layouts: the owner-name layout has none "
                        "(section 3.2)")
            if not (OCFL / LAYOUT_FILE).exists():
                f.warning("ocfl", f"{LAYOUT_FILE}, which describes the layout, is missing (section 3.2)")
        else:
            try:
                ext = json.loads((OCFL / "ocfl_layout.json").read_text(encoding="utf-8")).get("extension")
            except (OSError, ValueError):
                ext = None
            if ext != HASHED_LAYOUT:
                f.error("ocfl", f"ocfl_layout.json must name the extension {HASHED_LAYOUT} (section 3.2)")
            cfg = OCFL / "extensions" / HASHED_LAYOUT / "config.json"
            if cfg.exists():
                c = json.loads(cfg.read_text(encoding="utf-8"))
                if (c.get("digestAlgorithm", "sha256"), c.get("tupleSize", 3), c.get("numberOfTuples", 3)) != \
                        ("sha256", 3, 3):
                    f.error("ocfl", "the hashed layout keeps its default parameters (section 3.2)")
        found = {}
        for obj_id, d, inv in objects():
            rel = d.relative_to(OCFL).as_posix()
            if inv is None or obj_id is None:
                f.error(f"ocfl/{rel}", "an object without a readable inventory")
                continue
            try:
                expected = path_of(obj_id)
            except ValueError as e:
                f.error(f"ocfl/{rel}", str(e))
                continue
            if rel != expected:
                f.error(where(obj_id), f"is at ocfl/{rel}, and its identifier puts it at ocfl/{expected} (section 3.2)")
            if obj_id in found:
                f.error(where(obj_id), "two objects of the storage root have this identifier (section 4)")
            found[obj_id] = (d, inv)
            check_object_storage(f, schema, obj_id, d, inv)
        <<check the storage root with an independent OCFL validator>>
        return found

### The inventories, the versions and the inventory chain

For each object: the digest algorithm, the checksum file of the inventory,
the root inventory equal to that of its head version, and every stored file
against its digest. This last check reads every file of the archive, and is
what makes the verifier slow on large archives.

Then each version (section 4.1): versions numbered `v1`, `v2`, ...; its own
copy of the inventory with its checksum file, which is the inventory *as of
that version*: its head is that version, and it records exactly the
versions `v1` to `vN` of the root inventory, each as the root records it,
equal as JSON values (section 14.2), since a pin of a copy that recorded
another history would fix a history other than the object's; a user with a
name and a message, which the computed first version of a key log alone
lacks; logical paths in normalisation form C, without a leading or final
`/`, empty, `.` or `..` segments, or `\`; and the files every version holds:
`object.json`, `datacite.json` except in an owner object, `genesis.json`
except in a draft (section 4.1).

Last, the inventory chain (section 4.3): the `object.json` of every version
of a line after the first has `previous`, the digest of the inventory file
of the version before, as its checksum file states it; a first version and
a draft have none. The key logs are checked for it with the other rules of
key logs (section 14.3), so they are left out here.

    # in check the files and the storage of an archive:
    def check_logical_path(p):
        """Whether the logical path P follows the rules of section 4.1."""
        parts = p.split("/")
        return (unicodedata.normalize("NFC", p) == p and "\\" not in p
                and all(x not in ("", ".", "..") for x in parts))


    def check_object_storage(f, schema, obj_id, d, inv):
        place = where(obj_id)
        if inv.get("digestAlgorithm") != "sha512":
            f.error(place, "the digest algorithm is not sha512 (section 4.1)")
        root = (d / "inventory.json").read_bytes()
        sc = d / "inventory.json.sha512"
        if not sc.exists() or owners.sidecar_digest(sc.read_bytes()) != names.sha512_hex(root):
            f.error(place, "the checksum file of the inventory does not state its digest")
        head = inv.get("head", "")
        if not (d / head / "inventory.json").exists() or (d / head / "inventory.json").read_bytes() != root:
            f.error(place, f"the inventory of {head} is not the root inventory")
        for dig, paths in inv.get("manifest", {}).items():
            for cp in paths:
                if not (d / cp).exists():
                    f.error(place, f"missing {cp}")
                elif digest(d / cp) != dig:
                    f.error(place, f"{cp} does not have the digest of the manifest")
        versions = sorted(inv.get("versions", {}), key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)
        kind = (read_json(d, inv, OBJ) or {}).get("kind")
        draft = obj_id.startswith("sheaf:draft:")
        for n, ver in enumerate(versions, 1):
            at = f"{place} {ver}"
            if ver != f"v{n}":
                f.error(at, "versions are numbered v1, v2, ... without zero padding (section 4.1)")
                continue
            <<check the inventory copy of an object version>>
            vinfo = inv["versions"][ver]
            if not (kind == "owner" and n == 1) and (not vinfo.get("user", {}).get("name") or not vinfo.get("message")):
                f.error(at, "a version has a user with a name, and a message (section 4.1)")
            logical = {p for ps in vinfo.get("state", {}).values() for p in ps}
            for p in sorted(logical):
                if not check_logical_path(p):
                    f.error(at, f"the logical path {p!r} breaks the rules of section 4.1")
            needed = [OBJ] + (["datacite.json"] if kind != "owner" else []) + ([] if draft else [GENESIS])
            for name in needed:
                if name not in logical:
                    f.error(at, f"has no {name} (section 4.1)")
            obj = read_json(d, inv, OBJ, ver) if OBJ in logical else None
            if obj is None:
                continue
            if kind != "owner":
                schema(f"{at}/{OBJ}", obj, "object")
                <<check previous in an object version>>

The copy of the inventory in the version folder, and its checksum file.

    # in check the inventory copy of an object version:
    copy_path = d / ver / "inventory.json"
    if not copy_path.exists() or not (d / ver / "inventory.json.sha512").exists():
        f.error(at, "no copy of the inventory with its checksum file in the version folder (section 4.1)")
    else:
        if owners.sidecar_digest((d / ver / "inventory.json.sha512").read_bytes()) != digest(copy_path):
            f.error(at, "the checksum file of the inventory copy does not state its digest")
        try:
            copy = json.loads(copy_path.read_text(encoding="utf-8"))
        except ValueError:
            copy = {}
        upto = versions[:n]
        if copy.get("head") != ver:
            f.error(at, f"the inventory copy has the head {copy.get('head')}")
        if sorted(copy.get("versions") or {}) != sorted(upto):
            f.error(at, f"the inventory copy does not record exactly the versions v1 to {ver}")
        elif any(copy["versions"][v] != inv["versions"][v] for v in upto):
            f.error(at, "the inventory copy disagrees with the inventory about the versions it records")

`previous` is compared with what the checksum file of the version before
states, and that with the digest of its inventory file, which the copy
check above makes.

    # in check previous in an object version:
    if n == 1 or draft:
        if "previous" in obj:
            f.error(at, "a first version, or a draft, has no previous (section 4.3)")
    else:
        sc = d / f"v{n - 1}" / "inventory.json.sha512"
        expected = owners.sidecar_digest(sc.read_bytes()) if sc.exists() else None
        if "previous" not in obj:
            f.error(at, "object.json has no previous (section 4.3)")
        elif obj["previous"] != expected:
            f.error(at, f"previous is not the digest of the inventory of v{n - 1} (section 4.3)")

### An independent OCFL validator

An independent OCFL validator, `ocfl-py`, checks each object and the
storage root when it is installed: the tools write OCFL themselves, and a
second implementation catches what they might get wrong in the same way
twice. Only its errors are reported: its warnings are on what OpenSheaf
does on purpose, such as the witness folder, an extension folder not yet
registered with OCFL (section 7.2), or the first version of a key log,
which has no message or user (section 6.1). Without it, the check is not
made, which is a warning.

    # in check the storage root with an independent OCFL validator:
    try:
        import ocfl
        from ocfl.validator import Validator
    except ImportError:
        f.warning("ocfl", "the storage root is not checked by an OCFL validator: ocfl-py is not installed"
                  " (pip install 'opensheaf[validate]')")
    else:
        for obj_id, (d, inv) in found.items():
            v = Validator(log_warnings=False, log_errors=True)
            if not v.validate_object(str(d)):
                f.error(where(obj_id), f"OCFL validator: {v.status_str()}")
        if not ocfl.StorageRoot(root=str(OCFL)).validate(log_warnings=False):
            f.error("ocfl", "the OCFL validator rejects the storage root")

Key logs (14.3)
---------------

The owner objects are checked first, each from its first version, by
`KeyLog.check` of [chapter 6](06-owners.md), which makes the checks of
section 14.3: the genesis record and the computed first version, byte for
byte; the keeper's check digit, through the genesis record; `keys.json`
and the signatures of every later version; versions held after an ending
version or a fork record (warnings); ending versions; the rules on keys,
`next` and `exposed`; and fork records. Its errors and warnings are
reported as they are; the files are also checked against their schemas.
The results: the latest version of each key log, the exposed keys, and
ended owners, with their fork point and successor.

    # in check the key logs of an archive:
    def check_key_logs(f, found, schema):
        """The checks of section 14.3; returns {owner name: KeyLog} of the key logs held."""
        logs = {}
        for obj_id, (d, inv) in found.items():
            if (read_json(d, inv, OBJ) or {}).get("kind") != "owner":
                continue
            place = where(obj_id)
            try:
                log = owners.load_key_log(d)
            except owners.OwnerError as e:
                f.error(place, str(e))
                continue
            errors, warnings = log.check()
            for e in errors:
                f.error(place, e)
            for w in warnings:
                f.warning(place, w)
            try:
                schema(f"{place} v1/{GENESIS}", json.loads(log.genesis), "genesis")
            except ValueError:
                pass
            for v in log.versions:
                if v.keys is not None:
                    schema(f"{place} v{v.number}/keys.json", v.keys, "keys")
            logs[log.owner] = log
            latest = [v for v in log.versions if v.is_version]
            if latest:
                f.result(place, f"key log of {log.owner}: latest version v{latest[-1].number}")
            for did in sorted(log.exposed_keys()):
                f.result(place, f"exposed key {did}")
            if log.fork_point:
                f.result(place, f"ended by a fork of its key log at v{log.fork_point} (section 6.3)")
            elif log.ended:
                f.result(place, "ended (section 6.3)" + (f", successor {log.successor} (named by the ending "
                                                          "version)" if log.successor else ""))
        return logs

Lines (14.4)
------------

For every other object, the verifier checks its identity, its records and
its signatures. Drafts ([chapter 24](24-drafts.md)) are checked as section
10.1 says, as they stand: no genesis record, and no line in `object.json`.
With a resolver (`--remote`), the members of collections held in other
archives are resolved.

    # in check the lines of an archive:
    def check_lines(f, found, logs, schema, disc, resolver=None):
        """The checks of sections 14.4 and 14.5; returns {identifier: statuses} of the lines."""
        statuses, genesis_names = {}, {}
        tombstoned = {t.get("id") for t in disc.get("tombstones", []) if isinstance(t, dict)}
        for obj_id, (d, inv) in found.items():
            head = read_json(d, inv, OBJ) or {}
            if head.get("kind") == "owner":
                continue
            place = where(obj_id)
            if obj_id.startswith("sheaf:draft:"):
                if any(k in head for k in ("name", "owner", "parent")) or read_logical(d, inv, GENESIS):
                    f.error(place, "a draft has no genesis record, and no name, owner or parent (section 10.1)")
                continue
            <<check the identity of a line>>
            <<check the records of a line>>
            <<check the signatures of a line>>
        for gname, ids in genesis_names.items():
            lines = [i for i, branch in ids if not branch]
            if len(lines) > 1:
                f.error(", ".join(where(i) for i in lines), "objects with the same genesis record: only the "
                        "originator's line and its branches may share one (section 5.4)")
        kept = {}
        for obj_id, (d, inv) in found.items():
            if (read_json(d, inv, OBJ) or {}).get("kind") == "collection" and obj_id in statuses:
                check_members(f, found, logs, statuses, tombstoned, schema, obj_id, d, inv, resolver)
                check_accepted_copies(f, found, obj_id, d, inv, kept)
        return statuses

### Identity

The genesis record is part of every version, byte for byte (section 5.1),
and valid; the name in the identifier is one of its names (section 5.2),
and every `object.json` records the line of the identifier. The owner of a
line is the originator of its work, whose line is named by algorithm 0
(section 5.3); a line of another owner is a branch, which declares its
parent. Objects of the archive with the same genesis
name must be the originator's line and its branches (section 5.4); here,
two lines that are not branches are an error. A branch is checked as
section 9.3 says (below).

    # in check the identity of a line:
    _, nm, owner = obj_id.split(":")
    genesis = None
    for ver in inv["versions"]:
        p = read_logical(d, inv, GENESIS, ver)
        g = p.read_bytes() if p else None
        obj = read_json(d, inv, OBJ, ver) or {}
        if (obj.get("name"), obj.get("owner")) != (nm, owner):
            f.error(f"{place} {ver}", "object.json does not record the line of the identifier (section 4.3)")
        if g is None:
            continue
        if genesis is None:
            genesis = g
        elif g != genesis:
            f.error(f"{place} {ver}", "genesis.json differs from that of v1 (section 5.1)")
    rec = None
    if genesis is not None:
        try:
            rec = names.read_genesis(genesis)
            schema(f"{place} {GENESIS}", json.loads(genesis), "genesis")
        except ValueError as e:
            f.error(place, f"{GENESIS}: {e}")
    if rec is not None:
        genesis_names.setdefault(names.name(genesis), []).append((obj_id, "parent" in head))
        if rec["kind"] != head.get("kind"):
            f.error(place, f"its genesis record is of kind {rec['kind']}, its object.json of kind {head.get('kind')}")
        if not names.is_name_of(nm, genesis):
            f.error(place, "its name is not a name of its genesis record (section 5.2)")
        elif rec.get("originator") != owner:
            if "parent" in head:
                check_branch(f, place, obj_id, d, inv, genesis, logs, found, tombstoned, resolver)
            else:
                f.error(place, "a line of another owner than the originator is a branch, and declares its "
                        "parent (section 5.3)")
        elif names.algorithm(nm) != 0:
            f.error(place, "the originator's line is named by algorithm 0 (section 5.3)")
        elif any("parent" in (read_json(d, inv, OBJ, v) or {}) for v in inv["versions"]):
            f.error(place, "the originator's line has no parent: an originator never owns a branch of its own "
                    "work (sections 5.3 and 9)")

### Records

The rules of sections 4.2 to 4.4 in every version, and between versions for
documents (below): the descriptions agree on the document version, a
withdrawal has its date in both, `datacite.json` has the properties
section 4.4 requires, the notes find their files, a document version holds
its main source and renditions. A collection version holds its member list,
checked with its members after every line has its statuses.

    # in check the records of a line:
    for ver in inv["versions"]:
        for message in description_errors(d, inv, ver):
            f.error(f"{place} {ver}", message)
    if head.get("kind") == "document":
        for message in document_version_errors(obj_id, d, inv):
            f.error(place, message)

The descriptions are checked against each other and against sections 4.3
and 4.4. A Creative Commons or arXiv licence must be identified, by SPDX or
by URL, so that archives record the same licence the same way
(section 4.4).

    # in check the descriptions of an object version:
    def description_errors(d, inv, ver):
        """The breaches of sections 4.3 and 4.4 in the descriptions of VER of the object in D."""
        out = []
        logical = {p for ps in inv["versions"][ver]["state"].values() for p in ps}
        obj = read_json(d, inv, OBJ, ver) if OBJ in logical else None
        dc = read_json(d, inv, "datacite.json", ver) if "datacite.json" in logical else None
        if obj is None or dc is None:
            return out
        if str(obj.get("documentVersion")) != dc.get("version"):
            out.append("datacite.json and object.json disagree on the version")
        if obj.get("status") == "withdrawn" and date_of(dc, "Withdrawn") != obj.get("withdrawal", {}).get("date"):
            out.append("withdrawal dates disagree")
        for k in ("titles", "creators", "publicationYear", "types", "version", "publisher"):
            if k not in dc:
                out.append(f"datacite.json lacks {k}")
        for r in dc.get("rightsList", []):
            if r.get("rightsIdentifier") is None and r.get("rights", "").lower().startswith(("creative", "arxiv")) \
                    and not r.get("rightsUri"):
                out.append("licence without SPDX identifier and without rightsUri")
        for note in [obj.get("changes"), obj.get("sourcesMissing"), obj.get("licence")] + \
                obj.get("notices", []) + [obj.get("withdrawal", {}).get("reason")]:
            if note and note.get("path") and note["path"] not in logical:
                out.append(f"note file {note['path']} not in the version")
        if obj.get("kind") == "document":
            if obj.get("mainSource") and obj["mainSource"] not in logical:
                out.append("main source not in the version")
            if obj.get("sourcesMissing") and obj.get("mainSource"):
                out.append("sourcesMissing together with a main source")
            for r in obj.get("renditions", []):
                if r["path"] not in logical:
                    out.append(f"rendition {r['path']} not in the version")
        elif obj.get("kind") == "collection" and "members.json" not in logical:
            out.append("collection without members.json")
        return out

### Signatures

The status of every signature file and version (section 7.3), against the
key log of the owner kept beside the line (section 6.5). A key log missing
is an error, unless a tombstone stands for it (section 13.2), a warning; the
signatures that need it are unchecked. A signature file that is invalid, or
any other file of the witness folder that is not a witness, is a warning
(section 7.2): a host cannot break a version by adding a file. A version
that is not a version of its line (unsigned, or with invalid signatures
only) is a warning (sections 7.5 and 14.4), and so is an unchecked one, a
check not completed; a contested version is a result. The latest signed
version is a result too, with the line's status when it is withdrawn.

    # in check the signatures of a line:
    log = logs.get(owner)
    if log is None:
        owner_id = names.object_id(owner, owner)
        (f.warning if owner_id in tombstoned else f.error)(
            place, f"the key log of its owner {owner} is not in the storage root (section 6.5)")
    judgements, sts = line_statuses(d, inv, log)
    statuses[obj_id] = sts
    for i, (js, s) in enumerate(zip(judgements, sts), 1):
        at = f"{place} v{i}"
        for j in js:
            if j.status != sign.GOOD:
                f.warning(at, f"{j.file}: {j.status}: {j.reason}")
        others = [n for n in witnesses_of(d, f"v{i}") if not (n.startswith("signature-") and n.endswith(".json"))]
        for n in others:
            f.warning(at, f"{n}: not a witness these tools know (section 7.2)")
        if s in (sign.UNSIGNED, sign.INVALID):
            f.warning(at, f"not a version of the line: {s} (sections 7.3 and 7.5)")
        elif s == sign.UNCHECKED:
            f.warning(at, "unchecked: the version of the key log its signatures name is not reached (section 7.3)")
        elif s == sign.CONTESTED:
            f.result(at, "contested (section 7.3)")
    wdir = d / sign.WITNESSES
    for x in (sorted(wdir.iterdir()) if wdir.is_dir() else []):
        if not (x.is_dir() and x.name in inv["versions"]):
            f.warning(place, f"{sign.WITNESSES}/{x.name}: not the folder of a version (section 7.2)")
    signed = sign.latest_signed(sts)
    if signed is None:
        f.warning(place, "the line has no signed version (section 7.3)")
    else:
        f.result(place, f"latest signed version v{signed}")
        if (read_json(d, inv, OBJ, f"v{signed}") or {}).get("status") == "withdrawn":
            f.result(place, "withdrawn (section 13.1)")

### Document versions

The rules of section 4.2 concern the sequence of object versions of a
document, and are checked in one pass over them, remembering for each
document version its own files, its change note, and whether its sources
were missing.

    # in check the document versions of a document:
    def document_version_errors(obj_id, d, inv):
        """Section 4.2: numbering without gaps, the same files for the same
        document version (a version with sourcesMissing may be completed by adding
        files), the history, and notices kept unchanged."""
        errors = []
        seen, files_of, missing_of, highest = {}, {}, {}, 0
        had_history, notices = False, []
        for ver, vinfo in inv["versions"].items():
            <<the files of an object version that belong to its document version>>
            <<check the number and the files of a document version>>
            <<check the history recorded in an object version>>
            <<check that an object version keeps the earlier notices>>
        return errors

A document version is its *own* files: everything except the descriptions,
the identity files (the genesis record and, in a branch, the evidence of
its branch point, section 4.1), and the files of
notices and of a withdrawal, which description-only versions add, and the
file of the licence terms (`licence`, section 4.3): licence terms describe
the object, like `rightsList` in `datacite.json`, not the document version,
so a description-only version may add or replace them. Its change note
belongs to the document version, since it was written and deposited with it
(section 4.3), and so does the note of missing sources (a completion
"changes or removes no file of the version", section 4.2).

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
           if p not in IDENTITY and not is_evidence(p) and p not in notes}
    change = (obj.get("changes") or {}).get("text")
    if not seen and obj.get("parent"):
        highest = n - 1          # a branch numbers on from its branch point (section 9.4)

A document version seen before must have the same own files and change
note, except while its sources are missing: then files may be added (a
[completion](14-description.md)), never changed or removed. A document
version not seen before must have the next number, and must be new: an
object version holding the same own files and change note as an earlier
document version keeps its number (the rule of new versions, sections 4.2
and 14.4). Only this equality is checked; the first such earlier version is
named.

    # in check the number and the files of a document version:
    if n in seen:
        before, mis = files_of[n], missing_of[n]
        if mis:
            if any(before.get(p) not in (None, dig) for p, dig in own.items()) or not set(before) <= set(own):
                errors.append(f"{ver} changes files of document version {n} (only additions allowed)")
        elif own != before or change != seen[n]:
            errors.append(f"{ver} has other files than document version {n}")
        missing_of[n] = bool(obj.get("sourcesMissing"))
        files_of[n] = own
    else:
        if n != highest + 1:
            errors.append(f"{ver} document version {n} breaks the numbering (expected {highest + 1})")
        m = next((k for k in seen if files_of[k] == own and seen[k] == change), None)
        if m is not None:
            errors.append(f"{ver} document version {n} holds the same files and change note "
                          f"as document version {m}, whose number it keeps")
        highest = max(highest, n)
        seen[n], files_of[n], missing_of[n] = change, own, bool(obj.get("sourcesMissing"))

The history, once present, must stay present; it may name only object
versions that exist at that point; it must list each document version
known so far exactly once; and each entry must be the last object version
holding its document version, as known when the history was written.

    # in check the history recorded in an object version:
    hist = obj.get("history")
    if had_history and hist is None:
        errors.append(f"{ver} lacks the history of earlier versions")
    if hist is not None:
        had_history = True
        known = [v for v in inv["versions"] if int(v[1:]) <= int(ver[1:])]
        if any(h not in known for h in hist):
            errors.append(f"{ver} history names unknown object versions")
        else:
            docs = [read_json(d, inv, OBJ, h)["documentVersion"] for h in hist]
            if len(set(docs)) != len(docs) or set(docs) != set(range(1, highest + 1)):
                errors.append(f"{ver} history does not list each document version once")
            for h, k in zip(hist, docs):
                later = [v for v in known if int(v[1:]) > int(h[1:])
                         and read_json(d, inv, OBJ, v)["documentVersion"] == k]
                if later:
                    errors.append(f"{ver} history entry {h} is not the last object version of {k}")

Every notice of an object version must be present, unchanged, in the next
one, and so in every later one.

    # in check that an object version keeps the earlier notices:
    cur = obj.get("notices", [])
    if any(x not in cur for x in notices):
        errors.append(f"{ver} drops or changes an earlier notice")
    notices = cur

Collections (14.5)
------------------

For each collection version, the rules of section 8 on `members.json`: its
schema; a `type`, `catalogue` or `selection`; a member of a catalogue has
`version` and `inventorySha512` and no revisions, a member of a selection a
non-empty list of `revisions`, each with its three fields, of distinct
document versions, and none of `version`, `inventorySha512` or `follow`.

Then the pins of the members held in this archive, in every version: the
pinned object version exists, its inventory has the pinned digest (a
mismatch of a copy held in the archive is an error), it holds the stated
document version, its `object.json` has the member's `kind`, `name` and
`owner` (section 8.5), and its status. A version pinned that is not a
version of its line is an error, since a collection pins only signed
versions (section 8.5); an unchecked or contested one, or an object version
the copy lacks, a warning. A revision set must also be in the order of the
document's history (section 8.4), read from its latest signed version.
A member of the head that is not held here is reported as removed when
the archive has a tombstone of its line (section 13.3), and otherwise as
not resolved, a warning, unless the verifier resolves members (`--remote`):
each pin is then resolved from the member's `at` as a resolver does
([resolution](20-resolution.md)), and its status (section 8.5) is a result
when verified, an error when not a version, and a warning otherwise,
contested included (section 14.5). The copy found must be of the kind,
name and owner the member gives, and a revision must hold its document
version.

    # in check the members of a collection version:
    def check_members(f, found, logs, statuses, tombstoned, schema, obj_id, d, inv, resolver=None):
        for ver in inv["versions"]:
            at = f"{where(obj_id)} {ver}"
            mem = read_json(d, inv, "members.json", ver)
            if mem is None:
                continue
            schema(f"{at}/members.json", mem, "collection")
            kind = mem.get("type")
            if kind not in ("catalogue", "selection"):
                f.error(at, "members.json has no valid type (catalogue or selection)")
            for m in mem.get("members", []):
                mid = names.object_id(m.get("name"), m.get("owner"))
                who = f"{at} member {where(mid)}"
                <<check the fields of a member>>
                if mid in found:
                    <<check the pins of a member held in the archive>>
                elif ver == inv["head"]:
                    if resolver is not None:
                        <<resolve the pins of a member of another archive>>
                    elif mid in tombstoned:
                        f.result(who, "removed: a tombstone in this archive (section 13.3)")
                    else:
                        f.warning(who, "not held in this archive: not resolved (osheaf verify --remote resolves "
                                  "it, section 14.5)")

The pins of a member of another archive, resolved.

    # in resolve the pins of a member of another archive:
    for pv, pin, n in member_pins(m):
        res = resolver.pin(m.get("name"), m.get("owner"), pv, pin, m.get("at", []))
        if res.copy is not None:
            pobj = res.copy.read(OBJ, int(pv[1:])) or {}
            if (pobj.get("kind"), pobj.get("name"), pobj.get("owner")) != \
                    (m.get("kind"), m.get("name"), m.get("owner")) or (n is not None and pobj.get("documentVersion") != n):
                f.error(f"{who} {pv}", "the version pinned is not of the kind, line and document version the "
                        "member gives (section 8.5)")
        if res.status == "not a version":
            f.error(f"{who} {pv}", "not a version: a collection pins only signed versions (section 8.5)")
        elif res.status == "verified":
            f.result(f"{who} {pv}", f"verified at {res.copy.where} (section 8.5)")
        else:
            f.warning(f"{who} {pv}", f"{res.status} (section 8.5)")

The fields of a member, by the type of its collection.

    # in check the fields of a member:
    if kind == "catalogue" and (not m.get("version") or not m.get("inventorySha512") or "revisions" in m):
        f.error(who, "a member of a catalogue needs version and inventorySha512, and no revisions")
    if kind == "selection":
        revs = m.get("revisions")
        if any(k in m for k in ("version", "inventorySha512", "follow")):
            f.error(who, "a member of a selection has no version, inventorySha512 or follow")
        if not isinstance(revs, list) or not revs or any(
                not all(r.get(k) for k in ("documentVersion", "version", "inventorySha512")) for r in revs):
            f.error(who, "a member of a selection needs revisions, each with documentVersion, "
                    "version and inventorySha512")
        elif len({r["documentVersion"] for r in revs}) != len(revs):
            f.error(who, "a document version is vetted twice")

The pins of a member held in the archive.

    # in check the pins of a member held in the archive:
    md, minv = found[mid]
    sts = statuses.get(mid, [])
    for pv, pin, n in member_pins(m):
        p = md / str(pv) / "inventory.json"
        if not p.exists():
            f.warning(f"{who} {pv}", "unavailable: the copy held here lacks this version")
            continue
        if digest(p) != pin:
            f.error(f"{who} {pv}", "mismatch: the inventory held here has another digest (section 8.5)")
            continue
        pobj = read_json(md, minv, OBJ, pv) or {}
        if (pobj.get("kind"), pobj.get("name"), pobj.get("owner")) != (m.get("kind"), m.get("name"), m.get("owner")):
            f.error(f"{who} {pv}", "kind, name and owner are not those of the version pinned (section 8.5)")
        if n is not None and pobj.get("documentVersion") != n:
            f.error(f"{who} {pv}", f"does not hold document version {n}")
        s = sts[int(pv[1:]) - 1] if 0 < int(pv[1:]) <= len(sts) else None
        if s in (sign.UNSIGNED, sign.INVALID):
            f.error(f"{who} {pv}", "not a version: a collection pins only signed versions (section 8.5)")
        elif s in (sign.UNCHECKED, sign.CONTESTED):
            f.warning(f"{who} {pv}", f"{s} (section 8.5)")
    if kind == "selection" and sts:
        signed = sign.latest_signed(sts)
        hist = history_of(md, minv, f"v{signed}" if signed else None)
        order = [doc_version_of(md, minv, h) for h in hist]
        vetted = [r.get("documentVersion") for r in m.get("revisions") or []]
        pos = [order.index(x) for x in vetted if x in order]
        if pos != sorted(pos):
            f.error(who, "revisions not in the order of the history (section 8.4)")

Selections keep their accepted copies apart: two selections of the
archive with the same owner must not keep accepted copies of the same
document (sections 9.6 and 14.5), which would be one line. An accepted copy
is a member of a selection that is a branch owned by the selection's owner;
the document is its genesis record, by its genesis name.

    # in check the members of a collection version:
    def check_accepted_copies(f, found, obj_id, d, inv, kept):
        mem = read_json(d, inv, "members.json") or {}
        if mem.get("type") != "selection":
            return
        owner = obj_id.split(":")[2]
        for m in mem.get("members", []):
            mid = names.object_id(m.get("name"), m.get("owner"))
            if m.get("owner") != owner or mid not in found:
                continue
            md, minv = found[mid]
            if "parent" not in (read_json(md, minv, OBJ) or {}):
                continue
            g = read_logical(md, minv, GENESIS, "v1")
            key = (owner, names.name(g.read_bytes()) if g else mid)
            other = kept.setdefault(key, obj_id)
            if other != obj_id:
                f.error(where(obj_id), f"keeps an accepted copy of the document that {where(other)}, a selection "
                        "of the same owner, keeps: selections keeping copies of one document have different "
                        "owners (section 9.6)")

Branches (9.3, 9.4)
-------------------

A branch is checked at its first version and at every version that moves
its branch point, as section 9.3 says, by the checks of the
[branches](23-branches.md) module (`branch.verdict`), against the key logs
held beside it; and between those versions the identity files (the
genesis record and the evidence) must stay the same, byte for byte
(section 9.4). A version that moves the branch point must keep to the same
parent line, move forward, to another document version, and be
continuous: the two parent inventories have the same `id`, every entry of
`versions` of the previous one is equal to the entry of the same version
in the new one, and the digests of those entries are in the new manifest.

An inconsistent branch point is an error, an unchecked one a warning; the
verdict of the branch, the weakest of its branch points, is a result, and
so is whether the parent's line is held here, removed (a tombstone) or
withdrawn, or found elsewhere (with `--remote`, at the base URL that
`parent.url` gives when the storage root has its conventional name
`ocfl/`, and at the places the resolver knows). A rename that neither the
objects nor the tombstones of the archive justify (the names of smaller
algorithm numbers are free here for the owner) is a warning (section 5.3).

    # in check a branch:
    def check_branch(f, place, obj_id, d, inv, genesis, logs, found, tombstoned, resolver=None):
        from . import branch
        _, nm, owner = obj_id.split(":")
        prev_obj = prev_ev = None
        verdicts = []
        for ver in sorted(inv["versions"], key=lambda v: int(v[1:])):
            at = f"{place} {ver}"
            obj = read_json(d, inv, OBJ, ver) or {}
            state = {p: dig for dig, ps in inv["versions"][ver]["state"].items() for p in ps}
            ev = {p: dig for p, dig in state.items() if is_evidence(p) or p == GENESIS}
            p = obj.get("parent")
            if not isinstance(p, dict):
                f.error(at, "every version of a branch has parent (section 9.1)")
                continue
            if prev_obj is not None and p == prev_obj.get("parent"):
                if ev != prev_ev:
                    f.error(at, "the identity files change without moving the branch point (section 9.4)")
            else:
                v, problems = branch.verdict(branch.level_of_version(d, inv, ver), obj, genesis, logs.get)
                verdicts.append(v)
                if v == branch.INCONSISTENT:
                    f.error(at, "inconsistent branch point: " + "; ".join(problems))
                elif v == branch.UNCHECKED:
                    f.warning(at, "unchecked branch point: " + "; ".join(problems))
                if prev_obj is not None and v != branch.INCONSISTENT:
                    <<check that a branch point moves forward and continuously>>
            prev_obj, prev_ev = obj, ev
        if not verdicts:
            return
        verdict = max(verdicts, key=branch.ORDER.get)
        p = prev_obj["parent"]
        pid = names.object_id(p["name"], p["owner"])
        f.result(place, f"a branch of {where(pid)}: {verdict} (section 9.3)")
        <<report the parent line of a branch>>
        rec = names.read_genesis(genesis)
        if nm != p["name"] and names.algorithm(nm) > names.algorithm(p["name"]):
            gone = {t.get("name") for t in TOMBSTONES if t.get("owner") == owner}
            for k in range(names.algorithm(p["name"]), names.algorithm(nm)):
                other = names.name(genesis, k)
                if names.object_id(other, owner) not in found and other not in gone:
                    f.warning(place, f"renamed by algorithm {names.algorithm(nm)}, though algorithm {k} gives a "
                              "line free here (section 5.3)")
                    break
        if owner == rec.get("originator"):
            f.error(place, "an originator never owns a branch of its own work (section 5.3)")

Moving forward and continuously (section 9.4).

    # in check that a branch point moves forward and continuously:
    old = prev_obj["parent"]
    pinv_old = json.loads(read_logical(d, inv, "parent.inventory.json", f"v{int(ver[1:]) - 1}").read_bytes())
    pinv_new = json.loads(read_logical(d, inv, "parent.inventory.json", ver).read_bytes())
    if (p.get("owner"), p.get("name")) != (old.get("owner"), old.get("name")):
        f.error(at, "a branch point moves only to a version of the same parent line (section 9.4)")
    elif int(p["objectVersion"][1:]) <= int(old["objectVersion"][1:]) or \
            p.get("documentVersion") == old.get("documentVersion"):
        f.error(at, "a branch point moves only to a higher object version, holding another document "
                "version (section 9.4)")
    if pinv_old.get("id") != pinv_new.get("id") or any(
            pinv_new.get("versions", {}).get(v) != e for v, e in pinv_old.get("versions", {}).items()) or any(
            dg not in pinv_new.get("manifest", {}) for e in pinv_old.get("versions", {}).values()
            for dg in e.get("state", {})):
        f.error(at, "the new parent inventory does not continue the previous one (section 9.4)")

The parent's line, as far as the verifier finds it.

    # in report the parent line of a branch:
    if pid in found:
        pd, pinv = found[pid]
        signed = latest_signed(pd, pinv, logs.get(p["owner"]))
        status = (read_json(pd, pinv, OBJ, signed) or {}).get("status") if signed else None
        f.result(place, "the parent's line is held here" + (", withdrawn" if status == "withdrawn" else ""))
    elif pid in tombstoned:
        f.result(place, "the parent's line is removed: a tombstone in this archive (section 13.3)")
    elif resolver is not None:
        res = resolver.latest(p["name"], p["owner"], [p["url"].split("/ocfl/")[0] + "/"] if p.get("url") else [])
        f.result(place, f"the parent's line: {res.status}" + (f" at {res.copy.where}" if res.copy else ""))
    else:
        f.result(place, "the parent's line is not held here (osheaf verify --remote looks for it)")

The archive as a whole (14.6)
-----------------------------

The discovery document is a map, checked against the storage root: it must
list every object but drafts, each with the values its object gives, which
are those the tools would write now (`discovery()`, with the status of
each line read from its latest signed version); an entry that differs is
stale, which happens when an object was changed by other means than these
tools. Labels are distinct. `mainCollection` names a catalogue it lists;
when `owners` is present, the members of the main catalogue are lines of
those owners, and the owners listed are owner objects held, a breach of
these being a warning. `drafts` lists only drafts, with their heads. The
extensions the objects use are listed, a warning otherwise.

The tombstones (section 13.3): each with `id` the line of its `name` and
`owner`, no two with the same `id`, and none for an object of the storage
root or an entry of `objects`; and, a warning, none standing for an owner
object that lines of the archive need, which only the law or its keeper
justifies (section 13.2).

    # in check the archive as a whole:
    def check_archive(f, found, statuses, disc):
        """The checks of section 14.6 on the discovery document and its tombstones."""
        if not disc:
            return
        listed = {}
        for o in disc.get("objects", []):
            if not isinstance(o, dict):
                continue
            if o.get("id") in listed:
                f.error("opensheaf.json", f"lists {where(o.get('id'))} twice")
            listed[o.get("id")] = o
        now_disc = discovery()
        expected = {o["id"]: o for o in now_disc["objects"]}
        fields = ("kind", "name", "owner", "head", "inventorySha512", "status")
        for obj_id, e in expected.items():
            o = listed.get(obj_id)
            if o is None:
                f.error("opensheaf.json", f"does not list {where(obj_id)}, an object of the storage root (section 3.1)")
                continue
            stale = [k for k in fields if o.get(k) != e.get(k)]
            if stale:
                f.error("opensheaf.json", f"the entry of {where(obj_id)} is stale: " +
                        ", ".join(f"{k} {o.get(k)} instead of {e.get(k)}" for k in stale))
        for obj_id in listed:
            if obj_id not in expected:
                f.error("opensheaf.json", f"lists {obj_id}, which is not an object of the storage root (section 3.1)")
        labels = [o["label"] for o in listed.values() if o.get("label")]
        for lb in sorted({x for x in labels if labels.count(x) > 1}):
            f.error("opensheaf.json", f"the label {lb} is given twice (section 3.1)")
        <<check the main catalogue, the owners, the drafts and the extensions listed>>
        <<check the tombstones of the discovery document>>

The main catalogue, the owners, the drafts and the extensions.

    # in check the main catalogue, the owners, the drafts and the extensions listed:
    main = disc.get("mainCollection")
    if main is None:
        f.warning("opensheaf.json", "no mainCollection (section 3.1)")
    elif main not in listed or listed[main].get("kind") != "collection":
        f.error("opensheaf.json", f"mainCollection {main} is not a collection it lists")
    elif main in found:
        md, minv = found[main]
        mem = read_json(md, minv, "members.json") or {}
        if mem.get("type") != "catalogue":
            f.error("opensheaf.json", "mainCollection is not a catalogue (section 8.1)")
        if "owners" in disc:
            for m in mem.get("members", []):
                if m.get("owner") not in disc["owners"]:
                    f.warning("opensheaf.json", f"the main catalogue lists {m.get('name')}, a line of an owner "
                              "that owners does not list (section 8.1)")
    for o in disc.get("owners", []):
        if names.object_id(o, o) not in found:
            f.warning("opensheaf.json", f"owners lists {o}, whose key log is not held here (section 3.1)")
    drafts = {o["id"]: o for o in now_disc.get("drafts", [])}
    for dr in disc.get("drafts", []):
        if dr.get("id") not in drafts or drafts[dr["id"]]["head"] != dr.get("head"):
            f.error("opensheaf.json", f"drafts lists {dr.get('id')}, which is not a draft held with that head")
    missing = set(now_disc.get("extensions", [])) - set(disc.get("extensions", []))
    for e in sorted(missing):
        f.warning("opensheaf.json", f"extensions does not list {e}, which objects use (section 3.1)")

The tombstones, each also reported as a removal, a result.

    # in check the tombstones of the discovery document:
    seen = set()
    needed = {names.object_id(i.split(":")[2], i.split(":")[2]) for i in found if not i.startswith("sheaf:draft:")}
    for t in disc.get("tombstones", []):
        tid = t.get("id")
        if tid != names.object_id(t.get("name"), t.get("owner")):
            f.error("opensheaf.json", f"the tombstone {tid} is not the line of its name and owner (section 13.3)")
        if tid in seen:
            f.error("opensheaf.json", f"two tombstones of {tid}")
        seen.add(tid)
        if tid in found or tid in listed:
            f.error("opensheaf.json", f"{tid} has a tombstone, and is an object of the archive (section 13.3)")
        elif t.get("kind") == "owner" and tid in needed:
            f.warning("opensheaf.json", f"a tombstone stands for the key log {tid}, which lines of the archive "
                      "need: only the law or its keeper justifies it (section 13.2)")
        else:
            f.result("opensheaf.json", f"removed: {tid} ({t.get('date')}: {t.get('reason')})")

The indexes
-----------

The indexes the discovery document declares (section 12.5) are checked
against the storage root: every file against the schema of indexes, under
the name of its prefix; every object with a genesis record and every
sealed version, carried key-log versions included, has its entry, with
the values its object gives, in the file of its prefix; each tombstone has
its entries in `names/` and `sha512/` with the status `removed`, and none
in `owners/`; and, the verifier having access to the files, there are no
other entries, among them none of a draft. The entries the tools would
write now are the measure (`index_entries`, [chapter 16](16-index.md)).

    # in check the indexes of the archive:
    def check_indexes(f, schema, disc):
        declared = disc.get("indexes") or {}
        if not declared:
            f.warning("opensheaf.json", "no indexes declared (section 12.5)")
            return
        expected = index_entries()
        gone = {t.get("id"): t for t in disc.get("tombstones", []) if isinstance(t, dict)}
        for index, length in declared.items():
            if index not in INDEX_KEY:
                continue
            key, held = INDEX_KEY[index], []
            for p in sorted((ROOT / index).glob("*.json")) if (ROOT / index).is_dir() else []:
                place = f"{index}/{p.name}"
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except ValueError as e:
                    f.error(place, f"not JSON: {e}")
                    continue
                schema(place, data, "index")
                if data.get("index") != index:
                    f.error(place, f"an index file of {index}/ names the index {data.get('index')}")
                for e in data.get("entries", []):
                    if not isinstance(e, dict) or str(e.get(key, ""))[:length] != p.stem or len(p.stem) != length:
                        f.error(place, f"an entry not in the file of its prefix ({str(e)[:60]}...)")
                    held.append(e)
            want = [e for e in expected[index] if e.get("status") != "removed"]
            for e in want:
                if e not in held:
                    f.error(f"{index}/", f"no entry, or a stale one, for {e.get('id', e.get('owner'))} "
                            f"{e.get('version', '')} (section 12.5)")
            for e in held:
                if e in want:
                    continue
                if e.get("id") in gone and e.get("status") == "removed":
                    continue
                f.error(f"{index}/", f"an entry the storage root does not justify: {e.get('id', e.get('owner'))} "
                        f"{e.get('version', '')} (section 12.5)")
            for tid, t in gone.items():
                if index in ("names", "sha512") and not any(e.get("id") == tid and e.get("status") == "removed"
                                                            for e in held):
                    f.error(f"{index}/", f"no entry with the status removed for the tombstone {tid} (section 12.5)")
                if index == "owners" and any(e.get("owner") == t.get("owner") and t.get("name") in e.get("names", [])
                                             for e in held):
                    f.error(f"{index}/", f"owners/ lists {tid}, which is taken down (section 12.5)")

The presentation files
----------------------

Presentation files are never authoritative (section 3), and a verifier
does not trust them; but an archive that declares the profile `website`
(appendix A.3) promises what they show, and some of it can be checked from
the files alone. The home page presents the latest signed version of the
main catalogue: it shows the pin of every member, the beginning of its
digest, as the [website](30-website.md) and the [TeXmacs index](16-index.md)
write it, which tells a stale home page from a current one. Each member
whose line is held here has a landing page at `paper/<label>/` (or
`paper/<name>/` without a label), which gives the full `sheaf:` URI of its
line (appendix A.3, section 12.2). Under the profile, what is missing is an
error; an archive that has an `index.html` without declaring the profile is
told the same as warnings. A member whose line was taken down here is not
looked for: the takedown removed it from the pages (section 13.2).

    # in check the presentation files of the profile website:
    def check_presentation(f, disc):
        """Appendix A.3: the home page shows the pin of every member of the latest signed
        version of the main catalogue, and each member held here has a landing page giving the
        full sheaf: URI of its line."""
        website = "website" in (disc.get("profiles") or [])
        home = ROOT / "index.html"
        if not website and not home.exists():
            return
        report = f.error if website else f.warning
        note = "" if website else " (the archive does not declare the profile website)"
        members = main_members() or []
        if not home.exists():
            report("index.html", "the home page is missing (appendix A.3)" + note)
            return
        page = home.read_text(encoding="utf-8", errors="replace")
        gone = {t.get("id") for t in TOMBSTONES}
        for m in members:
            if f"sheaf:{m.get('name')}:{m.get('owner')}" in gone:
                continue
            pin = (member_pins(m)[-1][1] or "")
            if pin[:32] not in page:
                report("index.html", f"does not show the pin of {m.get('name')}" + note)
            try:
                obj_id = names.object_id(m.get("name"), m.get("owner"))
                held_here = (obj_dir(obj_id) / "inventory.json").is_file()
            except (ValueError, TypeError):
                continue
            if held_here:
                landing = ROOT / "paper" / (label_of(obj_id) or m["name"]) / "index.html"
                text = landing.read_text(encoding="utf-8", errors="replace") if landing.is_file() else ""
                if f"sheaf:{m['name']}:{m['owner']}" not in text:
                    report(landing.relative_to(ROOT).as_posix(), f"no landing page giving the sheaf: URI of "
                           f"{where(obj_id)} (appendix A.3)" + note)

Keys left in the archive
------------------------

Private keys MUST NOT be stored in an archive (section 15.4): whatever an
archive holds is public and copied. The tools never write one there, and
refuse to export rotation keys inside it ([chapter 7](07-keys.md)), but a
person may copy one in by mistake. With access to the files, the verifier
looks for files that look like keys: exported rotation keys (by their
first line or their name), printed sheets, the files of current keys
(`.key`), and small files holding nothing but the base64 of 32 bytes, the
form of a seed. It cannot be sure, and the finding is a warning. The
folders of git and of the tools' staging are not searched.

    # in look for keys left in the archive:
    def look_for_keys(f):
        """Warn of the files of the archive that look like private keys (section 15.4)."""
        rotation_name = re.compile(r"^rotation-[a-z2-7]{16}-[a-z2-7]{16}\.txt$")
        for p in sorted(ROOT.rglob("*")):
            rel = p.relative_to(ROOT)
            if rel.parts[0] == ".git" or rel.parts[0].startswith(".staging-") or p.is_symlink() or not p.is_file():
                continue
            looks = rotation_name.match(p.name) or p.suffix == ".key"
            if not looks and p.stat().st_size < 4096:
                text = p.read_bytes().decode("ascii", "replace")
                if text.startswith((keys.ROTATION_FORMAT, keys.SHEET_TITLE)):
                    looks = True
                else:
                    try:
                        import base64
                        looks = len(base64.b64decode(text.strip(), validate=True)) == 32
                    except ValueError:
                        looks = False
            if looks:
                f.warning(rel.as_posix(), "looks like a private key: keys are never kept in an archive "
                          "(section 15.4)")

The command
-----------

The command prints the findings, one per line, with their severity and
place, then their numbers; with `--json`, the findings as a JSON list, for
programs. Its exit status counts the errors only, so that it can run in
continuous integration: an archive with warnings passes (section 14.1).
With `--remote`, the members of collections held in other archives are
resolved from their locations and given their statuses (section 14.5).

    # in the verify command:
    def verify(args):
        found = verify_findings(remote=getattr(args, "remote", False))
        if getattr(args, "json", False):
            print(json.dumps(found, indent=2, ensure_ascii=False))
        else:
            for x in found:
                print(f"{x['severity']}: {x['place']}: {x['message']}")
            e, w, r = (found.count(s) for s in ("error", "warning", "result"))
            print(("OK" if not e else f"{e} error(s)") + f", {w} warning(s), {r} result(s)")
        sys.exit(1 if found.count("error") else 0)
