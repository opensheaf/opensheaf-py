# Generated from literate/05-names.md by opensheaf-literate: edit the document, not this file.
"""Names and identifiers of OpenSheaf 0.2 (https://opensheaf.org): digests
and encodings, did:key URIs, genesis records and the names computed from
them (section 5), the canonical JSON of computed files (JCS, RFC 8785),
sheaf: URIs (section 12.1) and the check digit of ORCID iDs (section 6.6)."""

import base64
import binascii
import datetime
import hashlib
import json
import re
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Optional


def sha256(data):
    """The SHA-256 digest of DATA (bytes), as bytes."""
    return hashlib.sha256(data).digest()


def sha512_hex(data):
    """The SHA-512 digest of DATA (bytes), in lowercase hexadecimal."""
    return hashlib.sha512(data).hexdigest()


B32 = "abcdefghijklmnopqrstuvwxyz234567"


def b32(data):
    """DATA (bytes) in lowercase base32 (RFC 4648), without padding."""
    return base64.b32encode(data).decode("ascii").rstrip("=").lower()


def b32decode(text):
    """The bytes of TEXT, base32 (RFC 4648) without padding, in either case."""
    t = text.upper()
    if not re.fullmatch(r"[A-Z2-7]*", t):
        raise ValueError(f"not base32: {text!r}")
    try:
        return base64.b32decode(t + "=" * (-len(t) % 8))
    except binascii.Error as e:
        raise ValueError(f"not base32: {text!r} ({e})") from None


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(data):
    """DATA (bytes) in base58btc."""
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def b58decode(text):
    """The bytes of TEXT, in base58btc."""
    n = 0
    for c in text:
        i = B58.find(c)
        if i < 0:
            raise ValueError(f"not base58btc: {c!r} in {text!r}")
        n = n * 58 + i
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


ED25519_PUB = b"\xed\x01"   # the multicodec code of ed25519-pub, as a varint
DID_KEY = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}\Z")


def did_key(public):
    """The did:key URI of an Ed25519 public key (32 bytes)."""
    if len(public) != 32:
        raise ValueError("an Ed25519 public key has 32 bytes")
    return "did:key:z" + b58encode(ED25519_PUB + bytes(public))


def did_key_public(did):
    """The 32 bytes of the Ed25519 public key of a did:key URI (ValueError if it is not one)."""
    if not isinstance(did, str) or not did.startswith("did:key:z"):
        raise ValueError(f"not a did:key URI in base58btc: {did!r}")
    raw = b58decode(did[len("did:key:z"):])
    if len(raw) != 34 or raw[:2] != ED25519_PUB:
        raise ValueError(f"not the did:key URI of an Ed25519 key: {did!r}")
    if did_key(raw[2:]) != did:
        raise ValueError(f"not the canonical did:key URI of its key: {did!r}")
    return raw[2:]


def key_digest(did):
    """The digest of a key (section 6.1): base32 SHA-256 of its did:key URI, 52 characters."""
    return b32(sha256(did.encode("utf-8")))


def key_id(did):
    """The 16 characters naming the signature file of a key, signature-<k>.json (section 7.2)."""
    return key_digest(did)[:16]


def short(name):
    """NAME, an owner name or a did:key URI, shortened for a person: its first 8 and last 4 characters."""
    name = name[len("did:key:"):] if name.startswith("did:key:") else name
    return name if len(name) <= 14 else f"{name[:8]}…{name[-4:]}"


GENESIS = "genesis.json"
GENESIS_FORMAT = "opensheaf-genesis/0.2"
KINDS = ("document", "collection", "owner")
NAME = re.compile(r"^[a-z2-7]{52}\Z")
OWNER_NAME = re.compile(r"^[a-z2-7]{51}[aq]\Z")   # names of algorithm 0 (section 5.2)
CREATED = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z\Z")
NONCE = re.compile(r"^([0-9a-f]{2}){16,}\Z")


def utc_now():
    """The time now, in UTC, to the second, as 2026-03-02T09:14:00Z."""
    return (datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))


def new_nonce():
    """128 bits from a cryptographically secure generator, in lowercase hexadecimal."""
    return secrets.token_hex(16)


