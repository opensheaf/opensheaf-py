Signatures and the statuses of versions
=======================================

In version 0.2, a version of a line is the owner's only when the owner has
signed it (section 7): **a line is its signed versions, wherever they are
stored**. A signature is a small JSON file in the object's witness folder,
`extensions/opensheaf-witnesses/`, outside every version, so that
signatures can be added to a version after it is made. It signs a message
of five lines that binds the key to one object version, its inventory, and
the version of the owner's key log that lists the key.

This chapter is the module `sign.py`: the signed message, signature files,
the verification of Ed25519 signatures with the strictness section 7.2
requires, and the statuses of section 7.3, of signature files (good,
unchecked, invalid) and of the versions of a line (signed, vouched for,
contested, unchecked, invalid, unsigned). It knows key logs only through a
function that finds a key-log version by its number and digest, which the
[owners](06-owners.md) provide.

    # in src/opensheaf/sign.py:
    <<signatures: the docstring and the imports>>


    <<signatures: the signed message and signature files>>


    <<signatures: strict verification>>


    <<signatures: reading a signature file>>


    <<signatures: the status of a signature file>>


    <<signatures: the statuses of the versions of a line>>

The module builds on the names, and on PyNaCl for Ed25519.

    # in signatures: the docstring and the imports:
    """Signatures of object versions (section 7 of OpenSheaf 0.2): the signed
    message, signature files, strict Ed25519 verification, and the statuses of
    signature files and of the versions of a line (section 7.3)."""

    import base64
    import binascii
    import json
    import re
    from dataclasses import dataclass
    from typing import Optional

    from nacl.exceptions import BadSignatureError, CryptoError
    from nacl.signing import VerifyKey

    from . import names

    SIGNATURE_FORMAT = "opensheaf-signature/0.2"
    WITNESSES = "extensions/opensheaf-witnesses"

The signed message and signature files
--------------------------------------

What is signed is not the file but a message of five lines (section 7.2),
each ended by a line feed, with nothing else: the format, which keeps these
signatures apart from any other use of the key; the identifier of the
object; the object version; the digest of its inventory file; and the pin
of the key-log version that lists the key. The signer is not in the
message: it is the owner part of the object, and of the pin.

    # in signatures: the signed message and signature files:
    def message(object_id, version, inventory, key_log):
        """The message signed for VERSION of OBJECT_ID, whose inventory has the digest INVENTORY,
        naming the key-log version KEY_LOG (a pin), as bytes (section 7.2)."""
        return (f"{SIGNATURE_FORMAT}\nobject {object_id}\nversion {version}\n"
                f"inventory {inventory}\nkeylog {key_log}\n").encode("utf-8")

A signature file is named after its key, `signature-<k>.json`, in the
folder of its version in the witness folder, so that a reader that knows
the keys can fetch it without listing the folder. It holds the fields of
the message, the signer and the key, and the signature in base64. The tools
write it as they write all JSON, indented, in the order of section 7.2.

    # in signatures: the signed message and signature files:
    def file_name(did):
        """The name of the signature file of the key DID (section 7.2)."""
        return f"signature-{names.key_id(did)}.json"


    def signature_file(key, object_id, version, inventory, signer, key_log):
        """The bytes of the signature file of VERSION of OBJECT_ID by KEY (a Key)."""
        sig = key.sign(message(object_id, version, inventory, key_log))
        d = {"format": SIGNATURE_FORMAT, "object": object_id, "version": version, "inventorySha512": inventory,
             "signer": signer, "key": key.did, "keyLog": key_log,
             "signature": base64.b64encode(sig).decode("ascii")}
        return (json.dumps(d, indent=2) + "\n").encode("utf-8")

Strict verification
-------------------

Ed25519 libraries do not all accept the same signatures: RFC 8032 allows
some latitude, and implementations have used it differently (Chalkias,
Garillot, Nikolaenko, "Taming the many EdDSAs", 2020). A signature that one
verifier accepts and another refuses would make a version signed in one
archive and not in another, so section 7.2 fixes the verification: the
cofactorless equation of RFC 8032, section 5.1.7, and the rejection of a
signature whose `S` is not less than the group order L, of a key that is
not the canonical encoding of a point or is a point of small order, and of
an `R` of small order. These are libsodium's rules, which PyNaCl applies;
the function also checks them itself, before calling it, so that the rules
stand written here and do not depend on the version of libsodium.

