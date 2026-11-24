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
            stop("no archive here (no osheaf.json in this folder or above it): give --root")
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        log = key_log(owner)
        if log is None:
            stop(f"the key log of {names.short(owner)} is not in the storage root")
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
The command ends with a summary, the owner name and the `did:key` in full,
to be copied:

```
Done: the owner em4v3kp5…gora is made, with v1 of its key log:
  owner          em4v3kp5…(the full name)
  current key    did:key:z6MkpZ85…(in full), kept in the keychain
  rotation keys  3, kept in github:mgubi/opensheaf-keys; any 2 of them sign the next version of the key log
```

(in `osheaf init`, it starts "The owner …", and the archive's own "Done:"
line follows).
With `OPENSHEAF_KEY_STORE=none` ([chapter 7](07-keys.md)) it is kept in the
wallet only, and an owner without a wallet is refused: its current key
would be lost when the command ends.

    # in create an owner:
    def owner_init(args, done=True):
        """Make an owner (section 6.2): its current key on this device, its rotation keys,
        exported outside the archive, and the first version of its key log, in the storage root."""
        single = bool(getattr(args, "single_rotation_key", False))
        n_rot = 1 if single else int(getattr(args, "rotation", None) or 3)
        next_threshold = 1 if single else int(getattr(args, "next_threshold", None) or n_rot // 2 + 1)
        others = list(getattr(args, "key", None) or [])
        threshold = int(getattr(args, "threshold", None) or 1)
        if not 1 <= next_threshold <= n_rot or not 1 <= threshold <= 1 + len(others):
            stop("a threshold is at least 1, and at most the number of keys (section 6.1, rule 1)")
        keeper = getattr(args, "keeper", None)
        if keeper and not names.keeper_valid(keeper, strict=True):
            stop(f"a keeper is an ORCID iD (with its check digit) or https://<domain>/: {keeper}")
        if getattr(args, "print", False) and not getattr(args, "export", None):
            stop("--print prints the sheets of the rotation keys exported with --export DIR: give "
                 "--export DIR with it (in a wallet, the keys are not exported, and no sheet is printed)")
        w = level_wallet(args)
        if w is None and not getattr(args, "export", None):
            stop("give --export DIR, a folder outside the archive where the rotation keys are written "
                 "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
        if w is not None and getattr(args, "no_passphrase", False):
            stop("--no-passphrase: the keys in a wallet are always locked with a passphrase")
        if w is None and not keys.kept_on_device():
            stop(f"{keys.KEY_STORE}=none keeps no current key on this computer: keep the keys in a "
                 "wallet (--keys github:OWNER/REPO|command)")
        for did in others:
            try:
                names.did_key_public(did)
            except ValueError:
                stop(f"not a did:key URI of an Ed25519 key: {did}")
        current = keys.new_key()
        rotation = [keys.new_key() for _ in range(n_rot)]
        while True:
            try:
                log = owners.new_owner([current] + others, rotation, threshold=threshold,
                                       next_threshold=next_threshold, keeper=keeper)
            except (ValueError, owners.OwnerError) as e:
                stop(str(e))
            if not obj_dir(log.id).exists():
                break
        if next_threshold == 1:
            warn(owners.SINGLE_ROTATION_RISK)
        if getattr(args, "export", None):
            export_and_confirm(rotation, log.owner, 1, args)
        if w is not None:
            keep_in_wallet(w, log.owner, rotation, 1, args, current=[(current, 1)])
        try:
            store = keys.store_current_key(log.owner, current)
        except (keys.KeyStoreError, OSError) as e:
            stop(str(e))
        owners.write_key_log(unlinked(obj_dir(log.id)), log)
        kept = f"{w.name} only ({keys.KEY_STORE}=none)" if store == keys.NONE else store_name(store)
        print(f"{'Done: the' if done else 'The'} owner {names.short(log.owner)} is made, with v1 of its key log:")
        print(f"  owner          {log.owner}")
        print(f"  current key    {current.did}, kept in {kept}")
        for did in others:
            print(f"  current key    {did}, of another device")
        print(rotation_line(n_rot, next_threshold, kept_where(args, w)))
        warn(owners.ROTATION_KEYS_WARNING)
        return log

`osheaf owner init` makes an owner in an existing archive, which then hosts
it: its owner name joins `owners` in the configuration, its owner catalogue
is sealed, empty, and signed with its new current key (section 8.1: the
catalogue is created when the owner is set up in the archive; see
[the owner catalogues](15-owner-catalogues.md)), and the discovery document
lists it with its catalogue. A GitHub wallet chosen for it is recorded in the
configuration as the owner's (`record_wallet`, below), so that later
commands find the keys there.

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
            if changed:
                write_file(cfg_path, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
            record_wallet(log.owner, getattr(args, "keys", None))
            if log.owner in archive_owners() and log.owner not in CATALOGUES:
                collect(argparse_namespace(owner=log.owner))
        write_discovery()


    def wallet_config(args, owner):
        """The `keys` of osheaf.json naming the GitHub wallet of --keys for OWNER, or None."""
        spec = getattr(args, "keys", None) or ""
        return {owner: {"wallets": [spec]}} if spec.startswith("github:") else None

A passphrase is asked twice, without echo, or taken from the environment
variable `OPENSHEAF_PASSPHRASE`, for scripts, or printed by the command of
`OPENSHEAF_PASSPHRASE_COMMAND`, run by the shell, whose standard output,
less its final line feed, is the passphrase (nothing else is stripped,
neither there nor from a passphrase typed, so that the same passphrase
gives the same key whichever way it comes): `security find-generic-password -w -s
opensheaf-passphrase` reads it from the macOS keychain, `op read
op://Private/opensheaf/password` from 1Password. A command that fails or
prints nothing is said so, and the passphrase is asked. An empty
passphrase is refused: an owner who wants plain files says so, with
`--no-passphrase`.
It is asked once per command and per place of keys, however many keys it
encrypts or decrypts there, naming the wallet whose keys it opens, if any:
a rotation that reads the rotation keys from a wallet and keeps new ones
there asks once. Keys in two places are asked for twice: a rotation that
reads its rotation keys from files (`--rotation-key FILE`) and keeps the
new ones in a wallet (`--keys`) asks for the passphrase of the files, then
for that of the wallet, which the new keys get, so that the wallet's keys
are never locked, unseen, with the passphrase of other files. The command line forgets it when the command ends
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
        asked = _ASKED.setdefault("passphrases", {})
        if where in asked:
            return asked[where]
        command = os.environ.get(PASSPHRASE_COMMAND, "").strip()
        if command:
            r = subprocess.run(command, shell=True, capture_output=True, text=True)
            given = r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout
            if r.returncode == 0 and given:
                asked[where] = given
                return given
            warn(f"{PASSPHRASE_COMMAND} gave no passphrase: {r.stderr.strip()}")
        import getpass
        first = getpass.getpass(f"Passphrase of the keys in {where}: " if where else "Passphrase of the keys: ")
        if not first:
            stop("an empty passphrase: give --no-passphrase to export the keys without a passphrase lock")
        if confirm and getpass.getpass("The passphrase again: ") != first:
            stop("the two passphrases differ")
        asked[where] = first
        return first


    def forget_passphrase():
        _ASKED.clear()
        keys.forget_seen()

### The security level and the wallet

A command that makes keys keeps them at the security level of `--keys`:
`offline` (the default) gives no wallet, `github:OWNER/REPO` the GitHub
wallet, `command` the command wallet configured in the user's
configuration file or in `OPENSHEAF_WALLET` ([chapter 9](09-wallets.md)).
The `key` commands, which read keys from a wallet or move them, name it
with `--wallet`, or else the one configured for the owner they are about:
among the user's own wallets and those `osheaf.json` hints for it, the
first that holds its keys ([chapter 9](09-wallets.md)); `owner` is None for a
command about no owner yet, which takes the first wallet configured. Either way, the repositories of the archive are given to
the wallet, which refuses them.

    # in the security level and the wallet of a command:
    def archive_repositories():
        from . import wallet
        return wallet.archive_repositories(ROOT, ARCHIVE.get("baseUrl"))


    def configured_wallet(owner=None):
        """The wallet configured for OWNER (OPENSHEAF_WALLET, the user's configuration, or "keys" of
        osheaf.json), or None."""
        from . import wallet
        try:
            return wallet.configured(ARCHIVE.get("keys"), forbidden=archive_repositories(), owner=owner)
        except wallet.WalletError as e:
            stop(str(e))


    def level_wallet(args, owner=None):
        """The wallet of the security level --keys (or of --wallet), or None for offline (the default)."""
        from . import wallet
        spec = getattr(args, "keys", None) or getattr(args, "wallet", None) or wallet.OFFLINE
        try:
            if spec == "command":
                w = configured_wallet(owner)
                return w if isinstance(w, wallet.CommandWallet) else wallet.parse(spec)
            return wallet.parse(spec, forbidden=archive_repositories())
        except wallet.WalletError as e:
            stop(str(e))


    def wallet_for(args, owner=None, putting=False):
        """The wallet a command reads or moves keys of OWNER with: that of --wallet (--keys), or the configured
        one; PUTTING (keys are put into it): a wallet that only osheaf.json names is confirmed first."""
        from . import wallet
        w = level_wallet(args, owner)
        if w is None:
            w = configured_wallet(owner)
            if w is not None and putting and wallet.hinted_only(ARCHIVE.get("keys"), owner, w.name):
                print(f"The key wallet {w.name} is named by {CONFIG_NAME} of this archive, which whoever can change "
                      "the archive writes, and not by your own configuration: the keys would be put there.",
                      file=sys.stderr)
                if not confirmed("put", args):
                    stop(f"not confirmed: nothing was put into {w.name} (give --wallet, or add the wallet to "
                         f"{wallet.user_config_path()})")
        if w is None:
            stop("no key wallet: give --wallet github:OWNER/REPO (or command), or configure one in "
                 f'{wallet.user_config_path()}, or in osheaf.json for the owner ("keys": {{"<owner>": {{"wallets": [...]}}}}), '
                 "or in OPENSHEAF_WALLET")
        return w

### The wallet recorded in the configuration

A GitHub wallet given to a command that keeps keys in it, `osheaf init
--new-owner --keys`, `owner init --keys`, `owner rotate --keys` and `key
push --wallet`, is recorded in `osheaf.json` as a hint for the owner,
`"keys": {"<owner>": {"wallets": ["github:OWNER/REPO"]}}`, added to the
wallets hinted already for the owner, unless it is one of them. The
command says so. Since the keys of an owner may be in several wallets, a
hint is never replaced: `osheaf key wallet --remove` removes one. A
command wallet is never recorded
([chapter 9](09-wallets.md)), nor anything at the offline level.

`write_config` writes `osheaf.json` back as the tools write it, and
`ARCHIVE` with it.

    # in the security level and the wallet of a command:
    def write_config(cfg):
        """Write CFG to osheaf.json, and to the settings of this run."""
        write_file(ROOT / CONFIG_NAME, json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
        for k in ("keys", "formerAddresses", "index"):
            if k in cfg:
                ARCHIVE[k] = cfg[k]
            else:
                ARCHIVE.pop(k, None)


    def hinted(cfg, owner, spec, add=True):
        """CFG with the wallet SPEC added to the hints of OWNER (or removed, ADD false)."""
        from . import wallet
        given = dict(cfg.get("keys")) if isinstance(cfg.get("keys"), dict) else {}
        own = [w for w in wallet.hints({owner: given.get(owner)}, owner)]
        own = own + [spec] if add else [w for w in own if w != spec]
        if own:
            given[owner] = {"wallets": own}
        else:
            given.pop(owner, None)
        out = dict(cfg)
        if given:
            out["keys"] = given
        else:
            out.pop("keys", None)
        return out


    def record_wallet(owner, spec):
        """Record the GitHub wallet SPEC as a hint for OWNER in osheaf.json, unless it is hinted already."""
        from . import wallet
        spec = (spec or "").strip()
        if not spec.startswith("github:") or ROOT is None or not (ROOT / CONFIG_NAME).exists():
            return
        cfg = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
        if spec in wallet.hints(cfg.get("keys"), owner):
            return
        write_config(hinted(cfg, owner, spec))
        print(f"The key wallet {spec} is recorded in {CONFIG_NAME} for {names.short(owner)} "
              f"(osheaf key wallet --remove {spec} removes it).")

### Exporting and confirming

The files are written by `keys.export_rotation_keys`, which refuses a
folder inside the archive (section 15.4), and each is read back at once,
with the passphrase, so that a file that cannot be decrypted is found now,
not when the key is needed. For each key the tool prints the file and the
four characters that check its seed (the check of its printed sheet). The
owner confirms by typing these checks back, after putting the files or
sheets away; `--yes` skips the question, for scripts. A refusal writes
nothing to the key log: the files exported are those of keys never
committed, and can be deleted. `--print` also prints each key as a sheet,
to keep on paper; it goes with `--export` only, and is refused without it
(the keys kept in a wallet are not exported, and it used to print nothing,
silently).

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
            stop(str(e))
        lock = "locked with your passphrase" if secret else "with no lock (--no-passphrase)"
        print(f"Exported {plural(len(rotation), 'rotation key')} of {names.short(owner)} to {paths[0].parent}, "
              f"{lock}:")
        for key, path in zip(rotation, paths):
            print(f"  {key_label(keys.ROTATION, key.did)}  {path.name}  check {keys.sheet_check(key.seed)}")
        if getattr(args, "print", False):
            for key in rotation:
                print(keys.rotation_key_sheet(key, owner, version))
        if getattr(args, "yes", False):
            return
        print("Put the files (or the printed sheets) away, apart from this computer and from each other.")
        for key, path in zip(rotation, paths):
            typed = input(f"Type the check of {path.name} to confirm: ").strip().upper()
            if typed != keys.sheet_check(key.seed):
                stop("not confirmed: nothing was written to the key log (the exported files may be deleted)")

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
        warn(wallet.risk(w.name, owner))
        unlocked = unlocked_passkeys(owner)
        secret = wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
        try:
            w.check_writable()
            todo = [(key, keys.ROTATION, version) for key in rotation]
            todo += [(key, keys.CURRENT, v) for key, v in current if w.read(owner, key.id, keys.CURRENT) is None]
            n = len(todo)
            print(f"Saving {the_keys(n)} of {names.short(owner)} to {w.name}…", file=sys.stderr)
            for i, (key, kind, v) in enumerate(todo, 1):
                plain = kind == keys.CURRENT and getattr(args, "plain_current", False)
                wallet.put_key(w, owner, key, kind, v, None if plain else secret, unlocked)
                print(f"  {i}/{n} {key_label(kind, key.did)}  saved", file=sys.stderr)
        except wallet.WalletError as e:
            stop(f"{e}: nothing was written to the key log")
        enroll_hint(owner, unlocked)

### How the commands speak

The commands of owners and keys speak in one plain style. A result is a
full sentence, with a capital and a period, on the standard output; a line
of progress ends with "…", and the steps under it are indented, numbered
when they are counted (`  2/4 rotation key  z6MkgYBn…uTGo  saved`), on the
standard error, with the warnings (`Warning: …`) and the statements of
risk. Owners and keys are named in their short form (`names.short`, the
first 8 and last 4 characters) where they only tell which is which, and in
full where the user may have to copy them: the owner made, the `did:key` of
a new key, the current keys of a new version of the key log. What the code
calls a *wrap* is a *lock* for the user: a key in a wallet has a
passphrase lock, and a passkey lock for each passkey enrolled; the words
wrap, envelope and key-encryption key stay in the code. Before it removes
anything, a command lists what will change and asks the user to type a
word, always as "Type forget to confirm:" (`--yes` skips it, for scripts);
a command of several steps ends with a summary that starts with "Done:".
An error ends the command with one sentence, through `stop`: its first
word is capitalized unless it is a name (an option, a file, a `did:key`, a
wallet such as `command`, or a program such as `gh`).

    # in keep keys in a wallet:
    def lock_words(locks):
        """What opens a key with the locks LOCKS (wallet.locks), for a person: "your passkey
        (unlock.opensheaf.org) and your passphrase"."""
        words = [f"your {x}" for x in locks if x.startswith("passkey")] + \
                [f"your {x}" for x in locks if not x.startswith("passkey")]
        return " and ".join(words) or "no passphrase or passkey (they have no lock)"


    def kept_where(args, w):
        """Where the new rotation keys are kept: the folder of --export, the wallet W, or both."""
        places = ([str(Path(args.export).resolve())] if getattr(args, "export", None) else []) + \
                 ([w.name] if w is not None else [])
        return " and in ".join(places)


    def rotation_line(n, next_threshold, where, new=False):
        """The line of a summary on the rotation keys: N (NEW) of them, kept in WHERE."""
        verb = "signs" if next_threshold == 1 else "sign"
        more = "" if n == 1 else f"; any {next_threshold} of them {verb} the next version of the key log"
        return f"  rotation keys  {n}{' new' if new else ''}, kept in {where}{more}"


    def plural(n, noun):
        """N NOUN, in the singular or the plural ("1 key", "2 keys")."""
        return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


    def the_keys(n, noun="key"):
        """"the key" or "the N keys"."""
        return f"the {noun}" if n == 1 else f"the {n} {noun}s"


    def key_label(kind, did):
        """A key in a line of progress: its kind and its short did:key, in columns."""
        return f"{kind + ' key':<14}{names.short(did)}"


    LOWER_NAMES = ("gh", "osheaf", "command")


    def sentence(text):
        """TEXT as a sentence: its first word capitalized, unless it is a name (of a program, a wallet,
        an owner, a key, an option or a file), and a final period."""
        m = re.match(r"([a-z][a-z']{0,14})(?=[ ,;])", text)
        if m and m.group(1) not in LOWER_NAMES:
            text = text[0].upper() + text[1:]
        return text if text.endswith((".", "?", "!", ":", "…")) else text + "."


    def stop(text):
        """End the command with the message TEXT, a sentence."""
        sys.exit(sentence(text))


    def warn(text):
        """Say TEXT, a warning, on the standard error."""
        print("Warning: " + sentence(text), file=sys.stderr)


    def confirmed(word, args=None):
        """Whether the user typed WORD to confirm what was listed (always, with --yes)."""
        if args is not None and getattr(args, "yes", False):
            return True
        return input(f"Type {word} to confirm: ").strip() == word


    def store_name(store):
        """Where a current key kept in STORE is, for a person."""
        return STORE_NAMES.get(store, store)


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
                stop(f"{f}: {e}")
            if rk.owner not in (None, owner):
                stop(f"{f} is a rotation key of {names.short(rk.owner)}, not of {names.short(owner)}")
            out.append(rk.key)
        return out

Without `--rotation-key`, the rotation keys come from a wallet: that of
`--keys` (or `--wallet`) when one is given, which wins, or else the one
configured. A wallet given explicitly that does not hold enough of them
(the new wallet of a rotation that moves the keys elsewhere) is followed by
the one configured, and the command says so. The keys needed are those whose
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
        tried = [w for w in (level_wallet(args, owner), configured_wallet(owner)) if w is not None]
        tried = [w for k, w in enumerate(tried) if w.name not in {x.name for x in tried[:k]}]
        if not tried:
            stop("give the rotation keys that sign the new version of the key log (--rotation-key FILE), "
                 "or the wallet that keeps them (--keys github:OWNER/REPO)")
        need = prev.keys["nextThreshold"]
        for k, w in enumerate(tried):
            out = wallet_rotation_keys(w, owner, prev)
            if len(out) >= need:
                print(f"Read {plural(len(out), 'rotation key')} of v{prev.number} from {w.name}.", file=sys.stderr)
                return out, w
            if k + 1 < len(tried):
                print(f"{w.name} holds {len(out)} of them: reading from {tried[k + 1].name}, the wallet "
                      "configured", file=sys.stderr)
        stop(f"the wallet {w.name} holds {len(out)} of the rotation keys of v{prev.number} of the key log of "
             f"{names.short(owner)}, and {need} sign the next version: give them with --rotation-key FILE")


    def wallet_rotation_keys(w, owner, prev):
        """The rotation keys of PREV's next that the wallet W holds, read until nextThreshold of them."""
        from . import wallet
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
            stop(str(e))
        return out

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
    MOVED_UP = ("Moved up to the maximum security level: the rotation keys kept in {w} are used up and sign "
                "nothing more (section 6.2), and the new ones are kept offline only. To remove the used ones "
                "from {w}: osheaf key forget --from-wallet --used. The current keys kept in {w} still sign until "
                "a version of the key log retires them (osheaf owner rotate --retire DID); then osheaf key "
                "forget --from-wallet DID removes them.")


    def owner_rotate(args, exposed=()):
        """A new version of the key log changing the current keys (section 6.2) or exposing
        some (section 6.3), signed by rotation keys, committing new rotation keys."""
        owner, log = owner_of(args)
        who = names.short(owner)
        prev = log.latest()
        if prev is None:
            stop(f"the owner {who} has ended (section 6.3): its key log takes no new version")
        if getattr(args, "print", False) and not getattr(args, "export", None):
            stop("--print prints the sheets of the rotation keys exported with --export DIR: give "
                 "--export DIR with it (in a wallet, the keys are not exported, and no sheet is printed)")
        w = level_wallet(args, owner)
        if w is None and not getattr(args, "export", None):
            stop("give --export DIR, a folder outside the archive where the new rotation keys are written "
                 "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
        if w is not None and getattr(args, "no_passphrase", False):
            stop("--no-passphrase: the keys in a wallet are always locked with a passphrase")
        signers, source = rotation_signers(args, owner, prev)
        n_rot = int(getattr(args, "rotation", None) or len(prev.keys["next"]))
        next_threshold = int(getattr(args, "next_threshold", None) or min(prev.keys["nextThreshold"], n_rot))
        for did in list(getattr(args, "add", None) or []) + list(getattr(args, "retire", None) or []) + list(exposed):
            try:
                names.did_key_public(did)
            except ValueError:
                stop(f"not a did:key URI of an Ed25519 key: {did}")
        new = [keys.new_key() for _ in range(n_rot)]
        try:
            v = log.rotate(signers, next_keys=new, next_threshold=next_threshold,
                           add=getattr(args, "add", None) or (), retire=getattr(args, "retire", None) or (),
                           exposed=exposed, threshold=getattr(args, "threshold", None),
                           message=getattr(args, "message", None) or ("Keys exposed" if exposed else "Keys changed"),
                           user=depositor())
        except owners.OwnerError as e:
            stop(str(e))
        if next_threshold == 1:
            warn(owners.SINGLE_ROTATION_RISK)
        if getattr(args, "export", None):
            export_and_confirm(new, owner, v.number, args)
        if w is not None:
            try:
                here = keys.current_keys(owner, v.keys["keys"])
            except keys.KeyStoreError:
                here = []
            keep_in_wallet(w, owner, new, v.number, args, current=[(k, version_listing(log, k.did)) for k in here])
        owners.write_key_log(unlinked(obj_dir(log.id)), log)
        write_discovery()
        print(f"Done: v{v.number} of the key log of {who}, signed by {plural(len(signers), 'rotation key')} "
              f"of v{prev.number}:")
        for did in v.keys["keys"]:
            print(f"  current key    {did}")
        for did in exposed:
            print(f"  exposed key    {did}")
        print(rotation_line(n_rot, next_threshold, kept_where(args, w), new=True))
        if exposed:
            print("What an exposed key alone signed is contested (section 7.3): osheaf sign signs it again.")
        if source is not None and w is None:
            print(MOVED_UP.format(w=source.name), file=sys.stderr)
        if w is not None:
            record_wallet(owner, getattr(args, "keys", None))


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
        who = names.short(owner)
        successor = getattr(args, "successor", None)
        if successor is not None and not names.OWNER_NAME.match(successor):
            stop(f"the successor is an owner name: {successor}")
        if log.latest() is None:
            stop(f"the owner {who} has ended (section 6.3): its key log takes no new version")
        signers, _ = rotation_signers(args, owner, log.latest())
        try:
            v = log.end(signers, successor=successor, exposed=getattr(args, "expose", None) or (),
                        message=getattr(args, "message", None) or "Owner ended", user=depositor())
        except owners.OwnerError as e:
            stop(str(e))
        owners.write_key_log(unlinked(obj_dir(log.id)), log)
        write_discovery()
        print(f"Done: the owner {who} has ended, at v{v.number} of its key log" +
              (f"; its successor is {successor}." if successor else "."))

Completing an interrupted write
-------------------------------

A write of the key log interrupted before its root inventory was replaced
leaves an orphan version after the head, and the key log takes no new
version until it is settled (the chapter on [owners](06-owners.md) says
why: a different version of the same number, signed by the same rotation
keys, would fork it). `owner complete` settles it: a signed orphan that
passes the checks becomes the head, an unsigned one is removed, and a
signed one that fails the checks is left for a person, with the reason.

    # in end an owner:
    def owner_complete(args):
        """Settle a version of the key log that an interrupted write left after its head."""
        owner, log = owner_of(args)
        if log.orphan is None:
            print(f"The key log of {names.short(owner)} has no version written after its head: nothing to do.")
            return
        n = log.orphan.number
        try:
            done = owners.complete_orphan(unlinked(obj_dir(log.id)))
        except owners.OwnerError as e:
            stop(str(e))
        write_discovery()
        print(f"Done: v{n} of the key log of {names.short(owner)} "
              + ("is completed: it is the head." if done == "completed"
                 else "carried no signature, and is removed."))

Showing
-------

`owner show` describes the key log, version by version, with its current
keys, its end and its exposed keys, and its findings (section 14.3), and
marks the current keys that this computer holds. When the owner names a
keeper, it reads the keeper's place and says whether the keeper confirms
the link (section 6.6; `keeper_link` in the chapter on
[owners](06-owners.md)); `--offline` leaves the network alone, and a
place that cannot be read leaves the link not checked:

```
Owner         em4v3kp5…(the full name)
Keeper        https://orcid.org/0000-0002-4014-2949  confirmed (ORCID record links the owner)
Key log       v1  20ac7d88772cd510  1 current key, 3 rotation keys (any 2 sign the next version)
              v2  0900f00f39defb0e  2 current keys (any 1 signs), 3 rotation keys (any 2 sign the next version)
Current keys  did:key:z6MkpZ85…  (on this computer)
              did:key:z6MkgYBn…
```

    # in show an owner:
    def owner_show(args):
        owner, log = owner_of(args)
        latest, here = log.latest(), []
        if latest is not None:
            try:
                here = [k.did for k in keys.current_keys(owner, latest.keys["keys"])]
            except keys.KeyStoreError as e:
                warn(str(e))
        if getattr(args, "offline", False):
            link = owners.KeeperLink(owners.keeper_of(log), owners.NOT_CHECKED, "offline: --offline given")
        else:
            link = owners.keeper_link(log)
        for line in owners.describe(log, here, link):
            print(line)

A new current key
-----------------

A new device makes its own current key, never copied from another
(section 6.2): `osheaf key new` makes it, keeps it in the credential store
under the owner name, and prints its `did:key`, which a new version of the
key log adds to the current keys (`osheaf owner rotate --add`), with the
rotation keys kept apart. Until then it signs nothing. With
`OPENSHEAF_KEY_STORE=none`, which keeps no key on the device, it refuses.
`--owner` must be an owner name, as for `osheaf key import`: it names the
store the key goes to.

    # in a new current key for this device:
    def key_new(args):
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        if not isinstance(owner, str) or not names.OWNER_NAME.match(owner):
            stop(f"--owner: an owner name, not {owner!r}")
        if not keys.kept_on_device():
            stop(NOT_KEPT)
        key = keys.new_key()
        try:
            store = keys.store_current_key(owner, key)
        except (keys.KeyStoreError, OSError) as e:
            stop(str(e))
        print(f"New current key of {names.short(owner)}, kept in {store_name(store)}:")
        print(f"  {key.did}")
        print(f"It signs once a version of the key log adds it: osheaf owner rotate --add {key.did} "
              "--rotation-key FILE ... --export DIR")
        return key

Key wallets
-----------

Four commands move current keys between this device and a wallet
([chapter 9](09-wallets.md)), and show what a wallet holds.

`osheaf key push` puts the current keys of this device into the wallet:
those of the latest version of the key log, or those named. A key made on
a new device with `osheaf key new`, and not yet listed, is pushed by name.
A key the wallet holds already is left as it is, and when it holds all of
them nothing is asked. The current keys are locked with the passphrase
(and with the passkey, if one has opened the keys in this command) unless
`--plain-current`; the risk is stated, and the last line says how they are
locked.

    # in the commands of key wallets:
    def key_push(args):
        """Put the current keys of this device into the wallet."""
        from . import wallet
        owner, log = owner_of(args)
        who = names.short(owner)
        latest = log.latest()
        if latest is None:
            stop(f"the owner {who} has ended (section 6.3)")
        w = wallet_for(args, owner, putting=True)
        dids = list(getattr(args, "did", None) or latest.keys["keys"])
        try:
            here = keys.current_keys(owner, dids)
        except keys.KeyStoreError as e:
            stop(str(e))
        if not here:
            stop(f"this computer holds none of the keys {', '.join(names.short(d) for d in dids)} of {who}")
        try:
            w.check_writable()
            there = {k.did for k in here if w.read(owner, k.id, keys.CURRENT) is not None}
        except wallet.WalletError as e:
            stop(str(e))
        n = len(here)
        if len(there) == n:
            print(f"{'The current key' if n == 1 else f'The {n} current keys'} of {who} "
                  f"{'is' if n == 1 else 'are'} already in {w.name}.")
            record_wallet(owner, getattr(args, "wallet", None))
            return
        warn(wallet.risk(w.name, owner))
        plain = getattr(args, "plain_current", False)
        unlocked = [] if plain else unlocked_passkeys(owner)
        secret = None if plain else wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
        print(f"Saving {the_keys(n, 'current key')} of {who} to {w.name}…", file=sys.stderr)
        try:
            for i, key in enumerate(here, 1):
                if key.did in there:
                    print(f"  {i}/{n} {key_label(keys.CURRENT, key.did)}  already there", file=sys.stderr)
                    continue
                wallet.put_key(w, owner, key, keys.CURRENT, version_listing(log, key.did), secret, unlocked)
                print(f"  {i}/{n} {key_label(keys.CURRENT, key.did)}  saved", file=sys.stderr)
        except wallet.WalletError as e:
            stop(str(e))
        saved = n - len(there)
        lock = "with no lock (--plain-current)" if plain else \
            "locked with your passkey and your passphrase" if unlocked else "locked with your passphrase"
        print(f"Done: {plural(saved, 'current key')} of {who} saved to {w.name}, {lock}.")
        record_wallet(owner, getattr(args, "wallet", None))

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
            stop(f"the owner {names.short(owner)} has ended (section 6.3)")
        w = wallet_for(args, owner)
        if not keys.kept_on_device():
            print(not_kept(w, owner))
            return
        try:
            have = {k.did for k in keys.current_keys(owner, latest.keys["keys"])}
        except keys.KeyStoreError as e:
            stop(str(e))
        pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
        print(pull_summary(w, owner, latest, have, pulled))


    STORE_NAMES = {"keyring": "the keychain" if sys.platform == "darwin" else "the system keyring",
                   "security": "the keychain", "file": "a file of this computer",
                   keys.NONE: "memory, for this command only"}
    NOT_KEPT = (f"No current key is kept on this computer ({keys.KEY_STORE}=none), so a new one would be "
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
                    stop(f"the wallet {w.name} holds another key than {did} under its name")
                store = keys.store_current_key(owner, key)
                print(f"  {key_label(keys.CURRENT, did)}  kept in {store_name(store)}", file=sys.stderr)
                out.append((key, store))
        except (wallet.WalletError, keys.KeyStoreError, OSError) as e:
            stop(str(e))
        return out


    def pull_summary(w, owner, latest, have, pulled):
        """The sentence that says what a pull did: HAVE, the did:keys held before, PULLED, [(key, store)]."""
        total, held, who = len(latest.keys["keys"]), len(have) + len(pulled), names.short(owner)
        if pulled:
            stores = sorted({store_name(s) for _, s in pulled})
            out = f"Pulled {plural(len(pulled), 'current key')} of {who} from {w.name} into {' and '.join(stores)}."
            return out + (f" This computer holds {held} of its {total} current keys." if held < total else "")
        if held == total:
            return (f"The current key of {who} is already on this computer." if total == 1
                    else f"The {total} current keys of {who} are already on this computer.")
        return (f"The wallet {w.name} holds no current key of {who} that this computer lacks: this computer "
                f"holds {held} of the {total}.")


    def pull_from_wallet(owner, latest, found):
        """FOUND, the current keys of OWNER on this device, with those the configured wallet adds."""
        w = configured_wallet(owner)
        if w is None:
            return found
        held = {k.did for k in found}
        return found + [k for k, _ in pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in held])]

`osheaf key list` shows what the wallet holds, as a table: for each key,
its owner, its kind, its `did:key` (both short), the version of the key log
that commits it, and its locks (`passphrase`, and `passkey (RP)` for the
passkeys of each relying party), as the files say, without decrypting
them. No secret is shown:

```
The wallet github:mgubi/opensheaf-keys holds 4 keys:
  Owner          Kind      Key            Version  Locks
  em4v3kp5…gora  current   z6MkpZ85…Svuy  v1       passphrase, passkey (unlock.opensheaf.org)
  em4v3kp5…gora  rotation  z6MkgYBn…uTGo  v1       passphrase, passkey (unlock.opensheaf.org)
  ...
```

    # in the commands of key wallets:
    def key_list(args):
        """What the wallet holds, as a table: the owner, kind, key, version and locks of each key."""
        from . import wallet
        owner = getattr(args, "owner", None)
        w = wallet_for(args, owner or ARCHIVE.get("owner"))
        try:
            rows = wallet.listing(w, owner)
        except wallet.WalletError as e:
            stop(str(e))
        whose = f" of {names.short(owner)}" if owner else ""
        if not rows:
            print(f"The wallet {w.name} holds no key{whose}.")
            return
        print(f"The wallet {w.name} holds {plural(len(rows), 'key')}{whose}:")
        table = [("Owner", "Kind", "Key", "Version", "Locks")] + [
            (names.short(o), kind, names.short(did), version or "-", ", ".join(locks) or "none")
            for o, _, kind, did, version, locks in rows]
        widths = [max(len(r[i]) for r in table) for i in range(4)]
        for r in table:
            print("  " + "  ".join(c.ljust(n) for c, n in zip(r, widths)) + "  " + r[4])

Two commands say where keys are looked for, one for each side of the
many to many of [chapter 9](09-wallets.md). `osheaf key wallet` is about
an owner (`--owner`, by default the archive's) in this archive: it lists
the wallets in which its keys are looked for, in order, and where each is
named (the environment, `osheaf.json`, the user's file); `--add` records
a GitHub wallet as a hint for the owner in `osheaf.json`, `--remove`
removes one. Only an owner the archive hosts gets hints, and only GitHub
wallets that are not repositories of the archive. This command reads no
wallet.

```
$ osheaf key wallet
The keys of em4v3kp5...gora are looked for in, in order:
  github:mgubi/opensheaf-keys       osheaf.json
  github:institute/opensheaf-keys   /Users/me/.config/opensheaf/config.json
$ osheaf key wallet --owner q7tz2m4x... --add github:jdoe/opensheaf-keys
Done: osheaf.json hints github:jdoe/opensheaf-keys for q7tz2m4x...b3ka.
```

    # in the commands of key wallets:
    def key_wallet(args):
        """The wallets in which the keys of the owner are looked for, in order; --add or --remove a hint
        for the owner in osheaf.json."""
        from . import wallet
        owner = key_owner(args)
        who = names.short(owner)
        add, remove = getattr(args, "add", None), getattr(args, "remove", None)
        if add and remove:
            stop("give --add or --remove, not both")
        if not add and not remove:
            try:
                found = wallet.candidates(ARCHIVE.get("keys"), owner)
            except wallet.WalletError as e:
                stop(str(e))
            if not found:
                print(f"No key wallet is configured for {who}: osheaf key wallet --add github:OWNER/REPO hints "
                      f"one in {CONFIG_NAME}, osheaf key wallets --add github:OWNER/REPO adds one to yours.")
                return
            print(f"The keys of {who} are looked for in, in order:")
            width = max(len(w) for w, _ in found)
            for w, where in found:
                print(f"  {w.ljust(width)}  {where}")
            return
        if ROOT is None:
            stop(f"run the command in an archive: the hints are in its {CONFIG_NAME}")
        if owner not in archive_owners():
            stop(f"{who} is not an owner of this archive")
        cfg = json.loads((ROOT / CONFIG_NAME).read_text(encoding="utf-8"))
        own = wallet.hints({owner: (cfg.get("keys") or {}).get(owner)}, owner) \
            if isinstance(cfg.get("keys"), dict) else []
        if remove:
            if remove not in own:
                print(f"{CONFIG_NAME} hints no {remove} for {who}.")
                return
            write_config(hinted(cfg, owner, remove, add=False))
            print(f"Done: {CONFIG_NAME} no longer hints {remove} for {who}.")
            return
        if not add.startswith("github:"):
            stop(f"{CONFIG_NAME} names GitHub wallets only, github:OWNER/REPO: a command wallet is configured "
                 f"in {wallet.user_config_path()} or in {wallet.WALLET}")
        try:
            w = wallet.parse(add)
        except wallet.WalletError as e:
            stop(str(e))
        if w.repo.lower() in archive_repositories():
            stop(f"{w.repo} is a repository of this archive, which is public: a key wallet is a private "
                 "repository of its own")
        if add in own:
            print(f"{CONFIG_NAME} hints {add} for {who} already.")
            return
        write_config(hinted(cfg, owner, add))
        print(f"Done: {CONFIG_NAME} hints {add} for {who}.")

`osheaf key wallets` is about the person: it lists the wallets they read,
`wallets` of their configuration file ([chapter 9](09-wallets.md)), with,
in an archive, the wallets it hints, and, first, that of
`OPENSHEAF_WALLET`; and for each, the owners whose keys it holds, how many,
and how they are locked: by the passphrase, by how many passkeys (one per
person of a group sharing the owner, or per device family), or not at all.
It reads each wallet, never a secret: the lines of the key files before
their seeds. A wallet it cannot read is said so, and the others are
listed. `--add` and `--remove` change the list of the configuration file,
keeping everything else in it; a wallet added is checked to be named
well, not read.

```
$ osheaf key wallets
github:mgubi/opensheaf-keys (/Users/me/.config/opensheaf/config.json):
  em4v3kp5...gora  4 keys  passphrase, 2 passkeys
github:institute/opensheaf-keys (osheaf.json):
  q7tz2m4x...b3ka  2 keys  passphrase, 3 passkeys
  em4v3kp5...gora  1 key   passphrase
```

    # in the commands of key wallets:
    def key_wallets(args):
        """The wallets of the person (and of the archive's hints), each with the owners whose keys it holds
        and their locks; --add or --remove a wallet of the configuration file."""
        from . import wallet
        add, remove = getattr(args, "add", None), getattr(args, "remove", None)
        if add and remove:
            stop("give --add or --remove, not both")
        if add or remove:
            return change_user_wallets(add, remove)
        try:
            listed = [(w, wallet.WALLET) for w in [os.environ.get(wallet.WALLET, "").strip()] if w]
            for o in archive_owners() if ARCHIVE.get("owner") else []:
                listed += [(w, CONFIG_NAME) for w in wallet.hints(ARCHIVE.get("keys"), o)]
            listed += [(w, str(wallet.user_config_path())) for w in wallet.user_wallets()]
        except wallet.WalletError as e:
            stop(str(e))
        seen, rows = set(), []
        for spec, where in listed:
            if spec not in seen and not spec.startswith("{"):
                seen.add(spec)
                rows.append((spec, where))
        if not rows:
            print("No key wallet is configured: osheaf key wallets --add github:OWNER/REPO adds one.")
            return
        for spec, where in rows:
            print(f"{spec} ({where}):")
            try:
                w = wallet.parse(spec, forbidden=archive_repositories())
                held = wallet.owners_held(w) if w is not None else []
            except wallet.WalletError as e:
                print(f"  cannot be read: {e}")
                continue
            if not held:
                print("  holds no key")
            for o, n, lock in held:
                print(f"  {names.short(o)}  {plural(n, 'key').ljust(7)} {lock}")


    def change_user_wallets(add, remove):
        """Add the wallet ADD to the wallets of the configuration file, or remove REMOVE."""
        from . import wallet
        path = wallet.user_config_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except (OSError, ValueError) as e:
            stop(f"{path}: {e}")
        data = data if isinstance(data, dict) else {}
        listed = [w for w in data.get("wallets", []) if isinstance(w, str)] \
            if isinstance(data.get("wallets"), list) else []
        if add:
            try:
                wallet.parse(add)
            except wallet.WalletError as e:
                stop(str(e))
            if add in ("", wallet.OFFLINE) or add.startswith("{"):
                stop("a wallet is github:OWNER/REPO or command")
            if add in listed:
                print(f"{add} is one of your wallets already.")
                return
            data["wallets"] = listed + [add]
        else:
            if remove not in listed:
                old = (data.get("keys") or {}).get("wallet") if isinstance(data.get("keys"), dict) else None
                stop(f'{remove} is named by "keys" of {path}: edit it there' if remove == old
                     else f"{remove} is not one of your wallets")
            data["wallets"] = [w for w in listed if w != remove]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Done: {add or remove} is {'added to' if add else 'removed from'} your wallets ({path}).")

Unlocking with a passkey
------------------------

The passphrase of a wallet can be left to a passkey ([chapter 7](07-keys.md),
[chapter 9](09-wallets.md)): enrolled once, it opens the keys of the owner
with Touch ID, on every device the passkey reaches (all the Macs of one
iCloud Keychain), through the page `https://unlock.opensheaf.org/`.

Whenever a command reads a key of the wallet that a passkey can unlock
(`unlock_key`, which pulling current keys and reading rotation keys call),
`passkey_keks` asks the browser, once per command and owner, and keeps the
key-encryption key in memory until the command ends; the PRF secret is
never stored, and the key read is then kept on this device as before. The
passphrase is asked instead when the browser gives nothing: an error of
the page, no answer in two minutes, or Ctrl-C at the prompt; or never,
when `OPENSHEAF_UNLOCK` is `passphrase`, or when `OPENSHEAF_PASSPHRASE`
holds the passphrase (a script, continuous integration: no browser there).

What the browser sends is not trusted until it has opened a key: the
key-encryption key derived from the answer is kept for the rest of the
command only for a credential one of whose wraps it unwraps. An answer
that names no credential is tried against the wraps of each credential
asked for, and kept for the one it opens; an answer that opens nothing is
a failure, and the passphrase is asked. Otherwise a forged answer, sent to
the listener by another program, would be kept as "unlocked", and the
keys that the command writes next would get a wrap under the forger's
secret.

Only the passkeys of the relying party of the page, `unlock.opensheaf.org`,
are asked for. Wraps of the passkeys made on `opensheaf.org`, the first
relying party (chapter 7), are left to the passphrase, and the command
says once how to move them: `osheaf key enroll --new-passkey`, then
`osheaf key forget --rp opensheaf.org`.

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
        if any(p.rp == keys.OLD_PASSKEY_RP for p in wraps) and owner not in _ASKED.setdefault("old rp", set()):
            _ASKED["old rp"].add(owner)
            print(f"A passkey of {names.short(owner)} was enrolled on {keys.OLD_PASSKEY_RP}, which osheaf no longer "
                  f"asks: run osheaf key enroll --new-passkey to move it to {keys.PASSKEY_RP} (then osheaf key "
                  f"forget --rp {keys.OLD_PASSKEY_RP}).", file=sys.stderr)
        wraps = [p for p in wraps if p.rp == keys.PASSKEY_RP]
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
                stop(f"the passkey did not unlock the keys of {names.short(owner)}: {e}")
            print(f"The passkey did not open the keys ({e}): osheaf asks for the passphrase instead.",
                  file=sys.stderr)
            return None
        kek = keys.passkey_kek(prf)
        opened = [c for c in ([cred] if cred else creds) if any(p.cred == c and p.opens(kek) for p in wraps)]
        if not opened:
            failed.add(owner)
            if force:
                stop(f"the passkey's answer opens no key of {names.short(owner)}: nothing was unlocked")
            print("The passkey's answer opens no key: osheaf asks for the passphrase instead.", file=sys.stderr)
            return None
        for c in opened[:1]:
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
        if os.environ.get(PASSPHRASE) or w.name in _ASKED.get("passphrases", {}):
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
            stop(f"{e}: this is not the passphrase of the keys of {names.short(owner)} in {w.name}")
        return secret


    def enroll_hint(owner, unlocked):
        if not unlocked and owner in _ASKED.get("seen", set()):
            print(f"The new keys of {names.short(owner)} open with your passphrase only: run osheaf key enroll "
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
A key kept unencrypted (`--plain-current`) is left as it is. Only the
passkeys of `unlock.opensheaf.org` count as enrolled: an owner whose keys
open only with a passkey of `opensheaf.org` gets a new passkey.

A new passkey is checked before anything is written under it. The page
is told the credentials the owner has already, and asks WebAuthn to
exclude them, so that enrolling again on the provider that holds one
fails, rather than replace it; and once the page has created the passkey
and sent its secret, the command opens the page a second time, to unlock
with the new credential alone, and goes on only if the secret is the same:
an answer that did not come from that passkey is found then, and nothing
is changed. Opening each
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
            stop(str(e))


    def encrypted_entries(w, owner):
        out = [(kid, t) for kid, t in wallet_entries(w, owner)
               if any(x.startswith("encryption ") and x.split()[1:2] != ["none"] for x in t.splitlines())]
        if not out:
            stop(f"the wallet {w.name} holds no key of {names.short(owner)} locked with a passphrase")
        return out


    def key_owner(args):
        owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
        if not owner or not names.OWNER_NAME.match(owner):
            stop("give --owner NAME, or run the command in an archive")
        return owner


    def key_enroll(args):
        """Let a passkey open the keys of the owner in the wallet."""
        import hmac
        from . import passkey, wallet
        owner = key_owner(args)
        w = wallet_for(args, owner)
        _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
        try:
            w.check_writable()
        except wallet.WalletError as e:
            stop(str(e))
        who = names.short(owner)
        print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
        entries = encrypted_entries(w, owner)
        salt = keys.passkey_salt(owner)
        known = list(dict.fromkeys(p.cred for _, t in entries for p in keys.passkeys_of(t)
                                   if p.salt == salt and p.rp == keys.PASSKEY_RP))
        new = bool(getattr(args, "new_passkey", False)) or not known
        todo = entries if new else [(kid, t) for kid, t in entries
                                    if not {p.cred for p in keys.passkeys_of(t)} & set(known)]
        if not todo:
            print(f"Every key of {who} in {w.name} already opens with your passkey.")
            return
        secret = passphrase(confirm=False, where=w.name)
        n = len(todo)
        print(f"Opening {the_keys(n)} of {who} in {w.name} with the passphrase…", file=sys.stderr)
        for i, (kid, t) in enumerate(todo, 1):
            try:
                rk = keys.read_key(t, secret)
            except keys.KeyStoreError as e:
                stop(f"{w.name} {kid}: {e}: nothing was changed")
            print(f"  {i}/{n} {key_label(rk.kind, rk.key.did)}  opened", file=sys.stderr)
        halt = "stop: nothing is changed"
        try:
            if new:
                cred, prf = passkey.enroll(owner, known, no_browser=_ASKED["no_browser"], ctrl_c=halt)
                print("The passkey is made. Once more, to check it…", file=sys.stderr)
                again, prf2 = passkey.unlock(owner, [cred], no_browser=_ASKED["no_browser"], ctrl_c=halt)
                if again not in (None, cred) or not hmac.compare_digest(prf, prf2):
                    stop("the new passkey did not give the same secret twice: nothing was changed")
            else:
                cred, prf = passkey.unlock(owner, known, no_browser=_ASKED["no_browser"], ctrl_c=halt)
        except passkey.UnlockFailed as e:
            stop(f"no passkey: {e}; nothing was changed")
        kek = keys.passkey_kek(prf)
        if not new:
            opened = [c for c in ([cred] if cred else known)
                      if any(_opens(t, c, kek) for _, t in entries if c in {p.cred for p in keys.passkeys_of(t)})]
            if not opened:
                stop("the passkey used does not open the keys it is enrolled for: nothing was changed")
            cred = opened[0]
        unlocked = keys.Passkey(cred, salt, kek=kek)
        print(f"Adding a passkey lock to {the_keys(n)} of {who} in {w.name}…", file=sys.stderr)
        try:
            for i, (kid, _) in enumerate(todo, 1):
                kind, did = wallet.add_passkey(w, owner, kid, secret, unlocked)
                print(f"  {i}/{n} {key_label(kind, did)}  lock added", file=sys.stderr)
        except wallet.WalletError as e:
            stop(str(e))
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
        owner = key_owner(args)
        w = wallet_for(args, owner)
        _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
        who = names.short(owner)
        print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
        entries = [(kid, t) for kid, t in wallet_entries(w, owner) if keys.passkeys_of(t)]
        if not entries:
            stop(f"no key of {who} in {w.name} has a passkey lock: run osheaf key enroll")
        keks = passkey_keks(owner, [p for _, t in entries for p in keys.passkeys_of(t)], force=True)
        if not keks:
            stop(f"no passkey of {who} to unlock with")
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
                stop(str(e))
            pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
            print(pull_summary(w, owner, latest, have, pulled))

A key to and from a password manager
------------------------------------

`osheaf key export --clipboard` copies a current key of this device, as the
text of [chapter 7](07-keys.md), to the clipboard, to be pasted into a note
of a password manager such as the Passwords app of macOS, which keeps it
in the user's iCloud keychain; `--stdout` prints it instead, the one case
in which a command prints a secret on its standard output, since it is
asked for. `--encrypt` encrypts the seed under the passphrase. On the
clipboard, the key is cleared after a minute ([chapter 9](09-wallets.md)),
and the command warns that the clipboard is readable by any program of
the user and may be sent to the user's other devices. The key is
the one named, or the one current key of the latest version of the key log
that this device holds.

    # in a key to and from a password manager:
    def key_export(args):
        """Copy a current key of this device to the clipboard (or print it, --stdout)."""
        from . import wallet
        if not getattr(args, "clipboard", False) and not getattr(args, "stdout", False):
            stop("give --clipboard, or --stdout to print the key")
        owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
        if not owner:
            stop("give --owner NAME, or run the command in an archive")
        who = names.short(owner)
        if getattr(args, "did", None):
            dids = [args.did]
        else:
            latest = key_log(owner).latest() if ROOT is not None and key_log(owner) else None
            if latest is None:
                stop(f"name the key to export, by its did:key (no key log of {who} here)")
            dids = latest.keys["keys"]
        try:
            here = keys.current_keys(owner, dids)
        except keys.KeyStoreError as e:
            stop(str(e))
        if not here:
            stop(f"this computer holds none of the keys {', '.join(names.short(d) for d in dids)} of {who}")
        if len(here) > 1:
            stop(f"this computer holds {len(here)} current keys of {who}: name the one to export by its did:key, "
                 "one of " + ", ".join(k.did for k in here))
        key = here[0]
        locked = getattr(args, "encrypt", False)
        text = keys.key_text(key, owner, keys.CURRENT, passphrase() if locked else None)
        if getattr(args, "stdout", False):
            sys.stdout.write(text)
        else:
            try:
                wallet.to_clipboard(text)
            except wallet.WalletError as e:
                stop(str(e))
            wallet.clear_later(text)
            print(f"The current key {names.short(key.did)} of {who}"
                  f"{', locked with your passphrase,' if locked else ''} is on the clipboard: paste it into a note "
                  f"of your password manager (the Passwords app) within {int(wallet.CLEAR_AFTER)} seconds; then "
                  "osheaf clears the clipboard if it still holds the key.", file=sys.stderr)
            warn("any program of yours can read the clipboard, and Universal Clipboard may send it to your "
                 "other Apple devices nearby")
        warn("a current key kept in a password manager is on every device that it syncs with, while section 6.2 "
             "has one key per device")

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
            stop("give --clipboard or --stdin")
        if not keys.kept_on_device():
            stop(NOT_KEPT)
        try:
            text = wallet.from_clipboard() if args.clipboard else sys.stdin.read()
        except wallet.WalletError as e:
            stop(str(e))
        try:
            try:
                rk = keys.read_key(text)
            except keys.PassphraseNeeded:
                rk = keys.read_key(text, passphrase(confirm=False))
        except keys.KeyStoreError as e:
            stop(str(e))
        if rk.kind != keys.CURRENT:
            stop("a rotation key is never kept on a device: give its file to the command it signs "
                 "(--rotation-key FILE), or keep it in a wallet")
        owner = rk.owner or getattr(args, "owner", None) or ARCHIVE.get("owner")
        if getattr(args, "owner", None) and rk.owner and args.owner != rk.owner:
            stop(f"the key is one of {names.short(rk.owner)}, not of {names.short(args.owner)}")
        if not owner or not names.OWNER_NAME.match(owner):
            stop("the text names no owner: give --owner NAME")
        who = names.short(owner)
        log = key_log(owner) if ROOT is not None else None
        latest = log.latest() if log is not None else None
        if latest is not None and rk.key.did not in latest.keys["keys"]:
            warn(f"{rk.key.did} is not a current key of v{latest.number} of the key log of {who}: it signs "
                 f"nothing until a version adds it (osheaf owner rotate --add {rk.key.did})")
        try:
            if keys.current_keys(owner, [rk.key.did]):
                print(f"The current key {names.short(rk.key.did)} of {who} is already on this computer.")
                return
            store = keys.store_current_key(owner, rk.key)
        except (keys.KeyStoreError, OSError) as e:
            stop(str(e))
        print(f"The current key {names.short(rk.key.did)} of {who} is now kept in {store_name(store)}.")


    def forget_here(owner, dids):
        """Remove the current keys DIDS of OWNER from this computer, and say so; stop if a store
        failed to remove one."""
        failed = []
        for did in dids:
            failed += [(did, store, why) for store, why in keys.forget_current_key(owner, did)]
        if failed:
            stop("not removed from this computer:\n" + "\n".join(
                f"  {names.short(did)} in {store_name(store)}: {why}" for did, store, why in failed))
        if dids:
            print(f"This computer no longer holds {the_keys(len(dids), 'current key')} "
                  f"{', '.join(names.short(d) for d in dids)} of {names.short(owner)}.")

Forgetting a key
----------------

`osheaf key forget DID...` removes current keys from the stores of this
device, a retired key for instance, after listing them, saying which the
latest version of the key log still lists, and the same confirmation as
below (`--yes` for scripts); a store that fails to remove one is reported,
and the command stops rather than say the key is gone. With `--from-wallet`, they are removed
from the wallet too, the one case in which the tools delete anything there;
`--from-wallet --used` removes from the wallet the keys of the owner that the
latest version of its key log no longer needs: current keys it does not
list, and rotation keys it does not commit, used up (section 6.2 asks
that they be destroyed). A rotation key the latest version commits is kept
unless `--force`: without `nextThreshold` of them the owner can never
change its keys (section 6.2). Removing from a wallet lists the keys that
go, and is confirmed by typing `forget` ("Type forget to confirm:"),
unless `--yes`; each key is then removed in turn, and a line "Done: …"
says how many.

`osheaf key forget --passkey CRED` and `--rp RP` remove passkey locks (the
wraps of chapter 7), not keys: those of the credential `CRED`, a passkey
lost or replaced, or those of the relying party `RP`, `opensheaf.org` after
moving to `unlock.opensheaf.org`. Every key of the owner in the wallet that
has such a lock is written back without it, its passphrase lock and its
other locks kept, after the same confirmation; the last line says what
opens the keys now:

```
Removing the opensheaf.org passkey lock from 4 keys of em4v3kp5…gora in github:mgubi/opensheaf-keys:
  current key   z6MkpZ85…Svuy
  rotation key  z6MkgYBn…uTGo
  ...
Type forget to confirm: forget
  1/4 current key   z6MkpZ85…Svuy  lock removed
  ...
Done: the 4 keys open with your passkey (unlock.opensheaf.org) and your passphrase.
```

    # in forget a key:
    def key_forget(args):
        """Remove keys from this device, and with --from-wallet from the wallet; or passkey locks."""
        from . import wallet
        if getattr(args, "passkey", None) or getattr(args, "rp", None):
            return forget_passkey_wraps(args)
        owner, log = owner_of(args)
        who = names.short(owner)
        latest = log.latest()
        listed = set(latest.keys["keys"]) if latest else set()
        committed = {d[:16] for d in latest.keys["next"]} if latest else set()
        dids = list(getattr(args, "did", None) or [])
        if getattr(args, "used", False):
            if not getattr(args, "from_wallet", False) or dids:
                stop("--used goes with --from-wallet, and names no key")
        elif not dids:
            stop("name the keys to forget, by their did:key")
        for did in dids:
            try:
                names.did_key_public(did)
            except ValueError:
                stop(f"not a did:key URI of an Ed25519 key: {did}")
        if not getattr(args, "from_wallet", False):
            print(f"Removing {the_keys(len(dids), 'current key')} of {who} from this computer:", file=sys.stderr)
            for did in dids:
                use = ("a current key of the latest version of the key log: without it, this computer "
                       "may no longer sign" if did in listed else "not a current key of the latest version")
                print(f"  {names.short(did)}  ({use})", file=sys.stderr)
            if not confirmed("forget", args):
                stop("not confirmed: nothing was removed")
            forget_here(owner, dids)
            return
        w = wallet_for(args, owner)
        try:
            rows = wallet.listing(w, owner)
        except wallet.WalletError as e:
            stop(str(e))
        if getattr(args, "used", False):
            gone = [r for r in rows if r[3] not in listed and r[1] not in committed]
        else:
            gone = [r for r in rows if r[3] in dids]
        needed = [r for r in gone if r[1] in committed]
        if needed and not getattr(args, "force", False):
            stop(f"{', '.join(names.short(r[3]) for r in needed)}: "
                 f"{'a rotation key' if len(needed) == 1 else 'rotation keys'} of the latest version of the key log, "
                 "kept (an owner without enough of them to sign the next version can never change its keys, "
                 "section 6.2); --force removes them")
        n = len(gone)
        if gone:
            here = f", and {the_keys(len(dids), 'current key')} from this computer" if dids else ""
            print(f"Removing {plural(n, 'key')} of {who} from {w.name}{here}:", file=sys.stderr)
            for r in gone:
                print(f"  {key_label(r[2], r[3])}", file=sys.stderr)
            if not confirmed("forget", args):
                stop("not confirmed: nothing was removed")
        forget_here(owner, dids)
        if not gone:
            print(f"The wallet {w.name} holds none of these keys of {who}.")
            return
        try:
            for i, (o, kid, kind, did, _, _) in enumerate(gone, 1):
                w.forget(o, kid, kind)
                print(f"  {i}/{n} {key_label(kind, did)}  removed", file=sys.stderr)
        except wallet.WalletError as e:
            stop(str(e))
        print(f"Done: {plural(n, 'key')} of {who} removed from {w.name}.")


    def forget_passkey_wraps(args):
        """Remove the passkey locks (wrap lines) of --passkey CRED or --rp RP from the keys of the owner
        in the wallet."""
        from collections import Counter
        from . import wallet
        cred, rp = getattr(args, "passkey", None), getattr(args, "rp", None)
        if getattr(args, "did", None) or getattr(args, "used", False):
            stop("--passkey and --rp remove passkey locks, and name no key")
        owner = key_owner(args)
        w = wallet_for(args, owner)
        who = names.short(owner)
        try:
            w.check_writable()
        except wallet.WalletError as e:
            stop(str(e))
        todo = []
        for kid, text in wallet_entries(w, owner):
            try:
                new = keys.remove_passkeys(text, cred, rp)
            except keys.KeyStoreError as e:
                stop(f"{w.name} {kid}: {e}: nothing was changed")
            if new.strip() != text.strip():
                todo.append((kid, wallet.describe(text), new))
        what = (f"the {rp} lock of the passkey {cred}" if cred and rp else
                f"the {rp} passkey lock" if rp else f"the lock of the passkey {cred}")
        if not todo:
            print(f"No key of {who} in {w.name} has {what}.")
            return
        n = len(todo)
        print(f"Removing {what} from {plural(n, 'key')} of {who} in {w.name}:", file=sys.stderr)
        for _, f, _ in todo:
            print(f"  {key_label(f.get('kind', '?'), f.get('key', '?'))}", file=sys.stderr)
        if not confirmed("forget", args):
            stop("not confirmed: nothing was removed")
        try:
            for i, (kid, f, new) in enumerate(todo, 1):
                kind = f.get("kind", keys.CURRENT)
                w.write(owner, kid, kind, new)
                if (w.read(owner, kid, kind) or "").strip() != new.strip():
                    raise wallet.WalletError(f"{w.name} did not keep the {kind} key {f.get('key')}")
                print(f"  {i}/{n} {key_label(kind, f.get('key', kid))}  lock removed", file=sys.stderr)
        except wallet.WalletError as e:
            stop(str(e))
        groups = Counter(tuple(wallet.locks(new)) for _, _, new in todo)
        said = [f"{the_keys(k) if len(groups) == 1 else plural(k, 'key')} {'opens' if k == 1 else 'open'} with "
                f"{lock_words(locks)}" for locks, k in groups.items()]
        print("Done: " + "; ".join(said) + ".")

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
            stop(f"{args.id} has no object version {ver}")
        owner = obj_id.split(":")[2]
        who = names.short(owner)
        if owner not in archive_owners():
            stop(f"{args.id} is a line of an owner this archive does not host: only its owner signs it")
        log, latest, signers = signing_keys(owner)
        statuses = line_statuses(d, inv, log)[1]
        status = statuses[int(ver[1:]) - 1]
        if status != sign.CONTESTED:
            stop(f"{args.id} {ver} is {status}: signing again is for a version contested by an exposed key "
                 "(section 7.1)")
        held = set(witnesses_of(d, ver))
        fresh = [k for k in signers if k.did not in log.exposed_keys() and sign.file_name(k.did) not in held]
        if len(fresh) < latest.keys["threshold"]:
            stop(f"this computer holds {plural(len(fresh), 'current key')} of {who} that "
                 f"{'has' if len(fresh) == 1 else 'have'} not signed {ver}, and "
                 f"v{latest.number} of the key log needs {latest.keys['threshold']}")
        dig = names.sha512_hex((d / ver / "inventory.json").read_bytes())
        if not getattr(args, "yes", False):
            print(f"Signing {args.id} {ver} again, with {plural(len(fresh), 'current key')} of {who}:")
            print(f"  document version {doc_version_of(d, inv, ver)}, deposited {inv['versions'][ver]['created']}"
                  + (f": {inv['versions'][ver]['message']}" if inv["versions"][ver].get("message") else ""))
            print(f"Sign it again only if {who} made this version.")
            if not confirmed(dig[:8]):
                stop("not confirmed: nothing was signed")
        wdir = unlinked(d / sign.WITNESSES / ver)
        wdir.mkdir(parents=True, exist_ok=True)
        pin = log.pin(latest.number)
        for key in fresh:
            with open(wdir / sign.file_name(key.did), "xb") as f:
                f.write(sign.signature_file(key, obj_id, ver, dig, owner, pin))
        write_discovery()
        print(f"Done: {args.id} {ver} signed again by {plural(len(fresh), 'key')} of {who}, under v{latest.number} "
              f"of the key log; it is now {line_statuses(d, inv, log)[1][int(ver[1:]) - 1]}.")