def genesis_record(kind, *, originator=None, keys=None, threshold=None, next_digests=None,
                   next_threshold=None, keeper=None, extensions=None, created=None, nonce=None):
    """The bytes of a new genesis record (section 5.1)."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    nonce = nonce or new_nonce()
    created = created or utc_now()
    if not NONCE.match(nonce) or not CREATED.match(created):
        raise ValueError("a nonce of at least 128 bits in hexadecimal, and a date in UTC, are needed")
    rec = {"format": GENESIS_FORMAT, "kind": kind, "created": created}
    if kind == "owner":
        if originator is not None:
            raise ValueError("an owner is its own originator: its genesis record names none")
        rec["nonce"] = nonce
        rec.update(keys=list(keys or []), threshold=threshold,
                   next=list(next_digests or []), nextThreshold=next_threshold)
        problems = key_rules_of_record(rec)
        if problems:
            raise ValueError("; ".join(problems))
        if keeper is not None:
            rec["keeper"] = [keeper] if isinstance(keeper, str) else list(keeper)
            if len(rec["keeper"]) != 1 or not keeper_valid(rec["keeper"][0]):
                raise ValueError(f"a keeper is one ORCID iD or https://<domain>/: {keeper!r}")
        if extensions:
            rec["extensions"] = extensions
    else:
        if not isinstance(originator, str) or not OWNER_NAME.match(originator):
            raise ValueError(f"the originator must be an owner name: {originator!r}")
        if any(v is not None for v in (keys, threshold, next_digests, next_threshold, keeper, extensions)):
            raise ValueError("keys, thresholds, keeper and extensions are only for an owner")
        rec["originator"] = originator
        rec["nonce"] = nonce
    return (json.dumps(rec, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def key_rules_of_record(rec):
    """The problems of the keys of an owner's genesis record (section 6.1, rules 1 to 3)."""
    problems = []
    keys, nxt = rec.get("keys"), rec.get("next")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and DID_KEY.match(k) for k in keys):
        problems.append("keys must be a list of at least one did:key URI of an Ed25519 key")
        keys = []
    if not isinstance(nxt, list) or not nxt or not all(isinstance(d, str) and OWNER_NAME.match(d) for d in nxt):
        problems.append("next must be a list of at least one digest of a key (52 characters of base32)")
        nxt = []
    for field, items in (("keys", keys), ("next", nxt)):
        if len(set(items)) != len(items):
            problems.append(f"{field} lists an item twice")
    for field, count, items in (("threshold", rec.get("threshold"), keys),
                                ("nextThreshold", rec.get("nextThreshold"), nxt)):
        if type(count) is not int or count < 1:
            problems.append(f"{field} must be a positive integer")
        elif count > len(items):
            problems.append(f"{field} {count} exceeds the {len(items)} item(s) it counts (rule 1)")
    both = {key_digest(k) for k in keys} & set(nxt)
    if both:
        problems.append("a key is both a current key and a rotation key (rules 2 and 3)")
    return problems


def write_genesis(path, data):
    """Write the bytes of a new genesis record; never replaces a file."""
    with open(path, "xb") as f:
        f.write(data)


