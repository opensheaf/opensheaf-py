# Generated from literate/08-signatures.md by opensheaf-literate: edit the document, not this file.
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


def message(object_id, version, inventory, key_log):
    """The message signed for VERSION of OBJECT_ID, whose inventory has the digest INVENTORY,
    naming the key-log version KEY_LOG (a pin), as bytes (section 7.2)."""
    return (f"{SIGNATURE_FORMAT}\nobject {object_id}\nversion {version}\n"
            f"inventory {inventory}\nkeylog {key_log}\n").encode("utf-8")


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


FIELDS = {
    "format": re.compile("^" + re.escape(SIGNATURE_FORMAT) + "$"),
    "object": re.compile(r"^sheaf:[a-z2-7]{52}:[a-z2-7]{51}[aq]$"),
    "version": re.compile(r"^v[1-9][0-9]*$"),
    "inventorySha512": re.compile(r"^[0-9a-f]{128}$"),
    "signer": names.OWNER_NAME,
    "key": names.DID_KEY,
    "keyLog": re.compile(r"^sheaf:([a-z2-7]{51}[aq])/v([1-9][0-9]*)\?sha512=([0-9a-f]{128})$"),
    "signature": re.compile(r"^[A-Za-z0-9+/]{86}==$"),
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


def judge_folder(witnesses, **context):
    """The judgements of the signature files among WITNESSES ({file name: bytes}) of one version."""
    return [judge(data, name, **context) for name, data in sorted(witnesses.items())
            if name.startswith("signature-") and name.endswith(".json")]


SIGNED, VOUCHED, CONTESTED, UNSIGNED = "signed", "vouched for", "contested", "unsigned"


def signed_directly(judgements, leave_out=None):
    """Whether the good JUDGEMENTS of one version sign it directly, without those LEAVE_OUT selects."""
    groups = {}
    for j in judgements:
        if j.status == GOOD and not (leave_out and leave_out(j)):
            groups.setdefault(j.key_log, (j.threshold, set()))[1].add(j.key)
    return any(len(keys) >= threshold for threshold, keys in groups.values())


def _would_be_signed(judgements):
    if any(j.status == UNCHECKED for j in judgements):
        return True
    return signed_directly(judgements)


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


def latest_signed(statuses):
    """The number of the latest signed version that is not contested, or None."""
    found = [i + 1 for i, s in enumerate(statuses) if s in (SIGNED, VOUCHED)]
    return found[-1] if found else None


def line_statuses_of(object_id, owner, versions, log, trusted=None):
    """The judgements and statuses of the versions of a line of OWNER, given as (version,
    inventory digest, witness files) in order, against the key log LOG (owners.KeyLog)."""
    judgements = [judge_folder(witnesses, object_id=object_id, version=version, inventory=digest,
                               owner=owner, lookup=log.lookup)
                  for version, digest, witnesses in versions]
    return judgements, line_statuses(judgements, exposed=log.exposed_keys(), fork_point=log.fork_point,
                                     trusted=trusted)
