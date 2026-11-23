# Generated from literate/07-keys.md by opensheaf-literate: edit the document, not this file.
"""Keys of owners (sections 6.2 and 15.4 of OpenSheaf 0.2): Ed25519 keys made
as RFC 8032 says; current keys kept in the system's credential store (or a
file of the user's configuration); rotation keys exported once, to files
outside the archive (encrypted under a passphrase) and to a printed sheet,
and read back; keys as the encrypted files of a key wallet (an envelope that
the passphrase and passkeys unlock) and as a text for a password manager;
predictable keys for the tests only.

Current keys are found, in this order: the environment variable
OPENSHEAF_SIGNING_KEY (the base64 seed of one key, for continuous
integration); the credential store, through the package keyring, under
the service opensheaf-current-key and the account <owner>:<k>; on macOS
the keychain directly, under the same names; and the file
~/.config/opensheaf/keys/<owner>/<k>.key, readable only by its owner.
OPENSHEAF_KEY_STORE=keyring|security|file uses that store alone;
OPENSHEAF_KEY_STORE=none keeps current keys in the memory of a command only,
opened from the key wallet by each command that signs."""

import base64
import binascii
import hashlib
import hmac
import os
import shutil
import subprocess
import sys
from pathlib import Path

from nacl import pwhash, secret, utils
from nacl.exceptions import CryptoError
from nacl.signing import SigningKey

from . import names


class KeyStoreError(Exception):
    """A key that cannot be made, kept, found or read back."""


class Key:
    """An Ed25519 key, from its 32-byte seed (the private key of RFC 8032)."""

    def __init__(self, seed):
        if len(seed) != 32:
            raise KeyStoreError("the seed of an Ed25519 key has 32 bytes")
        self.seed = bytes(seed)
        self._signing = SigningKey(self.seed)
        self.public = bytes(self._signing.verify_key)
        self.did = names.did_key(self.public)
        self.digest = names.key_digest(self.did)
        self.id = self.digest[:16]

    def sign(self, message):
        """The Ed25519 signature (RFC 8032) of MESSAGE (bytes), 64 bytes."""
        return self._signing.sign(message).signature

    def __repr__(self):
        return f"Key({self.did})"


def new_key():
    """A new key, from a secure random seed (or, in the tests only, a predictable one)."""
    label = _next_test_label()
    if label is not None:
        return example_key(label)
    return Key(utils.random(32))


TEST_KEYS = "OSHEAF_TEST_KEYS"
EXAMPLE_PREFIX = "opensheaf appendix C example key "
_test_labels = {"spec": None, "next": 0}


def example_key(label):
    """The key of appendix C made from LABEL (for the tests and the examples only)."""
    return Key(names.sha256((EXAMPLE_PREFIX + label).encode("utf-8")))


def _next_test_label():
    spec = os.environ.get(TEST_KEYS)
    if not spec:
        return None
    if "PYTEST_CURRENT_TEST" not in os.environ:
        raise KeyStoreError(f"{TEST_KEYS} is set outside the tests: refusing to make predictable keys")
    if _test_labels["spec"] != spec:
        _test_labels.update(spec=spec, next=0)
    labels = [x.strip() for x in spec.split(",")]
    if _test_labels["next"] >= len(labels):
        raise KeyStoreError(f"{TEST_KEYS} has no label left for another key")
    _test_labels["next"] += 1
    return labels[_test_labels["next"] - 1]


SERVICE = "opensheaf-current-key"
SIGNING_KEY = "OPENSHEAF_SIGNING_KEY"
KEY_STORE = "OPENSHEAF_KEY_STORE"
STORES = ("keyring", "security", "file")
NONE = "none"


def _stores():
    pinned = os.environ.get(KEY_STORE)
    if pinned:
        if pinned not in STORES + (NONE,):
            raise KeyStoreError(f"{KEY_STORE} is one of {', '.join(STORES + (NONE,))}")
        return [] if pinned == NONE else [pinned]
    return list(STORES)


