Owners and their key logs
=========================

An *owner* is a keyed identity, a person, a group or an institution, that
decides the versions of its lines and signs them (section 6). It is itself
an object of the archive, of kind `owner`, named by its genesis record like
any work: its owner name. Its object versions are its *key log*, the
history of its keys: which *current keys* sign its lines, and which
*rotation keys*, committed in advance by their digests, may sign the next
version of the key log. A key log checks itself from its owner name alone:
its first version is computed from the genesis record, and each later one
is signed by rotation keys that the one before committed to. A copy of a
key log from any source is therefore as good as the original (section 6.5).

This chapter is the module `owners.py`. It makes the files of every version
of a key log, byte for byte; keeps a key log in memory as the list of its
versions, with their inventories and signature files; checks it as section
14.3 asks, rules of section 6.1, signatures, endings and fork records; and
reads and writes it as an OCFL object folder. It does not place the folder
in an archive, nor decide who may write there: the [archive](10-archive.md)
does, through the functions below. The keys themselves are made and kept by
the [keys](07-keys.md) module, and signatures are made and judged by the
[signatures](08-signatures.md) module.

    # in src/opensheaf/owners.py:
    <<owners: the docstring and the imports>>


    <<owners: the files of a key-log version>>


    <<owners: inventories of key logs>>


    <<owners: the computed first version>>


    <<owners: the rules of keys.json>>


    <<owners: versions and carried versions>>


    <<owners: a key log>>


    <<owners: creating an owner>>


    <<owners: reading and writing a key log on disk>>

The module builds on the names and on the signatures.

    # in owners: the docstring and the imports:
    """Owners and their key logs (section 6 of OpenSheaf 0.2): the files of
    each key-log version, the computed first version, later versions signed
    by rotation keys (rotating, exposing, ending), fork records, the checks
    of section 14.3, and key logs read from and written to OCFL object folders."""

    import json
    import os
    from dataclasses import dataclass, field
    from pathlib import Path

    from . import names, sign
    from .names import GENESIS, jcs, key_digest, sha512_hex

    OBJECT_FORMAT = "opensheaf-object/0.2"
    KEYS_FORMAT = "opensheaf-keys/0.2"
    SPECIFICATION = "0.2"
    INVENTORY_TYPE = "https://ocfl.io/1.1/spec/#inventory"
    OBJ, KEYS, FORKED = "object.json", "keys.json", "forked/"
    RESERVED = {"object.json", "datacite.json", "genesis.json", "members.json", "keys.json", "forked",
                "parent.inventory.json", "parent.object.json", "parent.signatures", "parent.chain"}


    class OwnerError(Exception):
        """A key-log version that section 6 does not allow, or a key log that cannot be read."""

The files of a key-log version
------------------------------

Every version of a key log holds the genesis record, `object.json` and
`keys.json` (section 6.1), and nothing else but files the specification
does not define (a display name), and a fork record its carried versions
instead of `keys.json` (below).

The `object.json` of an owner has only the fields every object has: format
and specification, kind `owner`, status `active` (an owner is never
withdrawn), and `name` and `owner`, both the owner name; from the second
version on, `previous`, the digest of the inventory file of the version
before (section 4.3). It is written in JCS, the canonical JSON of the
[names](05-names.md) chapter: the first version requires it, and later
versions follow it, which costs nothing and keeps every `object.json` of a
key log in one form.

    # in owners: the files of a key-log version:
    def owner_object(owner, previous=None):
        """The bytes of object.json of a key-log version (sections 4.3 and 6.1)."""
        d = {"format": OBJECT_FORMAT, "specification": SPECIFICATION, "kind": "owner",
             "status": "active", "name": owner, "owner": owner}
        if previous is not None:
            d["previous"] = previous
        return jcs(d)

