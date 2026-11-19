# Generated from literate/07-keys.md by opensheaf-literate: edit the document, not this file.
"""Keys of owners (sections 6.2 and 15.4 of OpenSheaf 0.2): Ed25519 keys made
as RFC 8032 says; current keys kept in the system's credential store (or a
file of the user's configuration); rotation keys exported once, to files
outside the archive (encrypted under a passphrase) and to a printed sheet,
and read back; predictable keys for the tests only.

Current keys are found, in this order: the environment variable
OPENSHEAF_SIGNING_KEY (the base64 seed of one key, for continuous
integration); the credential store, through the package keyring, under
the service opensheaf-current-key and the account <owner>:<k>; on macOS
the keychain directly, under the same names; and the file
~/.config/opensheaf/keys/<owner>/<k>.key, readable only by its owner.
OPENSHEAF_KEY_STORE=keyring|security|file uses that store alone."""

import base64
import binascii
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


def _stores():
    pinned = os.environ.get(KEY_STORE)
    if pinned:
        if pinned not in STORES:
            raise KeyStoreError(f"{KEY_STORE} is one of {', '.join(STORES)}")
        return [pinned]
    return list(STORES)


def _account(owner, kid):
    return f"{owner}:{kid}"


def key_folder(owner):
    """The folder of the key files of OWNER in the user's configuration."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opensheaf" / "keys" / owner


def _read(store, owner, kid):
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
    return path.read_text(encoding="ascii").strip() if path.exists() else None


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
        for store in _stores():
            text = _read(store, owner, kid)
            if text:
                key = key_from_base64(text, f"{store} {_account(owner, kid)}")
                if key.did != did:
                    raise KeyStoreError(f"{store} {_account(owner, kid)} holds another key than {did}")
                found.append(key)
                break
    return found


def store_current_key(owner, key, store=None):
    """Keep the current key KEY of OWNER on this device; returns the name of the store used."""
    text = base64.b64encode(key.seed).decode("ascii")
    for s in ([store] if store else _stores()):
        if _write(s, owner, key.id, text) and _read(s, owner, key.id) == text:
            return s
    raise KeyStoreError(f"no store kept the key {key.did}")


def _write(store, owner, kid, text):
    account = _account(owner, kid)
    if store == "keyring":
        try:
            import keyring
            keyring.set_password(SERVICE, account, text)
            return True
        except Exception:
            return False
    if store == "security":
        if sys.platform != "darwin" or not shutil.which("security"):
            return False
        r = subprocess.run(["security", "-i"], input=f"add-generic-password -U -s {SERVICE} -a {account} -w {text}\n",
                           capture_output=True, text=True)
        return r.returncode == 0
    folder = key_folder(owner)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(folder / f"{kid}.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(text + "\n")
    print(f"warning: the key {kid} of {owner} is kept in {folder / f'{kid}.key'}, protected only by the "
          "permissions of your files; install the package keyring to keep it in your system's "
          "credential store", file=sys.stderr)
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


ROTATION_FORMAT = "opensheaf-rotation-key/0.2"
OPSLIMIT, MEMLIMIT = pwhash.argon2id.OPSLIMIT_MODERATE, pwhash.argon2id.MEMLIMIT_MODERATE


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


def rotation_key_text(key, owner, version, passphrase=None, *, opslimit=OPSLIMIT, memlimit=MEMLIMIT):
    """The text of the exported file of the rotation key KEY of OWNER, committed in VERSION."""
    lines = [ROTATION_FORMAT, f"owner {owner}", f"version v{version}", f"key {key.did}", f"digest {key.digest}"]
    if passphrase is None:
        lines += ["encryption none", "seed " + base64.b64encode(key.seed).decode("ascii")]
    else:
        salt = utils.random(pwhash.argon2id.SALTBYTES)
        box = secret.SecretBox(pwhash.argon2id.kdf(secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"),
                                                   salt, opslimit=opslimit, memlimit=memlimit))
        lines += [f"encryption argon2id-secretbox opslimit={opslimit} memlimit={memlimit} "
                  f"salt={base64.b64encode(salt).decode('ascii')}",
                  "seed " + base64.b64encode(box.encrypt(key.seed)).decode("ascii")]
    return "\n".join(lines) + "\n"


def export_rotation_keys(keys, owner, version, folder, *, passphrase=None, archive_root=None,
                         opslimit=OPSLIMIT, memlimit=MEMLIMIT):
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


class RotationKey:
    """A rotation key read back, with what its file or sheet says about it."""

    def __init__(self, key, owner=None, version=None):
        self.key, self.owner, self.version = key, owner, version


def read_rotation_key(source, passphrase=None):
    """The rotation key of a file or a sheet (a path, or its text), checked against its fields."""
    text = Path(source).read_text(encoding="utf-8") if isinstance(source, Path) else source
    fields = {}
    for line in text.splitlines():
        name, _, value = line.strip().partition(" ")
        if name and name not in fields:
            fields[name] = value.strip()
    if text.startswith(ROTATION_FORMAT):
        key = Key(_seed_of_file(fields, passphrase))
    else:
        groups = fields.get("seed", "").replace(" ", "")
        try:
            seed = names.b32decode(groups)
        except ValueError:
            seed = b""
        if len(seed) != 32 or fields.get("check", "").upper() != sheet_check(seed):
            raise KeyStoreError("the seed does not match its check: a character is mistyped")
        key = Key(seed)
    if fields.get("key", key.did) != key.did or fields.get("digest", key.digest) != key.digest:
        raise KeyStoreError("the seed is not that of the key the file or sheet names")
    version = fields.get("version", "").split(" ")[0]
    return RotationKey(key, fields.get("owner"), int(version[1:]) if version[1:].isdigit() else None)


def _seed_of_file(fields, passphrase):
    encryption = fields.get("encryption", "").split()
    try:
        data = base64.b64decode(fields.get("seed", ""), validate=True)
    except (binascii.Error, ValueError):
        raise KeyStoreError("the seed of the file is not base64") from None
    if encryption == ["none"]:
        return data
    if not encryption or encryption[0] != "argon2id-secretbox":
        raise KeyStoreError(f"unknown encryption: {' '.join(encryption)!r}")
    if passphrase is None:
        raise KeyStoreError("this rotation key is encrypted: a passphrase is needed")
    params = dict(p.partition("=")[::2] for p in encryption[1:])
    try:
        salt = base64.b64decode(params["salt"], validate=True)
        box = secret.SecretBox(pwhash.argon2id.kdf(secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"), salt,
                                                   opslimit=int(params["opslimit"]),
                                                   memlimit=int(params["memlimit"])))
        return box.decrypt(data)
    except (KeyError, ValueError, binascii.Error):
        raise KeyStoreError("the encryption of the file is damaged") from None
    except CryptoError:
        raise KeyStoreError("wrong passphrase, or a damaged file") from None