def read_genesis(data):
    """The fields of a genesis record, from its bytes (ValueError if it is not one)."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("a genesis record has no byte order mark")
    try:
        rec = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ValueError(f"a genesis record is JSON in UTF-8 ({e})") from None
    if not isinstance(rec, dict) or rec.get("format") != GENESIS_FORMAT:
        raise ValueError(f"not a genesis record of format {GENESIS_FORMAT}")
    if rec.get("kind") not in KINDS:
        raise ValueError(f"unknown kind {rec.get('kind')!r}")
    if not isinstance(rec.get("created"), str) or not CREATED.match(rec["created"]):
        raise ValueError("created must be a date and time in UTC")
    if not isinstance(rec.get("nonce"), str) or not NONCE.match(rec["nonce"]):
        raise ValueError("nonce must have at least 128 bits in lowercase hexadecimal")
    owner_fields = {"keys", "threshold", "next", "nextThreshold", "keeper", "extensions"}
    allowed = {"format", "kind", "created", "nonce"} | (owner_fields if rec["kind"] == "owner" else {"originator"})
    if set(rec) - allowed:
        raise ValueError(f"fields not allowed in a genesis record of kind {rec['kind']}: "
                         + ", ".join(sorted(set(rec) - allowed)))
    if rec["kind"] == "owner":
        problems = key_rules_of_record(rec)
        if "keeper" in rec and not (isinstance(rec["keeper"], list) and len(rec["keeper"]) == 1
                                    and isinstance(rec["keeper"][0], str) and keeper_valid(rec["keeper"][0])):
            problems.append("keeper must be a list of one ORCID iD (with its check digit) or https://<domain>/")
        if "extensions" in rec and not (isinstance(rec["extensions"], dict)
                                        and all(isinstance(v, dict) for v in rec["extensions"].values())):
            problems.append("extensions must map names of extensions to objects")
        if problems:
            raise ValueError("; ".join(problems))
    elif not isinstance(rec.get("originator"), str) or not OWNER_NAME.match(rec["originator"]):
        raise ValueError("a document or a collection names its originator, an owner name")
    return rec


def name(genesis, k=0):
    """The name of algorithm K (0 to 15) of a genesis record, from its bytes (section 5.2)."""
    if not 0 <= k <= 15:
        raise ValueError("the algorithms of names are numbered 0 to 15")
    s = b32(sha256(f"opensheaf-name-{k}\n".encode("ascii") + genesis))
    return s[:-1] + B32[B32.index(s[-1]) | k]


def algorithm(nm):
    """The algorithm number of a name, read from its last character."""
    return B32.index(nm[-1]) & 0xF


def is_name_of(nm, genesis):
    """Whether NM is one of the 16 names of the genesis record GENESIS (bytes)."""
    return isinstance(nm, str) and bool(NAME.match(nm)) and name(genesis, algorithm(nm)) == nm


def object_id(nm, owner):
    """The identifier of the line (NM, OWNER): sheaf:<name>:<owner> (section 4)."""
    return f"sheaf:{nm}:{owner}"


def key_log_pin(owner, number, digest):
    """The pin of version NUMBER of the key log of OWNER, as keyLog writes it (section 7.2)."""
    return f"sheaf:{owner}/v{number}?sha512={digest}"


JCS_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def jcs(value):
    """The JCS form (RFC 8785) of a JSON value, as UTF-8 bytes, without a final line feed.
    Numbers must be integers of at most 2^53 in absolute value."""
    return _jcs(value).encode("utf-8")


def _jcs(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, int):
        if abs(v) > 2 ** 53:
            raise ValueError(f"the integer {v} has no exact form in JCS")
        return str(v)
    if isinstance(v, float):
        raise ValueError("the canonical JSON of OpenSheaf has no fractional numbers")
    if isinstance(v, str):
        return _jcs_string(v)
    if isinstance(v, (list, tuple)):
        return "[" + ",".join(_jcs(x) for x in v) + "]"
    if isinstance(v, dict):
        if not all(isinstance(k, str) for k in v):
            raise TypeError("the names of JSON members are strings")
        items = sorted(v.items(), key=lambda kv: _utf16(kv[0]))
        return "{" + ",".join(_jcs_string(k) + ":" + _jcs(x) for k, x in items) + "}"
    raise TypeError(f"not a JSON value: {type(v).__name__}")


def _utf16(s):
    try:
        return s.encode("utf-16-be")
    except UnicodeEncodeError:
        raise ValueError("a string with a lone surrogate has no JCS form") from None


def _jcs_string(s):
    out = ['"']
    for c in s:
        if c in JCS_ESCAPES:
            out.append(JCS_ESCAPES[c])
        elif c < " ":
            out.append(f"\\u{ord(c):04x}")
        elif "\ud800" <= c <= "\udfff":
            raise ValueError("a string with a lone surrogate has no JCS form")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


@dataclass
class SheafURI:
    """A sheaf: URI (section 12.1), by its parts."""
    name: str
    owner: Optional[str] = None      # an owner name, "*" for the work, None for the originator's line
    version: Optional[int] = None    # the number of /v<n>
    sha512: Optional[str] = None     # the inventory digest of a pin
    at: Optional[str] = None         # the hint, decoded
    params: tuple = ()               # other parameters, (name, value) pairs, ignored by resolvers

    def __str__(self):
        s = f"sheaf:{self.name}"
        if self.owner is not None:
            s += f":{self.owner}"
        if self.version is not None:
            s += f"/v{self.version}"
        query = []
        if self.sha512 is not None:
            query.append(f"sha512={self.sha512}")
        if self.at is not None:
            query.append("at=" + urllib.parse.quote(self.at, safe="-._~"))
        query += [f"{k}={v}" for k, v in self.params]
        return s + ("?" + "&".join(query) if query else "")

    def canonical(self, originator=None, genesis_name=None):
        """The canonical form (section 12.1), given the originator of the work and, for
        sheaf:<name>:*, its genesis name when NAME is not of algorithm 0."""
        if not self.is_complete():
            raise ValueError(f"a short form has no canonical form until it is expanded: {self}")
        nm, owner = self.name, self.owner
        if owner == "*":
            if algorithm(nm) != 0:
                if genesis_name is None:
                    raise ValueError("the canonical form of a work needs its genesis name")
                nm = genesis_name
        elif owner is not None and owner == originator:
            owner = None
        return str(SheafURI(nm, owner, self.version, self.sha512))

    def is_complete(self):
        """Whether the name and the owner part are complete, not short forms (section 12.2)."""
        return len(self.name) == 52 and (self.owner in (None, "*") or len(self.owner) == 52)

    def matches(self, nm, owner):
        """Whether the line (NM, OWNER) is a candidate for this URI, possibly a short form
        (section 12.2); without an owner part, the caller gives the originator as OWNER."""
        return nm.startswith(self.name) and (self.owner in (None, "*") or owner.startswith(self.owner))


PART = re.compile(r"^[a-z2-7]+\Z")
UNRESERVED_OR_ESCAPED = re.compile(r"^(?:[A-Za-z0-9\-._~]|%[0-9A-Fa-f]{2})*\Z")


def parse_sheaf(text, *, short=False, fold=False):
    """The parts of a sheaf: URI (section 12.1); SHORT accepts short forms (section 12.2),
    FOLD folds uppercase letters where case is folded. ValueError if it is not one."""
    def fail(why):
        raise ValueError(f"not a sheaf: URI ({why}): {text!r}")

    head, q, query = text.partition("?")
    if fold:
        head = head.lower()
    m = re.fullmatch(r"sheaf:([^:/]+)(?::([^:/]+))?(?:/v([^/]*))?", head)
    if not m:
        fail("sheaf:<name>[:<owner>][/v<n>]")
    nm, owner, version = m.groups()
    for label, part in (("name", nm), ("owner", owner)):
        if part is None or (label == "owner" and part == "*"):
            continue
        if not PART.match(part) or len(part) > 52 or (len(part) < 52 and not (short and len(part) >= 8)):
            fail(f"the {label} has 52 characters of base32" + (", or at least 8" if short else ""))
    if owner and len(owner) == 52 and not OWNER_NAME.match(owner):
        fail("an owner name is a name of algorithm 0")
    if version is not None and not re.fullmatch(r"[1-9][0-9]*", version):
        fail("a version is /v and a positive integer without leading zeros")
    uri = SheafURI(nm, owner, int(version) if version else None)
    if q:
        seen, params = [], []
        for p in query.split("&"):
            key, eq, value = p.partition("=")
            if fold:
                key = key.lower()
            if not eq or not key:
                fail("parameters are name=value")
            if key == "sha512":
                if fold:
                    value = value.lower()
                if "sha512" in seen or uri.version is None or not re.fullmatch(r"[0-9a-f]{128}", value):
                    fail("one sha512, after a version, of 128 hexadecimal digits")
                uri.sha512 = value
            elif key == "at":
                if "at" in seen or not UNRESERVED_OR_ESCAPED.match(value):
                    fail("one at, percent-encoded")
                at = urllib.parse.unquote(value)
                if not at.startswith("https://") or not at.endswith("/"):
                    fail("at is an https URL ending with /")
                uri.at = at
            else:
                params.append((key, value))
            if key == "sha512" and "at" in seen:
                fail("at comes after sha512")
            seen.append(key)
        uri.params = tuple(params)
    if owner == "*" and (uri.version is not None or uri.sha512 is not None):
        fail("a work, sheaf:<name>:*, has no version")
    return uri


ORCID = re.compile(r"^(?:https://orcid\.org/)?([0-9]{4})-([0-9]{4})-([0-9]{4})-([0-9]{3}[0-9X])\Z")
KEEPER_DOMAIN = re.compile(r"^https://[a-z0-9.-]+/\Z")


def orcid_check_digit(digits):
    """The check digit (ISO 7064 MOD 11-2) of the first 15 digits of an ORCID iD."""
    total = 0
    for ch in digits:
        total = (total + int(ch)) * 2
    r = (12 - total % 11) % 11
    return "X" if r == 10 else str(r)


def orcid_valid(text):
    """Whether TEXT is an ORCID iD (bare or as https://orcid.org/...) with a correct check digit."""
    m = ORCID.match(text)
    if not m:
        return False
    digits = "".join(m.groups())
    return orcid_check_digit(digits[:15]) == digits[15]


def keeper_valid(uri):
    """Whether URI is a keeper (section 6.6): https://orcid.org/<iD> with its check digit,
    or https://<domain>/."""
    if uri.startswith("https://orcid.org/"):
        return orcid_valid(uri)
    return bool(KEEPER_DOMAIN.match(uri))
