The commands of owners and their keys
=====================================

The last part of `core.py` is the commands that make an owner and keep its
key log: `osheaf owner init`, `owner rotate`, `owner expose`, `owner end`,
`owner show`, and `osheaf key new`. They join the modules of identity,
[owners](06-owners.md) and [keys](07-keys.md), to the archive: the key log
of an owner is the owner object `sheaf:<owner>:<owner>` of the storage
root, written append-only by `owners.write_key_log`, and the keys are kept
where [chapter 7](07-keys.md) says, never in the archive (section 15.4).

Every line needs its owner's key log beside it, in the same storage root
(section 6.5). In one archive the owner object serves every line of that
owner: the owner-name layout puts it at `<owner>/<owner>/`, next to them,
and a new version of the key log, written there, is at once beside every
line. An owner that also writes in other archives copies its owner object
there, and brings each copy up to date from another with `osheaf owner
pull`, which meets two copies of a key log as section 6.3 says
([copies](22-mirrors.md)). The keys go where the owner's *security level* says: offline, the
default and the maximum, or in a key wallet, kept by the module of
[chapter 9](09-wallets.md); `osheaf key push`, `pull`, `list`, `export`,
`import` and `forget` move them between this device, a wallet and a
password manager, and `osheaf key enroll` and `unlock` open those of a
wallet with a passkey. The last command of this chapter, `osheaf sign`, signs a
version of a line again after an exposure.

    # in the commands of owners and their keys:
    <<the owner a command is about>>


    <<a passphrase, asked or from the environment>>


    <<the security level and the wallet of a command>>


    <<export rotation keys and confirm that they are kept>>


    <<keep keys in a wallet>>


    <<read the rotation keys that sign a version of the key log>>


    <<create an owner>>


    <<change the keys of an owner>>


    <<end an owner>>


    <<show an owner>>


    <<a new current key for this device>>


    <<the commands of key wallets>>


    <<unlock the keys of a wallet with a passkey>>


    <<a key to and from a password manager>>


    <<forget a key>>


    <<sign again a version contested by an exposed key>>

The owner a command is about is the archive's, unless `--owner` names
another owner it hosts. Its key log must be in the storage root.

    # in the owner a command is about:
    def owner_of(args):
        """The owner name a command is about, and its key log in the storage root."""
        if ROOT is None:
            sys.exit("no archive here (no osheaf.json in this folder or above it): give --root")
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        log = key_log(owner)
        if log is None:
            sys.exit(f"the key log of {owner} is not in the storage root")
        return owner, log


    def depositor():
        return {"name": ARCHIVE["depositor"]["name"], "address": ARCHIVE["depositor"]["address"]}

Making an owner
---------------

An owner is made as section 6.2 says. One current key is made on this
device, and kept here; `--key did:key...` adds the current keys of other
devices, made there with `osheaf key new`, for an owner whose `threshold`
needs several (a group, section 6.2). The rotation keys are made at once,
three by default with a `nextThreshold` of 2, which survive the loss of one
or the theft of one (section 6.2); `--rotation N` and `--next-threshold M`
choose others, and `--single-rotation-key` the minimal setup, one key with
a `nextThreshold` of 1, whose risk the tool states, as section 6.2 requires.
A keeper, an ORCID iD or a domain, may be named (section 6.6).

At the security level `offline`, the default, the rotation keys are never
kept on the device: they are exported, before anything is written, to a
folder outside the archive (`--export DIR`, a USB key for instance), one
file each, encrypted under a passphrase unless `--no-passphrase`, and
printed as sheets with `--print`. The owner then confirms, by typing the
check of each key, that the files and sheets are kept; only then is the key
log written. A key log whose rotation keys were lost before they were put
away would be an owner that can never change its keys (section 6.2). At a
wallet level (`--keys github:OWNER/REPO` or `--keys command`,
[chapter 9](09-wallets.md)) the rotation keys and the current key are kept
in the wallet instead, encrypted under the passphrase (the current key in
clear with `--plain-current`), and read back from it before the key log is
written; the risk is stated; `--export` may be given too, for an offline
copy of the rotation keys.

