# Generated from literate/06-owners.md by opensheaf-literate: edit the document, not this file.
"""Owners and their key logs (section 6 of OpenSheaf 0.2): the files of
each key-log version, the computed first version, later versions signed
by rotation keys (rotating, exposing, ending), fork records, the checks
of section 14.3, and key logs read from and written to OCFL object folders."""

import copy
import json
import os
import re
import shutil
import urllib.error
import urllib.request
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
            "parent"}


class OwnerError(Exception):
    """A key-log version that section 6 does not allow, or a key log that cannot be read."""


def owner_object(owner, previous=None):
    """The bytes of object.json of a key-log version (sections 4.3 and 6.1)."""
    d = {"format": OBJECT_FORMAT, "specification": SPECIFICATION, "kind": "owner",
         "status": "active", "name": owner, "owner": owner}
    if previous is not None:
        d["previous"] = previous
    return jcs(d)


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
    return parts[0] if len(parts) == 2 and parts[1] == "inventory.json" else None


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
        return _exact_or_none(self.files.get(KEYS))

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
        return names.json_value(data) if data is not None else None
    except ValueError:
        return None


def _exact_or_none(data):
    try:
        return names.loads_exact(data) if data is not None else None
    except ValueError:
        return None


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
        return _exact_or_none(self.files.get("keys.json"))

    @property
    def witnesses(self):
        return {n: b for n, b in self.files.items() if n not in CARRIED_FILES}


class KeyLog:
    """The key log of an owner: its genesis record and the versions held (section 6)."""

    def __init__(self, genesis, versions=None):
        self.genesis = genesis
        self.owner = names.name(genesis)
        self.id = names.object_id(self.owner, self.owner)
        self.versions = versions if versions is not None else [first_version(genesis)]
        self.problems = []
        self.orphan = None
        self._checked = None

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

    def verified(self, number, digest):
        """The version NUMBER whose inventory has DIGEST if it is a version of the key log
        (section 14.3), held or carried by the valid fork record; else None."""
        v = self.lookup(number, digest)
        return v if v is not None and v.is_version else None

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
                problems.append("keys.json is not JSON with exact integers only (section 2)" if KEYS in v.files
                                else "no keys.json, and not a fork record")
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

    def lookup_held(self, side):
        """A lookup among the versions SIDE, for the checks (before the key log is fully checked)."""
        def lookup(number, digest):
            return next((x for x in side if x.number == number and x.digest == digest), None)
        return lookup

    def _signature_problems(self, v, prev, lookup, warnings, where=None):
        where = where or f"v{v.number}"
        need = (prev.keys or {}).get("nextThreshold")
        if (prev.keys or {}).get("ended") or not isinstance(need, int) or isinstance(need, bool):
            return [f"follows v{prev.number}, which ends the key log or commits to no rotation keys: "
                    "nothing follows an ending version (section 6.3)"]
        good = set()
        for j in sign.judge_folder(v.witnesses, object_id=self.id, version=f"v{v.number}",
                                   inventory=v.digest, owner=self.owner, lookup=lookup, key_log=True):
            if j.status == sign.GOOD and j.key_log == (prev.number, prev.digest):
                good.add(j.key)
            elif j.status != sign.GOOD:
                warnings.append(f"{where}/{j.file}: {j.status}: {j.reason}")
        if len(good) < need:
            return [f"signed by {len(good)} rotation key{'' if len(good) == 1 else 's'} of v{prev.number}, "
                    f"which needs {need} (section 6.1)"]
        return []

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

    def refuse_orphan(self):
        """OwnerError if the folder of this key log holds a version written and not completed."""
        if self.orphan is not None:
            raise OwnerError(f"v{self.orphan.number} of the key log of {self.owner} is on disk after its head: "
                             f"{ORPHAN_HELP}")

    def _prepare(self, signers):
        self.refuse_orphan()
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
        self.refuse_orphan()
        self.versions.append(version)
        self._checked = None
        errors, _ = self.check()
        if errors:
            self.versions.pop()
            self._checked = None
            raise OwnerError("the new version would not be a version of the key log: " + "; ".join(errors))
        return version

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

    def pull(self, other, *, user, created=None):
        """Meet OTHER, another copy of this key log (sections 6.3 and 6.5): append the versions
        it has beyond this one, or a fork record; returns (what, number)."""
        if other.genesis != self.genesis:
            raise OwnerError("the other copy is the key log of another owner")
        errors, _ = self.check()
        if errors:
            raise OwnerError("the key log has errors: " + "; ".join(errors))
        other.check()
        mine, theirs = self.side(), other.side()
        for a, b in zip(mine, theirs):
            if a.digest != b.digest:
                return self._met_fork(theirs[a.number - 1:], user, created)
        their_fr = other.fork_record
        if len(theirs) > len(mine):
            if self.fork_record is not None:
                return "reported", len(mine) + 1
            for v in theirs[len(mine):] + ([their_fr] if their_fr else []):
                self._append(copy.deepcopy(v))
            return "extended", len(theirs) - len(mine) + (1 if their_fr else 0)
        if their_fr is not None:
            first = their_fr.carried[0]
            held = mine[first.number - 1] if first.number <= len(mine) else None
            if held is not None and held.digest != first.digest:
                if self.fork_record is not None:
                    return "reported", first.number
                if len(theirs) == len(mine) and self.versions[-1] is mine[-1]:
                    self._append(copy.deepcopy(their_fr))
                    return "fork", first.number
                return self._met_fork(their_fr.carried, user, created)
        return ("same" if len(theirs) == len(mine) else "behind"), 0

    def _met_fork(self, other_side, user, created):
        if self.fork_record is not None:
            return "reported", other_side[0].number
        self.record_fork(other_side, user=user, created=created)
        return "fork", other_side[0].number

    def met(self, other):
        """A copy of this key log, in memory, having met OTHER as a reader does (no file written)."""
        out = copy.deepcopy(self)
        try:
            out.pull(other, user={"name": "reader"})
        except OwnerError:
            pass
        return out


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


