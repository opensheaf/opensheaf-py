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
([key wallets](09-wallets.md)), which passkeys can also unlock, and as a short text for a password manager;
reads them back when they are needed; and, for the tests only, makes
predictable keys.

    # in src/opensheaf/keys.py:
    <<keys: the docstring and the imports>>


    <<keys: a key>>


    <<keys: predictable keys for the tests>>


    <<keys: where current keys are kept>>


    <<keys: encrypting a seed>>


    <<keys: a seed unlocked in several ways>>


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

`OPENSHEAF_KEY_STORE=none` keeps no current key on the computer at all:
a key lives in the memory of the command that needs it, and nowhere else.
When a command signs, it opens the current key from the owner's key wallet
([key wallets](09-wallets.md)), with the passkey (one Touch ID, through the
browser) or the passphrase, signs, and forgets it when it ends; the next
command that signs asks again. It suits a computer where osheaf runs from
ever new Python environments, as `uvx` makes them while developing: the
keychain then never asks for its permission, at the price of one Touch ID
per command that signs. Without a wallet, nothing can sign; `osheaf key
new` and `osheaf key import`, which would make or bring a key only to lose
it, refuse.

    # in keys: where current keys are kept:
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
is an error, never used. A key file that is a symbolic link, or that other
users may read or write (any permission beyond 0600), is refused, with a
message, rather than read: a link could make the tools read a key from
elsewhere, and loose permissions mean the key may have leaked.

Each item of a store is read at most once in a command. On macOS, every
read of a keychain item by a program that the item does not list asks the
user's permission ("python3 wants to use your confidential information
stored in opensheaf-current-key"), unless the user has answered *Always
Allow*; a command that asked twice for the same key, once to see whether
the computer holds it and once to sign, would ask twice. What a command
has read, a seed or the absence of one, is therefore remembered in its
memory, `_SEEN`, by store, owner and key (and, for files, by folder);
writing and forgetting a key update it, and the memory is cleared at the
start and the end of every command (`forget_seen`, called with
`forget_passphrase` of [the owner commands](19-owner-commands.md)). The
keys held in memory only, with `OPENSHEAF_KEY_STORE=none`, are kept there
too, under the store `none`, which no read ever reaches.

    # in keys: where current keys are kept:
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

The current keys of an owner on this device are those found among its
current keys, in the stores and in memory; with the environment variable,
the one key it holds, which must be one of them.

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
            for store in _stores() + [NONE]:
                text = _lookup(store, owner, kid)
                if text:
                    key = key_from_base64(text, f"{store} {_account(owner, kid)}")
                    if key.did != did:
                        raise KeyStoreError(f"{store} {_account(owner, kid)} holds another key than {did}")
                    found.append(key)
                    break
        return found

Storing a key tries the stores in the same order (with
`OPENSHEAF_KEY_STORE=none`, memory alone), and remembers what it wrote, so
that the command does not read it again. A store may accept and forget:
keyring has a backend that does nothing, chosen only by a user who asks for
it, which is taken for a store that refuses. With `security`, the seed is
passed on the standard input of `security -i` rather than on its command
line, where other users of the machine could see it, and read back with
`find-generic-password -w`: a key is reported kept only once the keychain
gives the same seed back. The file is created with mode 0600, inside a
folder of mode 0700, and never replaces another, nor follows a link.

    # in keys: where current keys are kept:
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
        print(f"warning: the key {kid} of {owner} is kept in {folder / f'{kid}.key'}, protected only by the "
              "permissions of your files; install the package keyring to keep it in your system's "
              "credential store", file=sys.stderr)
        return True

On macOS, an item that keyring writes to the keychain trusts one program
without asking: the one that wrote it, the very Python binary of the
environment that ran osheaf. Another Python, such as the one of a new `uvx`
environment, is asked for, once per read, until the user answers *Always
Allow*, which adds that Python to the item. An item that the `security`
command writes trusts, in the same way, the `security` command, the same
program of the system whatever Python runs osheaf; with
`OPENSHEAF_KEY_STORE=security`, *Always Allow* is answered once for all.
osheaf adds no other program itself: `-A` would let every program of the
user read the key without asking, and a list of programs given with `-T`
would name the Python binaries of environments that come and go.

Plainly: the keychain protects a current key from other users of the
computer and from a copy of the disk, not from programs that run as you.
Once *Always Allow* is answered for `security` (or for a Python), any
program running as you can run `security find-generic-password -w` (or
that Python) and read the key, without a question; against malware
running as you, the keychain is no better than the file store. What
protects the owner then is that a current key can be retired, and an
exposed one declared, with the rotation keys, which are kept elsewhere
(section 6.2).