The genesis record gives the owner name, the name of algorithm 0 of the
record (section 6.2); if it is taken in the archive, a new nonce is drawn
(section 5.3). The first version of the key log is computed from the
genesis record (section 6.1) and written into the storage root; the
current key is kept in the system's credential store, under the owner name.
With `OPENSHEAF_KEY_STORE=none` ([chapter 7](07-keys.md)) it is kept in the
wallet only, and an owner without a wallet is refused: its current key
would be lost when the command ends.

    # in create an owner:
    def owner_init(args):
        """Make an owner (section 6.2): its current key on this device, its rotation keys,
        exported outside the archive, and the first version of its key log, in the storage root."""
        single = bool(getattr(args, "single_rotation_key", False))
        n_rot = 1 if single else int(getattr(args, "rotation", None) or 3)
        next_threshold = 1 if single else int(getattr(args, "next_threshold", None) or n_rot // 2 + 1)
        others = list(getattr(args, "key", None) or [])
        threshold = int(getattr(args, "threshold", None) or 1)
        if not 1 <= next_threshold <= n_rot or not 1 <= threshold <= 1 + len(others):
            sys.exit("a threshold is at least 1, and at most the number of keys (section 6.1, rule 1)")
        keeper = getattr(args, "keeper", None)
        if keeper and not names.keeper_valid(keeper):
            sys.exit(f"a keeper is an ORCID iD (with its check digit) or https://<domain>/: {keeper}")
        w = level_wallet(args)
        if w is None and not getattr(args, "export", None):
            sys.exit("give --export DIR, a folder outside the archive where the rotation keys are written "
                     "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
        if w is not None and getattr(args, "no_passphrase", False):
            sys.exit("--no-passphrase: the keys in a wallet are always encrypted")
        if w is None and not keys.kept_on_device():
            sys.exit(f"{keys.KEY_STORE}=none keeps no current key on this computer: keep the keys in a "
                     "wallet (--keys github:OWNER/REPO|command)")
        for did in others:
            try:
                names.did_key_public(did)
            except ValueError:
                sys.exit(f"not a did:key URI of an Ed25519 key: {did}")
        current = keys.new_key()
        rotation = [keys.new_key() for _ in range(n_rot)]
        while True:
            try:
                log = owners.new_owner([current] + others, rotation, threshold=threshold,
                                       next_threshold=next_threshold, keeper=keeper)
            except (ValueError, owners.OwnerError) as e:
                sys.exit(str(e))
            if not obj_dir(log.id).exists():
                break
        if next_threshold == 1:
            print("warning: " + owners.SINGLE_ROTATION_RISK, file=sys.stderr)
        if getattr(args, "export", None):
            export_and_confirm(rotation, log.owner, 1, args)
        if w is not None:
            keep_in_wallet(w, log.owner, rotation, 1, args, current=[(current, 1)])
        try:
            store = keys.store_current_key(log.owner, current)
        except (keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        owners.write_key_log(obj_dir(log.id), log)
        print(f"owner {log.owner}")
        kept = f"{w.name} only, {keys.KEY_STORE}=none" if store == keys.NONE else store
        print(f"current key of this device {current.did} (kept in {kept})")
        print("warning: " + owners.ROTATION_KEYS_WARNING, file=sys.stderr)
        return log

`osheaf owner init` makes an owner in an existing archive, which then hosts
it: its owner name joins `owners` in the configuration, and the discovery
document lists it. A GitHub wallet chosen for it becomes the wallet of the
archive, if it has none (`wallet_config`), so that later commands find the
keys there.

    # in create an owner:
    def owner_init_command(args):
        log = owner_init(args)
        cfg_path = ROOT / CONFIG_NAME
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            changed = False
            if log.owner not in [cfg.get("owner")] + cfg.get("owners", []):
                cfg["owners"] = cfg.get("owners", []) + [log.owner]
                ARCHIVE.setdefault("owners", []).append(log.owner)
                changed = True
            if wallet_config(args) and "keys" not in cfg:
                cfg["keys"] = ARCHIVE["keys"] = wallet_config(args)
                changed = True
            if changed:
                cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        write_discovery()


    def wallet_config(args):
        """The `keys` of osheaf.json naming the GitHub wallet of --keys, or None."""
        spec = getattr(args, "keys", None) or ""
        return {"wallet": spec} if spec.startswith("github:") else None

A passphrase is asked twice, without echo, or taken from the environment
variable `OPENSHEAF_PASSPHRASE`, for scripts, or printed by the command of
`OPENSHEAF_PASSPHRASE_COMMAND`, run by the shell, whose standard output,
stripped, is the passphrase: `security find-generic-password -w -s
opensheaf-passphrase` reads it from the macOS keychain, `op read
op://Private/opensheaf/password` from 1Password. A command that fails or
prints nothing is said so, and the passphrase is asked. An empty
passphrase is refused: an owner who wants plain files says so, with
`--no-passphrase`.
It is asked once per command, however many keys it encrypts or decrypts,
naming the wallet whose keys it opens, if any:
a rotation that reads the rotation keys from a wallet and keeps new ones
there asks once. The command line forgets it when the command ends
(`forget_passphrase`), together with what the command has read from the
stores of current keys ([chapter 7](07-keys.md)). A good place for it is a password manager, such as
the Passwords app of macOS: a different provider from the wallet, so that
neither alone gives the keys.

    # in a passphrase, asked or from the environment:
    PASSPHRASE = "OPENSHEAF_PASSPHRASE"
    PASSPHRASE_COMMAND = "OPENSHEAF_PASSPHRASE_COMMAND"
    _ASKED = {}


    def passphrase(confirm=True, where=None):
        """The passphrase of the keys (of the wallet WHERE, if given), asked once per command."""
        if os.environ.get(PASSPHRASE):
            return os.environ[PASSPHRASE]
        if "passphrase" in _ASKED:
            return _ASKED["passphrase"]
        command = os.environ.get(PASSPHRASE_COMMAND, "").strip()
        if command:
            r = subprocess.run(command, shell=True, capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                _ASKED["passphrase"] = r.stdout.strip()
                return _ASKED["passphrase"]
            print(f"warning: {PASSPHRASE_COMMAND} gave no passphrase: {r.stderr.strip()}", file=sys.stderr)
        import getpass
        first = getpass.getpass(f"Passphrase of the keys in {where}: " if where else "Passphrase of the keys: ")
        if not first:
            sys.exit("an empty passphrase: give --no-passphrase to export the keys unencrypted")
        if confirm and getpass.getpass("The passphrase again: ") != first:
            sys.exit("the two passphrases differ")
        _ASKED["passphrase"] = first
        return first


    def forget_passphrase():
        _ASKED.clear()
        keys.forget_seen()

### The security level and the wallet

A command that makes keys keeps them at the security level of `--keys`:
`offline` (the default) gives no wallet, `github:OWNER/REPO` the GitHub
wallet, `command` the command wallet configured in `osheaf.json` or in
`OPENSHEAF_WALLET` ([chapter 9](09-wallets.md)). A command that reads
keys from a wallet, or moves them, uses the wallet of `--keys`, or else the
one configured. Either way, the repositories of the archive are given to
the wallet, which refuses them.

    # in the security level and the wallet of a command:
    def archive_repositories():
        from . import wallet
        return wallet.archive_repositories(ROOT, ARCHIVE.get("baseUrl"))


    def configured_wallet():
        """The wallet configured for the archive (OPENSHEAF_WALLET, or "keys" of osheaf.json), or None."""
        from . import wallet
        try:
            return wallet.configured(ARCHIVE.get("keys"), forbidden=archive_repositories())
        except wallet.WalletError as e:
            sys.exit(str(e))


    def level_wallet(args):
        """The wallet of the security level --keys, or None for offline (the default)."""
        from . import wallet
        spec = getattr(args, "keys", None) or wallet.OFFLINE
        try:
            if spec == "command":
                w = configured_wallet()
                return w if isinstance(w, wallet.CommandWallet) else wallet.parse(spec, ARCHIVE.get("keys"))
            return wallet.parse(spec, forbidden=archive_repositories())
        except wallet.WalletError as e:
            sys.exit(str(e))


    def wallet_for(args):
        """The wallet a command reads or moves keys with: that of --keys, or the configured one."""
        w = level_wallet(args) or configured_wallet()
        if w is None:
            sys.exit("no key wallet: give --keys github:OWNER/REPO (or command), or configure one in "
                     'osheaf.json ("keys": {"wallet": ...}) or in OPENSHEAF_WALLET')
        return w

### Exporting and confirming

The files are written by `keys.export_rotation_keys`, which refuses a
folder inside the archive (section 15.4), and each is read back at once,
with the passphrase, so that a file that cannot be decrypted is found now,
not when the key is needed. For each key the tool prints the file and the
four characters that check its seed (the check of its printed sheet). The
owner confirms by typing these checks back, after putting the files or
sheets away; `--yes` skips the question, for scripts. A refusal writes
nothing to the key log: the files exported are those of keys never
committed, and can be deleted.

    # in export rotation keys and confirm that they are kept:
    def export_and_confirm(rotation, owner, version, args):
        """Export the rotation keys ROTATION of OWNER, committed in VERSION, and have the
        owner confirm that they are kept; stops if not."""
        secret = None if getattr(args, "no_passphrase", False) else passphrase()
        try:
            paths = keys.export_rotation_keys(rotation, owner, version, args.export, passphrase=secret,
                                              archive_root=ROOT)
            for key, path in zip(rotation, paths):
                if keys.read_rotation_key(path, secret).key.did != key.did:
                    raise keys.KeyStoreError(f"{path} does not read back")
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        for key, path in zip(rotation, paths):
            print(f"rotation key {key.did}\n  file  {path}\n  check {keys.sheet_check(key.seed)}")
            if getattr(args, "print", False):
                print(keys.rotation_key_sheet(key, owner, version))
        if getattr(args, "yes", False):
            return
        print("Put the files (or the printed sheets) away, apart from this device and from each other.")
        for key, path in zip(rotation, paths):
            typed = input(f"type the check of {path.name} to confirm it is kept: ").strip().upper()
            if typed != keys.sheet_check(key.seed):
                sys.exit("not confirmed: nothing was written to the key log (the files exported may be deleted)")

### Keeping keys in a wallet

At a wallet level, the rotation keys committed by a version, and the
current keys of this device that the version lists and the wallet does not
hold yet, are put into the wallet, each read back at once, before the
version is written. The risk is stated first, on the standard error, and
then the passphrase is asked (once, if an export asked it already). Each
write to a GitHub wallet is a request, which takes a moment: the command
says what it saves, and each key as it is saved.

    # in keep keys in a wallet:
    def keep_in_wallet(w, owner, rotation, version, args, current=()):
        """Keep the rotation keys ROTATION of OWNER, committed in VERSION, and the current keys CURRENT
        ([(key, version listing it)]) in the wallet W; stops if it fails."""
        from . import wallet
        print("warning: " + wallet.risk(w.name, owner), file=sys.stderr)
        unlocked = unlocked_passkeys(owner)
        secret = wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
        try:
            w.check_writable()
            todo = [(key, keys.ROTATION, version) for key in rotation]
            todo += [(key, keys.CURRENT, v) for key, v in current if w.read(owner, key.id, keys.CURRENT) is None]
            print(f"Saving {the_keys(len(todo))} of {names.short(owner)} to {w.name}…", file=sys.stderr)
            for key, kind, v in todo:
                plain = kind == keys.CURRENT and getattr(args, "plain_current", False)
                wallet.put_key(w, owner, key, kind, v, None if plain else secret, unlocked)
                print(f"{kind.capitalize()} key {key.did}: kept in {w.name}")
        except wallet.WalletError as e:
            sys.exit(f"{e}: nothing was written to the key log")
        enroll_hint(owner, unlocked)


    def plural(n, noun):
        """N NOUN, in the singular or the plural ("1 key", "2 keys")."""
        return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


    def the_keys(n, noun="key"):
        """"the key" or "the N keys"."""
        return f"the {noun}" if n == 1 else f"the {n} {noun}s"


    def key_label(kind, did):
        """A key in a line of progress: its kind and its short did:key, in columns."""
        return f"{kind + ' key':<13}{names.short(did)}"


    def version_listing(log, did):
        """The number of the first version of LOG whose current keys list DID, or None."""
        return next((v.number for v in log.side() if v.keys and did in v.keys.get("keys", [])), None)

### Reading the rotation keys

The rotation keys that sign the next version of the key log are read from
their files (`--rotation-key FILE`, repeated), or from typed sheets: each
must be of this owner and a rotation key of the latest version of its key
log, which `KeyLog.add` checks again. An encrypted file asks for the
passphrase once, for all of them.

    # in read the rotation keys that sign a version of the key log:
    def rotation_keys(files, owner):
        """The rotation keys of OWNER read from FILES."""
        out = []
        for f in files:
            try:
                try:
                    rk = keys.read_rotation_key(Path(f))
                except keys.PassphraseNeeded:
                    rk = keys.read_rotation_key(Path(f), passphrase(confirm=False))
            except (keys.KeyStoreError, OSError) as e:
                sys.exit(f"{f}: {e}")
            if rk.owner not in (None, owner):
                sys.exit(f"{f} is a rotation key of {rk.owner}, not of {owner}")
            out.append(rk.key)
        return out

Without `--rotation-key`, the rotation keys come from a wallet: the one
configured, or else that of `--keys`. The keys needed are those whose
digests are in `next` of the latest version of the key log, filed in the
wallet under their first 16 characters; `nextThreshold` of them are read,
with the passphrase asked once. The wallet is returned with the keys, so
that a rotation can tell the owner that it has used them up.

    # in read the rotation keys that sign a version of the key log:
    def rotation_signers(args, owner, prev):
        """(the rotation keys that sign the version after PREV, the wallet they come from or None)."""
        files = getattr(args, "rotation_key", None)
        if files:
            return rotation_keys(files, owner), None
        from . import wallet
        w = configured_wallet() or level_wallet(args)
        if w is None:
            sys.exit("give the rotation keys that sign the new version of the key log (--rotation-key FILE), "
                     "or the wallet that keeps them (--keys github:OWNER/REPO)")
        need, out = prev.keys["nextThreshold"], []
        print(f"Reading {the_keys(need, 'rotation key')} of v{prev.number} of {names.short(owner)} that sign "
              f"from {w.name}…", file=sys.stderr)
        try:
            for digest in prev.keys["next"]:
                key = unlock_key(w, owner, digest[:16], keys.ROTATION)
                if key is not None and key.digest == digest:
                    out.append(key)
                    print(f"  {len(out)}/{need} {key_label(keys.ROTATION, key.did)}  opened", file=sys.stderr)
                if len(out) == need:
                    break
        except wallet.WalletError as e:
            sys.exit(str(e))
        if len(out) < need:
            sys.exit(f"{w.name} holds {len(out)} of the rotation keys of v{prev.number} of the key log of {owner}, "
                     f"and {need} sign the next version: give them with --rotation-key FILE")
        print(f"Read {plural(len(out), 'rotation key')} of v{prev.number} from {w.name}.", file=sys.stderr)
        return out, w

Changing keys
-------------

`owner rotate` writes a new version of the key log (section 6.1), signed by
`nextThreshold` rotation keys of the latest version: it adds current keys
(`--add did:key`, made on their devices with `osheaf key new`), retires
others (`--retire did:key`, section 6.2), may change the `threshold`, and
commits new rotation keys, made now and kept as for a new owner, at the
security level of `--keys`, as many as before with the same
`nextThreshold` unless `--rotation` and `--next-threshold` say otherwise.
The rotation keys that sign come from their files, or from the wallet.
Signing with the rotation keys of a wallet and keeping the new ones
offline (`--keys offline --export DIR`) *moves the owner up* to the
maximum level: the keys left in the wallet are used up (section 6.2), and
the command says so, and what remains to do about the current keys kept
there. `owner expose` does the same and declares
keys exposed (section 6.3): stolen, leaked or copied current keys, which an
owner MUST expose at once when they could together reach a threshold. The
data of extensions in force is kept. The version is made in memory and
checked by `KeyLog.add` (the rules of section 6.1, the signatures), the new
rotation keys are exported and confirmed, and only then is it written.

    # in change the keys of an owner:
    def owner_rotate(args, exposed=()):
        """A new version of the key log changing the current keys (section 6.2) or exposing
        some (section 6.3), signed by rotation keys, committing new rotation keys."""
        owner, log = owner_of(args)
        prev = log.latest()
        if prev is None:
            sys.exit(f"the owner {owner} has ended (section 6.3): its key log takes no new version")
        w = level_wallet(args)
        if w is None and not getattr(args, "export", None):
            sys.exit("give --export DIR, a folder outside the archive where the new rotation keys are written "
                     "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
        if w is not None and getattr(args, "no_passphrase", False):
            sys.exit("--no-passphrase: the keys in a wallet are always encrypted")
        signers, source = rotation_signers(args, owner, prev)
        n_rot = int(getattr(args, "rotation", None) or len(prev.keys["next"]))
        next_threshold = int(getattr(args, "next_threshold", None) or min(prev.keys["nextThreshold"], n_rot))
        for did in list(getattr(args, "add", None) or []) + list(getattr(args, "retire", None) or []) + list(exposed):
            try:
                names.did_key_public(did)
            except ValueError:
                sys.exit(f"not a did:key URI of an Ed25519 key: {did}")
        new = [keys.new_key() for _ in range(n_rot)]
        try:
            v = log.rotate(signers, next_keys=new, next_threshold=next_threshold,
                           add=getattr(args, "add", None) or (), retire=getattr(args, "retire", None) or (),
                           exposed=exposed, threshold=getattr(args, "threshold", None),
                           message=getattr(args, "message", None) or ("Keys exposed" if exposed else "Keys changed"),
                           user=depositor())
        except owners.OwnerError as e:
            sys.exit(str(e))
        if next_threshold == 1:
            print("warning: " + owners.SINGLE_ROTATION_RISK, file=sys.stderr)
        if getattr(args, "export", None):
            export_and_confirm(new, owner, v.number, args)
        if w is not None:
            try:
                here = keys.current_keys(owner, v.keys["keys"])
            except keys.KeyStoreError:
                here = []
            keep_in_wallet(w, owner, new, v.number, args, current=[(k, version_listing(log, k.did)) for k in here])
        owners.write_key_log(obj_dir(log.id), log)
        write_discovery()
        print(f"{owner}: v{v.number} of the key log, current keys: {', '.join(v.keys['keys'])}")
        if source is not None and w is None:
            print(f"moved up: the rotation keys kept in {source.name} are used up and sign nothing more "
                  "(section 6.2); the new ones are kept offline only. osheaf key forget --wallet --used removes "
                  f"the used ones; current keys kept in {source.name} still sign until a version retires them "
                  "(osheaf owner rotate --retire) and osheaf key forget --wallet removes them", file=sys.stderr)
        for did in exposed:
            print(f"exposed {did}: what it alone signed is contested (section 7.3)")


    def owner_expose(args):
        owner_rotate(args, exposed=list(args.exposed))

Ending
------

`owner end` signs the last version of the key log, with `ended` and,
optionally, the successor that continues the owner's work (section 6.3):
another owner name. Nothing is signed for the owner afterwards; the
ending version has no keys, so no rotation keys are made. It may also
expose keys (`--expose`). The rotation keys come from their files or from
the wallet, as for a rotation.

    # in end an owner:
    def owner_end(args):
        """The ending version of the key log (section 6.3)."""
        owner, log = owner_of(args)
        successor = getattr(args, "successor", None)
        if successor is not None and not names.OWNER_NAME.match(successor):
            sys.exit(f"the successor is an owner name: {successor}")
        if log.latest() is None:
            sys.exit(f"the owner {owner} has ended (section 6.3): its key log takes no new version")
        signers, _ = rotation_signers(args, owner, log.latest())
        try:
            v = log.end(signers, successor=successor, exposed=getattr(args, "expose", None) or (),
                        message=getattr(args, "message", None) or "Owner ended", user=depositor())
        except owners.OwnerError as e:
            sys.exit(str(e))
        owners.write_key_log(obj_dir(log.id), log)
        write_discovery()
        print(f"{owner}: ended at v{v.number} of its key log" + (f", successor {successor}" if successor else ""))

Showing
-------

`owner show` describes the key log, version by version, with its current
keys, its end and its exposed keys, and its findings (section 14.3), and
says which of its current keys this device holds.

    # in show an owner:
    def owner_show(args):
        owner, log = owner_of(args)
        for line in owners.describe(log):
            print(line)
        latest = log.latest()
        if latest is not None:
            try:
                here = keys.current_keys(owner, latest.keys["keys"])
            except keys.KeyStoreError as e:
                print(f"warning: {e}", file=sys.stderr)
                here = []
            for k in here:
                print(f"on this device {k.did}")

A new current key
-----------------

A new device makes its own current key, never copied from another
(section 6.2): `osheaf key new` makes it, keeps it in the credential store
under the owner name, and prints its `did:key`, which a new version of the
key log adds to the current keys (`osheaf owner rotate --add`), with the
rotation keys kept apart. Until then it signs nothing. With
`OPENSHEAF_KEY_STORE=none`, which keeps no key on the device, it refuses.

    # in a new current key for this device:
    def key_new(args):
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        if not keys.kept_on_device():
            sys.exit(NOT_KEPT)
        key = keys.new_key()
        try:
            store = keys.store_current_key(owner, key)
        except (keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        print(key.did)
        print(f"kept in {store}; it signs once a version of the key log adds it: "
              f"osheaf owner rotate --add {key.did} --rotation-key FILE ... --export DIR")
        return key

Key wallets
-----------

Four commands move current keys between this device and a wallet
([chapter 9](09-wallets.md)), and show what a wallet holds.

`osheaf key push` puts the current keys of this device into the wallet:
those of the latest version of the key log, or those named. A key made on
a new device with `osheaf key new`, and not yet listed, is pushed by name.
A key the wallet holds already is left as it is. The current keys are
encrypted under the passphrase unless `--plain-current`; the risk is
stated.

    # in the commands of key wallets:
    def key_push(args):
        """Put the current keys of this device into the wallet."""
        from . import wallet
        owner, log = owner_of(args)
        latest = log.latest()
        if latest is None:
            sys.exit(f"the owner {owner} has ended (section 6.3)")
        w = wallet_for(args)
        dids = list(getattr(args, "did", None) or latest.keys["keys"])
        try:
            here = keys.current_keys(owner, dids)
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        if not here:
            sys.exit(f"this device holds none of the keys {', '.join(dids)} of {owner}")
        print("warning: " + wallet.risk(w.name, owner), file=sys.stderr)
        unlocked = [] if getattr(args, "plain_current", False) else unlocked_passkeys(owner)
        secret = None if getattr(args, "plain_current", False) else \
            wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
        try:
            w.check_writable()
            for key in here:
                if w.read(owner, key.id, keys.CURRENT) is not None:
                    print(f"Current key {key.did}: in {w.name} already")
                    continue
                wallet.put_key(w, owner, key, keys.CURRENT, version_listing(log, key.did), secret, unlocked)
                print(f"Current key {key.did}: pushed to {w.name}")
        except wallet.WalletError as e:
            sys.exit(str(e))

`osheaf key pull` is the other way: the current keys of the latest version
of the key log that this device does not hold are read from the wallet,
and kept in the device's store, which serves as a cache: signing then
reads them there, without calling the wallet. Signing pulls them itself
when this device holds too few current keys and a wallet is configured
(`pull_from_wallet`, called by `signing_keys`): a new laptop signs at once,
asking for the passphrase once. The command says what it pulls, and then
in a sentence what this device holds. With `OPENSHEAF_KEY_STORE=none`,
nothing is pulled: the keys stay in the wallet by choice, and each command
that signs opens them there.

    # in the commands of key wallets:
    def key_pull(args):
        """Keep on this device the current keys of the owner that the wallet holds."""
        owner, log = owner_of(args)
        latest = log.latest()
        if latest is None:
            sys.exit(f"the owner {owner} has ended (section 6.3)")
        w = wallet_for(args)
        if not keys.kept_on_device():
            print(not_kept(w, owner))
            return
        try:
            have = {k.did for k in keys.current_keys(owner, latest.keys["keys"])}
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
        print(pull_summary(w, owner, latest, have, pulled))


    STORE_NAMES = {"keyring": "the keychain" if sys.platform == "darwin" else "the system keyring",
                   "security": "the keychain", "file": "a file of this computer",
                   keys.NONE: "memory, for this command only"}
    NOT_KEPT = (f"{keys.KEY_STORE}=none: no current key is kept on this computer, so a new one would be "
                "lost when the command ends")


    def not_kept(w, owner):
        """The sentence that says why nothing is pulled with OPENSHEAF_KEY_STORE=none."""
        return (f"The current keys of {names.short(owner)} are not kept on this computer, by choice "
                f"({keys.KEY_STORE}=none): each command that signs opens them in {w.name}.")


    def pull_current_keys(w, owner, dids):
        """[(key, store)]: the keys DIDS of OWNER that the wallet W holds, kept on this device in STORE."""
        from . import wallet
        out = []
        if dids:
            print(f"Pulling {the_keys(len(dids), 'current key')} of {names.short(owner)} from {w.name}…",
                  file=sys.stderr)
        try:
            for did in dids:
                key = unlock_key(w, owner, names.key_id(did), keys.CURRENT)
                if key is None:
                    print(f"  {key_label(keys.CURRENT, did)}  not in {w.name}", file=sys.stderr)
                    continue
                if key.did != did:
                    sys.exit(f"{w.name} holds another key than {did} under its name")
                store = keys.store_current_key(owner, key)
                print(f"  {key_label(keys.CURRENT, did)}  kept in {STORE_NAMES.get(store, store)}", file=sys.stderr)
                out.append((key, store))
        except (wallet.WalletError, keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        return out


    def pull_summary(w, owner, latest, have, pulled):
        """The sentence that says what a pull did: HAVE, the did:keys held before, PULLED, [(key, store)]."""
        total, held, who = len(latest.keys["keys"]), len(have) + len(pulled), names.short(owner)
        if pulled:
            stores = sorted({STORE_NAMES.get(s, s) for _, s in pulled})
            out = f"Pulled {plural(len(pulled), 'current key')} of {who} from {w.name} into {' and '.join(stores)}."
            return out + (f" This computer holds {held} of its {total} current keys." if held < total else "")
        if held == total:
            return (f"The current key of {who} is already on this computer." if total == 1
                    else f"The {total} current keys of {who} are already on this computer.")
        return (f"{w.name} holds no current key of {who} that this computer lacks: it holds {held} of the "
                f"{total}.")


    def pull_from_wallet(owner, latest, found):
        """FOUND, the current keys of OWNER on this device, with those the configured wallet adds."""
        w = configured_wallet()
        if w is None:
            return found
        held = {k.did for k in found}
        return found + [k for k, _ in pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in held])]

`osheaf key list` shows what the wallet holds: for each key, its owner, its
name, its kind, its `did:key` and the version of the key log that commits
it, as the files say, without decrypting them. No secret is shown.

    # in the commands of key wallets:
    def key_list(args):
        """What the wallet holds: owner, key, kind, did:key, version."""
        from . import wallet
        w = wallet_for(args)
        try:
            rows = wallet.listing(w, getattr(args, "owner", None))
        except wallet.WalletError as e:
            sys.exit(str(e))
        for owner, kid, kind, did, version in rows:
            print(f"{owner} {kid} {kind:8} {did} {version}".rstrip())

Unlocking with a passkey
------------------------

The passphrase of a wallet can be left to a passkey ([chapter 7](07-keys.md),
[chapter 9](09-wallets.md)): enrolled once, it opens the keys of the owner
with Touch ID, on every device the passkey reaches (all the Macs of one
iCloud Keychain), through the page `https://opensheaf.org/manager/unlock.html`.

Whenever a command reads a key of the wallet that a passkey can unlock
(`unlock_key`, which pulling current keys and reading rotation keys call),
`passkey_keks` asks the browser, once per command and owner, and keeps the
key-encryption key in memory until the command ends; the PRF secret is
never stored, and the key read is then kept on this device as before. The
passphrase is asked instead when the browser gives nothing: an error of
the page, no answer in two minutes, or Ctrl-C at the prompt; or never,
when `OPENSHEAF_UNLOCK` is `passphrase`, or when `OPENSHEAF_PASSPHRASE`
holds the passphrase (a script, continuous integration: no browser there).

    # in unlock the keys of a wallet with a passkey:
    def passkey_keks(owner, wraps, force=False):
        """{cred: key-encryption key} of the passkeys among WRAPS of OWNER unlocked in this command,
        asking the browser if none is; None to use the passphrase."""
        from . import passkey
        cache = _ASKED.setdefault("passkeys", {})
        _ASKED.setdefault("seen", set()).add(owner)
        failed = _ASKED.setdefault("failed", set())
        salt = keys.passkey_salt(owner)
        wraps = [p for p in wraps if p.salt == salt]
        if not wraps:
            return None
        if any(p.cred in cache for p in wraps):
            return {c: p.kek for c, p in cache.items()}
        if not force and (os.environ.get(PASSPHRASE) or os.environ.get(passkey.UNLOCK, "") == "passphrase"
                          or owner in failed):
            return None
        creds = list(dict.fromkeys(p.cred for p in wraps))
        try:
            cred, prf = passkey.unlock(owner, creds, no_browser=_ASKED.get("no_browser", False),
                                       ctrl_c="stop" if force else "type the passphrase instead")
        except passkey.UnlockFailed as e:
            failed.add(owner)
            if force:
                sys.exit(f"the passkey did not unlock the keys of {owner}: {e}")
            print(f"The passkey did not open the keys ({e}): osheaf asks for the passphrase instead.",
                  file=sys.stderr)
            return None
        kek = keys.passkey_kek(prf)
        for c in ([cred] if cred else creds):
            cache[c] = keys.Passkey(c, salt, kek=kek)
        return {c: p.kek for c, p in cache.items()}


    def unlock_key(w, owner, kid, kind):
        """The key KID of OWNER, of KIND, from the wallet W, unlocked by a passkey or the passphrase."""
        from . import wallet
        return wallet.get_key(w, owner, kid, kind, lambda: passphrase(confirm=False, where=w.name), passkey_keks)

A key put into the wallet by a command that has unlocked a passkey of the
owner gets a wrap under that passkey as well as under the passphrase
(which a key written always needs: it is the way back); the passphrase is
then asked once, and checked against a key of the wallet rather than
typed twice. A command that
met a passkey of the owner without unlocking it says how to add it to the
new keys: `osheaf key enroll` again, which uses the same passkey.

    # in unlock the keys of a wallet with a passkey:
    def unlocked_passkeys(owner):
        """The passkeys of OWNER unlocked in this command."""
        salt = keys.passkey_salt(owner)
        return [p for p in _ASKED.get("passkeys", {}).values() if p.salt == salt]


    def wallet_passphrase(w, owner):
        """The passphrase, for keys written after a passkey has opened others: asked once, and checked
        against a key of OWNER in the wallet W, so that the new keys are under the same passphrase."""
        from . import wallet
        if os.environ.get(PASSPHRASE) or "passphrase" in _ASKED:
            return passphrase(where=w.name)
        try:
            texts = [t for _, t in wallet_entries(w, owner) if keys.wraps_of(t)]
        except SystemExit:
            texts = []
        if not texts:
            return passphrase(where=w.name)
        secret = passphrase(confirm=False, where=w.name)
        try:
            keys.read_key(texts[0], secret)
        except keys.KeyStoreError as e:
            sys.exit(f"{e}: this is not the passphrase of the keys of {owner} in {w.name}")
        return secret


    def enroll_hint(owner, unlocked):
        if not unlocked and owner in _ASKED.get("seen", set()):
            print(f"The new keys of {names.short(owner)} open with the passphrase only: run osheaf key enroll "
                  "so that your passkey opens them too.", file=sys.stderr)

`osheaf key enroll` adds a passkey to the keys of the owner in the wallet.
It reads them all, and asks the passphrase once, which must open every
encrypted one, before the browser is opened. The first time, the page
creates a passkey for `opensheaf.org`, named after the owner, and derives
its secret; later, it is the passkey already there that opens the keys
added since (`--new-passkey` creates another, for another provider or a
hardware key, which then opens them too). Every key that this passkey does
not open yet gets a wrap under it, keeping its passphrase wrap, and is
written back to the wallet (with the GitHub wallet, one commit per file).
A key kept unencrypted (`--plain-current`) is left as it is. Opening each
key with the passphrase (Argon2id) and writing each back takes a moment:
the command says what it does, key by key, on the standard error, and
ends with one sentence on the standard output.

    # in unlock the keys of a wallet with a passkey:
    def wallet_entries(w, owner):
        """[(kid, text)] of the keys of OWNER in the wallet W."""
        from . import wallet
        try:
            return [(kid, wallet.read_any(w, o, kid)) for o, kid in w.entries(owner)]
        except wallet.WalletError as e:
            sys.exit(str(e))


    def encrypted_entries(w, owner):
        out = [(kid, t) for kid, t in wallet_entries(w, owner)
               if any(x.startswith("encryption ") and x.split()[1:2] != ["none"] for x in t.splitlines())]
        if not out:
            sys.exit(f"{w.name} holds no encrypted key of {owner}")
        return out


    def key_owner(args):
        owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
        if not owner or not names.OWNER_NAME.match(owner):
            sys.exit("give --owner NAME, or run the command in an archive")
        return owner


    def key_enroll(args):
        """Let a passkey open the keys of the owner in the wallet."""
        from . import passkey, wallet
        owner, w = key_owner(args), wallet_for(args)
        _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
        try:
            w.check_writable()
        except wallet.WalletError as e:
            sys.exit(str(e))
        who = names.short(owner)
        print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
        entries = encrypted_entries(w, owner)
        salt = keys.passkey_salt(owner)
        known = list(dict.fromkeys(p.cred for _, t in entries for p in keys.passkeys_of(t) if p.salt == salt))
        new = bool(getattr(args, "new_passkey", False)) or not known
        todo = entries if new else [(kid, t) for kid, t in entries
                                    if not {p.cred for p in keys.passkeys_of(t)} & set(known)]
        if not todo:
            print(f"Every encrypted key of {who} in {w.name} already opens with your passkey.")
            return
        secret = passphrase(confirm=False, where=w.name)
        n = len(todo)
        print(f"Opening {the_keys(n)} of {who} in {w.name} with the passphrase…", file=sys.stderr)
        for i, (kid, t) in enumerate(todo, 1):
            try:
                rk = keys.read_key(t, secret)
            except keys.KeyStoreError as e:
                sys.exit(f"{w.name} {kid}: {e}: nothing was changed")
            print(f"  {i}/{n} {key_label(rk.kind, rk.key.did)}  opened", file=sys.stderr)
        stop = "stop: nothing is changed"
        try:
            cred, prf = passkey.enroll(owner, no_browser=_ASKED["no_browser"], ctrl_c=stop) if new else \
                passkey.unlock(owner, known, no_browser=_ASKED["no_browser"], ctrl_c=stop)
        except passkey.UnlockFailed as e:
            sys.exit(f"no passkey: {e}; nothing was changed")
        kek = keys.passkey_kek(prf)
        if not new:
            opened = [c for c in ([cred] if cred else known)
                      if any(_opens(t, c, kek) for _, t in entries if c in {p.cred for p in keys.passkeys_of(t)})]
            if not opened:
                sys.exit("the passkey used does not open the keys it is enrolled for: nothing was changed")
            cred = opened[0]
        unlocked = keys.Passkey(cred, salt, kek=kek)
        print(f"Saving {the_keys(n)} to {w.name}…", file=sys.stderr)
        try:
            for i, (kid, _) in enumerate(todo, 1):
                kind, did = wallet.add_passkey(w, owner, kid, secret, unlocked)
                print(f"  {i}/{n} {key_label(kind, did)}  saved", file=sys.stderr)
        except wallet.WalletError as e:
            sys.exit(str(e))
        print(f"Done: {the_keys(n)} of {who} {'opens' if n == 1 else 'open'} with your passkey (Touch ID) "
              "and still with your passphrase.")


    def _opens(text, cred, kek):
        try:
            keys.read_key(text, keks={cred: kek})
            return True
        except keys.KeyStoreError:
            return False

`osheaf key unlock` opens with the passkey the keys of the owner that it
can open, which checks that the enrollment works, and, in an archive,
keeps on this device the current keys of the latest version of the key
log that it does not hold, as `osheaf key pull` does, with one Touch ID
(with `OPENSHEAF_KEY_STORE=none`, it says that they are not kept, by
choice).
It never falls back to the passphrase: it is the passkey that it tries.
It says how many keys the passkey opened, and what this device holds.

    # in unlock the keys of a wallet with a passkey:
    def key_unlock(args):
        """Open with the passkey the keys of the owner in the wallet; in an archive, pull its current keys."""
        owner, w = key_owner(args), wallet_for(args)
        _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
        who = names.short(owner)
        print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
        entries = [(kid, t) for kid, t in wallet_entries(w, owner) if keys.passkeys_of(t)]
        if not entries:
            sys.exit(f"no key of {owner} in {w.name} opens with a passkey: run osheaf key enroll")
        keks = passkey_keks(owner, [p for _, t in entries for p in keys.passkeys_of(t)], force=True)
        if not keks:
            sys.exit(f"no passkey of {owner} to unlock")
        opened, n = sum(1 for _, t in entries if any(_opens(t, c, k) for c, k in keks.items())), len(entries)
        if opened == n:
            print(f"{'The key' if n == 1 else 'Both keys' if n == 2 else f'All {n} keys'} of {who} opened "
                  "with your passkey.")
        else:
            print(f"{opened} of the {n} keys of {who} opened with your passkey; the others need the passphrase.")
        log = key_log(owner) if ROOT is not None else None
        latest = log.latest() if log is not None else None
        if latest is not None and not keys.kept_on_device():
            print(not_kept(w, owner))
        elif latest is not None:
            try:
                have = {k.did for k in keys.current_keys(owner, latest.keys["keys"])}
            except keys.KeyStoreError as e:
                sys.exit(str(e))
            pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
            print(pull_summary(w, owner, latest, have, pulled))

A key to and from a password manager
------------------------------------

`osheaf key export --clipboard` copies a current key of this device, as the
text of [chapter 7](07-keys.md), to the clipboard, to be pasted into a note
of a password manager such as the Passwords app of macOS, which keeps it
in the user's iCloud keychain; `--stdout` prints it instead, the one case
in which a command prints a secret on its standard output, since it is
asked for. `--encrypt` encrypts the seed under the passphrase. The key is
the one named, or the one current key of the latest version of the key log
that this device holds.

    # in a key to and from a password manager:
    def key_export(args):
        """Copy a current key of this device to the clipboard (or print it, --stdout)."""
        from . import wallet
        if not getattr(args, "clipboard", False) and not getattr(args, "stdout", False):
            sys.exit("give --clipboard, or --stdout to print the key")
        owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
        if not owner:
            sys.exit("give --owner NAME, or run the command in an archive")
        if getattr(args, "did", None):
            dids = [args.did]
        else:
            latest = key_log(owner).latest() if ROOT is not None and key_log(owner) else None
            if latest is None:
                sys.exit(f"name the key to export, by its did:key (no key log of {owner} here)")
            dids = latest.keys["keys"]
        try:
            here = keys.current_keys(owner, dids)
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        if len(here) != 1:
            sys.exit(f"this device holds {len(here)} of the keys {', '.join(dids)} of {owner}: name one by its did:key")
        key = here[0]
        text = keys.key_text(key, owner, keys.CURRENT, passphrase() if getattr(args, "encrypt", False) else None)
        if getattr(args, "stdout", False):
            sys.stdout.write(text)
        else:
            try:
                wallet.to_clipboard(text)
            except wallet.WalletError as e:
                sys.exit(str(e))
            print(f"the current key {key.did} of {owner} is on the clipboard: paste it into a note of your "
                  "password manager (the Passwords app), then copy something else", file=sys.stderr)
        print("warning: a current key kept in a password manager is on every device that it syncs with; "
              "section 6.2 has one key per device", file=sys.stderr)

`osheaf key import --clipboard` (or `--stdin`) reads such a text back, asks
for the passphrase if it is encrypted, and keeps the key on this device. A
rotation key is refused: it is never kept on a device, but read from its
file or its wallet when it signs. A key that the latest version of the key
log does not list is kept with a warning: it signs nothing until a version
adds it. With `OPENSHEAF_KEY_STORE=none` it refuses, as `osheaf key new`
does.

    # in a key to and from a password manager:
    def key_import(args):
        """Keep on this device a key copied from a password manager (the clipboard, or the standard input)."""
        from . import wallet
        if bool(getattr(args, "clipboard", False)) == bool(getattr(args, "stdin", False)):
            sys.exit("give --clipboard or --stdin")
        if not keys.kept_on_device():
            sys.exit(NOT_KEPT)
        try:
            text = wallet.from_clipboard() if args.clipboard else sys.stdin.read()
        except wallet.WalletError as e:
            sys.exit(str(e))
        try:
            try:
                rk = keys.read_key(text)
            except keys.PassphraseNeeded:
                rk = keys.read_key(text, passphrase(confirm=False))
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        if rk.kind != keys.CURRENT:
            sys.exit("a rotation key is never kept on a device: give its file to the command it signs "
                     "(--rotation-key FILE), or keep it in a wallet")
        owner = rk.owner or getattr(args, "owner", None) or ARCHIVE.get("owner")
        if getattr(args, "owner", None) and rk.owner and args.owner != rk.owner:
            sys.exit(f"the key is one of {rk.owner}, not of {args.owner}")
        if not owner or not names.OWNER_NAME.match(owner):
            sys.exit("the text names no owner: give --owner NAME")
        log = key_log(owner) if ROOT is not None else None
        latest = log.latest() if log is not None else None
        if latest is not None and rk.key.did not in latest.keys["keys"]:
            print(f"warning: {rk.key.did} is not a current key of v{latest.number} of the key log of {owner}: "
                  "it signs nothing until a version adds it", file=sys.stderr)
        try:
            if keys.current_keys(owner, [rk.key.did]):
                print(f"{rk.key.did}: on this device already")
                return
            store = keys.store_current_key(owner, rk.key)
        except (keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        print(f"{rk.key.did}\nkept in {store}")

Forgetting a key
----------------

`osheaf key forget DID...` removes current keys from the stores of this
device, a retired key for instance. With `--wallet`, they are removed from
the wallet too, the one case in which the tools delete anything there;
`--wallet --used` removes from the wallet the keys of the owner that the
latest version of its key log no longer needs: current keys it does not
list, and rotation keys it does not commit, used up (section 6.2 asks
that they be destroyed). A rotation key the latest version commits is kept
unless `--force`: without `nextThreshold` of them the owner can never
change its keys (section 6.2). Removing from a wallet is confirmed by
typing `forget`, unless `--yes`.

    # in forget a key:
    def key_forget(args):
        """Remove keys from this device, and with --wallet from the wallet."""
        from . import wallet
        owner, log = owner_of(args)
        latest = log.latest()
        listed = set(latest.keys["keys"]) if latest else set()
        committed = {d[:16] for d in latest.keys["next"]} if latest else set()
        dids = list(getattr(args, "did", None) or [])
        if getattr(args, "used", False):
            if not getattr(args, "wallet", False) or dids:
                sys.exit("--used goes with --wallet, and names no key")
        elif not dids:
            sys.exit("name the keys to forget, by their did:key")
        for did in dids:
            try:
                names.did_key_public(did)
            except ValueError:
                sys.exit(f"not a did:key URI of an Ed25519 key: {did}")
        if not getattr(args, "wallet", False):
            for did in dids:
                keys.forget_current_key(owner, did)
                print(f"{did}: forgotten on this device")
            return
        w = wallet_for(args)
        try:
            rows = wallet.listing(w, owner)
        except wallet.WalletError as e:
            sys.exit(str(e))
        if getattr(args, "used", False):
            gone = [r for r in rows if r[3] not in listed and r[1] not in committed]
        else:
            gone = [r for r in rows if r[3] in dids]
        needed = [r for r in gone if r[1] in committed]
        if needed and not getattr(args, "force", False):
            sys.exit(f"{', '.join(r[3] for r in needed)}: rotation keys of the latest version of the key log, "
                     "kept (an owner without nextThreshold of them can never change its keys, section 6.2); "
                     "--force removes them")
        for r in gone:
            print(f"to remove from {w.name}: {r[2]} key {r[3]}")
        if gone and not getattr(args, "yes", False) and input("type forget to remove them: ").strip() != "forget":
            sys.exit("not confirmed: nothing was removed")
        for did in dids:
            keys.forget_current_key(owner, did)
            print(f"{did}: forgotten on this device")
        if not gone:
            print(f"{w.name} holds none of these keys")
        try:
            for o, kid, kind, did, _ in gone:
                w.forget(o, kid, kind)
                print(f"{did}: removed from {w.name}")
        except wallet.WalletError as e:
            sys.exit(str(e))

Signing again
-------------

The signatures made with a key that the owner's key log exposes stay good,
since the format does not date signatures; but the versions that need
them are *contested* (section 7.3), never the latest signed version, and
archives that know of the exposure never add them (section 7.5). The owner
may add signatures to a version later, with current keys that have not
signed it, only to a version it knows it made, and only while it is not
ended (sections 6.4 and 7.1): so it signs again, with keys not exposed, a
version contested by an exposed key, which is then signed by keys that
are not suspect, and no longer contested.

`osheaf sign LABEL --version vN` does that. It refuses a version that is
not contested (there is nothing to repair), an owner that has ended (by an
ending version or a fork: `signing_keys` signs nothing for it, and after a
fork nothing is added without evidence, section 7.5), and a device that
does not hold `threshold` current keys of the latest version of the key
log that have not signed the version. The owner confirms that it made the
version, by typing the first eight characters of its inventory digest,
unless `--yes`: a thief holding an exposed key could have made it
(section 7.3). The signature files name the latest version of the key log,
and are added to the witness folder, never replacing one.

    # in sign again a version contested by an exposed key:
    def sign_again(args):
        """Sign again a version of a line contested by an exposed key (sections 6.4 and 7.1)."""
        obj_id = resolve(args.id)
        d = obj_dir(obj_id)
        inv = load_inventory(d)
        ver = args.version
        if ver not in inv["versions"]:
            sys.exit(f"{args.id} has no object version {ver}")
        owner = obj_id.split(":")[2]
        if owner not in archive_owners():
            sys.exit(f"{args.id} is a line of an owner this archive does not host: only its owner signs it")
        log, latest, signers = signing_keys(owner)
        statuses = line_statuses(d, inv, log)[1]
        status = statuses[int(ver[1:]) - 1]
        if status != sign.CONTESTED:
            sys.exit(f"{args.id} {ver} is {status}: signing again is for a version contested by an exposed key "
                     "(section 7.1)")
        held = set(witnesses_of(d, ver))
        fresh = [k for k in signers if k.did not in log.exposed_keys() and sign.file_name(k.did) not in held]
        if len(fresh) < latest.keys["threshold"]:
            sys.exit(f"this device holds {plural(len(fresh), 'current key')} of {owner} that "
                     f"{'has' if len(fresh) == 1 else 'have'} not signed {ver}, and "
                     f"v{latest.number} of the key log needs {latest.keys['threshold']}")
        dig = names.sha512_hex((d / ver / "inventory.json").read_bytes())
        if not getattr(args, "yes", False):
            print(f"{args.id} {ver}: document version {doc_version_of(d, inv, ver)}, deposited "
                  f"{inv['versions'][ver]['created']}: {inv['versions'][ver].get('message', '')}")
            if input(f"did {owner[:16]}... make it? type {dig[:8]} to sign it again: ").strip() != dig[:8]:
                sys.exit("not confirmed: nothing was signed")
        wdir = d / sign.WITNESSES / ver
        wdir.mkdir(parents=True, exist_ok=True)
        pin = log.pin(latest.number)
        for key in fresh:
            with open(wdir / sign.file_name(key.did), "xb") as f:
                f.write(sign.signature_file(key, obj_id, ver, dig, owner, pin))
        write_discovery()
        print(f"{args.id} {ver}: signed again by {plural(len(fresh), 'key')}, naming v{latest.number} of the key log: "
              f"{line_statuses(d, inv, log)[1][int(ver[1:]) - 1]}")