SINGLE_ROTATION_RISK = (
    "With a single rotation key, its loss leaves the owner unable ever to change its keys "
    "or end, and its theft lets the thief take the owner over (sections 6.2 and 15.1).")
ROTATION_KEYS_WARNING = (
    "Keep the rotation keys safe: an owner left with fewer of them than the next version of its key "
    "log needs to sign can never change its keys or end (section 6.2).")


def describe(log, here=(), link=None):
    """Lines describing the key log LOG for a person; HERE, the did:keys held on this computer;
    LINK, the KeeperLink to its keeper, if it was looked for."""
    errors, warnings = log.check()
    rec = _json_or_none(log.genesis) or {}
    out = [f"Owner         {log.owner}"]
    if rec.get("keeper"):
        how = f"  {link.status}" + (f" ({link.reason})" if link.reason else "") if link else ""
        out.append(f"Keeper        {rec['keeper'][0]}{how}")
        claim = successor_claim(log, link)
        if claim:
            out.append(f"Successor     {link.successor}  {claim}")
    for i, v in enumerate(log.versions):
        k = v.keys or {}
        what = ("fork record, carrying " + ", ".join(f"v{c.number}" for c in v.carried) if v.fork_record
                else "ended" + (f", successor {k['successor']}" if k.get("successor") else "") if k.get("ended")
                else _signers(k.get("keys", []), k.get("threshold"), "current key", "sign")
                     + ", " + _signers(k.get("next", []), k.get("nextThreshold"), "rotation key",
                                       "sign the next version")
                     + (f", exposes {len(k['exposed'])}" if k.get("exposed") else ""))
        mark = "" if v.is_version else " (not a version)"
        out.append(f"{'Key log' if i == 0 else '':<14}v{v.number}  {v.digest[:16]}  {what}{mark}")
    latest = log.latest()
    if latest is not None:
        out += [f"{'Current keys' if i == 0 else '':<14}{did}" + ("  (on this computer)" if did in here else "")
                for i, did in enumerate(latest.keys["keys"])]
    out += [f"{'Exposed keys' if i == 0 else '':<14}{did}" for i, did in enumerate(sorted(log.exposed_keys()))]
    if log.fork_point:
        out.append(f"Status        ended by a fork at v{log.fork_point}")
    elif log.ended:
        out.append("Status        ended")
    out += [f"Error: {e}" for e in errors] + [f"Warning: {w}" for w in warnings]
    return out