Hence the advice for running osheaf with `uvx` without installing it: name
the Python, so that uv runs the same interpreter of its own every time
(the environments of `uvx` link to it), and answer *Always Allow* once:

```sh
uvx --python 3.13 --from "opensheaf[validate,keys] @ git+https://github.com/opensheaf/opensheaf-py" osheaf ...
```

with `--refresh` to update osheaf. Without `--python`, uvx may pick another
Python from one day to the next, and each one is asked anew; when uv
updates its Python 3.13, the new one is asked once. Who prefers never to
be asked keeps no key on the computer: `OPENSHEAF_KEY_STORE=none`, above.

A retired key is no longer needed; `forget_current_key` removes it from
every store, and from the memory of the command.

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
            _SEEN[_slot(store, owner, kid)] = None
        _SEEN.pop(_slot(NONE, owner, kid), None)

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

The cost recorded in a file is read from the file, which may come from
anywhere: a wallet, a clipboard, a USB key. A file that asks for more than
libsodium's "sensitive" cost (4 passes, 1 GiB), or less than its minimum,
is refused before Argon2id runs, so that a crafted file cannot make the
command run for hours or exhaust the memory; and a machine that cannot
give the memory asked for is told so, as an error of the key, not a crash.

    # in keys: encrypting a seed:
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

A seed unlocked in several ways
------------------------------

A key kept in a wallet is read back on every device that pulls it, and
typing a long passphrase on each is the price of the wallet's security.
A *passkey* (WebAuthn, the sign-in of the browser and of the operating
system, synchronised by iCloud Keychain or another provider) can stand in
for the passphrase, with Touch ID or another check of the user, through
its PRF extension, which derives a stable 32-byte secret from the passkey
and a salt, never leaving the authenticator otherwise. The way from the
command line to a passkey is a page in the browser, at
`https://unlock.opensheaf.org/` ([chapter 9](09-wallets.md)), an origin
that serves that page alone.

So that one key can be opened by the passphrase and by one passkey or
more, its file holds the seed encrypted by *envelope encryption*: the seed
is encrypted (SecretBox, as above) under a random 32-byte *data key*, and
the data key is *wrapped*, encrypted again, once per way of unlocking,
each on a line of its own, under a key-encryption key:

- `wrap passphrase argon2id opslimit=N memlimit=N salt=S BOX`: the
  key-encryption key is derived from the passphrase by Argon2id, as above;
- `wrap passkey prf rp=unlock.opensheaf.org cred=C salt=S BOX`: the passkey of
  the relying party `rp`, whose credential identifier is `C` (base64url),
  gives the PRF secret for the salt `S` (base64); the key-encryption key
  is HKDF-SHA256 of that secret (RFC 5869, no salt, info `opensheaf wallet
  passkey v1`, 32 bytes).

`BOX` is the data key in a SecretBox (its nonce first), in base64. The
field `encryption` is `envelope-secretbox`, followed by the `wrap` lines,
then the `seed`. A file always keeps its passphrase wrap: the passkey is a
convenience, and the passphrase the way back when a browser or a passkey
is missing. The PRF salt is the same for every key of an owner, the
SHA-256 digest of `opensheaf wallet unlock v1 ` followed by the owner
name, so that one check of the user unlocks all of them.

The relying party is `unlock.opensheaf.org` (`PASSKEY_RP`), whose origin
serves nothing but the unlock page, so that no other page of the project's
sites, present or future, can ask a passkey for these secrets. The first
passkeys were made for `opensheaf.org` itself (`OLD_PASSKEY_RP`), from a
page of the Manager; their wraps are still read, and still open with the
passphrase, but the command line no longer asks the browser for them: the
owner enrolls a passkey of the new relying party (`osheaf key enroll
--new-passkey`), then removes the old wraps (`osheaf key forget --rp
opensheaf.org`). The salt and the derivation of the key-encryption key are
the same for both.

    # in keys: a seed unlocked in several ways:
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

A passkey of an owner is its credential identifier and its salt, and, once
the user has unlocked it in this command, its key-encryption key, held in
memory only: the PRF secret and the key derived from it are never stored.
A passkey read from a file also carries the box of its wrap, so that a
key-encryption key that the browser sends can be checked against it before
it is trusted (`opens`).

    # in keys: a seed unlocked in several ways:
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