A point of small order (dividing 8) has one of five `y` coordinates: 0
(order 4), 1 (the neutral element), −1 (order 2), and the two of the points
of order 8; the encodings p and p + 1 of 0 and 1 are not canonical, but
equally small. The sign of `x`, the top bit, does not matter. A canonical
encoding has `y` less than p.

    # in signatures: strict verification:
    L = 2 ** 252 + 27742317777372353535851937790883648493   # the order of the group
    P = 2 ** 255 - 19
    Y8 = int.from_bytes(bytes.fromhex("26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05"), "little")
    SMALL_ORDER_Y = {0, 1, P - 1, P, P + 1, Y8, P - Y8}


    def _y(encoding):
        return int.from_bytes(encoding, "little") & ((1 << 255) - 1)


    def verify(did, msg, signature):
        """Whether SIGNATURE (64 bytes) is a valid Ed25519 signature of MSG by the key DID, verified
        as section 7.2 says."""
        try:
            public = names.did_key_public(did)
        except ValueError:
            return False
        if len(signature) != 64 or int.from_bytes(signature[32:], "little") >= L:
            return False
        if _y(public) >= P or _y(public) in SMALL_ORDER_Y or _y(signature[:32]) in SMALL_ORDER_Y:
            return False
        try:
            VerifyKey(public).verify(msg, signature)
            return True
        except (BadSignatureError, CryptoError, ValueError, TypeError):
            return False

Reading a signature file
------------------------

A signature file must have exactly the fields of section 7.2, each of its
form: an identifier, a version, a digest, owner names, a `did:key`, a pin
of a key-log version whose owner is the signer, and 64 bytes of signature
in base64 with padding. Anything else makes it malformed, and so invalid.

    # in signatures: reading a signature file:
    FIELDS = {
        "format": re.compile("^" + re.escape(SIGNATURE_FORMAT) + r"\Z"),
        "object": re.compile(r"^sheaf:[a-z2-7]{52}:[a-z2-7]{51}[aq]\Z"),
        "version": re.compile(r"^v[1-9][0-9]*\Z"),
        "inventorySha512": re.compile(r"^[0-9a-f]{128}\Z"),
        "signer": names.OWNER_NAME,
        "key": names.DID_KEY,
        "keyLog": re.compile(r"^sheaf:([a-z2-7]{51}[aq])/v([1-9][0-9]*)\?sha512=([0-9a-f]{128})\Z"),
        "signature": re.compile(r"^[A-Za-z0-9+/]{86}==\Z"),
    }


    def read_signature_file(data):
        """The fields of a signature file, from its bytes (ValueError if it is malformed)."""
        try:
            d = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise ValueError(f"not JSON in UTF-8 ({e})") from None
        if not isinstance(d, dict) or set(d) != set(FIELDS):
            raise ValueError("a signature file has exactly the fields " + ", ".join(FIELDS))
        for field, pattern in FIELDS.items():
            if not isinstance(d[field], str) or not pattern.match(d[field]):
                raise ValueError(f"{field} is not of its form")
        names.did_key_public(d["key"])
        if FIELDS["keyLog"].match(d["keyLog"]).group(1) != d["signer"]:
            raise ValueError("keyLog names the key log of another owner than the signer")
        return d

The status of a signature file
------------------------------

A signature file is judged against the version whose folder holds it and
against the key log of the line's owner (section 7.3). It is *invalid*
when:

1. it is malformed, or its name does not match the digest of its key;
2. its signature does not verify;
3. its object, version and inventory digest are not those of the version
   that holds it;
4. its signer is not the line's owner;
5. the key-log version it names is reached, with that digest, and the key
   is not in its `keys` (for a signature of a key-log version, not one of
   its rotation keys, whose digests its `next` holds);
6. the version named is not a version of the key log, or is a fork record;
7. for a signature of a key-log version, it signs the first version, which
   is computed, or names another version than the one before.

