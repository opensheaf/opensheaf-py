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
([copies](22-mirrors.md)). The last command of this chapter, `osheaf
sign`, signs a version of a line again after an exposure.

    # in the commands of owners and their keys:
    <<the owner a command is about>>


    <<a passphrase, asked or from the environment>>


    <<export rotation keys and confirm that they are kept>>


    <<read the rotation keys that sign a version of the key log>>


    <<create an owner>>


    <<change the keys of an owner>>


    <<end an owner>>


    <<show an owner>>


    <<a new current key for this device>>


    <<sign again a version contested by an exposed key>>

The owner a command is about is the archive's, unless `--owner` names
another owner it hosts. Its key log must be in the storage root.

    # in the owner a command is about:
    def owner_of(args):
        """The owner name a command is about, and its key log in the storage root."""
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

The rotation keys are never kept on the device: they are exported, before
anything is written, to a folder outside the archive (`--export DIR`, a USB
key for instance), one file each, encrypted under a passphrase unless
`--no-passphrase`, and printed as sheets with `--print`. The owner then
confirms, by typing the check of each key, that the files and sheets are
kept; only then is the key log written. A key log whose rotation keys were
lost before they were put away would be an owner that can never change its
keys (section 6.2).

The genesis record gives the owner name, the name of algorithm 0 of the
record (section 6.2); if it is taken in the archive, a new nonce is drawn
(section 5.3). The first version of the key log is computed from the
genesis record (section 6.1) and written into the storage root; the
current key is kept in the system's credential store, under the owner name.

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
        if not getattr(args, "export", None):
            sys.exit("give --export DIR, a folder outside the archive where the rotation keys are written")
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
            print("warning: " + owners.SINGLE_ROTATION_RISK)
        export_and_confirm(rotation, log.owner, 1, args)
        try:
            store = keys.store_current_key(log.owner, current)
        except (keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        owners.write_key_log(obj_dir(log.id), log)
        print(f"owner {log.owner}")
        print(f"current key of this device {current.did} (kept in {store})")
        print("warning: " + owners.ROTATION_KEYS_WARNING)
        return log

`osheaf owner init` makes an owner in an existing archive, which then hosts
it: its owner name joins `owners` in the configuration, and the discovery
document lists it.

    # in create an owner:
    def owner_init_command(args):
        log = owner_init(args)
        cfg_path = ROOT / CONFIG_NAME
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if log.owner not in [cfg.get("owner")] + cfg.get("owners", []):
                cfg["owners"] = cfg.get("owners", []) + [log.owner]
                cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                ARCHIVE.setdefault("owners", []).append(log.owner)
        write_discovery()

A passphrase is asked twice, without echo, or taken from the environment
variable `OPENSHEAF_PASSPHRASE`, for scripts. An empty passphrase is
refused: an owner who wants plain files says so, with `--no-passphrase`.

    # in a passphrase, asked or from the environment:
    PASSPHRASE = "OPENSHEAF_PASSPHRASE"


    def passphrase(confirm=True):
        """The passphrase of exported rotation keys."""
        if os.environ.get(PASSPHRASE):
            return os.environ[PASSPHRASE]
        import getpass
        first = getpass.getpass("passphrase of the rotation keys: ")
        if not first:
            sys.exit("an empty passphrase: give --no-passphrase to export the keys unencrypted")
        if confirm and getpass.getpass("the passphrase again: ") != first:
            sys.exit("the two passphrases differ")
        return first

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

### Reading the rotation keys

The rotation keys that sign the next version of the key log are read from
their files (`--rotation-key FILE`, repeated), or from typed sheets: each
must be of this owner and a rotation key of the latest version of its key
log, which `KeyLog.add` checks again. An encrypted file asks for the
passphrase once, for all of them.

    # in read the rotation keys that sign a version of the key log:
    def rotation_keys(files, owner):
        """The rotation keys of OWNER read from FILES."""
        if not files:
            sys.exit("give the rotation keys that sign the new version of the key log (--rotation-key FILE)")
        out, secret = [], None
        for f in files:
            try:
                try:
                    rk = keys.read_rotation_key(Path(f), secret)
                except keys.KeyStoreError as e:
                    if secret is not None or "passphrase is needed" not in str(e):
                        raise
                    secret = passphrase(confirm=False)
                    rk = keys.read_rotation_key(Path(f), secret)
            except (keys.KeyStoreError, OSError) as e:
                sys.exit(f"{f}: {e}")
            if rk.owner not in (None, owner):
                sys.exit(f"{f} is a rotation key of {rk.owner}, not of {owner}")
            out.append(rk.key)
        return out

Changing keys
-------------

`owner rotate` writes a new version of the key log (section 6.1), signed by
`nextThreshold` rotation keys of the latest version: it adds current keys
(`--add did:key`, made on their devices with `osheaf key new`), retires
others (`--retire did:key`, section 6.2), may change the `threshold`, and
commits new rotation keys, made now and exported as for a new owner, as many
as before with the same `nextThreshold` unless `--rotation` and
`--next-threshold` say otherwise. `owner expose` does the same and declares
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
        signers = rotation_keys(getattr(args, "rotation_key", None), owner)
        if not getattr(args, "export", None):
            sys.exit("give --export DIR, a folder outside the archive where the new rotation keys are written")
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
            print("warning: " + owners.SINGLE_ROTATION_RISK)
        export_and_confirm(new, owner, v.number, args)
        owners.write_key_log(obj_dir(log.id), log)
        write_discovery()
        print(f"{owner}: v{v.number} of the key log, current keys: {', '.join(v.keys['keys'])}")
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
expose keys (`--expose`).

    # in end an owner:
    def owner_end(args):
        """The ending version of the key log (section 6.3)."""
        owner, log = owner_of(args)
        successor = getattr(args, "successor", None)
        if successor is not None and not names.OWNER_NAME.match(successor):
            sys.exit(f"the successor is an owner name: {successor}")
        signers = rotation_keys(getattr(args, "rotation_key", None), owner)
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
                print(f"warning: {e}")
                here = []
            for k in here:
                print(f"on this device {k.did}")

A new current key
-----------------

A new device makes its own current key, never copied from another
(section 6.2): `osheaf key new` makes it, keeps it in the credential store
under the owner name, and prints its `did:key`, which a new version of the
key log adds to the current keys (`osheaf owner rotate --add`), with the
rotation keys kept apart. Until then it signs nothing.

    # in a new current key for this device:
    def key_new(args):
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        key = keys.new_key()
        try:
            store = keys.store_current_key(owner, key)
        except (keys.KeyStoreError, OSError) as e:
            sys.exit(str(e))
        print(key.did)
        print(f"kept in {store}; it signs once a version of the key log adds it: "
              f"osheaf owner rotate --add {key.did} --rotation-key FILE ... --export DIR")
        return key

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
            sys.exit(f"this device holds {len(fresh)} current key(s) of {owner} that have not signed {ver}, and "
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
        print(f"{args.id} {ver}: signed again by {len(fresh)} key(s), naming v{latest.number} of the key log: "
              f"{line_statuses(d, inv, log)[1][int(ver[1:]) - 1]}")