The data key is wrapped under the passphrase as the seed was before,
Argon2id with a fresh salt.

    # in keys: a seed unlocked in several ways:
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

Reading a wrap line gives its method, its parameters and its box; the
passkeys of a file are those of its `passkey` lines, which tell the
command line what to ask the browser for.

    # in keys: a seed unlocked in several ways:
    def parse_wrap(line):
        """{method, kind, box, and the parameters} of a wrap line."""
        parts = line.split()
        if len(parts) < 4 or parts[0] != "wrap":
            raise KeyStoreError(f"not a wrap line: {line!r}")
        out = dict(p.partition("=")[::2] for p in parts[3:-1])
        try:
            out.update(method=parts[1], kind=parts[2], box=base64.b64decode(parts[-1], validate=True))
            if "salt" in out:
                out["salt"] = base64.b64decode(out["salt"], validate=True)
        except (binascii.Error, ValueError):
            raise KeyStoreError("a wrap of the key is damaged") from None
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

Opening the envelope unwraps the data key with a passkey whose
key-encryption key is known (`keks`, by credential), or else with the
passphrase; without either, it says which passkeys could unlock it, so
that the caller can ask the browser for one, or the passphrase.

    # in keys: a seed unlocked in several ways:
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

A passkey is added to a key file already written, by `osheaf key enroll`:
the data key, unwrapped with the passphrase, is wrapped once more, and
the line added after the other wraps; the seed and the other wraps stay as
they are. A file written before envelopes, its seed encrypted directly
under the passphrase (`encryption argon2id-secretbox`), is read as before,
and rewritten as an envelope when a passkey is added to it.

    # in keys: a seed unlocked in several ways:
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

The wraps of a passkey that is lost, or of a relying party no longer
asked (`OLD_PASSKEY_RP`), are removed by `osheaf key forget --passkey` or
`--rp`: the lines of the passkey wraps that match go, and nothing else,
the passphrase wrap above all, so that the file opens as before.

    # in keys: a seed unlocked in several ways:
    def remove_passkeys(text, cred=None, rp=None):
        """The key file TEXT without the passkey wraps of the credential CRED, or of the relying party RP."""
        def gone(line):
            if not line.startswith("wrap passkey "):
                return False
            w = parse_wrap(line)
            return (cred is None or w.get("cred") == cred) and (rp is None or w.get("rp", PASSKEY_RP) == rp)
        if cred is None and rp is None:
            raise KeyStoreError("name the passkey wraps to remove, by credential or relying party")
        lines = text.splitlines()
        kept = [x for x in lines if not gone(x.strip())]
        if not any(x.strip().startswith("wrap passphrase ") for x in kept):
            raise KeyStoreError("the key would have no passphrase wrap left")
        return "\n".join(kept) + "\n"

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
is pushed before any version lists it. Encrypted, the seed is in an
envelope (above): a passphrase wrap always, and a passkey wrap for each
passkey given, unlocked, or added later by `osheaf key enroll`; files
written before envelopes, with one `encryption argon2id-secretbox`, are
still read. Unencrypted (`--plain-current`), it is `encryption none`.

```
opensheaf-key/0.2
kind current
owner 56wo6cdpjsxk7ddgnqfp2quipfghukhtmvjuahvwzko7m4tkz3pa
version v1
key did:key:z6Mkh5i2epG9LsWNnYbBHG7ctEiNLZPjsBNXxNUcsaYgEtNm
digest oxthfb6b4q3sqathmcpnciqggfxlr3aekgfg2tpm2lgrm2qnalha
encryption envelope-secretbox
wrap passphrase argon2id opslimit=3 memlimit=268435456 salt=... ...
wrap passkey prf rp=unlock.opensheaf.org cred=... salt=... ...
seed ...
```

    # in keys: key files for wallets:
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
rotation keys only. A seed in an envelope is opened with the
key-encryption keys of passkeys unlocked (`keks`, by credential), or with
the passphrase.

    # in keys: reading a key back:
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

A rotation key is read back to sign the next version of the key log;
`read_rotation_key` refuses a current key, which never signs one.

    # in keys: reading a key back:
    def read_rotation_key(source, passphrase=None):
        """The rotation key of a file or a sheet (a path, or its text), checked against its fields."""
        rk = read_key(source, passphrase)
        if rk.kind != ROTATION:
            raise KeyStoreError(f"{rk.key.did} is a {rk.kind} key, not a rotation key")
        return rk