It is *unchecked* when the reader cannot reach the version it names, with
that digest: the key log is absent or shorter, or holds another version of
that number. Otherwise it is *good*, for ever. The judgement records the
key and the key-log version named, and that version's threshold, which is
what the status of the version needs.

    # in signatures: the status of a signature file:
    GOOD, UNCHECKED, INVALID = "good", "unchecked", "invalid"


    @dataclass
    class Judgement:
        """The status of one signature file (section 7.3)."""
        file: str
        status: str
        reason: str = ""
        key: Optional[str] = None
        key_log: Optional[tuple] = None     # (number, digest) of the key-log version named
        threshold: Optional[int] = None     # its threshold (or nextThreshold), for a good signature

The key-log version is found by `lookup(number, digest)`, which returns the
version held or carried (an object with `keys`, the parsed `keys.json`,
`fork_record` and `is_version`), or None when it cannot be reached.

    # in signatures: the status of a signature file:
    def judge(data, file, *, object_id, version, inventory, owner, lookup, key_log=False):
        """The status of the signature file FILE (bytes DATA) of VERSION of OBJECT_ID, whose
        inventory has the digest INVENTORY, on a line of OWNER; KEY_LOG for a version of a key log."""
        def bad(reason, d=None):
            return Judgement(file, INVALID, reason, d and d.get("key"))

        try:
            d = read_signature_file(data)
        except ValueError as e:
            return bad(f"malformed: {e}")
        if file != file_name(d["key"]):
            return bad("its name does not match the digest of its key")
        try:
            sig = base64.b64decode(d["signature"], validate=True)
        except (binascii.Error, ValueError):
            return bad("the signature is not base64", d)
        if not verify(d["key"], message(d["object"], d["version"], d["inventorySha512"], d["keyLog"]), sig):
            return bad("the signature does not verify", d)
        if (d["object"], d["version"], d["inventorySha512"]) != (object_id, version, inventory):
            return bad("it signs another version, or another inventory", d)
        if d["signer"] != owner:
            return bad("its signer is not the owner of the line", d)
        _, n, digest = FIELDS["keyLog"].match(d["keyLog"]).groups()
        n = int(n)
        if key_log and (version == "v1" or n != int(version[1:]) - 1):
            return bad("a key-log version is signed against the version before it, never the first", d)
        found = lookup(n, digest)
        if found is None:
            return Judgement(file, UNCHECKED, f"v{n} of the key log, with that digest, is not reached",
                             d["key"], (n, digest))
        if found.fork_record or not found.is_version:
            return bad(f"v{n} is not a version of the key log, or is a fork record", d)
        keys = found.keys or {}
        if key_log:
            if names.key_digest(d["key"]) not in keys.get("next", []):
                return bad(f"the key is not a rotation key of v{n} of the key log", d)
            threshold = keys.get("nextThreshold")
        else:
            if d["key"] not in keys.get("keys", []):
                return bad(f"the key is not a current key of v{n} of the key log", d)
            threshold = keys.get("threshold")
        return Judgement(file, GOOD, "", d["key"], (n, digest), threshold)

A version's signatures are the files `signature-*.json` of its folder in
the witness folder; others' witnesses (`witness-<label>.json`) and the files
of extensions are not signatures of the line, and are left to whoever
knows them (section 7.2).

    # in signatures: the status of a signature file:
    def judge_folder(witnesses, **context):
        """The judgements of the signature files among WITNESSES ({file name: bytes}) of one version."""
        return [judge(data, name, **context) for name, data in sorted(witnesses.items())
                if name.startswith("signature-") and name.endswith(".json")]

The statuses of the versions of a line
--------------------------------------