def _signers(items, threshold, noun, what):
    """N NOUNs, and how many of them WHAT: "3 rotation keys (any 2 sign the next version)"."""
    if len(items) == 1:
        return _count(items, noun)
    verb = what.replace("sign", "signs", 1) if threshold == 1 else what
    return f"{_count(items, noun)} (any {threshold} {verb})"


def _count(items, noun):
    return f"{len(items)} {noun}" + ("" if len(items) == 1 else "s")


KEEPER_FORMAT = "opensheaf-keeper/0.2"
CONFIRMED, CLAIMED, ABSENT, NOT_CHECKED = "confirmed", "claimed only", "absent", "not checked"
ORCID_API = "https://pub.orcid.org/v3.0/{}/researcher-urls"
KEEPER_TIMEOUT = 15
USER_AGENT = "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"
OWNER_WORD = re.compile(r"(?<![a-z0-9])[a-z2-7]{51}[aq](?![a-z0-9])")


class KeeperUnreachable(Exception):
    """The place of a keeper cannot be read."""


def fetch_json(url):
    """The JSON value at URL, or None if there is none (HTTP 404 or 410); KeeperUnreachable if it
    cannot be read."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=KEEPER_TIMEOUT) as r:
            data = r.read((1 << 20) + 1)
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return None
        raise KeeperUnreachable(f"{url}: HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise KeeperUnreachable(f"{url}: {getattr(e, 'reason', e)}") from None
    if len(data) > 1 << 20:
        raise KeeperUnreachable(f"{url}: more than 1 MB")
    try:
        return names.json_value(data)
    except ValueError:
        raise KeeperUnreachable(f"{url}: not JSON") from None


@dataclass
class KeeperLink:
    """The link between an owner and its keeper (section 6.6), as found."""
    keeper: object                   # the keeper's URI, or None
    status: str                      # CONFIRMED, CLAIMED, ABSENT or NOT_CHECKED
    reason: str = ""                 # how it was confirmed, or why not
    successor: object = None         # the successor the keeper names, if any
    document: object = None          # the keeper's file of format opensheaf-keeper/0.2, when read


def keeper_of(log):
    """The keeper named by the genesis record of the key log LOG, or None."""
    try:
        return (names.read_genesis(log.genesis).get("keeper") or [None])[0] if log else None
    except ValueError:
        return None


def keeper_link(log, fetch=None):
    """The link between the owner of the key log LOG and its keeper (section 6.6), read with
    FETCH (a function of a URL, like fetch_json, which it defaults to)."""
    fetch = fetch or fetch_json
    keeper, owner = keeper_of(log), log.owner
    if keeper is None:
        return KeeperLink(None, ABSENT, "the owner names no keeper")
    orcid = keeper.startswith("https://orcid.org/")
    if not orcid and not names.keeper_domain(keeper):
        return KeeperLink(keeper, NOT_CHECKED, "not a DNS name (an address, localhost): not fetched")
    url = ORCID_API.format(keeper.rsplit("/", 1)[1]) if orcid else keeper + ".well-known/opensheaf"
    try:
        data = fetch(url)
    except KeeperUnreachable as e:
        return KeeperLink(keeper, NOT_CHECKED, f"offline: {e}")
    if orcid:
        links = data.get("researcher-url") if isinstance(data, dict) else None
        for item in links if isinstance(links, list) else []:
            value = (item.get("url") or {}).get("value") if isinstance(item, dict) else None
            words = OWNER_WORD.findall(value) if isinstance(value, str) else []
            if words and words[0] == owner:
                others = [w for w in words[1:] if w != owner]
                return KeeperLink(keeper, CONFIRMED, "ORCID record links the owner", others[0] if others else None)
        return KeeperLink(keeper, CLAIMED, "the ORCID record has no link naming the owner")
    if data is None:
        return KeeperLink(keeper, CLAIMED, f"there is no {url}")
    if not isinstance(data, dict) or data.get("format") != KEEPER_FORMAT:
        return KeeperLink(keeper, CLAIMED, f"{url} is not of format {KEEPER_FORMAT}")
    listed = data.get("owners")
    if not (isinstance(listed, list) and owner in listed):
        return KeeperLink(keeper, CLAIMED, f"{url} does not list the owner", document=data)
    succ = (data.get("successors") or {}).get(owner) if isinstance(data.get("successors"), dict) else None
    succ = succ if isinstance(succ, str) and names.OWNER_NAME.match(succ) and succ != owner else None
    return KeeperLink(keeper, CONFIRMED, f"{url} lists the owner", succ, data)


def successor_claim(log, link):
    """How the successor named by the keeper in LINK stands, for a person: "named by the keeper"
    (accepted), "claimed by the keeper (...)", or None when the keeper names none, or the one the
    key log names."""
    if link is None or link.successor is None or link.successor == log.successor:
        return None
    if log.successor:
        return f"claimed by the keeper (the ending version names {log.successor}; section 6.6)"
    return "named by the keeper (section 6.6)"


def linked(base, rel):
    """Whether the path REL below BASE passes through a symbolic link (REL itself included)."""
    at = Path(base)
    for part in Path(rel).parts:
        at = at / part
        if at.is_symlink():
            return True
    return False


def witness_files(obj_dir, version):
    """{file name: bytes} of the regular files of the witness folder of VERSION of the object in
    OBJ_DIR; a link, or a folder reached through one, is not followed (section 15.2)."""
    rel = f"{sign.WITNESSES}/{version}"
    w = Path(obj_dir) / rel
    if linked(obj_dir, rel) or not w.is_dir():
        return {}
    return {f.name: f.read_bytes() for f in sorted(w.iterdir()) if not f.is_symlink() and f.is_file()}


def safe_relative(rel):
    """Whether REL is a relative path that stays below its base: no leading /, no \\, ., .. or empty parts."""
    return (isinstance(rel, str) and bool(rel) and not rel.startswith("/") and "\\" not in rel
            and all(x not in ("", ".", "..") for x in rel.split("/")))


def content_path(cp, inv, n=None):
    """Whether CP, a path of the manifest of the inventory INV (of version N), is a content path of the
    object: vK/<contentDirectory>/..., K <= N."""
    cd = inv.get("contentDirectory", "content") if isinstance(inv, dict) else "content"
    if not safe_relative(cp) or not safe_relative(cd) or "/" in cd:
        return False
    parts = cp.split("/")
    return (len(parts) >= 3 and re.fullmatch(r"v[1-9][0-9]*", parts[0]) is not None and parts[1] == cd
            and (n is None or int(parts[0][1:]) <= n))


def load_key_log(obj_dir):
    """The key log held in the OCFL object folder OBJ_DIR."""
    obj_dir, problems, versions = Path(obj_dir), [], []
    try:
        root = (obj_dir / "inventory.json").read_bytes()
        head = int(names.json_value(root)["head"][1:])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise OwnerError(f"{obj_dir}: not an OCFL object with an inventory ({e})") from None
    for n in range(1, head + 1):
        vdir = obj_dir / f"v{n}"
        try:
            inv_bytes = (vdir / "inventory.json").read_bytes()
            entry = names.json_value(inv_bytes)
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
                cp = manifest[d][0]
                if not content_path(cp, entry, n):
                    problems.append(f"v{n}: a content path out of the object: {cp!r}")
                    raise KeyError(cp)
                if linked(obj_dir, cp):
                    raise OSError(f"{cp} passes through a symbolic link")
                data = (obj_dir / cp).read_bytes()
            except (OSError, KeyError, IndexError, TypeError):
                problems.append(f"v{n}: the content of {paths[0]} is missing")
                data = b""
            if sha512_hex(data) != d:
                problems.append(f"v{n}: {paths[0]} does not have the digest its inventory states")
            for path in paths:
                files[path] = data
        witnesses = witness_files(obj_dir, f"v{n}")
        versions.append(Version(n, files, inv_bytes, sc, witnesses))
    if not versions or GENESIS not in versions[0].files:
        raise OwnerError(f"{obj_dir}: no genesis record in the first version")
    if versions[-1].number == head and root != versions[-1].inventory:
        problems.append("the root inventory differs from that of the head version")
    log = KeyLog(versions[0].files[GENESIS], versions)
    if json.loads(root).get("id") != log.id:
        problems.append(f"the identifier of the object is not {log.id}, that of the owner its genesis record names")
    log.problems = problems
    log.orphan = read_orphan(obj_dir, head + 1)
    return log


ORPHAN_HELP = ("an earlier write of the key log was interrupted before its root inventory was replaced; "
               "osheaf owner complete settles it (it completes a signed version, removes an unsigned one), "
               "and signing another version of that number would fork the key log (section 6.3)")


def read_orphan(obj_dir, n):
    """The version vN in OBJ_DIR after its head, written by an interrupted write, or None."""
    vdir = obj_dir / f"v{n}"
    if not vdir.is_dir():
        return None
    try:
        inv_bytes = (vdir / "inventory.json").read_bytes()
    except OSError:
        inv_bytes = b""
    sc = (vdir / "inventory.json.sha512").read_bytes() if (vdir / "inventory.json.sha512").is_file() else b""
    files = {}
    try:
        entry = names.json_value(inv_bytes)
        for d, paths in entry["versions"][f"v{n}"]["state"].items():
            cp = entry["manifest"][d][0]
            if content_path(cp, entry, n) and not linked(obj_dir, cp) and (obj_dir / cp).is_file():
                for path in paths:
                    files[path] = (obj_dir / cp).read_bytes()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError, OSError):
        pass
    witnesses = witness_files(obj_dir, f"v{n}")
    return Version(n, files, inv_bytes, sc, witnesses)


def complete_orphan(obj_dir):
    """Settle the orphan of the key log in OBJ_DIR: 'completed' (it is the next version, now the
    head), 'removed' (unsigned), or None if there is none; OwnerError if it is signed and fails
    the checks of the key log."""
    obj_dir = Path(obj_dir)
    log = load_key_log(obj_dir)
    o = log.orphan
    if o is None:
        return None
    trial = KeyLog(log.genesis, log.versions + [o])
    errors, _ = trial.check()
    if not errors and not log.check()[0]:
        tmp = obj_dir / "inventory.json.tmp"
        tmp.write_bytes(o.inventory)
        os.replace(tmp, obj_dir / "inventory.json")
        (obj_dir / "inventory.json.sha512").write_bytes(o.sidecar or sidecar(o.inventory))
        return "completed"
    if not o.witnesses:
        shutil.rmtree(obj_dir / f"v{o.number}")
        shutil.rmtree(obj_dir / sign.WITNESSES / f"v{o.number}", ignore_errors=True)
        return "removed"
    raise OwnerError(f"{obj_dir}: v{o.number}, written by an interrupted write, carries signatures and is not "
                     f"a version of the key log ({'; '.join(errors) or 'the key log before it has errors'}): it is "
                     f"left for a person; remove v{o.number}/ and {sign.WITNESSES}/v{o.number}/ only if they "
                     "were never copied anywhere (section 6.3)")


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
        if vdir.exists():
            there = vdir / "inventory.json"
            if not there.is_file() or there.read_bytes() != v.inventory:
                raise OwnerError(f"{obj_dir}: v{v.number} is there already, another version than the one "
                                 f"written now: {ORPHAN_HELP}")
        vdir.mkdir(exist_ok=True)
        inv = json.loads(v.inventory)
        by_digest = {sha512_hex(data): data for data in v.files.values()}
        for d, paths in inv["manifest"].items():
            for cp in paths:
                if not content_path(cp, inv, v.number):
                    raise OwnerError(f"{obj_dir}: v{v.number}: a content path out of the object: {cp!r}")
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
