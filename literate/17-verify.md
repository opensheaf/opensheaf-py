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
[owner catalogues](15-owner-catalogues.md) and the
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

A `pattern` of a JSON Schema is an ECMA-262 regular expression, whose `$`
matches only at the end of the string; Python's `$` also matches before a
final newline, so that `jsonschema` would let the label `paper-a\n` pass
`^[a-z0-9]+(-[a-z0-9]+)*$`. The keyword is checked with `ecma_pattern`,
which writes each `$` outside a character class as `\Z`, so that the
schemas mean the same here as in the JavaScript tools.

    # in the findings of a verifier:
    def ecma_pattern(pattern):
        """PATTERN, an ECMA-262 regular expression of a JSON Schema, for Python's re: each $ outside a
        character class and not escaped becomes \\Z (the end of the string, not before a newline)."""
        out, escaped, in_class = [], False, False
        for c in pattern:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "$" and not in_class:
                c = r"\Z"
            out.append(c)
        return "".join(out)


    def schema_validator(jsonschema):
        """The validator class of the JSON Schemas of 0.2: Draft 2020-12, its pattern read as ECMA-262."""
        def pattern(validator, patrn, instance, schema):
            if validator.is_type(instance, "string") and not re.search(ecma_pattern(patrn), instance):
                yield jsonschema.ValidationError(f"{instance!r} does not match {patrn!r}")
        return jsonschema.validators.extend(jsonschema.Draft202012Validator, {"pattern": pattern})


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
                validators[name] = schema_validator(jsonschema)(schema, format_checker=formats)
            for e in validators[name].iter_errors(data):
                f.add(severity, place, e.message)
        return check

The checks
----------

The verifier first tells an archive of version 0.1 by its configuration
or its discovery document, and reports a single error: section 16.1 says
that such an archive is rebuilt, and these tools do not read it. The pages
of an archive that pages its objects (section 3.1) are read and checked
against their schema with the discovery document, a page missing being an
error, and their entries are checked as `objects` are: that every object
of the storage root is listed, and none twice, also across pages. Then the
steps of section 14, in order, during which the statuses of each line
([chapter 10](10-archive.md)) and the result of each verification of a
signature ([chapter 8](08-signatures.md)) are kept, so that each is
computed once.

    # in check an archive and list its findings:
    def verify_findings(remote=False, keeper_fetch=None):
        """The findings of the checks of section 14 on the archive, in the order of 14.2 to 14.6;
        REMOTE: also resolve the members of other archives (section 14.5) and read the places of
        keepers (section 6.6), with KEEPER_FETCH (owners.fetch_json by default)."""
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
                disc = names.loads_format(disc_path.read_bytes())
            except ValueError as e:
                f.error("opensheaf.json", str(e))
                disc = None
            if not isinstance(disc, dict):
                if disc is not None:
                    f.error("opensheaf.json", "the discovery document is a JSON object (section 3.1)")
                disc = {}
            elif disc.get("specification") == "0.1":
                f.error("archive", "specification 0.1: rebuild (section 16.1)")
                return f
            else:
                schema("opensheaf.json", disc, "archive")
                if "objectPages" in disc:
                    disc["objects"] = check_object_pages(f, schema, disc)
        SKIPPED.clear()
        global STATUSES
        before, STATUSES = STATUSES, ({} if STATUSES is None else STATUSES)
        try:
            with sign.remembered():
                return checked(f, schema, disc, remote, keeper_fetch)
        finally:
            SKIPPED.clear()
            STATUSES = before


    def checked(f, schema, disc, remote, keeper_fetch):
        """The steps of section 14, with their findings in F."""
        found = guarded(f, "the storage root", check_storage, f, schema, disc) or {}
        logs = guarded(f, "the key logs", check_key_logs, f, found, schema) or {}
        guarded(f, "the keepers", check_keepers, f, logs, remote, keeper_fetch, schema)
        resolver = None
        if remote:
            from . import remote as remote_
            resolver = remote_.Resolver()
        try:
            statuses = guarded(f, "the lines", check_lines, f, found, logs, schema, disc, resolver) or {}
            if resolver is not None:
                for severity, message in resolver.notes:
                    f.add(severity, "resolution", message)
        finally:
            if resolver is not None:
                resolver.__exit__(None, None, None)
        guarded(f, "the archive", check_archive, f, found, statuses, disc)
        guarded(f, "the indexes", check_indexes, f, schema, disc)
        guarded(f, "the presentation files", check_presentation, f, disc)
        look_for_keys(f)
        look_for_links(f)
        return f

The files the verifier reads are anyone's, and a file it did not foresee
(a content path out of the object, a list where a mapping is expected, a
JSON nested a hundred thousand times) must become a finding, not end the
verification half way with a traceback. Each object is checked on its own,
and one that cannot be read is reported and left out of the later steps
(`check_storage`); each step runs under `guarded`, which turns what stops
it into an error that says which step stopped, and goes on to the next.