`keys.json` states the keys of the version (section 6.1): the current keys
and how many must sign a version of a line (`threshold`); the digests of
the rotation keys that sign the next version of the key log and how many
must (`next`, `nextThreshold`); the data of extensions in force; and, when
the version says so, the keys it exposes, or that the owner ends, with its
successor. An ending version has no keys, no threshold and no `next`
(section 6.3). The first version's `keys.json` is computed (below); later
ones are written as the archive writes JSON, indented, with the fields in
the order of the specification's examples.

    # in owners: the files of a key-log version:
    def keys_file(*, keys=None, threshold=None, next_digests=None, next_threshold=None,
                  extensions=None, exposed=None, ended=False, successor=None):
        """The bytes of keys.json of a key-log version after the first (section 6.1)."""
        d = {"format": KEYS_FORMAT}
        if ended:
            if any(v is not None for v in (keys, threshold, next_digests, next_threshold)):
                raise OwnerError("an ending version has no keys, threshold, next or nextThreshold (section 6.3)")
            d["ended"] = True
            if successor is not None:
                d["successor"] = successor
        else:
            if successor is not None:
                raise OwnerError("only an ending version names a successor (section 6.3)")
            d.update(keys=list(keys), threshold=threshold, next=list(next_digests), nextThreshold=next_threshold)
        if extensions:
            d["extensions"] = extensions
        if exposed:
            d["exposed"] = list(exposed)
        return (json.dumps(d, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

Inventories of key logs
-----------------------

The inventory of a key-log version is an OCFL 1.1 inventory, kept in the
version's folder with its checksum file (section 4.1). The first version's
is computed in JCS (below); later versions extend the inventory of the
version before: new content is stored under the version's folder, content
seen before is only listed in the state, and the version records when it
was made, why (`message`) and by whom (`user`), which every version but the
computed first one must have (section 4.1).

The bytes of a later inventory are free, as long as they are written once
and kept. The tools write them in one order, so that the same versions
always give the same bytes: the members of the inventory sorted by name,
the manifest by version and then by path, each state by the first path of
each digest, and the members of a version as `created`, `state`, `message`
and `user`. This is the order in which the specification's examples were
computed, which lets the tests check the digests of appendix C.

    # in owners: inventories of key logs:
    def inventory(prev, object_id, number, files, created, message=None, user=None):
        """The inventory (a dict) of version NUMBER of an object holding FILES ({logical path:
        bytes}), extending PREV, the inventory of the version before (None for the first)."""
        v = f"v{number}"
        if prev is None:
            if number != 1:
                raise OwnerError("only the first version has no inventory before it")
            inv = {"digestAlgorithm": "sha512", "head": v, "id": object_id, "manifest": {},
                   "type": INVENTORY_TYPE, "versions": {}}
        else:
            inv = json.loads(json.dumps(prev))
            if inv.get("head") != f"v{number - 1}" or inv.get("id") != object_id:
                raise OwnerError(f"{v} must follow v{number - 1} of {object_id}")
        content = inv.get("contentDirectory", "content")
        inv["head"] = v
        state = {}
        for path, data in sorted(files.items()):
            d = sha512_hex(data)
            if d not in inv["manifest"]:
                inv["manifest"][d] = [f"{v}/{content}/{path}"]
            state.setdefault(d, []).append(path)
        entry = {"created": created, "state": state}
        if message is not None:
            entry["message"] = message
        if user is not None:
            entry["user"] = user
        inv["versions"][v] = entry
        return ordered_inventory(inv)


    def ordered_inventory(inv):
        """INV with its members in the order the tools write them."""
        def place(content_path):
            ver, _, rest = content_path.partition("/")
            return (int(ver[1:]) if ver[1:].isdigit() else 0, rest)

        def ordered_version(e):
            first = {k: e[k] for k in ("created", "state", "message", "user") if k in e}
            first["state"] = dict(sorted(e["state"].items(), key=lambda kv: min(kv[1])))
            return {**first, **{k: e[k] for k in sorted(e) if k not in first}}

        out = {k: inv[k] for k in sorted(inv)}
        out["manifest"] = dict(sorted(inv["manifest"].items(), key=lambda kv: place(min(kv[1], key=place))))
        out["versions"] = {k: ordered_version(inv["versions"][k])
                           for k in sorted(inv["versions"], key=lambda k: int(k[1:]))}
        return out

An inventory file is the indented JSON of the archive, with a final line
feed, except the computed first version's, in JCS; its checksum file states
its SHA-512 digest and its name, as `sha512sum` writes it.

    # in owners: inventories of key logs:
    def inventory_file(inv):
        """The bytes of an inventory file (not the computed first version's, which is JCS)."""
        return (json.dumps(inv, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


    def sidecar(inventory_bytes):
        """The bytes of the checksum file of an inventory file."""
        return f"{sha512_hex(inventory_bytes)}  inventory.json\n".encode("ascii")


    def sidecar_digest(data):
        """The digest a checksum file states, or None."""
        try:
            parts = data.decode("ascii").split()
        except UnicodeDecodeError:
            return None
        return parts[0].lower() if len(parts) == 2 and parts[1] == "inventory.json" else None

The computed first version
--------------------------

The first version of a key log is computed from the genesis record, and
never signed (section 6.1): every reader rebuilds it, and must get the same
bytes, so that the first signatures, which name it by its pin, can be
checked in any copy. It holds exactly three files: the genesis record, as
written; `object.json`, in JCS, without `previous`; and `keys.json`, the JCS
form of `format` and the `keys`, `threshold`, `next` and `nextThreshold` of
the genesis record, nothing else (the keeper and the extensions of the
first version are those of the genesis record). Its inventory is the JCS
form of the OCFL inventory of these files with nothing optional: no
`contentDirectory`, no `fixity`, and a version with `created`, the
`created` of the genesis record, and its `state`, without `message` or
`user`.

    # in owners: the computed first version:
    def first_keys(rec):
        """The bytes of keys.json of the computed first version, from the fields of the genesis record."""
        return jcs({"format": KEYS_FORMAT, **{f: rec[f] for f in ("keys", "threshold", "next", "nextThreshold")}})


    def first_version(genesis):
        """The computed first version of the key log of the owner whose genesis record is GENESIS (bytes)."""
        rec = names.read_genesis(genesis)
        if rec["kind"] != "owner":
            raise OwnerError("the genesis record of an owner has kind owner")
        owner = names.name(genesis)
        files = {GENESIS: genesis, OBJ: owner_object(owner), KEYS: first_keys(rec)}
        digests = {path: sha512_hex(data) for path, data in files.items()}
        inv = {"digestAlgorithm": "sha512", "head": "v1", "id": names.object_id(owner, owner),
               "manifest": {d: [f"v1/content/{path}"] for path, d in digests.items()},
               "type": INVENTORY_TYPE,
               "versions": {"v1": {"created": rec["created"],
                                   "state": {d: [path] for path, d in digests.items()}}}}
        inv_bytes = jcs(inv)
        return Version(1, files, inv_bytes, sidecar(inv_bytes))

The rules of keys.json
----------------------

Section 6.1 states four rules on the keys of every version, read against
the versions before it on its side of a fork (a version carried by a fork
record has, as earlier versions, those held below the fork point and the
carried ones before it):

1. `threshold` does not exceed the number of `keys`, nor `nextThreshold`
   that of `next`;
2. `keys` lists no key that this version or an earlier one exposes, and no
   rotation key, revealed or not, that is, no key whose digest is in the
   `next` of this version or an earlier one;
3. `next` holds no digest of a current key of this version or an earlier
   one, and no digest that the `next` of an earlier version holds, so that
   each rotation key is committed in one version only;
4. `exposed` lists only keys that `keys` of an earlier version lists.

The first rule, and the parts of the second and third that concern one
version alone, are those of a genesis record, checked by
`key_rules_of_record` of the [names](05-names.md); the function below adds
the form of the file, the ending version of section 6.3 (no keys, a
successor other than the owner itself) and the comparisons with earlier
versions. It returns the problems found, so that the verifier can report
them all and the tools can refuse a version that has any.

    # in owners: the rules of keys.json:
    KEYS_FIELDS = {"format", "keys", "threshold", "next", "nextThreshold", "extensions", "ended", "successor", "exposed"}


    def key_rules(k, earlier, owner):
        """The problems of the keys.json K of a key-log version of OWNER, given the keys.json of
        the versions before it on its side (section 6.1, rules 1 to 4; section 6.3)."""
        if not isinstance(k, dict) or k.get("format") != KEYS_FORMAT:
            return [f"keys.json is not of format {KEYS_FORMAT}"]
        problems = []
        if set(k) - KEYS_FIELDS:
            problems.append("keys.json has fields the specification does not define: "
                            + ", ".join(sorted(set(k) - KEYS_FIELDS)))
        if "ended" in k and k["ended"] is not True:
            problems.append("ended, when present, is true")
        if k.get("ended") is True:
            if any(f in k for f in ("keys", "threshold", "next", "nextThreshold")):
                problems.append("an ending version has no keys, threshold, next or nextThreshold (section 6.3)")
            succ = k.get("successor")
            if succ is not None and (not isinstance(succ, str) or not names.OWNER_NAME.match(succ) or succ == owner):
                problems.append("successor is the owner name of another owner (section 6.3)")
        else:
            if "successor" in k:
                problems.append("only an ending version names a successor (section 6.3)")
            problems += names.key_rules_of_record(k)
        if "extensions" in k and not (isinstance(k["extensions"], dict)
                                      and all(isinstance(v, dict) for v in k["extensions"].values())):
            problems.append("extensions maps names of extensions to objects")
        exposed = k.get("exposed", [])
        if "exposed" in k and (not isinstance(exposed, list) or not exposed
                               or not all(isinstance(x, str) and names.DID_KEY.match(x) for x in exposed)
                               or len(set(exposed)) != len(exposed)):
            problems.append("exposed is a list of distinct did:key URIs")
            exposed = []
        keys = [x for x in k.get("keys", []) if isinstance(x, str)] if isinstance(k.get("keys"), list) else []
        nxt = [x for x in k.get("next", []) if isinstance(x, str)] if isinstance(k.get("next"), list) else []
        earlier_keys = {x for e in earlier for x in e.get("keys", [])}
        earlier_next = {x for e in earlier for x in e.get("next", [])}
        earlier_exposed = {x for e in earlier for x in e.get("exposed", [])}
        if set(keys) & (earlier_exposed | set(exposed)):
            problems.append("keys lists a key exposed by this version or an earlier one (rule 2)")
        if {key_digest(x) for x in keys} & earlier_next:
            problems.append("keys lists a rotation key of an earlier version (rule 2)")
        if set(nxt) & {key_digest(x) for x in earlier_keys}:
            problems.append("next holds the digest of a current key of an earlier version (rule 3)")
        if set(nxt) & earlier_next:
            problems.append("next holds a digest that next of an earlier version holds (rule 3)")
        if set(exposed) - earlier_keys:
            problems.append("exposed lists a key that keys of no earlier version lists (rule 4)")
        return problems

Versions and carried versions
-----------------------------

In memory, a version of a key log is its number, its files by logical path,
the bytes of its inventory file and of the checksum file, and the files of
its witness folder (section 7.2), by name: its signature files. Everything
else is derived from these bytes, so that what is checked is what is
stored: the digest of the inventory, which pins the version; `keys.json`,
parsed; and whether it is a fork record, a version without `keys.json`
holding `forked/`. The checks set `is_version` to false on a version that
section 6 does not admit as a version of the key log.

    # in owners: versions and carried versions:
    @dataclass
    class Version:
        """A version of a key log: its number, files, inventory file and witness files."""
        number: int
        files: dict                      # logical path -> bytes
        inventory: bytes                 # the inventory file of the version
        sidecar: bytes = b""             # its checksum file
        witnesses: dict = field(default_factory=dict)   # file of the witness folder vN/ -> bytes
        is_version: bool = True

        @property
        def digest(self):
            return sha512_hex(self.inventory)

        @property
        def keys(self):
            return _json_or_none(self.files.get(KEYS))

        @property
        def fork_record(self):
            return KEYS not in self.files and any(p.startswith(FORKED) for p in self.files)

        @property
        def carried(self):
            """The versions a fork record carries, in the order of their numbers."""
            groups = {}
            for path, data in self.files.items():
                if path.startswith(FORKED):
                    d, _, rest = path[len(FORKED):].partition("/")
                    groups.setdefault(d, {})[rest] = data
            return sorted((Carried(d, files) for d, files in groups.items()), key=lambda c: c.number or 0)


    def _json_or_none(data):
        try:
            return json.loads(data) if data is not None else None
        except ValueError:
            return None

A *carried* version is a version of the other side of a fork, kept by a
fork record under `forked/<d>/`, `<d>` being the first 16 characters of the
base32 SHA-256 digest of its inventory file (section 6.3): its inventory
file and checksum file, its `keys.json`, and its signature files with the
witnesses beside them. Its number is the head of its inventory. It answers
the same questions as a version held, so that signatures naming it are
judged in the same way.

    # in owners: versions and carried versions:
    CARRIED_FILES = ("inventory.json", "inventory.json.sha512", "keys.json")


    @dataclass
    class Carried:
        """A version of the other side of a fork, carried by a fork record (section 6.3)."""
        d: str
        files: dict                      # name under forked/<d>/ -> bytes
        is_version: bool = True
        fork_record = False

        @property
        def inventory(self):
            return self.files.get("inventory.json", b"")

        @property
        def sidecar(self):
            return self.files.get("inventory.json.sha512", b"")

        @property
        def digest(self):
            return sha512_hex(self.inventory)

        @property
        def number(self):
            inv = _json_or_none(self.inventory)
            head = inv.get("head") if isinstance(inv, dict) else None
            return int(head[1:]) if isinstance(head, str) and head[1:].isdigit() else None

        @property
        def keys(self):
            return _json_or_none(self.files.get("keys.json"))

        @property
        def witnesses(self):
            return {n: b for n, b in self.files.items() if n not in CARRIED_FILES}

A key log
---------

A key log is its genesis record, from which its owner name and identifier
follow, and the list of its versions held, from `v1`. A new key log holds
only the computed first version. `problems` collects what the loader found
wrong in the files themselves (a digest that does not match), reported with
the errors of the checks.

    # in owners: a key log:
    class KeyLog:
        """The key log of an owner: its genesis record and the versions held (section 6)."""

        def __init__(self, genesis, versions=None):
            self.genesis = genesis
            self.owner = names.name(genesis)
            self.id = names.object_id(self.owner, self.owner)
            self.versions = versions if versions is not None else [first_version(genesis)]
            self.problems = []
            self._checked = None

        <<owners: what a key log says>>

        <<owners: checking a key log>>

        <<owners: adding a version to a key log>>

        <<owners: rotating, exposing and ending>>

        <<owners: recording a fork>>

### What a key log says

These questions are answered after the checks, from the versions they
admit. The *pin* of a version, as signature files name it, is
`sheaf:<owner>/v<n>?sha512=<digest>`. The *current keys* are those of the
latest version that is a version and has keys: none for an ended owner,
which nothing is signed for (section 6.3). The extensions in force are
those of the latest version, or of the genesis record for the first.

    # in owners: what a key log says:
    def pin(self, number):
        """The pin of version NUMBER held, as keyLog names it (section 7.2)."""
        return names.key_log_pin(self.owner, number, self.versions[number - 1].digest)

    def side(self):
        """The versions held that are versions of the key log, fork record excluded, in order."""
        self.check()
        return [v for v in self.versions if v.is_version and not v.fork_record]

    def latest(self):
        """The latest version of the key log with current keys, or None for an ended owner."""
        if self.ended:
            return None
        side = self.side()
        return side[-1] if side and side[-1].keys and "keys" in side[-1].keys else None

    def extensions(self):
        """The data of extensions in force as of the latest version (section 6.1)."""
        side = self.side()
        if len(side) <= 1:
            return names.read_genesis(self.genesis).get("extensions")
        return side[-1].keys.get("extensions")

An owner is *ended* by an ending version or by a fork record (section 6.3);
the *fork point* is the number of the first version a valid fork record
carries. Exposed keys count on either side of a fork (sections 6.3 and
7.3): those of the versions held and those of the versions carried.

    # in owners: what a key log says:
    @property
    def fork_record(self):
        """The valid fork record held, or None."""
        self.check()
        return next((v for v in self.versions if v.fork_record and v.is_version), None)

    @property
    def fork_point(self):
        fr = self.fork_record
        return fr.carried[0].number if fr else None

    @property
    def ended(self):
        return self.fork_record is not None or any(v.keys.get("ended") for v in self.side()[1:])

    @property
    def successor(self):
        """The successor named by an ending version held, or None (accepted or claimed: section 6.6)."""
        return next((v.keys.get("successor") for v in self.side()[1:] if v.keys.get("ended")), None)

    def exposed_keys(self):
        """The keys exposed by any version of the key log, on either side of a fork (section 6.3)."""
        found = set()
        for v in self.side():
            found.update(v.keys.get("exposed", []))
        fr = self.fork_record
        for c in (fr.carried if fr else []):
            found.update(c.keys.get("exposed", []))
        return found

Signatures name a key-log version by its number and digest. `lookup` finds
it among the versions held and, after a fork, among those the fork record
carries (section 7.3, rule 5); it returns the version found, which may be
one that is not a version (rule 6), or None when the reader cannot reach it.

    # in owners: what a key log says:
    def lookup(self, number, digest):
        """The version NUMBER whose inventory has DIGEST, held or carried, or None."""
        self.check()
        for v in self.versions:
            if v.number == number and v.digest == digest:
                return v
        fr = self.fork_record
        for c in (fr.carried if fr else []):
            if c.number == number and c.digest == digest:
                return c
        return None

### Checking a key log

The checks follow section 14.3, version by version from the first, since
each version is judged against the one before:

1. the genesis record, with the check digit of an ORCID keeper;
2. that the first version is the computed one, byte for byte, with no
   other file; a signature file of it is invalid, a warning;
3. for each later version, `object.json` (an owner's fields and
   `previous`), the genesis record unchanged, `keys.json` against the
   rules, and the signatures of `nextThreshold` rotation keys of the
   version before;
4. no version after an ending version but a fork record, and none after a
   fork record, those being warnings, as for lines;
5. each fork record, as the next section explains.

A version that fails is not a version of the key log, and the versions
after it cannot be checked: they are not versions either. The result is a
pair of lists, errors and warnings, kept until the key log changes.

    # in owners: checking a key log:
    def check(self):
        """The errors and warnings of the key log (section 14.3), as two lists of strings."""
        if self._checked is not None:
            return self._checked
        errors, warnings = list(self.problems), []
        self._checked = (errors, warnings)
        try:
            rec = names.read_genesis(self.genesis)
        except ValueError as e:
            errors.append(f"genesis.json: {e}")
            rec = None
        if rec is not None and rec["kind"] != "owner":
            errors.append("genesis.json: the genesis record of an owner has kind owner")
            rec = None
        if rec is None or not self.versions:
            for v in self.versions:
                v.is_version = False
            return self._checked
        v1 = self.versions[0]
        computed = first_version(self.genesis)
        if v1.number != 1 or v1.files != computed.files or v1.inventory != computed.inventory:
            errors.append("v1: not the version computed from the genesis record (section 6.1)")
            v1.is_version = False
        elif v1.sidecar and sidecar_digest(v1.sidecar) != v1.digest:
            errors.append("v1: the checksum file does not state the digest of the inventory")
            v1.is_version = False
        if any(n.startswith("signature-") for n in v1.witnesses):
            warnings.append("v1: a signature file of the computed first version is invalid (section 7.3)")
        side, state = [v1], None if v1.is_version else "broken"
        for v in self.versions[1:]:
            where = f"v{v.number}"
            if state == "broken":
                v.is_version = False
                warnings.append(f"{where}: follows a version that is not a version of the key log")
                continue
            if state == "forked" or (state == "ended" and not v.fork_record):
                v.is_version = False
                warnings.append(f"{where}: held after {'a fork record' if state == 'forked' else 'an ending version'}: "
                                "not a version of the key log (section 6.3)")
                continue
            problems = self._common_problems(v, side[-1])
            if v.fork_record:
                problems += self._fork_record_problems(v, side)
            elif v.keys is None:
                problems.append("no keys.json, and not a fork record")
            else:
                problems += key_rules(v.keys, [x.keys for x in side], self.owner)
                if not problems:
                    problems += self._signature_problems(v, side[-1], self.lookup_held(side), warnings)
            if problems:
                v.is_version = False
                errors += [f"{where}: {p}" for p in problems]
                state = "broken"
            elif v.fork_record:
                state = "forked"
            else:
                side.append(v)
                if v.keys.get("ended"):
                    state = "ended"
        return self._checked

Every version after the first holds the same genesis record and an
`object.json` with the fields of an owner and `previous`, the digest of the
inventory of the version before; its inventory has the owner object's `id`
and its number, and its checksum file states its digest.

    # in owners: checking a key log:
    def _common_problems(self, v, prev):
        problems = []
        inv = _json_or_none(v.inventory)
        if not isinstance(inv, dict) or inv.get("id") != self.id or inv.get("head") != f"v{v.number}":
            problems.append(f"the inventory is not that of v{v.number} of {self.id}")
        if v.sidecar and sidecar_digest(v.sidecar) != v.digest:
            problems.append("the checksum file does not state the digest of the inventory")
        if v.files.get(GENESIS) != self.genesis:
            problems.append("genesis.json differs from that of the first version")
        obj = _json_or_none(v.files.get(OBJ))
        expected = json.loads(owner_object(self.owner, prev.digest))
        if not isinstance(obj, dict) or {k: x for k, x in obj.items() if k != "extensions"} != expected:
            problems.append("object.json has not the fields of an owner and previous, the digest of "
                            f"the inventory of v{prev.number} (section 4.3)")
        for path in v.files:
            top = path.split("/")[0]
            if top in RESERVED and path not in (GENESIS, OBJ, KEYS) and not path.startswith(FORKED):
                problems.append(f"{path}: a name reserved by section 4.1")
        return problems

A version is signed when at least `nextThreshold` distinct rotation keys of
the version before, `nextThreshold` being that version's, sign it in good
signature files naming that version by its pin (section 6.1). The
signatures are judged by the [signatures](08-signatures.md) module, which
checks the rules of section 7.3 for signatures of key-log versions: a
rotation key of the version named, the version before. Invalid signature
files are reported as warnings, never fatal (section 7.2).

    # in owners: checking a key log:
    def lookup_held(self, side):
        """A lookup among the versions SIDE, for the checks (before the key log is fully checked)."""
        def lookup(number, digest):
            return next((x for x in side if x.number == number and x.digest == digest), None)
        return lookup

    def _signature_problems(self, v, prev, lookup, warnings, where=None):
        where = where or f"v{v.number}"
        good = set()
        for j in sign.judge_folder(v.witnesses, object_id=self.id, version=f"v{v.number}",
                                   inventory=v.digest, owner=self.owner, lookup=lookup, key_log=True):
            if j.status == sign.GOOD and j.key_log == (prev.number, prev.digest):
                good.add(j.key)
            elif j.status != sign.GOOD:
                warnings.append(f"{where}/{j.file}: {j.status}: {j.reason}")
        need = prev.keys["nextThreshold"]
        if len(good) < need:
            return [f"signed by {len(good)} rotation key(s) of v{prev.number}, which needs {need} (section 6.1)"]
        return []

### Fork records

A fork record (section 6.3) is the version an archive appends when it meets
a signed version of the key log that differs from the one of that number it
holds: it carries the other side, from the fork point on, and ends the
owner. It is valid only when it holds nothing but the genesis record,
`object.json` and the carried versions, each under the name its inventory
digest gives, with the owner object's `id` in its inventory, a checksum
file stating its digest, the `keys.json` its inventory lists, and
signatures: the first carried version signed against the version held
before it and differing from the version held at its number, every later
one against the carried version before it. Carried versions follow the
rules of section 6.1 against the versions before them on their side.

    # in owners: checking a key log:
    def _fork_record_problems(self, fr, side):
        problems = [f"{p}: a fork record holds only genesis.json, object.json and forked/ (section 6.3)"
                    for p in fr.files if p not in (GENESIS, OBJ) and not p.startswith(FORKED)]
        carried = fr.carried
        if not carried or any(c.number is None for c in carried):
            return problems + ["a fork record carries versions, each with its inventory"]
        first = carried[0].number
        held = {x.number: x for x in side}
        if [c.number for c in carried] != list(range(first, first + len(carried))):
            problems.append("the versions carried are consecutive")
        if first - 1 not in held or first not in held or held[first].digest == carried[0].digest:
            problems.append(f"the first version carried, v{first}, differs from a version held of that number")
            return problems
        before = [x for x in side if x.number < first]
        for c in carried:
            where = f"forked/{c.d}"
            inv = _json_or_none(c.inventory)
            if c.d != names.b32(names.sha256(c.inventory))[:16]:
                problems.append(f"{where}: not the name its inventory digest gives")
            if not isinstance(inv, dict) or inv.get("id") != self.id:
                problems.append(f"{where}: the inventory carried is not one of {self.id}")
                continue
            if sidecar_digest(c.sidecar) != c.digest:
                problems.append(f"{where}: the checksum file does not state the digest of the inventory")
            state = inv.get("versions", {}).get(f"v{c.number}", {}).get("state", {})
            if "keys.json" not in c.files or not any(KEYS in paths and d == sha512_hex(c.files["keys.json"])
                                                     for d, paths in state.items()):
                problems.append(f"{where}: keys.json is not the one its inventory lists")
                continue
            rules = key_rules(c.keys, [x.keys for x in before], self.owner)
            problems += [f"{where}: {p}" for p in rules]
            if not rules:
                problems += [f"{where}: {p}" for p in
                             self._signature_problems(c, before[-1], self.lookup_held(before), [], where)]
            before = before + [c]
        return problems

### Adding a version to a key log

A new version is made by the owner: the tools refuse a key log that has
errors, or an ended owner (section 6.3). It is signed by rotation keys of
the latest version, at least `nextThreshold` of them, and by nothing else:
current keys never sign the key log (section 6.1). Its `keys.json` must
pass the rules against the versions before. The version then holds the
genesis record, `object.json` with `previous`, `keys.json` and any other
files given, which may not take a name reserved by the specification; its
inventory extends that of the version before, and each rotation key signs
it in a signature file naming the version before by its pin (section 7.2).

The version is checked again once added, as any reader would, and removed
if the checks find anything: what the tools write is what verifiers accept.

    # in owners: adding a version to a key log:
    def _prepare(self, signers):
        errors, _ = self.check()
        if errors:
            raise OwnerError("the key log has errors: " + "; ".join(errors))
        if self.ended:
            raise OwnerError(f"the owner {self.owner} has ended (section 6.3): nothing is signed for it")
        prev = self.side()[-1]
        rotation = set(prev.keys["next"])
        for key in signers:
            if key.digest not in rotation:
                raise OwnerError(f"{key.did} is not a rotation key of v{prev.number} (section 6.1)")
        need, have = prev.keys["nextThreshold"], len({key.did for key in signers})
        if have < need:
            raise OwnerError(f"v{prev.number} needs {need} rotation keys to sign the next version, {have} given")
        return prev

    def add(self, keys_bytes, signers, *, message, user, created=None, files=None):
        """Add a version with KEYS_BYTES as keys.json, signed by the rotation keys SIGNERS (Keys)."""
        prev = self._prepare(signers)
        problems = key_rules(_json_or_none(keys_bytes), [v.keys for v in self.side()], self.owner)
        if problems:
            raise OwnerError("; ".join(problems))
        for path in files or {}:
            if path.split("/")[0] in RESERVED:
                raise OwnerError(f"{path}: a name reserved by section 4.1")
        n = prev.number + 1
        content = {GENESIS: self.genesis, OBJ: owner_object(self.owner, prev.digest), KEYS: keys_bytes,
                   **(files or {})}
        inv = inventory(json.loads(prev.inventory), self.id, n, content, created or names.utc_now(), message, user)
        inv_bytes = inventory_file(inv)
        digest, pin = sha512_hex(inv_bytes), self.pin(prev.number)
        witnesses = {sign.file_name(key.did): sign.signature_file(key, self.id, f"v{n}", digest, self.owner, pin)
                     for key in signers}
        return self._append(Version(n, content, inv_bytes, sidecar(inv_bytes), witnesses))

    def _append(self, version):
        self.versions.append(version)
        self._checked = None
        errors, _ = self.check()
        if errors:
            self.versions.pop()
            self._checked = None
            raise OwnerError("the new version would not be a version of the key log: " + "; ".join(errors))
        return version

### Rotating, exposing and ending

Three operations make the versions owners need (section 6.2 and 6.3). A
*rotation* adds and retires current keys, possibly changes the threshold,
and commits the next rotation keys, which must be new (rule 3): the keys
that sign this version are used up, and so are those of the same version
that did not sign. An *exposure* is a rotation that also lists keys in
`exposed`, and drops them from the current keys: a key that may have been
stolen must be exposed at once (section 6.3). An *ending* has no keys and
no `next`, and may name a successor.

Unless told otherwise, a new version keeps the threshold and the data of
the extensions in force, which section 6.1 asks every version to repeat.
The next rotation keys are given as keys, `did:key` URIs or digests: only
the digests are written.

    # in owners: rotating, exposing and ending:
    def rotate(self, signers, *, next_keys, next_threshold, add=(), retire=(), exposed=(), threshold=None,
               extensions=KEEP, message="Keys changed", user, created=None):
        """Add a version that adds and retires current keys and commits NEXT_KEYS (section 6.2)."""
        prev = self.latest()
        if prev is None:
            raise OwnerError(f"the owner {self.owner} has ended (section 6.3): nothing is signed for it")
        current = prev.keys["keys"]
        for did in retire:
            if did not in current:
                raise OwnerError(f"{did} is not a current key of {self.owner}")
        keys = [k for k in current if k not in retire and k not in exposed]
        keys += [_did(k) for k in add if _did(k) not in keys]
        if extensions is KEEP:
            extensions = self.extensions()
        data = keys_file(keys=keys, threshold=threshold or prev.keys["threshold"],
                         next_digests=[_digest(k) for k in next_keys], next_threshold=next_threshold,
                         extensions=extensions, exposed=list(exposed) or None)
        return self.add(data, signers, message=message, user=user, created=created)

    def expose(self, signers, exposed, *, next_keys, next_threshold, add=(), threshold=None,
               extensions=KEEP, message="Keys exposed", user, created=None):
        """Add a version that exposes the keys EXPOSED and drops them from the current keys (section 6.3)."""
        return self.rotate(signers, next_keys=next_keys, next_threshold=next_threshold, add=add,
                           exposed=exposed, threshold=threshold, extensions=extensions,
                           message=message, user=user, created=created)

    def end(self, signers, *, successor=None, exposed=(), message="Owner ended", user, created=None):
        """Add the ending version of the key log (section 6.3), naming SUCCESSOR if given."""
        if successor == self.owner:
            raise OwnerError("the successor of an owner is another owner (section 6.3)")
        data = keys_file(ended=True, successor=successor, exposed=list(exposed) or None)
        return self.add(data, signers, message=message, user=user, created=created)

`KEEP` marks the default of `extensions`, since `None` means none; keys
given as `Key` objects or URIs are turned into URIs and digests.

    # in owners: the rules of keys.json:
    KEEP = object()   # keep the data of extensions in force


    def _did(key):
        return key.did if hasattr(key, "did") else key


    def _digest(key):
        """The digest of a key given as a Key, a did:key URI, or already as a digest."""
        if hasattr(key, "digest"):
            return key.digest
        if key.startswith("did:key:"):
            names.did_key_public(key)
            return key_digest(key)
        if not names.OWNER_NAME.match(key):
            raise OwnerError(f"not a key, a did:key URI or the digest of a key: {key!r}")
        return key

### Recording a fork

An archive records a fork of a key log it holds by appending a fork record
(section 6.3), made by the archive and not signed. It is given the versions
of the other side it met, from the fork point to the latest signed one:
each as a `Version` of another copy, or as a `Carried` taken from another
fork record. The record is checked like any version, and refused if it is
not valid; a fork met once the key log already has a fork record is
reported, not recorded.

    # in owners: recording a fork:
    def record_fork(self, other, *, user, message="Fork record: another version met", created=None):
        """Append a fork record carrying OTHER, versions of the other side from the fork point on."""
        errors, _ = self.check()
        if errors:
            raise OwnerError("the key log has errors: " + "; ".join(errors))
        if self.fork_record is not None:
            raise OwnerError("a fork met once the key log has a fork record is reported, not recorded")
        prev = self.versions[-1]
        content = {GENESIS: self.genesis, OBJ: owner_object(self.owner, prev.digest)}
        for v in other:
            base = f"{FORKED}{names.b32(names.sha256(v.inventory))[:16]}/"
            content[base + "inventory.json"] = v.inventory
            content[base + "inventory.json.sha512"] = v.sidecar or sidecar(v.inventory)
            content[base + "keys.json"] = v.files[KEYS] if isinstance(v, Version) else v.files["keys.json"]
            for name, data in v.witnesses.items():
                content[base + name] = data
        n = prev.number + 1
        inv = inventory(json.loads(prev.inventory), self.id, n, content, created or names.utc_now(), message, user)
        inv_bytes = inventory_file(inv)
        return self._append(Version(n, content, inv_bytes, sidecar(inv_bytes)))

Creating an owner
-----------------

An owner tool creates an owner by making its keys and writing its genesis
record (section 6.2): the first current keys and threshold, the digests of
the first rotation keys and how many must sign the second version, and,
optionally, the keeper and the data of extensions. The key log is then the
computed first version alone. The specification recommends three rotation
keys with a `nextThreshold` of 2, which survive the loss of one or the
theft of one; the default threshold is a majority of the rotation keys,
which gives that. Whether the owner name is free where it will be written
is for the archive to decide, drawing a new nonce if not (section 6.2).

    # in owners: creating an owner:
    def new_owner(current, rotation, *, threshold=1, next_threshold=None, keeper=None, extensions=None,
                  created=None, nonce=None):
        """The key log of a new owner with the CURRENT keys and the ROTATION keys (Keys or did:key
        URIs), from a new genesis record (sections 5.1 and 6.2)."""
        rotation = list(rotation)
        genesis = names.genesis_record(
            "owner", keys=[_did(k) for k in current], threshold=threshold,
            next_digests=[_digest(k) for k in rotation],
            next_threshold=next_threshold or len(rotation) // 2 + 1,
            keeper=keeper, extensions=extensions, created=created, nonce=nonce)
        return KeyLog(genesis)

The minimal setup, a single rotation key, is allowed only with its risk
stated (section 6.2); so is the warning every owner tool must give when an
owner is left with fewer rotation keys than it needs. Both are kept here,
for every command that needs them.

    # in owners: creating an owner:
    SINGLE_ROTATION_RISK = (
        "With a single rotation key, its loss leaves the owner unable ever to change its keys "
        "or end, and its theft lets the thief take the owner over (sections 6.2 and 15.1).")
    ROTATION_KEYS_WARNING = (
        "An owner left with fewer than nextThreshold rotation keys of the latest version of its "
        "key log can never change its keys or end (section 6.2).")

`describe` summarises a key log for a person: the owner, its keeper, each
version with its digest and what it changed, and the current state, with
the problems found. The command line shows it.

    # in owners: creating an owner:
    def describe(log):
        """Lines describing the key log LOG for a person."""
        errors, warnings = log.check()
        rec = _json_or_none(log.genesis) or {}
        out = [f"owner {log.owner}"]
        if rec.get("keeper"):
            out.append(f"keeper {rec['keeper'][0]}")
        for v in log.versions:
            k = v.keys or {}
            what = ("fork record, carrying " + ", ".join(f"v{c.number}" for c in v.carried) if v.fork_record
                    else "ended" + (f", successor {k['successor']}" if k.get("successor") else "") if k.get("ended")
                    else f"{len(k.get('keys', []))} current key(s), threshold {k.get('threshold')}, "
                         f"{len(k.get('next', []))} rotation key(s), nextThreshold {k.get('nextThreshold')}"
                         + (f", exposes {len(k['exposed'])}" if k.get("exposed") else ""))
            mark = "" if v.is_version else " (not a version)"
            out.append(f"v{v.number} {v.digest[:16]}  {what}{mark}")
        latest = log.latest()
        if latest is not None:
            out += [f"current key {did}" for did in latest.keys["keys"]]
        if log.fork_point:
            out.append(f"ended by a fork at v{log.fork_point}")
        elif log.ended:
            out.append("ended")
        out += [f"exposed {did}" for did in sorted(log.exposed_keys())]
        out += [f"error: {e}" for e in errors] + [f"warning: {w}" for w in warnings]
        return out

Reading and writing a key log on disk
-------------------------------------

On disk a key log is an OCFL object folder: the namaste file, the root
inventory and its checksum file, and for each version a folder holding its
inventory, its checksum file and its new content, with the witness folder
`extensions/opensheaf-witnesses/vN/` beside them (section 7.2). Where the
folder lives in the storage root is the archive's layout (section 3.2).

The loader reads every version from the copy of the inventory in its own
folder (section 4.1), the files of its state through the manifest, and the
files of its witness folder. It records what is wrong in the files, a
digest that does not match or a missing file, as problems of the key log,
which its checks report, rather than stopping: a verifier wants them all.

    # in owners: reading and writing a key log on disk:
    def load_key_log(obj_dir):
        """The key log held in the OCFL object folder OBJ_DIR."""
        obj_dir, problems, versions = Path(obj_dir), [], []
        try:
            root = (obj_dir / "inventory.json").read_bytes()
            head = int(json.loads(root)["head"][1:])
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise OwnerError(f"{obj_dir}: not an OCFL object with an inventory ({e})") from None
        for n in range(1, head + 1):
            vdir = obj_dir / f"v{n}"
            try:
                inv_bytes = (vdir / "inventory.json").read_bytes()
                entry = json.loads(inv_bytes)
                manifest, state = entry["manifest"], entry["versions"][f"v{n}"]["state"]
            except (OSError, ValueError, KeyError, TypeError) as e:
                problems.append(f"v{n}: no readable inventory in the version folder (section 4.1; {e})")
                break
            sc = (vdir / "inventory.json.sha512").read_bytes() if (vdir / "inventory.json.sha512").exists() else b""
            if sidecar_digest(sc) != sha512_hex(inv_bytes):
                problems.append(f"v{n}: the checksum file does not state the digest of the inventory")
            files = {}
            for d, paths in state.items():
                try:
                    data = (obj_dir / manifest[d][0]).read_bytes()
                except (OSError, KeyError, IndexError):
                    problems.append(f"v{n}: the content of {paths[0]} is missing")
                    data = b""
                if sha512_hex(data) != d:
                    problems.append(f"v{n}: {paths[0]} does not have the digest its inventory states")
                for path in paths:
                    files[path] = data
            wdir = obj_dir / sign.WITNESSES / f"v{n}"
            witnesses = {f.name: f.read_bytes() for f in sorted(wdir.iterdir()) if f.is_file()} if wdir.is_dir() else {}
            versions.append(Version(n, files, inv_bytes, sc, witnesses))
        if not versions or GENESIS not in versions[0].files:
            raise OwnerError(f"{obj_dir}: no genesis record in the first version")
        if versions[-1].number == head and root != versions[-1].inventory:
            problems.append("the root inventory differs from that of the head version")
        log = KeyLog(versions[0].files[GENESIS], versions)
        if json.loads(root).get("id") != log.id:
            problems.append(f"the identifier of the object is not {log.id}, that of the owner its genesis record names")
        log.problems = problems
        return log

The writer adds to a folder what it does not hold yet: the versions after
its head, and the witness files it lacks. It never changes a file that is
there: the versions a folder holds must be those of the key log, byte for
byte, or it refuses. Content is written only once, in the version that
first holds it, as the manifest says, and the root inventory is replaced by
that of the new head last, so that a folder interrupted while writing still
holds a valid object at its old head.

    # in owners: reading and writing a key log on disk:
    def write_key_log(obj_dir, log):
        """Write to the OCFL object folder OBJ_DIR the versions and witness files of LOG it lacks."""
        obj_dir = Path(obj_dir)
        obj_dir.mkdir(parents=True, exist_ok=True)
        namaste = obj_dir / "0=ocfl_object_1.1"
        if not namaste.exists():
            namaste.write_text("ocfl_object_1.1\n")
        held = 0
        if (obj_dir / "inventory.json").exists():
            held = int(json.loads((obj_dir / "inventory.json").read_bytes())["head"][1:])
        for v in log.versions[:held]:
            if (obj_dir / f"v{v.number}" / "inventory.json").read_bytes() != v.inventory:
                raise OwnerError(f"{obj_dir}: v{v.number} differs from that of the key log of {log.owner}")
        for v in log.versions[held:]:
            vdir = obj_dir / f"v{v.number}"
            vdir.mkdir()
            inv = json.loads(v.inventory)
            by_digest = {sha512_hex(data): data for data in v.files.values()}
            for d, paths in inv["manifest"].items():
                for cp in paths:
                    if cp.startswith(f"v{v.number}/"):
                        (obj_dir / cp).parent.mkdir(parents=True, exist_ok=True)
                        (obj_dir / cp).write_bytes(by_digest[d])
            (vdir / "inventory.json").write_bytes(v.inventory)
            (vdir / "inventory.json.sha512").write_bytes(v.sidecar or sidecar(v.inventory))
        for v in log.versions:
            wdir = obj_dir / sign.WITNESSES / f"v{v.number}"
            for name, data in v.witnesses.items():
                if not (wdir / name).exists():
                    wdir.mkdir(parents=True, exist_ok=True)
                    with open(wdir / name, "xb") as f:
                        f.write(data)
        if len(log.versions) > held:
            head = log.versions[-1]
            tmp = obj_dir / "inventory.json.tmp"
            tmp.write_bytes(head.inventory)
            os.replace(tmp, obj_dir / "inventory.json")
            (obj_dir / "inventory.json.sha512").write_bytes(head.sidecar or sidecar(head.inventory))
