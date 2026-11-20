Keys: making them, keeping them, exporting them
===============================================

An owner has two kinds of keys (section 6.2). *Current keys* are in daily
use: one on each device the owner signs from, made there and never copied
elsewhere; they sign the versions of the owner's lines. *Rotation keys*
are used once, to sign the next version of the key log, and are kept apart
from the devices and from each other: on hardware tokens, on paper, on a
USB key in a drawer. Both are Ed25519 keys. Neither may ever be stored in an
archive (section 15.4): whatever an archive holds is public and copied.

This chapter is the module `keys.py`. It makes keys, as RFC 8032 says;
keeps current keys in the system's credential store, or failing that in a
file of the user's configuration; exports rotation keys once, when they are
made, to files outside the archive, encrypted under a passphrase, and to a
sheet to print; writes keys as the encrypted files that a key wallet keeps
([key wallets](09-wallets.md)) and as a short text for a password manager;
reads them back when they are needed; and, for the tests only, makes
predictable keys.

    # in src/opensheaf/keys.py:
    <<keys: the docstring and the imports>>


    <<keys: a key>>


    <<keys: predictable keys for the tests>>


    <<keys: where current keys are kept>>


    <<keys: encrypting a seed>>


    <<keys: exporting rotation keys>>


    <<keys: the printed sheet>>


    <<keys: key files for wallets>>


    <<keys: a key as text, for a password manager>>


    <<keys: reading a key back>>