An object that cannot be read is also left out of the storage root as the
later steps see it (`SKIPPED`, which `objects` passes over): they would
read it again, to compare the discovery document and the indexes with the
storage root, and stop on it. `SKIPPED` holds for one verification only.

    # in check an archive and list its findings:
    UNREADABLE = (UnsafePath, ValueError, KeyError, TypeError, AttributeError, IndexError,
                  RecursionError, OSError)


    def guarded(f, what, step, *args):
        """STEP(*ARGS), or None after an error in F if it stops on a file it cannot read."""
        try:
            return step(*args)
        except UNREADABLE as e:
            f.error("archive", f"the checks of {what} stopped on a file they cannot read "
                    f"({type(e).__name__}: {str(e)[:300]}); the rest of them are not made")
            return None


    def check_object_pages(f, schema, disc):
        """The entries of the pages of objects of DISC (section 3.1), each page checked; a page
        missing or not valid is an error, and its entries are not read."""
        out = []
        for path in disc.get("objectPages") or []:
            data = local_page(path) if isinstance(path, str) else None
            if data is None:
                f.error("opensheaf.json", f"the page of objects {path} is missing (section 3.1)")
                continue
            try:
                page = names.loads_format(data)
            except ValueError as e:
                f.error(path, str(e))
                continue
            schema(path, page, "objects")
            if isinstance(page, dict) and isinstance(page.get("objects"), list):
                out += [o for o in page["objects"] if isinstance(o, dict)]
        return out


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
with a `description`, and a configuration file of the extension, if present, keeps its default
parameters. Every object must be at the path its identifier gives in that
layout. The storage root the discovery document names is a relative path
below the archive (`storage_root_ok`), checked by hand, as the resolver
checks it, and not only by the schema, which may not be installed.

    # in check the files and the storage of an archive:
    def check_storage(f, schema, disc):
        """The checks of section 14.2; returns {identifier: (folder, inventory)} of the objects."""
        if not (OCFL / "0=ocfl_1.1").exists():
            f.error("ocfl", "no OCFL 1.1 storage root (0=ocfl_1.1)")
        if disc and disc.get("storageLayout") != LAYOUT:
            f.error("opensheaf.json", f"storageLayout is {disc.get('storageLayout')}, the configuration says {LAYOUT}")
        if disc and not storage_root_ok(disc.get("storageRoot")):
            f.error("opensheaf.json", f"storageRoot {disc.get('storageRoot')!r} is not a relative path of a folder "
                    "below the archive, ending with / (section 3.1)")
        if LAYOUT == OWNER_NAME_LAYOUT:
            if (OCFL / "ocfl_layout.json").exists():
                f.error("ocfl", "ocfl_layout.json names only registered layouts: the owner-name layout has none "
                        "(section 3.2)")
            if not (OCFL / LAYOUT_FILE).exists():
                f.warning("ocfl", f"{LAYOUT_FILE}, which describes the layout, is missing (section 3.2)")
        else:
            try:
                layout = names.json_value((OCFL / "ocfl_layout.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                layout = None
            layout = layout if isinstance(layout, dict) else {}
            if layout.get("extension") != HASHED_LAYOUT:
                f.error("ocfl", f"ocfl_layout.json must name the extension {HASHED_LAYOUT} (section 3.2)")
            if not isinstance(layout.get("description"), str) or not layout["description"].strip():
                f.error("ocfl", "ocfl_layout.json has a description (section 3.2)")
            cfg = OCFL / "extensions" / HASHED_LAYOUT / "config.json"
            try:
                c = names.json_value(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
            except (OSError, ValueError):
                c = None
            if not isinstance(c, dict):
                f.error("ocfl", f"extensions/{HASHED_LAYOUT}/config.json is not a JSON object")
            else:
                if (c.get("digestAlgorithm", "sha256"), c.get("tupleSize", 3), c.get("numberOfTuples", 3)) != \
                        ("sha256", 3, 3):
                    f.error("ocfl", "the hashed layout keeps its default parameters (section 3.2)")
        found, unread = {}, []
        for obj_id, d, inv in objects():
            rel = d.relative_to(OCFL).as_posix()
            if inv is None or obj_id is None:
                f.error(f"ocfl/{rel}", "an object without a readable inventory")
                unread.append(rel)
                SKIPPED.add(d)
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
            problem = inventory_problem(inv)
            try:
                if problem:
                    f.error(where(obj_id), f"{problem}: not checked further")
                    readable = False
                else:
                    readable = check_object_storage(f, schema, obj_id, d, inv)
            except UNREADABLE as e:
                f.error(where(obj_id), f"cannot be read ({type(e).__name__}: {str(e)[:300]}): not checked further")
                readable = False
            if readable is False:
                del found[obj_id]
                unread.append(obj_id)
                SKIPPED.add(d)
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

Section 4.1 reserves the names of the files it defines at the top level
of the content for those files: `object.json`, `datacite.json`,
`genesis.json`, `members.json`, `keys.json`, `forked` and `parent`. In a
document or a collection, `members.json` is the member list of a
collection only, `parent/` the evidence of the branch point of a branch
only (an `object.json` with `parent`), and `keys.json` and `forked` belong
to owner objects, whose key logs are checked apart (section 14.3). Any
other use of these names, as a file or as a folder, is an error. The
deposit refuses them in the same way (`deposit_path_problem`, in the
chapter on the [deposit](13-deposit.md)).

The files of the specification in each version, `object.json`,
`members.json`, and, in the evidence of a branch point, `object.json` and
the signature files of every level (`parent/object.json`,
`parent/signatures/...`, `parent/parent/...`), are read with `loads_format`
([names](05-names.md)): JSON in UTF-8 without a byte order mark, and
numbers that are integers written without a fraction or an exponent, of
absolute value at most 2^53 - 1 (section 2), in the data of extensions
too. A file that breaks it is reported with what breaks it, and
the object is not checked further, as a file it cannot read would stop
it: `2.0` read as a number would otherwise pass a schema whose `integer`
accepts it, and be compared with `2` elsewhere.

Before any of this, the inventory must have the shape the checks read: a
manifest mapping digests to lists of content paths, versions mapping names
to versions, each with a state of the same shape, a user that is a mapping
and a message that is text, if they are given. An inventory of another
shape is reported, and its object is not checked further: the checks would
otherwise stop on it.

    # in check the files and the storage of an archive:
    def inventory_problem(inv):
        """Why the inventory INV does not have the shape of an OCFL inventory, or None."""
        def paths_map(m):
            return isinstance(m, dict) and all(
                isinstance(k, str) and isinstance(v, list) and v and all(isinstance(p, str) for p in v)
                for k, v in m.items())
        if not paths_map(inv.get("manifest")):
            return "the inventory has no manifest of digests and content paths (OCFL 3.5.3)"
        versions = inv.get("versions")
        if not isinstance(versions, dict) or not versions or not all(
                isinstance(v, dict) for v in versions.values()):
            return "the inventory has no versions, each a JSON object (OCFL 3.5.3)"
        if inv.get("head") not in versions:
            return "the head of the inventory is not one of its versions (OCFL 3.5.1)"
        for name, v in versions.items():
            if not paths_map(v.get("state")):
                return f"{name} has no state of digests and logical paths (OCFL 3.5.3.1)"
            if not isinstance(v.get("user", {}), dict) or not isinstance(v.get("message", ""), str) \
                    or not isinstance(v.get("created", ""), str):
                return f"{name} has a user that is not a JSON object, or a message or time that is not text"
        return None


    RESERVED = ("object.json", "datacite.json", "genesis.json", "members.json", "keys.json", "forked", "parent")


    def reserved_name_errors(obj, logical):
        """The uses of the names section 4.1 reserves, among the logical paths LOGICAL of a version of
        a document or collection whose object.json is OBJ."""
        out = []
        for p in sorted(logical):
            top = p.split("/")[0]
            if top not in RESERVED:
                continue
            if p == top and top in ("object.json", "datacite.json", "genesis.json"):
                continue
            if p == top == "members.json" and obj.get("kind") == "collection":
                continue
            if top == "parent" and p != top and "parent" in obj:
                continue
            out.append(f"{p}: the name {top} is reserved for the file section 4.1 defines")
        return out


    def check_logical_path(p):
        """Whether the logical path P follows the rules of section 4.1."""
        parts = p.split("/")
        return (unicodedata.normalize("NFC", p) == p and "\\" not in p
                and all(x not in ("", ".", "..") for x in parts))


    EVIDENCE_FILE = re.compile(r"(?:parent/)+(?:object\.json|signatures/signature-[^/]+\.json)\Z")


    def format_file(p):
        """The schema of the file of the specification at the logical path P of a version, or None:
        object.json, members.json, and in the evidence of a branch point, at every level, object.json
        and the signature files."""
        if p in (OBJ, "members.json"):
            return "object" if p == OBJ else "collection"
        if EVIDENCE_FILE.match(p):
            return "object" if p.endswith("/" + OBJ) else "signature"
        return None


    def lexical_errors(d, inv, ver, logical):
        """The breaches of section 2 (UTF-8 without a byte order mark, numbers exact integers) in the
        files of the specification among the logical paths LOGICAL of VER of the object in D."""
        out = []
        for name in sorted(logical):
            if format_file(name):
                try:
                    names.loads_format(read_logical(d, inv, name, ver).read_bytes())
                except ValueError as e:
                    out.append(f"{name}: {e}")
        return out


    def check_object_storage(f, schema, obj_id, d, inv):
        place = where(obj_id)
        if inv.get("digestAlgorithm") != "sha512":
            f.error(place, "the digest algorithm is not sha512 (section 4.1)")
        <<check that the digests of an inventory are in lower case>>
        root = (d / "inventory.json").read_bytes()
        sc = d / "inventory.json.sha512"
        if not sc.exists() or owners.sidecar_digest(sc.read_bytes()) != names.sha512_hex(root):
            f.error(place, "the checksum file of the inventory does not state its digest")
        head = inv.get("head", "")
        if not (d / head / "inventory.json").exists() or (d / head / "inventory.json").read_bytes() != root:
            f.error(place, f"the inventory of {head} is not the root inventory")
        unsafe = False
        for dig, paths in inv.get("manifest", {}).items():
            for cp in paths:
                problem = content_problem(d, cp)
                if problem:
                    f.error(place, f"{problem}: it is not read, nor the object checked further")
                    unsafe = True
                elif not (d / cp).exists():
                    f.error(place, f"missing {cp}")
                elif digest(d / cp) != dig:
                    f.error(place, f"{cp} does not have the digest of the manifest")
        if unsafe:
            return False
        versions = sorted(inv.get("versions", {}), key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)
        try:
            kind = (read_json(d, inv, OBJ) or {}).get("kind")
        except ValueError:
            kind = None
        draft = obj_id.startswith("sheaf:draft:")
        malformed = False
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
            bad = lexical_errors(d, inv, ver, logical)
            for message in bad:
                f.error(at, message)
            malformed = malformed or bool(bad)
            obj = read_json(d, inv, OBJ, ver) if OBJ in logical and not bad else None
            if obj is None:
                continue
            schema(f"{at}/{OBJ}", obj, "object")
            for p in sorted(x for x in logical if x.startswith("parent/") and format_file(x)):
                schema(f"{at}/{p}", read_json(d, inv, p, ver), format_file(p))
            if kind != "owner":
                for message in reserved_name_errors(obj, logical):
                    f.error(at, message)
                <<check previous in an object version>>
        if malformed:
            f.error(place, "a file of the specification in it breaks the rules of section 2: not checked further")
            return False

Digests in inventories and checksum files are in lower case (section 4.1),
so that they compare as strings and every quotation of a pin is the same
string. A digest in upper case is reported as such, before the comparisons
that it would otherwise fail with a misleading "does not have the digest".
The checksum files are those of the root inventory and of every version
folder; the copies of the inventory in version folders are checked equal
to the root's, so their digests need no check of their own.

    # in check that the digests of an inventory are in lower case:
    stated = list(inv.get("manifest", {}))
    stated += [x for v in inv.get("versions", {}).values() for x in (v.get("state") or {})]
    stated += [x for alg in (inv.get("fixity") or {}).values() if isinstance(alg, dict) for x in alg]
    if any(isinstance(x, str) and x != x.lower() for x in stated):
        f.error(place, "the inventory has digests not in lower case (section 4.1)")
    for sc in [d / "inventory.json.sha512"] + sorted(d.glob("v*/inventory.json.sha512")):
        words = sc.read_bytes().split() if sc.exists() else []
        if words and words[0] != words[0].lower():
            f.error(place, f"{sc.relative_to(d)} states its digest not in lower case (section 4.1)")

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
made, which is a warning. Each object is given to it once; the storage
root as a whole is then validated without its objects
(`validate_objects=False`): its declaration, its extensions and the
hierarchy of folders down to the objects, whose errors are the only ones
that make `validate` false (an object rejected there is not, and is
reported above). It walks the folders of the storage root, links
included, so it is not run on a storage root with an object that cannot
be read.

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
        if unread:
            f.warning("ocfl", "the storage root as a whole is not given to the OCFL validator: it would read "
                      "the files of the objects that cannot be read")
        elif not ocfl.StorageRoot(root=str(OCFL)).validate(validate_objects=False, log_warnings=False):
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
reported as they are; the files are also checked against their schemas,
the signature files of the witness folders too (a breach is a warning, as
a malformed witness is, section 7.2).
The results: the latest version of each key log, the exposed keys, and
ended owners, with their fork point and successor.

    # in check the key logs of an archive:
    def check_witness_schemas(schema, at, witnesses):
        """The signature files among WITNESSES ({name: bytes}) of the version AT, against their schema; a
        breach is a warning, as a malformed witness is (section 7.2); one that is not JSON is judged
        apart."""
        for name, data in sorted(witnesses.items()):
            if name.startswith("signature-") and name.endswith(".json"):
                try:
                    value = names.json_value(data.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    continue
                schema(f"{at} {sign.WITNESSES}/{name}", value, "signature", "warning")


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
                check_witness_schemas(schema, f"{place} v{v.number}", v.witnesses)
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

A keeper named by an owner may confirm the link in a place it controls,
its ORCID record or its domain, and a verifier MAY check both directions
(section 6.6). That needs the network, so only `--remote` reads them
(`keeper_link`, in the chapter on [owners](06-owners.md)). The link is a
result, confirmed or claimed only, never an error: what the owner signed
is authentic either way, and the keeper decides nothing about its lines. A
place that cannot be read leaves the link not checked, a warning; without
`--remote` it is not checked either, which is said once for each keeper.
A successor that the keeper names is reported as section 6.6 says: named
by the keeper, or a claim when an ending version names another.

    # in check the key logs of an archive:
    def check_keepers(f, logs, remote, fetch=None, schema=lambda *a, **k: None):
        """The links of the owners of the key logs LOGS to their keepers (section 6.6), read with FETCH
        when REMOTE."""
        for log in logs.values():
            keeper = owners.keeper_of(log)
            if keeper is None:
                continue
            place = where(log.id)
            if not remote:
                f.result(place, f"keeper {keeper}: not checked (osheaf verify --remote reads its ORCID record "
                         "or domain, section 6.6)")
                continue
            link = owners.keeper_link(log, fetch)
            if link.status == owners.NOT_CHECKED:
                f.warning(place, f"keeper {keeper}: not checked ({link.reason})")
                continue
            if link.document is not None:
                schema(f"{place} keeper {keeper}", link.document, "keeper")
            f.result(place, f"keeper {keeper}: {link.status} ({link.reason}; section 6.6)")
            claim = owners.successor_claim(log, link)
            if claim:
                f.result(place, f"successor {link.successor} {claim}")

Lines (14.4)
------------

For every other object, the verifier checks its identity, its records and
its signatures. Drafts ([chapter 24](24-drafts.md)) are checked as section
10.1 says, as they stand: no genesis record, and no line in `object.json`.
With a resolver (`--remote`), the members of collections held in other
archives are resolved. Objects that share a genesis record, compared by
genesis name, the tombstones of the archive included (`genesisName`), are
the originator's line and branches of it (sections 5.4 and 14.4): a
tombstone of a line of the originator counts as that line, one of another
owner as a branch.

    # in check the lines of an archive:
    def check_lines(f, found, logs, schema, disc, resolver=None):
        """The checks of sections 14.4 and 14.5; returns {identifier: statuses} of the lines."""
        statuses, genesis_names, originators = {}, {}, {}
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
        for t in disc.get("tombstones", []) if isinstance(disc.get("tombstones"), list) else []:
            g = t.get("genesisName") if isinstance(t, dict) else None
            if g in genesis_names and isinstance(t.get("id"), str):
                genesis_names[g].append((t["id"], t.get("owner") != originators.get(g)))
        for gname, ids in genesis_names.items():
            lines = list(dict.fromkeys(i for i, branch in ids if not branch))
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
        originators[names.name(genesis)] = rec.get("originator")
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
documents and collections, a collection being a document whose source is
`members.json` (below): the descriptions agree on the document version, a
withdrawal has its date in both, `datacite.json` has the properties
section 4.4 requires, the notes find their files, a document version holds
its main source, and a document or collection version its renditions. A collection version holds its member list,
checked with its members after every line has its statuses.

    # in check the records of a line:
    for ver in inv["versions"]:
        for message in description_errors(d, inv, ver):
            f.error(f"{place} {ver}", message)
    if head.get("kind") in ("document", "collection"):
        for message in document_version_errors(obj_id, d, inv):
            f.error(place, message)
        for message in notice_warnings(d, inv):
            f.warning(place, message)

The descriptions are checked against each other and against sections 4.3
and 4.4. `rightsList` must hold at least one entry (#79): a version always
says on what terms its files may be used, if only that the rights are not
known. An entry of `rightsList` with `rightsIdentifier` or `rightsUri`
is a licence, one with neither a rights statement (section 4.4): the kind
is read from the file, never guessed from the name. An identifier is an
SPDX identifier, in lower case, so that archives record the same licence
the same way. Whether a licence allows a copy is not checked: the archive
keeping a copy answers for it (section 11.2).

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
        if not dc.get("rightsList"):
            out.append("datacite.json has no licence or rights statement in rightsList (section 4.4)")
        for r in dc.get("rightsList", []):
            ident = r.get("rightsIdentifier")
            if ident is not None and r.get("rightsIdentifierScheme") != "SPDX":
                out.append(f"rightsList: {ident} is not given as an SPDX identifier (section 4.4)")
            elif ident is not None and ident != ident.lower():
                out.append(f"rightsList: {ident} is not in lower case (section 4.4)")
        for note in [obj.get("changes"), obj.get("sourcesMissing"), obj.get("licence")] + \
                obj.get("notices", []) + [obj.get("withdrawal", {}).get("reason")]:
            if note and note.get("path") and note["path"] not in logical:
                out.append(f"note file {note['path']} not in the version")
        if obj.get("kind") == "document":
            if obj.get("mainSource") and obj["mainSource"] not in logical:
                out.append("main source not in the version")
            if obj.get("sourcesMissing") and obj.get("mainSource"):
                out.append("sourcesMissing together with a main source")
        elif obj.get("kind") == "collection" and "members.json" not in logical:
            out.append("collection without members.json")
        for r in obj.get("renditions", []):
            if r["path"] not in logical:
                out.append(f"rendition {r['path']} not in the version")
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
        check_witness_schemas(schema, at, witnesses_of(d, f"v{i}"))
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
        elif withdrawn := withdrawn_versions(d, inv, f"v{signed}"):
            f.result(place, f"reinstated; withdrawn: document version(s) {', '.join(map(str, sorted(withdrawn)))} "
                     "(section 13.1)")

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
        seen, files_of, missing_of, highest, first = {}, {}, {}, 0, 1
        fields_of, external_of = {}, {}
        had_history, notices, prev_ver, prev_obj = False, [], None, None

        def current_before(at):
            """The current document version as of object version AT, or None."""
            try:
                return doc_version_of(d, inv, current_version(d, inv, at)) if at else None
            except (KeyError, TypeError, ValueError, AttributeError, OSError):
                return None

        for ver, vinfo in inv["versions"].items():
            <<the files of an object version that belong to its document version>>
            <<check the number and the files of a document version>>
            <<check the fields that belong to a document version>>
            <<check that a withdrawal is kept until a new document version>>
            <<check the history recorded in an object version>>
            <<check that an object version keeps the earlier notices>>
            prev_ver, prev_obj = ver, obj
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
    if obj is None or obj.get("kind") not in ("document", "collection"):
        return errors
    n = obj.get("documentVersion")
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        errors.append(f"{ver}: documentVersion is a positive integer, not {n!r} (section 4.3): the "
                      "document versions are not checked further")
        return errors
    new_doc = n not in seen
    own, change = own_files(obj, {p: dig for dig, ps in vinfo["state"].items() for p in ps})

A document version seen before must have the same own files and change
note, except while its sources are missing: then files may be added (a
[completion](14-description.md)), never changed or removed. A document
version not seen before must have the next number, and must be new: its
own files, compared by logical path and digest, or its change note differ
from those of the current version as of the object version before (the
rule of new versions, sections 4.2 and 14.4). Files of an earlier version
that is not the current one, deposited again, are a revert, a new document
version.

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
        m = current_before(prev_ver)
        if m in seen and files_of[m] == own and seen[m] == change:
            errors.append(f"{ver} document version {n} holds the same files and change note "
                          f"as the current version {m}: it is no new document version (section 4.2)")
        highest = max(highest, n)
        seen[n], files_of[n], missing_of[n] = change, own, bool(obj.get("sourcesMissing"))

The fields that say what the files of a document version are belong to it,
like its change note: every object version holding the document version
has the same `mainSource`, `sourceFormat`, `sourcesMissing`, `renditions`
and `toolchain`, except while its sources are missing, when a completion
names them and may add renditions but drop none. The records at external
services of a document version are only added to: each one stays,
unchanged, in every later object version holding it (section 4.2). A
collection is a document whose source is `members.json`, and is checked
the same way.

    # in check the fields that belong to a document version:
    fields = {k: obj.get(k) for k in DOCUMENT_VERSION_FIELDS}
    external = obj.get("external", [])
    if n in fields_of:
        before = fields_of[n]
        if before["sourcesMissing"]:
            if any(r not in (fields["renditions"] or []) for r in before["renditions"] or []):
                errors.append(f"{ver} removes a rendition of document version {n} (section 4.2)")
        else:
            for k in DOCUMENT_VERSION_FIELDS:
                if fields[k] != before[k]:
                    errors.append(f"{ver} changes {k} of document version {n}, which belongs to it (section 4.2)")
        if any(e not in external for e in external_of[n]):
            errors.append(f"{ver} drops or changes an external record of document version {n} (section 4.2)")
    fields_of[n], external_of[n] = fields, external

The fields, in the order they are reported:

    # in check the descriptions of an object version:
    DOCUMENT_VERSION_FIELDS = ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain")

A withdrawal is a description-only version: a new document version is
never one. Once a line is withdrawn, every later object version keeps
`status` `withdrawn` and the same `withdrawal` until a new document
version reinstates it (section 13.1).

    # in check that a withdrawal is kept until a new document version:
    if new_doc and obj.get("status") == "withdrawn":
        errors.append(f"{ver} is a new document version and a withdrawal: a withdrawal is a "
                      "description-only version (section 13.1)")
    elif not new_doc and prev_obj is not None and prev_obj.get("status") == "withdrawn" and (
            obj.get("status") != "withdrawn" or obj.get("withdrawal") != prev_obj.get("withdrawal")):
        errors.append(f"{ver} drops or changes the withdrawal of {prev_ver}: only a new document version "
                      "reinstates a line (section 13.1)")

The history, once present, must stay present; it may name only object
versions that exist at that point; it must list each document version
known so far exactly once, from 1 (a branch numbers its own document
versions from 1, section 9.4); and each entry must be the last object version
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
            if len(set(docs)) != len(docs) or set(docs) != set(range(first, highest + 1)):
                errors.append(f"{ver} history does not list each document version once")
            for h, k in zip(hist, docs):
                later = [v for v in known if int(v[1:]) > int(h[1:])
                         and read_json(d, inv, OBJ, v)["documentVersion"] == k]
                if later:
                    errors.append(f"{ver} history entry {h} is not the last object version of {k}")

Every notice of an object version must be present, unchanged and in the
same order, at the start of the notices of the next one, and so of every
later one: a notice is numbered by its position, from 1 (section 4.2). A
new notice may replace an earlier one, by its number, which must be about
the same document version and not replaced already.

    # in check that an object version keeps the earlier notices:
    cur = obj.get("notices", [])
    if cur[:len(notices)] != notices:
        errors.append(f"{ver} drops, changes or moves an earlier notice")
    else:
        for k in range(len(notices), len(cur)):
            r = cur[k].get("replaces")
            if r is None:
                continue
            if not isinstance(r, int) or not 1 <= r <= k:
                errors.append(f"{ver} notice {k + 1} replaces no earlier notice ({r})")
            elif cur[r - 1].get("documentVersion") != cur[k].get("documentVersion"):
                errors.append(f"{ver} notice {k + 1} replaces notice {r}, about another document version")
            elif any(y.get("replaces") == r for y in cur[:k]):
                errors.append(f"{ver} notice {k + 1} replaces notice {r}, which is already replaced")
    notices = cur

The date of a notice is the date its author issued it, which should not
be later than its deposit, the `created` date of the object version that
added it (section 4.2). A later date is a warning: a notice dated in the
future, or a mistaken date.

    # in check the descriptions of an object version:
    def notice_warnings(d, inv):
        """The notices dated after the object version that added them (section 4.2)."""
        out, before = [], 0
        for ver, vinfo in inv["versions"].items():
            notices = (read_json(d, inv, OBJ, ver) or {}).get("notices", [])
            for k in range(before, len(notices)):
                date = notices[k].get("date", "")
                if isinstance(date, str) and date > vinfo["created"][:10]:
                    out.append(f"{ver} notice {k + 1} is dated {date}, after its deposit "
                               f"({vinfo['created'][:10]}, section 4.2)")
            before = max(before, len(notices))
        return out

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
version. The `datacite.json` of the collection version has a `HasPart`
relation to the DOI of every member (a catalogue's member) and revision
(a selection's) that has one (section 8.6).

    # in check the members of a collection version:
    def has_part_errors(d, inv, ver, mem):
        """The DOIs of members (a catalogue member's doi, a selection revision's doi) of the collection
        version VER in D to which its datacite.json has no HasPart relation (section 8.6)."""
        dc = read_json(d, inv, "datacite.json", ver) or {}
        rels = dc.get("relatedIdentifiers") if isinstance(dc.get("relatedIdentifiers"), list) else []
        parts = {str(r.get("relatedIdentifier")).lower() for r in rels if isinstance(r, dict)
                 and r.get("relationType") == "HasPart" and r.get("relatedIdentifierType") == "DOI"}
        members = [m for m in mem.get("members", []) if isinstance(m, dict)] if isinstance(mem, dict) else []
        dois = [m.get("doi") for m in members] + [r.get("doi") for m in members
                                                   for r in (m.get("revisions") or []) if isinstance(r, dict)]
        return [f"datacite.json has no HasPart relation to {doi}, the DOI of a member (section 8.6)"
                for doi in dict.fromkeys(x for x in dois if isinstance(x, str) and x) if doi.lower() not in parts]


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
            for message in has_part_errors(d, inv, ver, mem):
                f.error(at, message)
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

The pins of a member held in the archive. A key log has no statuses of
signed versions: a member that pins one of its versions is checked
against the key log held, whose version must have passed its checks
(section 14.3), not merely be there with the digest pinned.

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
        log = logs.get(m.get("owner")) if m.get("name") == m.get("owner") else None
        if log is not None and log.verified(int(pv[1:]), pin) is None:
            f.error(f"{who} {pv}", "not a version of the key log: a collection pins only versions (sections 6.1 "
                    "and 8.5)")
        <<report a member pinning a withdrawn document version>>
    if kind == "selection" and sts:
        signed = sign.latest_signed(sts)
        hist = history_of(md, minv, f"v{signed}" if signed else None)
        order = [doc_version_of(md, minv, h) for h in hist]
        vetted = [r.get("documentVersion") for r in m.get("revisions") or []]
        pos = [order.index(x) for x in vetted if x in order]
        if pos != sorted(pos):
            f.error(who, "revisions not in the order of the history (section 8.4)")

A member whose document version pinned is withdrawn, as the latest signed
version of its line says, is reported in the head of the collection, as a
result: a withdrawal is no breach, and holds also when the line has been
reinstated since (sections 13.1 and 14.5).

    # in report a member pinning a withdrawn document version:
    signed = sign.latest_signed(sts) if sts else None
    if ver == inv["head"] and signed:
        withdrawn = withdrawn_versions(md, minv, f"v{signed}")
        dv = pobj.get("documentVersion")
        if dv in withdrawn:
            f.result(f"{who} {pv}", f"document version {dv} is withdrawn, in {withdrawn[dv]} (section 13.1)")

Selections keep their accepted copies apart: an owner keeps one accepted
copy of a document, so selections that keep different accepted copies of
the same document have different owners (sections 9.6 and 14.5). The
selections of one owner, the issues of a journal, share its accepted copy,
and each of them may list it: that is no breach. What is one is an owner
whose selections list two different lines as accepted copies of one
document. An accepted copy is a member of a selection that is a branch
owned by the selection's owner; the document is its genesis record, by its
genesis name.

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
            other, other_copy = kept.setdefault(key, (obj_id, mid))
            if other_copy != mid:
                f.error(where(obj_id), f"keeps an accepted copy of a document of which {where(other)}, a selection "
                        "of the same owner, keeps another: selections keeping different accepted copies of one "
                        "document have different owners (section 9.6)")

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
withdrawn, or found elsewhere (with `--remote`, in the archive that holds
the object version at `parent.url`, found by its discovery document, and
at the places the resolver knows). A rename that neither the
objects nor the tombstones of the archive justify (the names of smaller
algorithm numbers are free here for the owner) is a warning (section 5.3).

The parent version, at every level of the chain, is also looked for in the
parent's line, as the verifier finds it (`parent_resolution`): held in
this archive, or with `--remote` resolved by its pin. Found with another
digest, it makes the branch point inconsistent; found signed, or vouched
for by a later signed version, it counts as signed (section 9.3).

    # in check a branch:
    def parent_resolution(found, resolver=None):
        """RESOLVE(parent) for branch.verdict: (whether the line found holds the parent version with the
        digest of the pin, its status there) for a parent version that the verifier finds, held in
        FOUND or resolved by RESOLVER; None for one it does not find."""
        def resolve(p):
            try:
                pid = names.object_id(p["name"], p["owner"])
                version, digest, n = p["objectVersion"], p["inventorySha512"], int(p["objectVersion"][1:])
            except (KeyError, TypeError, ValueError, AttributeError):
                return None
            if pid in found:
                pd, pinv = found[pid]
                if version not in pinv.get("versions", {}) or not (pd / version / "inventory.json").is_file():
                    return None
                if names.sha512_hex((pd / version / "inventory.json").read_bytes()) != digest:
                    return False, None
                return True, line_statuses(pd, pinv)[1][n - 1]
            if resolver is None:
                return None
            res = resolver.pin(p["name"], p["owner"], version, digest,
                               resolver.archive_of(p["url"]) if isinstance(p.get("url"), str) else [])
            if res.status in ("verified", "contested"):
                return True, sign.SIGNED if res.status == "verified" else sign.CONTESTED
            if any(c.digest(n) not in (None, digest) for c in res.copies or []):
                return False, None
            return None
        return resolve


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
                    f.error(at, "the identity files change without a new branch point (section 9.4)")
            else:
                v, problems = branch.verdict(branch.level_of_version(d, inv, ver), obj, genesis, logs.get,
                                             resolve=parent_resolution(found, resolver))
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

A new branch point is later, in the same parent line, and continues the
previous one (section 9.4).

    # in check that a branch point moves forward and continuously:
    old = prev_obj["parent"]
    pinv_old = json.loads(read_logical(d, inv, "parent/inventory.json", f"v{int(ver[1:]) - 1}").read_bytes())
    pinv_new = json.loads(read_logical(d, inv, "parent/inventory.json", ver).read_bytes())
    if (p.get("owner"), p.get("name")) != (old.get("owner"), old.get("name")):
        f.error(at, "a new branch point is a version of the same parent line (section 9.4)")
    elif int(p["objectVersion"][1:]) <= int(old["objectVersion"][1:]) or \
            p.get("documentVersion") == old.get("documentVersion"):
        f.error(at, "a new branch point is a higher object version, holding another document "
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
        res = resolver.latest(p["name"], p["owner"], resolver.archive_of(p["url"]) if p.get("url") else [])
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
tools. Labels are distinct. `owners` names each owner once, each with a
catalogue of its own: a collection it lists, of that owner, whose
`members.json` is a catalogue (section 8.1); `owners` missing is an error
(section 3.1 requires it, empty when the archive hosts no owner); a
warning, when an owner listed has no key log held here, and when an owner catalogue lists a member that is not a
document of a line of its owner held here, which section 8.1 does not
allow (a copy, another owner's line, a line of another archive); a member
taken down here is left to the next version of the catalogue (section
13.2).
`drafts` lists only drafts, with their heads. The extensions the objects
use are listed, a warning otherwise.

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
        <<check the owners and their catalogues, the drafts and the extensions listed>>
        <<check the tombstones of the discovery document>>

The owners and their catalogues, the drafts and the extensions.

    # in check the owners and their catalogues, the drafts and the extensions listed:
    if "owners" not in disc:
        f.error("opensheaf.json", "no owners: the owners hosted and their catalogues are not named (section 3.1)")
    seen_owners, seen_catalogues = set(), set()
    removed_here = {t.get("id") for t in disc.get("tombstones", []) if isinstance(t, dict)}
    for e in disc.get("owners", []):
        if not isinstance(e, dict):
            continue  # the schema reports it
        o, cat = e.get("owner"), e.get("catalogue")
        if o in seen_owners:
            f.error("opensheaf.json", f"owners lists {o} twice (section 3.1)")
        if cat in seen_catalogues:
            f.error("opensheaf.json", f"owners gives {cat} as the catalogue of two owners (section 3.1)")
        seen_owners.add(o)
        seen_catalogues.add(cat)
        try:
            if names.object_id(o, o) not in found:
                f.warning("opensheaf.json", f"owners lists {o}, whose key log is not held here (section 3.1)")
        except (ValueError, TypeError):
            continue
        entry = listed.get(cat) or {}
        if entry.get("kind") != "collection" or entry.get("owner") != o:
            f.error("opensheaf.json", f"the catalogue of {o} in owners, {cat}, is not a collection of that "
                    "owner it lists (section 8.1)")
            continue
        if cat not in found:
            continue
        md, minv = found[cat]
        mem = read_json(md, minv, "members.json") or {}
        if mem.get("type") != "catalogue":
            f.error("opensheaf.json", f"the owner catalogue of {o}, {where(cat)}, is not a catalogue (section 8.1)")
        for m in mem.get("members", []):
            if f"sheaf:{m.get('name')}:{m.get('owner')}" in removed_here:
                continue  # taken down: section 13.2 asks for a version without it
            try:
                mine = (m.get("owner") == o and m.get("kind") == "document"
                        and names.object_id(m.get("name"), o) in found)
            except (ValueError, TypeError):
                mine = False
            if not mine:
                f.warning("opensheaf.json", f"the owner catalogue of {o} lists {m.get('name')}, which is not a "
                          "document of a line of that owner held here (section 8.1)")
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
                    data = names.loads_format(p.read_bytes())
                except ValueError as e:
                    f.error(place, str(e))
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
owner catalogues: it shows the pin of every member, the beginning of its
digest, as the [website](30-website.md) and the [TeXmacs index](16-index.md)
write it, which tells a stale home page from a current one. Each member
whose line is held here has a landing page at the address built from its
name, which fixed files record (`paper/<name>/` for the originator's line,
`paper/<name>-<owner>/` for another, `name_address`), which gives the full `sheaf:` URI
of its line in canonical form (appendix A.3, sections 12.1 and 12.2):
`sheaf:<name>` for the originator's line, `sheaf:<name>:<owner>` for
another. Under the profile, what is missing is an
error. An archive that presents pages without declaring the profile is
told the same as warnings: one with an `index.html`, and one whose landing
pages are written with a TeXmacs index (the profile `texmacs`, a readable
index configured, or a folder `paper/`), whose `index.html`, an export
that needs TeXmacs, may not be there yet; its landing pages are checked
all the same. A member whose line was taken down here is not looked for:
the takedown removed it from the pages (section 13.2).

    # in check the presentation files of the profile website:
    def check_presentation(f, disc):
        """Appendix A.3: the home page shows the pin of every member of the latest signed
        version of each owner catalogue, and each member held here has a landing page giving the
        full sheaf: URI of its line; errors under the profile website, warnings for an archive
        that presents pages without declaring it."""
        profiles = disc.get("profiles") or []
        website = "website" in profiles
        home = ROOT / "index.html"
        landing_pages = ("texmacs" in profiles or bool(INDEX.get("html") or INDEX.get("template"))
                         or (ROOT / "paper").is_dir())
        if not (website or home.exists() or landing_pages):
            return
        report = f.error if website else f.warning
        note = "" if website else " (the archive does not declare the profile website)"
        members = catalogue_members() or []
        page = home.read_text(encoding="utf-8", errors="replace") if home.exists() else None
        if page is None and website:
            report("index.html", "the home page is missing (appendix A.3)")
        gone = {t.get("id") for t in TOMBSTONES}
        for m in members:
            if f"sheaf:{m.get('name')}:{m.get('owner')}" in gone:
                continue
            pin = (member_pins(m)[-1][1] or "")
            if page is not None and pin[:32] not in page:
                report("index.html", f"does not show the pin of {m.get('name')}" + note)
            try:
                obj_id = names.object_id(m.get("name"), m.get("owner"))
                held_here = (obj_dir(obj_id) / "inventory.json").is_file() and obj_dir(obj_id) not in SKIPPED
            except (ValueError, TypeError):
                continue
            if held_here:
                landing = ROOT / "paper" / name_address(obj_id) / "index.html"
                text = landing.read_text(encoding="utf-8", errors="replace") if landing.is_file() else ""
                if not landing_names(text, m["name"], m["owner"], obj_id):
                    report(landing.relative_to(ROOT).as_posix(), f"no landing page giving the sheaf: URI of "
                           f"{where(obj_id)} (appendix A.3)" + note)
                elif missing := landing_description_gaps(text):
                    report(landing.relative_to(ROOT).as_posix(), "the landing page of " + where(obj_id)
                           + " lacks " + ", ".join(missing) + " (appendix A.3)" + note)

The canonical form of the originator's line is `sheaf:<name>`, which is
a prefix of every other line of the work: it is found in the page only
when it is not followed by more of a URI (`:`, `/` or a character of a
name).

    # in check the presentation files of the profile website:
    def landing_names(text, nm, owner, obj_id):
        """Whether the landing page TEXT gives the sheaf: URI of the line (NM, OWNER), in canonical form."""
        g = read_logical(obj_dir(obj_id), load_inventory(obj_dir(obj_id)), GENESIS, "v1")
        try:
            originator = names.read_genesis(g.read_bytes()).get("originator") if g else None
        except ValueError:
            return False
        if originator == owner:
            return re.search(rf"sheaf:{nm}(?![a-z0-9:/])", text) is not None
        return f"sheaf:{nm}:{owner}" in text

A landing page also carries a description for programs (appendix A.3,
#77): FAIR Signposting links, of which those every page has are checked
(`cite-as`, `describedby`, `type`, and `item` when the version has a
rendition or a source), and a schema.org record in JSON-LD, which must
parse and have a type and identifiers. What the links and the record say
is not compared with the files: they are presentation, made from them.

    # in check the presentation files of the profile website:
    def landing_description_gaps(text):
        """What the landing page TEXT lacks of the description for programs of appendix A.3."""
        rels = set(re.findall(r'<link rel="([a-z-]+)"', text))
        missing = [f"the Signposting link {r}" for r in ("cite-as", "describedby", "type") if r not in rels]
        records = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
        try:
            ld = json.loads(records[0]) if records else None
        except ValueError:
            ld = None
        if not isinstance(ld, dict) or not ld.get("@type") or not ld.get("identifier"):
            missing.append("a schema.org record in JSON-LD with a type and identifiers")
        return missing

Keys left in the archive
------------------------

Private keys MUST NOT be stored in an archive (section 15.4): whatever an
archive holds is public and copied. The tools never write one there, and
refuse to export rotation keys inside it ([chapter 7](07-keys.md)), but a
person may copy one in by mistake. With access to the files, the verifier
looks for files that look like keys: exported rotation keys (by their
first line or their name), printed sheets, the files of current keys
(`.key`), and small files holding nothing but the base64 of 32 bytes, the
form of a seed. A private key found in a form it recognises is an error,
never a warning (section 15.4): whoever copies the archive copies the key.
The folders of git and of the tools' staging are not searched.

Nor does the verifier follow a symbolic link (section 15.2): a link in
the storage root, or among the files of the archive that the
specification defines (the discovery document, its pages of objects, the
indexes), is an error, and what it points to is never read. The
witness folders and the key logs are read without following them
(`witness_files`, `linked`, [owners](06-owners.md)), so that a link
there signs nothing.

    # in look for keys left in the archive:
    def look_for_keys(f):
        """Report the files of the archive that look like private keys, an error (section 15.4)."""
        rotation_name = re.compile(r"^rotation-[a-z2-7]{16}-[a-z2-7]{16}\.txt\Z")
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
                f.error(rel.as_posix(), "looks like a private key: keys are never kept in an archive "
                        "(section 15.4)")


    LINKS_SEARCHED = ("ocfl", "opensheaf.json", "objects", "indexes.json", "names", "owners", "sha512")


    def look_for_links(f):
        """Report the symbolic links among the files of the specification, never followed (section 15.2)."""
        for top in LINKS_SEARCHED:
            start = ROOT / top
            if start.is_symlink():
                f.error(top, "a symbolic link in the archive: never followed (section 15.2)")
                continue
            if not start.is_dir():
                continue
            for folder, dirs, files in os.walk(start):
                for name in sorted(dirs + files):
                    p = Path(folder) / name
                    if p.is_symlink():
                        f.error(p.relative_to(ROOT).as_posix(), "a symbolic link in the archive: never followed "
                                "(section 15.2)")

The command
-----------

The command prints the findings, one per line, with their severity and
place, then their numbers; with `--json`, the findings as a JSON list, for
programs. Its exit status counts the errors only, so that it can run in
continuous integration: an archive with warnings passes (section 14.1).
With `--remote`, the members of collections held in other archives are
resolved from their locations and given their statuses (section 14.5).
The standard output of `--json` is the JSON list alone: what the checks
say on the way (an owner catalogue without a signed version, met while the
presentation files are checked) goes to the standard error, as every
warning of these tools does, so that a program can parse the output
whatever the state of the archive.

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