A version of a line is *signed directly* when at least `threshold`
distinct current keys of one key-log version, `threshold` being that
version's, sign it in good signature files naming that version (section
7.3). Signatures naming different key-log versions do not add up: each is
judged against the version it names alone.

    # in signatures: the statuses of the versions of a line:
    SIGNED, VOUCHED, CONTESTED, UNSIGNED = "signed", "vouched for", "contested", "unsigned"


    def signed_directly(judgements, leave_out=None):
        """Whether the good JUDGEMENTS of one version sign it directly, without those LEAVE_OUT selects."""
        groups = {}
        for j in judgements:
            if j.status == GOOD and not (leave_out and leave_out(j)):
                groups.setdefault(j.key_log, (j.threshold, set()))[1].add(j.key)
        return any(len(keys) >= threshold for threshold, keys in groups.values())

A version is *unchecked* when it is not signed but would be if its
unchecked signatures were good. The threshold of a key-log version that
cannot be reached is unknown; the reading taken here is that such
signatures could be enough, so that a version with any unchecked signature
of a key-log version not reached is unchecked rather than unsigned: it is
shown with its status until the key log is found, and nothing relies on it
meanwhile.

    # in signatures: the statuses of the versions of a line:
    def _would_be_signed(judgements):
        if any(j.status == UNCHECKED for j in judgements):
            return True
        return signed_directly(judgements)

A version is also signed when it is *vouched for*: when a later version of
the same copy of the line is signed directly, since that version's inventory
fixes every earlier one, inventories included (sections 4.3 and 7.3).

A signed version is *contested* when it would not be signed if some of the
good signature files of its owner were left out, its own and those of the
versions that vouch for it: those made with a key that the owner's key log
exposes, in any version, on either side of a fork; and those naming a
version of the key log from a fork point on, of either side. Evidence that
the reader trusts, such as a timestamp dating a signature file before the
exposure or the fork, makes it count nonetheless: the caller says which
files it trusts.

The other versions are *invalid* when one of their signature files is, and
otherwise *unsigned*.

    # in signatures: the statuses of the versions of a line:
    def line_statuses(versions, *, exposed=frozenset(), fork_point=None, trusted=None):
        """The status of each version of one copy of a line (section 7.3), from VERSIONS, the
        judgements of the signature files of each version from v1; EXPOSED, the keys the owner's
        key log exposes, and FORK_POINT, its fork point, if any; TRUSTED(judgement) says whether
        other evidence dates a signature file before the exposure or the fork."""
        def leave_out(j):
            suspect = j.key in exposed or (fork_point is not None and j.key_log[0] >= fork_point)
            return suspect and not (trusted and trusted(j))

        direct = [signed_directly(js) for js in versions]
        clean = [signed_directly(js, leave_out) for js in versions]
        would = [_would_be_signed(js) for js in versions]
        statuses = []
        for i, js in enumerate(versions):
            if direct[i] or any(direct[i + 1:]):
                if clean[i] or any(clean[i + 1:]):
                    statuses.append(SIGNED if direct[i] else VOUCHED)
                else:
                    statuses.append(CONTESTED)
            elif would[i] or any(would[i + 1:]):
                statuses.append(UNCHECKED)
            elif any(j.status == INVALID for j in js):
                statuses.append(INVALID)
            else:
                statuses.append(UNSIGNED)
        return statuses

Readers use the *latest signed version* of a copy of a line, its latest
version that is signed and not contested: it gives the line's history,
current version and status (section 7.3).

    # in signatures: the statuses of the versions of a line:
    def latest_signed(statuses):
        """The number of the latest signed version that is not contested, or None."""
        found = [i + 1 for i, s in enumerate(statuses) if s in (SIGNED, VOUCHED)]
        return found[-1] if found else None

For a line whose owner's key log is at hand, `line_statuses_of` judges the
signature files of every version and gives their statuses, with the
exposures and the fork point of that key log.

    # in signatures: the statuses of the versions of a line:
    def line_statuses_of(object_id, owner, versions, log, trusted=None):
        """The judgements and statuses of the versions of a line of OWNER, given as (version,
        inventory digest, witness files) in order, against the key log LOG (owners.KeyLog)."""
        judgements = [judge_folder(witnesses, object_id=object_id, version=version, inventory=digest,
                                   owner=owner, lookup=log.lookup)
                      for version, digest, witnesses in versions]
        return judgements, line_statuses(judgements, exposed=log.exposed_keys(), fork_point=log.fork_point,
                                         trusted=trusted)