Ed25519 and the encryption of exported keys are those of libsodium, through
PyNaCl, a dependency of the package; the credential store is that of the
optional package keyring, as for the tokens of [Zenodo](50-zenodo.md).

    # in keys: the docstring and the imports:
    """Keys of owners (sections 6.2 and 15.4 of OpenSheaf 0.2): Ed25519 keys made
    as RFC 8032 says; current keys kept in the system's credential store (or a
    file of the user's configuration); rotation keys exported once, to files
    outside the archive (encrypted under a passphrase) and to a printed sheet,
    and read back; keys as the encrypted files of a key wallet and as a text for
    a password manager; predictable keys for the tests only.

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

A key
-----

A key is held as its *seed*, the 32 random bytes that RFC 8032 calls the
private key, from which the signing key and the public key are derived.
Everything the format needs follows from it: the `did:key` URI, the digest
committed in `next` (section 6.1), and the 16 characters that name its
signature files (section 7.2). The seed never appears in the representation
of the object, so that it cannot leak into a log or a traceback by
accident.

    # in keys: a key:
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

A new key takes its seed from libsodium's generator, the operating
system's secure one, as section 5.1.5 of RFC 8032 asks, unless the tests
ask for a predictable key (below).

    # in keys: a key:
    def new_key():
        """A new key, from a secure random seed (or, in the tests only, a predictable one)."""
        label = _next_test_label()
        if label is not None:
            return example_key(label)
        return Key(utils.random(32))

Predictable keys for the tests
------------------------------

The tests check the files the tools write against the examples of
appendix C, whose keys were made from known seeds: the SHA-256 digest of
`opensheaf appendix C example key ` followed by a label, such as
`authors laptop` or `authors rotation 1`. `example_key` makes such a key.
For the tests that run the command line, which makes its own keys, the
environment variable `OSHEAF_TEST_KEYS` lists labels, separated by commas,
which `new_key` uses in turn instead of random seeds.

Predictable keys are worthless as keys: anyone can make them. The hook is
therefore refused, with an error rather than a fallback, unless the process
is running under pytest, which sets `PYTEST_CURRENT_TEST` during each test;
a variable left set in a shell can never produce a real owner with
predictable keys. Labels that run out are an error too.

    # in keys: predictable keys for the tests:
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

Where current keys are kept
---------------------------

A current key is needed whenever the owner signs, so it is kept on the
device, in the safest place the device offers. The stores are tried in
order, as for the tokens of Zenodo:

1. **The environment variable** `OPENSHEAF_SIGNING_KEY`, holding the seed
   of one key in base64: for continuous integration, where the key is a
   secret of the repository (the archive template's workflow signs with a
   key of its own, exposed if the repository is compromised).
2. **The system's credential store**, through the Python package
   [keyring](https://pypi.org/project/keyring/): the keychain on macOS, the
   Credential Manager on Windows, the Secret Service on Linux. Keys are kept
   under the service `opensheaf-current-key` and the account
   `<owner>:<k>`, `<k>` naming the key as its signature files do.
3. **On macOS, the keychain directly**, through the `security` command,
   under the same names, when keyring is not installed.
4. **A file**, `~/.config/opensheaf/keys/<owner>/<k>.key` (or under
   `$XDG_CONFIG_HOME`), readable only by its user, with a warning when it
   is written: it protects the key only as far as the permissions of the
   user's files do.

The variable `OPENSHEAF_KEY_STORE` restricts the stores to one, for a user
who wants to know where the key is, and for the tests.

    # in keys: where current keys are kept:
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

Reading a seed from a store is a lookup by owner and key name: the caller
knows which keys it may use, the `keys` of the latest version of the key
log, and asks for each in turn. A store that is missing or refuses is
skipped. A seed is base64; one whose key is not the one it is filed under
is an error, never used.

    # in keys: where current keys are kept:
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

The current keys of an owner on this device are those found among its
current keys; with the environment variable, the one key it holds, which
must be one of them.

    # in keys: where current keys are kept:
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

Storing a key tries the stores in the same order, and checks that the key
can be read back, since a store may accept and forget (keyring has a
backend that does nothing). With `security`, the seed is passed on the
standard input of `security -i` rather than on its command line, where
other users of the machine could see it. The file is created with mode
0600, inside a folder of mode 0700, and never replaces another.

    # in keys: where current keys are kept:
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

A retired key is no longer needed; `forget_current_key` removes it from
every store.

    # in keys: where current keys are kept:
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

Encrypting a seed
-----------------

Whatever keeps a key outside the device's credential store, an exported
file, a key wallet, a password manager, keeps its seed encrypted under a
passphrase, unless the user chooses otherwise: Argon2id derives a key from
the passphrase and a random salt, and libsodium's SecretBox (XSalsa20 and
Poly1305) encrypts the seed, with a random nonce, and authenticates it, so
that a wrong passphrase or a damaged text is found at once. The
`encryption` field names the method and records the cost of Argon2id and
the salt, so that the tests can use the cheapest cost and users the
default, libsodium's "moderate" (the module's `OPSLIMIT` and `MEMLIMIT`,
read when a seed is encrypted, so that the tests can lower them); `none`
means a seed kept as it is.

    # in keys: encrypting a seed:
    OPSLIMIT, MEMLIMIT = pwhash.argon2id.OPSLIMIT_MODERATE, pwhash.argon2id.MEMLIMIT_MODERATE


    class PassphraseNeeded(KeyStoreError):
        """A key encrypted under a passphrase, read without one."""


    def encrypt_seed(seed, passphrase, *, opslimit=None, memlimit=None):
        """(the encryption field, the bytes kept): SEED encrypted under PASSPHRASE, or as it is if None."""
        if passphrase is None:
            return "none", seed
        opslimit = OPSLIMIT if opslimit is None else opslimit
        memlimit = MEMLIMIT if memlimit is None else memlimit
        salt = utils.random(pwhash.argon2id.SALTBYTES)
        box = secret.SecretBox(pwhash.argon2id.kdf(secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"), salt,
                                                   opslimit=opslimit, memlimit=memlimit))
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
            box = secret.SecretBox(pwhash.argon2id.kdf(secret.SecretBox.KEY_SIZE, passphrase.encode("utf-8"), salt,
                                                       opslimit=int(params["opslimit"]),
                                                       memlimit=int(params["memlimit"])))
            return box.decrypt(data)
        except (KeyError, ValueError, binascii.Error):
            raise KeyStoreError("the encryption of the key is damaged") from None
        except CryptoError:
            raise KeyStoreError("wrong passphrase, or a damaged key") from None

Exporting rotation keys
-----------------------

Rotation keys are made when a version of the key log commits them, and are
never stored on the device: they are exported at once, and the device
forgets them. Each goes to a file of its own, `rotation-<owner16>-<k>.txt`,
`<owner16>` being the first 16 characters of the owner name, in a folder
the user chooses (a USB key, for instance), so that the files of several
owners and keys can sit side by side and be told apart. A folder inside an
archive is refused, whether given or found by looking for `osheaf.json`
above it: an archive is public (section 15.4).

The file is plain text, one field per line: the format, the owner, the
key-log version whose `next` commits the key, the `did:key` and its digest,
so that the file says what it is without being decrypted; then the
encryption and the seed. Unless the user chooses otherwise, the seed is
encrypted under a passphrase, as the section above says.

```
opensheaf-rotation-key/0.2
owner 56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa
version v1
key did:key:z6Mkh5i2epG9LsWNnYbBHG7ctEiNLZPjsBNXxNUcsaYgEtNm
digest oxthfb6b4q3sqathmcpnciqggfxlr3aekgfg2tpm2lgrm2qnalha
encryption argon2id-secretbox opslimit=3 memlimit=268435456 salt=...
seed ...
```

    # in keys: exporting rotation keys:
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

Exporting writes one file per key, readable only by its user, never over
another file. It returns the paths written, so that the command can show
them and ask the user to confirm, before the version that commits the keys
is written, that they are where the user wants them.

    # in keys: exporting rotation keys:
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

The printed sheet
-----------------

Paper outlives devices and file formats. The sheet of a rotation key shows
the same fields as its file, and the seed in base32, in capitals, in groups
of four characters that can be read aloud and typed back, followed by a
check of four characters, the start of a digest of the seed, which catches
a mistyped character with near certainty. The sheet is not encrypted: it is
meant to be kept where only its owner can reach it, and says so. The
command line asks the user to type the check back once the sheet is
printed, before the version that commits the key is written.

    # in keys: the printed sheet:
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

Key files for wallets
---------------------

A key wallet ([chapter 9](09-wallets.md)) keeps the keys of owners, current
keys and rotation keys, one file each, `<owner>/<k>.key.enc`. The file is
that of an exported rotation key, with another format name and one more
field, `kind`, `current` or `rotation`, so that a key read back from a
wallet cannot be used as the other kind. The `version` is that of the key
log which commits the key (in `keys` for a current key, in `next` for a
rotation key), when it is known: a current key made with `osheaf key new`
is pushed before any version lists it.

```
opensheaf-key/0.2
kind current
owner 56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa
version v1
key did:key:z6Mkh5i2epG9LsWNnYbBHG7ctEiNLZPjsBNXxNUcsaYgEtNm
digest oxthfb6b4q3sqathmcpnciqggfxlr3aekgfg2tpm2lgrm2qnalha
encryption argon2id-secretbox opslimit=3 memlimit=268435456 salt=...
seed ...
```

    # in keys: key files for wallets:
    KEY_FORMAT = "opensheaf-key/0.2"
    CURRENT, ROTATION = "current", "rotation"
    KINDS = (CURRENT, ROTATION)


    def key_file_text(key, owner, kind, version=None, passphrase=None, *, opslimit=None, memlimit=None):
        """The text of the wallet file of the key KEY of OWNER, of KIND, committed in VERSION (or None)."""
        if kind not in KINDS:
            raise KeyStoreError(f"a key is {' or '.join(KINDS)}")
        return _file_text([KEY_FORMAT, f"kind {kind}"], key, owner, version, passphrase, opslimit, memlimit)

A key as text, for a password manager
-------------------------------------

A password manager such as the Passwords app of macOS keeps passwords and
notes, synchronised between the user's devices; a command-line tool cannot
write its items (those of the iCloud keychain), but the user can paste a
text into a note and copy it back. `key_text` is that text: the format, the
kind of key, the owner, the `did:key`, and the seed in base32 capitals in
groups of four, with the check of the printed sheet, so that it can also be
typed back by hand. Encrypted under a passphrase, the groups are those of
the encrypted seed, and the text has an `encryption` field; the check is
then of the encrypted bytes, and catches a damaged copy before the
passphrase is asked for.

```
opensheaf-key-text/0.2
kind current
owner 56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa
key did:key:z6Mkh5i2epG9LsWNnYbBHG7ctEiNLZPjsBNXxNUcsaYgEtNm
seed ABCD EFGH ...
check WXYZ
```

    # in keys: a key as text, for a password manager:
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

Reading a key back
------------------

A key is read back from any of these texts: an exported file of a rotation
key, a file of a wallet, a printed sheet typed back (only the lines `seed`
and `check` are needed then), or the text of a password manager, which may
come with other lines around it, pasted from a note: reading starts at its
format line. Either way the key is rebuilt from the seed and compared with
the fields that come with it, so that a wrong passphrase, a damaged file or
a mistyped seed is found here, not by a verifier later. A key without a
`kind` field is a rotation key: the exported files and the sheets hold
rotation keys only.

    # in keys: reading a key back:
    class ReadKey:
        """A key read back, with what its file, sheet or text says about it."""

        def __init__(self, key, owner=None, version=None, kind=ROTATION):
            self.key, self.owner, self.version, self.kind = key, owner, version, kind


    def read_key(source, passphrase=None):
        """The key of a file, a sheet or a text (a path, or its text), checked against its fields."""
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

A rotation key is read back to sign the next version of the key log;
`read_rotation_key` refuses a current key, which never signs one.

    # in keys: reading a key back:
    def read_rotation_key(source, passphrase=None):
        """The rotation key of a file or a sheet (a path, or its text), checked against its fields."""
        rk = read_key(source, passphrase)
        if rk.kind != ROTATION:
            raise KeyStoreError(f"{rk.key.did} is a {rk.kind} key, not a rotation key")
        return rk