def kept_on_device():
    """Whether current keys are kept on this device (unless OPENSHEAF_KEY_STORE=none)."""
    return os.environ.get(KEY_STORE) != NONE


def _owner(owner):
    if not isinstance(owner, str) or not names.OWNER_NAME.match(owner):
        raise KeyStoreError(f"not an owner name: {owner!r}")
    return owner


def _account(owner, kid):
    return f"{_owner(owner)}:{kid}"


def key_folder(owner):
    """The folder of the key files of OWNER in the user's configuration."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opensheaf" / "keys" / _owner(owner)


_SEEN = {}


def forget_seen():
    """Forget what this command has read from the stores, and the keys held in memory only."""
    _SEEN.clear()


def _slot(store, owner, kid):
    return (store, str(key_folder(owner)) if store == "file" else "", owner, kid)


def _lookup(store, owner, kid):
    slot = _slot(store, owner, kid)
    if slot not in _SEEN:
        _SEEN[slot] = _read(store, owner, kid)
    return _SEEN[slot]


def _read(store, owner, kid):
    if store == NONE:
        return None
    if store == "keyring":
        try:
            import keyring
            return keyring.get_password(SERVICE, _account(owner, kid))
        except Exception:   # no keyring, no store, or a store that refuses
            return None
    if store == "security":
        if sys.platform != "darwin" or not shutil.which("security"):
            return None
        r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", _account(owner, kid), "-w"],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else None
    path = key_folder(owner) / f"{kid}.key"
    if path.is_symlink():
        raise KeyStoreError(f"{path} is a symbolic link: a key file is a plain file of its own")
    if not path.exists():
        return None
    if path.stat().st_mode & 0o077:
        raise KeyStoreError(f"{path} can be read by other users: chmod 600 it (and check who read it)")
    return path.read_text(encoding="ascii").strip()


def key_from_base64(text, where):
    """The key whose seed is TEXT, in base64."""
    try:
        seed = base64.b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError):
        seed = b""
    if len(seed) != 32:
        raise KeyStoreError(f"{where}: not the base64 seed of an Ed25519 key")
    return Key(seed)


def current_keys(owner, keys):
    """The keys of OWNER kept on this device among KEYS, the did:key URIs of `keys` of the
    latest version of its key log."""
    env = os.environ.get(SIGNING_KEY, "").strip()
    if env:
        key = key_from_base64(env, SIGNING_KEY)
        if key.did not in keys:
            raise KeyStoreError(f"{SIGNING_KEY} holds {key.did}, which is not a current key of {owner}")
        return [key]
    found = []
    for did in keys:
        kid = names.key_id(did)
        for store in _stores() + [NONE]:
            text = _lookup(store, owner, kid)
            if text:
                key = key_from_base64(text, f"{store} {_account(owner, kid)}")
                if key.did != did:
                    raise KeyStoreError(f"{store} {_account(owner, kid)} holds another key than {did}")
                found.append(key)
                break
    return found


def store_current_key(owner, key, store=None):
    """Keep the current key KEY of OWNER on this device; returns the name of the store used
    ("none": in the memory of this command only)."""
    text = base64.b64encode(key.seed).decode("ascii")
    for s in ([store] if store else _stores() or [NONE]):
        if _write(s, owner, key.id, text):
            _SEEN[_slot(s, owner, key.id)] = text
            return s
    raise KeyStoreError(f"no store kept the key {key.did}")


def _write(store, owner, kid, text):
    account = _account(owner, kid)
    if store == NONE:
        return True
    if store == "keyring":
        try:
            import keyring
            from keyring.backends import null
            if isinstance(keyring.get_keyring(), null.Keyring):
                return False
            keyring.set_password(SERVICE, account, text)
            return True
        except Exception:
            return False
    if store == "security":
        if sys.platform != "darwin" or not shutil.which("security"):
            return False
        r = subprocess.run(["security", "-i"], input=f"add-generic-password -U -s {SERVICE} -a {account} -w {text}\n",
                           capture_output=True, text=True)
        if r.returncode != 0:
            return False
        back = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
                              capture_output=True, text=True)
        return back.returncode == 0 and back.stdout.strip() == text
    folder = key_folder(owner)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(folder / f"{kid}.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(text + "\n")
    print(f"Warning: A current key of {names.short(owner)} is kept in "
          f"{folder / f'{kid}.key'}, protected only by the permissions of your files; install the package "
          "keyring to keep it in your system's credential store.", file=sys.stderr)
    return True


def forget_current_key(owner, did):
    """Remove the current key DID of OWNER from every store of this device."""
    kid = names.key_id(did)
    for store in _stores():
        if store == "keyring":
            try:
                import keyring
                keyring.delete_password(SERVICE, _account(owner, kid))
            except Exception:
                pass
        elif store == "security" and sys.platform == "darwin" and shutil.which("security"):
            subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", _account(owner, kid)],
                           capture_output=True)
        elif store == "file":
            (key_folder(owner) / f"{kid}.key").unlink(missing_ok=True)
        _SEEN[_slot(store, owner, kid)] = None
    _SEEN.pop(_slot(NONE, owner, kid), None)


OPSLIMIT, MEMLIMIT = pwhash.argon2id.OPSLIMIT_MODERATE, pwhash.argon2id.MEMLIMIT_MODERATE


def _argon2id(passphrase, salt, opslimit, memlimit):
    """The key derived from PASSPHRASE by Argon2id, with a cost read from a file, checked first."""
    a = pwhash.argon2id
    opslimit, memlimit = int(opslimit), int(memlimit)
    if not (a.OPSLIMIT_MIN <= opslimit <= a.OPSLIMIT_SENSITIVE and a.MEMLIMIT_MIN <= memlimit <= a.MEMLIMIT_SENSITIVE):
        raise KeyStoreError(f"the key asks for an Argon2id cost out of bounds (opslimit={opslimit}, "
                            f"memlimit={memlimit}): at most {a.OPSLIMIT_SENSITIVE} and {a.MEMLIMIT_SENSITIVE}")
    if len(salt) != a.SALTBYTES:
        raise KeyStoreError("the encryption of the key is damaged")
    try:
        return a.kdf(secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"), salt,
                     opslimit=opslimit, memlimit=memlimit)
    except (MemoryError, RuntimeError) as e:
        raise KeyStoreError(f"Argon2id could not run with memlimit={memlimit} on this machine: {e}") from None


class PassphraseNeeded(KeyStoreError):
    """A key encrypted under a passphrase, read without one; PASSKEYS, the passkeys that could unlock it
    instead."""

    def __init__(self, message, passkeys=()):
        super().__init__(message)
        self.passkeys = list(passkeys)


def encrypt_seed(seed, passphrase, *, opslimit=None, memlimit=None):
    """(the encryption field, the bytes kept): SEED encrypted under PASSPHRASE, or as it is if None."""
    if passphrase is None:
        return "none", seed
    opslimit = OPSLIMIT if opslimit is None else opslimit
    memlimit = MEMLIMIT if memlimit is None else memlimit
    salt = utils.random(pwhash.argon2id.SALTBYTES)
    box = secret.SecretBox(_argon2id(passphrase, salt, opslimit, memlimit))
    return (f"argon2id-secretbox opslimit={opslimit} memlimit={memlimit} "
            f"salt={base64.b64encode(salt).decode('ascii')}", box.encrypt(seed))


def decrypt_seed(encryption, data, passphrase):
    """The seed kept as DATA, with the encryption field ENCRYPTION, under PASSPHRASE."""
    encryption = encryption.split()
    if encryption == ["none"]:
        return data
    if not encryption or encryption[0] != "argon2id-secretbox":
        raise KeyStoreError(f"unknown encryption: {' '.join(encryption)!r}")
    if passphrase is None:
        raise PassphraseNeeded("this key is encrypted: a passphrase is needed")
    params = dict(p.partition("=")[::2] for p in encryption[1:])
    try:
        salt = base64.b64decode(params["salt"], validate=True)
        box = secret.SecretBox(_argon2id(passphrase, salt, params["opslimit"], params["memlimit"]))
        return box.decrypt(data)
    except (KeyError, ValueError, binascii.Error):
        raise KeyStoreError("the encryption of the key is damaged") from None
    except CryptoError:
        raise KeyStoreError("wrong passphrase, or a damaged key") from None


ENVELOPE = "envelope-secretbox"
PASSKEY_RP = "unlock.opensheaf.org"
OLD_PASSKEY_RP = "opensheaf.org"
PASSKEY_INFO = b"opensheaf wallet passkey v1"
PASSKEY_SALT = "opensheaf wallet unlock v1 "


def passkey_salt(owner):
    """The PRF salt of the passkeys that unlock the keys of OWNER."""
    return names.sha256((PASSKEY_SALT + owner).encode("utf-8"))


def passkey_kek(prf_secret):
    """The key-encryption key of a passkey wrap: HKDF-SHA256 (RFC 5869) of its PRF secret."""
    prk = hmac.new(b"\0" * 32, bytes(prf_secret), hashlib.sha256).digest()
    return hmac.new(prk, PASSKEY_INFO + b"\x01", hashlib.sha256).digest()


def _b64(data):
    return base64.b64encode(data).decode("ascii")


class Passkey:
    """A passkey that unlocks keys: credential CRED (base64url), PRF SALT (bytes), relying party RP,
    and KEK, its key-encryption key, once unlocked."""

    def __init__(self, cred, salt, rp=PASSKEY_RP, kek=None, box=None):
        self.cred, self.salt, self.rp, self.kek, self.box = cred, bytes(salt), rp, kek, box

    def opens(self, kek):
        """Whether KEK unwraps the box of this wrap."""
        if self.box is None:
            return False
        try:
            secret.SecretBox(kek).decrypt(self.box)
            return True
        except (CryptoError, ValueError, TypeError):
            return False

    def wrap(self, data_key):
        """The wrap line of DATA_KEY under this passkey."""
        return (f"wrap passkey prf rp={self.rp} cred={self.cred} salt={_b64(self.salt)} "
                + _b64(secret.SecretBox(self.kek).encrypt(data_key)))

    def __repr__(self):
        return f"Passkey({self.rp} {self.cred})"


def envelope(seed, passphrase, passkeys=(), *, opslimit=None, memlimit=None):
    """(the wrap lines, the encrypted seed): SEED under a new data key, wrapped under PASSPHRASE and
    under each of PASSKEYS (unlocked)."""
    opslimit = OPSLIMIT if opslimit is None else opslimit
    memlimit = MEMLIMIT if memlimit is None else memlimit
    data_key = utils.random(secret.SecretBox.KEY_SIZE)
    return _wraps(data_key, passphrase, passkeys, opslimit, memlimit), secret.SecretBox(data_key).encrypt(seed)


def _wraps(data_key, passphrase, passkeys, opslimit, memlimit):
    salt = utils.random(pwhash.argon2id.SALTBYTES)
    box = secret.SecretBox(_argon2id(passphrase, salt, opslimit, memlimit)).encrypt(data_key)
    return ([f"wrap passphrase argon2id opslimit={opslimit} memlimit={memlimit} salt={_b64(salt)} {_b64(box)}"]
            + [p.wrap(data_key) for p in passkeys])


def parse_wrap(line):
    """{method, kind, box, and the parameters} of a wrap line."""
    parts = line.split()
    if len(parts) < 4 or parts[0] != "wrap":
        raise KeyStoreError(f"a damaged lock of the key: {line!r}")
    out = dict(p.partition("=")[::2] for p in parts[3:-1])
    try:
        out.update(method=parts[1], kind=parts[2], box=base64.b64decode(parts[-1], validate=True))
        if "salt" in out:
            out["salt"] = base64.b64decode(out["salt"], validate=True)
    except (binascii.Error, ValueError):
        raise KeyStoreError("a lock of the key is damaged") from None
    return out


def wraps_of(text):
    """The wrap lines of the key file TEXT."""
    return [line.strip() for line in text.splitlines() if line.strip().startswith("wrap ")]


def passkeys_of(text):
    """The passkeys (not unlocked) that can unlock the key file TEXT."""
    out = []
    for line in wraps_of(text):
        w = parse_wrap(line)
        if w["method"] == "passkey" and w["kind"] == "prf" and w.get("cred"):
            out.append(Passkey(w["cred"], w.get("salt", b""), w.get("rp", PASSKEY_RP), box=w["box"]))
    return out


def data_key(wraps, passphrase=None, keks=None):
    """The data key of the wrap lines WRAPS, unwrapped with KEKS ({cred: key}) or PASSPHRASE."""
    parsed = [parse_wrap(w) for w in wraps]
    for w in parsed:
        if w["method"] == "passkey" and keks and w.get("cred") in keks:
            try:
                return secret.SecretBox(keks[w["cred"]]).decrypt(w["box"])
            except CryptoError:
                pass
    if passphrase is None:
        raise PassphraseNeeded("this key is encrypted: a passphrase is needed",
                               [Passkey(w["cred"], w.get("salt", b""), w.get("rp", PASSKEY_RP), box=w["box"])
                                for w in parsed if w["method"] == "passkey" and w.get("cred")])
    for w in parsed:
        if w["method"] == "passphrase" and w["kind"] == "argon2id":
            try:
                kek = _argon2id(passphrase, w["salt"], int(w["opslimit"]), int(w["memlimit"]))
            except (KeyError, ValueError):
                raise KeyStoreError("the encryption of the key is damaged") from None
            try:
                return secret.SecretBox(kek).decrypt(w["box"])
            except CryptoError:
                pass
    raise KeyStoreError("wrong passphrase, or a damaged key")


def open_envelope(wraps, data, passphrase=None, keks=None):
    """The seed encrypted as DATA under the data key of the wrap lines WRAPS."""
    try:
        return secret.SecretBox(data_key(wraps, passphrase, keks)).decrypt(data)
    except CryptoError:
        raise KeyStoreError("the seed of the key is damaged") from None


def add_passkey(text, passphrase, passkey, *, opslimit=None, memlimit=None):
    """The key file TEXT with one more wrap, under PASSKEY (unlocked); PASSPHRASE opens it."""
    lines = text.splitlines()
    enc = next((i for i, x in enumerate(lines) if x.startswith("encryption ")), None)
    seed_at = next((i for i, x in enumerate(lines) if x.startswith("seed ")), None)
    if enc is None or seed_at is None or seed_at < enc:
        raise KeyStoreError("not a key file")
    method = lines[enc].split()[1:2]
    if method == [ENVELOPE]:
        key = data_key(wraps_of(text), passphrase)
        last = max(i for i, x in enumerate(lines) if x.startswith("wrap "))
        lines.insert(last + 1, passkey.wrap(key))
    elif method == ["none"]:
        raise KeyStoreError("this key is kept unencrypted: there is nothing to unlock")
    else:
        try:
            data = base64.b64decode(lines[seed_at][5:].strip(), validate=True)
        except ValueError:
            raise KeyStoreError("the seed of the key is damaged") from None
        seed = decrypt_seed(lines[enc][len("encryption "):], data, passphrase)
        wraps, data = envelope(seed, passphrase, [passkey], opslimit=opslimit, memlimit=memlimit)
        lines[enc:seed_at + 1] = [f"encryption {ENVELOPE}", *wraps, "seed " + _b64(data)]
    return "\n".join(lines) + "\n"


def remove_passkeys(text, cred=None, rp=None):
    """The key file TEXT without the passkey wraps of the credential CRED, or of the relying party RP."""
    def gone(line):
        if not line.startswith("wrap passkey "):
            return False
        w = parse_wrap(line)
        return (cred is None or w.get("cred") == cred) and (rp is None or w.get("rp", PASSKEY_RP) == rp)
    if cred is None and rp is None:
        raise KeyStoreError("name the passkey locks to remove, by credential or relying party")
    lines = text.splitlines()
    kept = [x for x in lines if not gone(x.strip())]
    if not any(x.strip().startswith("wrap passphrase ") for x in kept):
        raise KeyStoreError("the key would have no passphrase lock left")
    return "\n".join(kept) + "\n"


ROTATION_FORMAT = "opensheaf-rotation-key/0.2"


def rotation_file_name(owner, key):
    return f"rotation-{owner[:16]}-{key.id}.txt"


def archive_above(path, archive_root=None):
    """The archive folder that holds PATH, ARCHIVE_ROOT or one with osheaf.json, or None."""
    p = Path(path).resolve()
    if archive_root is not None:
        root = Path(archive_root).resolve()
        if p == root or root in p.parents:
            return root
    for d in [p, *p.parents]:
        if (d / "osheaf.json").exists():
            return d
    return None


def rotation_key_text(key, owner, version, passphrase=None, *, opslimit=None, memlimit=None):
    """The text of the exported file of the rotation key KEY of OWNER, committed in VERSION."""
    return _file_text([ROTATION_FORMAT], key, owner, version, passphrase, opslimit, memlimit)


def _file_text(head, key, owner, version, passphrase, opslimit, memlimit):
    encryption, data = encrypt_seed(key.seed, passphrase, opslimit=opslimit, memlimit=memlimit)
    lines = head + [f"owner {owner}"] + ([f"version v{version}"] if version else [])
    lines += [f"key {key.did}", f"digest {key.digest}", f"encryption {encryption}",
              "seed " + base64.b64encode(data).decode("ascii")]
    return "\n".join(lines) + "\n"


def export_rotation_keys(keys, owner, version, folder, *, passphrase=None, archive_root=None,
                         opslimit=None, memlimit=None):
    """Write the rotation keys KEYS of OWNER, committed in VERSION, to FOLDER, one file each."""
    inside = archive_above(folder, archive_root)
    if inside is not None:
        raise KeyStoreError(f"{folder} is inside the archive {inside}: keys are never kept in an archive "
                            "(section 15.4)")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = []
    for key in keys:
        path = folder / rotation_file_name(owner, key)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(rotation_key_text(key, owner, version, passphrase, opslimit=opslimit, memlimit=memlimit))
        paths.append(path)
    return paths


SHEET_TITLE = "OpenSheaf rotation key"


def sheet_check(seed):
    """The four characters that check a seed typed back from a sheet."""
    return names.b32(names.sha256(b"opensheaf-rotation-key-check\n" + seed))[:4].upper()


def rotation_key_sheet(key, owner, version):
    """The text of a sheet to print, holding the rotation key KEY of OWNER, committed in VERSION."""
    groups = names.b32(key.seed).upper()
    seed = " ".join(groups[i:i + 4] for i in range(0, len(groups), 4))
    return "\n".join([
        f"{SHEET_TITLE} ({ROTATION_FORMAT})",
        "Keep this sheet offline, apart from the owner's devices and its other rotation keys:",
        "with enough of them, whoever holds it can change the owner's keys.",
        "",
        f"owner    {owner}",
        f"version  v{version}",
        f"key      {key.did}",
        f"digest   {key.digest}",
        f"seed     {seed}",
        f"check    {sheet_check(key.seed)}",
    ]) + "\n"


KEY_FORMAT = "opensheaf-key/0.2"
CURRENT, ROTATION = "current", "rotation"
KINDS = (CURRENT, ROTATION)


def key_file_text(key, owner, kind, version=None, passphrase=None, *, passkeys=(), opslimit=None,
                  memlimit=None):
    """The text of the wallet file of the key KEY of OWNER, of KIND, committed in VERSION (or None),
    encrypted under PASSPHRASE and the unlocked PASSKEYS (or in clear if PASSPHRASE is None)."""
    if kind not in KINDS:
        raise KeyStoreError(f"a key is {' or '.join(KINDS)}")
    head = [KEY_FORMAT, f"kind {kind}"]
    if passphrase is None:
        return _file_text(head, key, owner, version, None, opslimit, memlimit)
    wraps, data = envelope(key.seed, passphrase, passkeys, opslimit=opslimit, memlimit=memlimit)
    lines = head + [f"owner {owner}"] + ([f"version v{version}"] if version else [])
    lines += [f"key {key.did}", f"digest {key.digest}", f"encryption {ENVELOPE}", *wraps, "seed " + _b64(data)]
    return "\n".join(lines) + "\n"


TEXT_FORMAT = "opensheaf-key-text/0.2"


def key_text(key, owner, kind=CURRENT, passphrase=None, *, opslimit=None, memlimit=None):
    """The text of the key KEY of OWNER, for a password manager, its seed encrypted under PASSPHRASE
    unless None."""
    encryption, data = encrypt_seed(key.seed, passphrase, opslimit=opslimit, memlimit=memlimit)
    groups = names.b32(data).upper()
    lines = [TEXT_FORMAT, f"kind {kind}", f"owner {owner}", f"key {key.did}"]
    if passphrase is not None:
        lines.append(f"encryption {encryption}")
    lines += ["seed " + " ".join(groups[i:i + 4] for i in range(0, len(groups), 4)),
              f"check {sheet_check(data)}"]
    return "\n".join(lines) + "\n"


class ReadKey:
    """A key read back, with what its file, sheet or text says about it."""

    def __init__(self, key, owner=None, version=None, kind=ROTATION):
        self.key, self.owner, self.version, self.kind = key, owner, version, kind


def read_key(source, passphrase=None, keks=None):
    """The key of a file, a sheet or a text (a path, or its text), checked against its fields; KEKS
    ({cred: key}) or PASSPHRASE open its seed if it is encrypted."""
    text = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) else source
    lines = text.splitlines()
    formats = (ROTATION_FORMAT, KEY_FORMAT, TEXT_FORMAT)
    start = next((i for i, line in enumerate(lines) if line.strip() in formats), None)
    fmt = lines[start].strip() if start is not None else None
    fields = {}
    for line in lines[start + 1 if start is not None else 0:]:
        name, _, value = line.strip().partition(" ")
        if name and name not in fields:
            fields[name] = value.strip()
    if fmt in (ROTATION_FORMAT, KEY_FORMAT):
        try:
            data = base64.b64decode(fields.get("seed", ""), validate=True)
        except (binascii.Error, ValueError):
            raise KeyStoreError("the seed of the file is not base64") from None
    else:
        try:
            data = names.b32decode(fields.get("seed", "").replace(" ", ""))
        except ValueError:
            data = b""
        if not data or fields.get("check", "").upper() != sheet_check(data):
            raise KeyStoreError("the seed does not match its check: a character is mistyped")
    if fields.get("encryption", "").split()[:1] == [ENVELOPE]:
        seed = open_envelope(wraps_of("\n".join(lines[start or 0:])), data, passphrase, keks)
    else:
        seed = decrypt_seed(fields.get("encryption", "none"), data, passphrase)
    if len(seed) != 32:
        raise KeyStoreError("not the seed of an Ed25519 key")
    key = Key(seed)
    if fields.get("key", key.did) != key.did or fields.get("digest", key.digest) != key.digest:
        raise KeyStoreError("the seed is not that of the key the file or sheet names")
    kind = fields.get("kind", ROTATION)
    if kind not in KINDS:
        raise KeyStoreError(f"unknown kind of key: {kind!r}")
    version = fields.get("version", "").split(" ")[0]
    return ReadKey(key, fields.get("owner"), int(version[1:]) if version[1:].isdigit() else None, kind)


def read_rotation_key(source, passphrase=None):
    """The rotation key of a file or a sheet (a path, or its text), checked against its fields."""
    rk = read_key(source, passphrase)
    if rk.kind != ROTATION:
        raise KeyStoreError(f"{rk.key.did} is a {rk.kind} key, not a rotation key")
    return rk
