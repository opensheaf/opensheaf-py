Creating an archive
===================

Near the end of `core.py` is `osheaf init`, which creates a new archive.
It comes late because it uses most of the others: it writes a
[configuration](10-archive.md), creates the storage root, the owner of the
archive with its key log (with the [commands of owners](19-owner-commands.md)),
the empty [main catalogue](15-main-collection.md), the
[discovery document](16-index.md) and the [website](30-website.md), with
its templates, after which the archive [verifies](17-verify.md) and is
ready for its first [deposit](13-deposit.md).

    # in create an archive:
    <<create an archive in a folder>>


    <<an argparse namespace for calling a command from code>>

What a new archive is
---------------------

An archive has an owner (section 6): the keyed identity that signs the
versions of its lines, here those of the archive's documents and of its
main catalogue (section 8.1: an archive that makes collections does so as
an owner). The owner is either made at once, with `--new-owner`, which
makes the current key of this device and the rotation keys, exports the
rotation keys to a folder outside the archive, and writes the first version
of the key log (section 6.2; the options are those of `osheaf owner init`);
or an existing owner, `--owner NAME`, whose key log is copied from the
folder of its owner object in another archive (`--key-log DIR`), since
every line needs its owner's key log beside it (section 6.5). Either way,
its owner object is put in the storage root, at `<owner>/<owner>/` in the
owner-name layout.

The layout is chosen once (section 3.2): the owner-name layout by default,
or the hashed layout, `--layout hashed`, for archives of tens of thousands
of lines.

The configuration is built from a few answers: the name, the base URL (to
which a final `/` is added, since URLs of the archive are made by appending
to it), the contact, and the curator, written `Family, Given`. The curator
is also the depositor, by default, with the contact as address; both can be
changed in the file afterwards. The main catalogue is labelled `main`. An
existing configuration is never overwritten. Version 0.1 asked for an
archive identifier, which version 0.2 has dropped: an archive is named by
no file (section 3).

The main catalogue is sealed and signed at once, empty, kept by `collect`
(newest first). A curated main collection (`--curated`), whose members of
any archive and order are the curator's, is made empty, of order `manual`,
and kept with the commands of [collections](21-collections.md). Then the
discovery document is written, so that the new archive is complete, if
empty, and passes verification.

A new archive has a website: it declares the profile `website` (appendix
A.3), its configuration names the folder of its templates
(`"index": {"html": {"templates": "templates"}}`), and the default
templates of the [package](31-templates.md) are copied there, to be edited;
a template already there is kept. The home page, the landing page of the
main catalogue, the owner's page and the sitemap are written at once. An
archive that wants a TeXmacs index instead changes `index` in its
configuration (see `osheaf help-config`) and may remove the files of the
website.

Since OpenSheaf 0.2 is a draft, `init` says so: an archive made now may
have to be rebuilt when the specification changes, as it has (section 16.1).

    # in create an archive in a folder:
    def init(args):
        """Create an archive in the folder: osheaf.json, the storage root, the owner and its
        key log (made, or copied), the empty main catalogue, the discovery document, and the
        website with its templates (to edit)."""
        root = Path(args.folder or ".").resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any((root / n).exists() for n in CONFIG_NAMES):
            sys.exit(f"{root} has a configuration already")
        layout = LAYOUTS.get(getattr(args, "layout", None) or "owner-name")
        if layout is None:
            sys.exit(f"--layout is one of {', '.join(LAYOUTS)}")
        if bool(getattr(args, "new_owner", False)) == bool(getattr(args, "owner", None)):
            sys.exit("init: give --new-owner, or --owner NAME --key-log DIR")
        family, _, given = args.curator.partition(",")
        family, given = family.strip(), given.strip()
        cfg = {
            "owner": None,
            "name": args.name,
            "contact": args.contact or args.base_url,
            "baseUrl": args.base_url if args.base_url.endswith("/") else args.base_url + "/",
            "profiles": ["website"],
            "storageLayout": layout,
            "mainCollection": "main",
            "curator": {"name": f"{family}, {given}" if given else family, "givenName": given,
                        "familyName": family, "affiliation": args.affiliation or ""},
            "depositor": {"name": f"{given} {family}".strip(), "address": args.contact or args.base_url},
            "index": {"html": {"templates": "templates"}},
        }
        global ARCHIVE
        set_paths(root, layout)
        ARCHIVE = dict(cfg)
        init_storage_root()
        <<the owner of a new archive>>
        cfg["owner"] = log.owner
        (root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        from . import html
        (root / "templates").mkdir(exist_ok=True)
        for f in sorted(html.DEFAULTS.iterdir()):
            if f.is_file() and not (root / "templates" / f.name).exists():
                shutil.copyfile(f, root / "templates" / f.name)
        configure(root)
        collect(args)
        index(argparse_namespace(no_html=True))
        print(f"archive created in {root}, owned by {log.owner}: edit {CONFIG_NAME} and templates/, then "
              f"deposit (osheaf deposit --new LABEL ...)")
        print("note: OpenSheaf 0.2 is a draft; until version 1.0 a revision may change the format in"
              " incompatible ways, and archives may have to be rebuilt")

A new owner is made by the command `owner init` of the
[next chapter](19-owner-commands.md); an existing one's key log is read
from its folder, checked (it must not have ended: an archive takes no new
deposits for an ended owner, section 7.5), and written into the storage
root at the path of its identifier.

    # in the owner of a new archive:
    if getattr(args, "new_owner", False):
        log = owner_init(args)
    else:
        if not getattr(args, "key_log", None):
            sys.exit("init --owner NAME needs --key-log DIR, the folder of its owner object")
        try:
            log = owners.load_key_log(Path(args.key_log))
        except owners.OwnerError as e:
            sys.exit(str(e))
        errors, _ = log.check()
        if log.owner != args.owner or errors:
            sys.exit(f"{args.key_log} is not a valid key log of {args.owner}: " + "; ".join(errors))
        if log.ended:
            sys.exit(f"the owner {log.owner} has ended (section 6.3)")
        owners.write_key_log(obj_dir(log.id), log)

`init` and the commands of owners call other commands directly, which
expect the arguments of their command. A namespace with the needed
attributes stands in for them.

    # in an argparse namespace for calling a command from code:
    def argparse_namespace(**kw):
        import argparse
        return argparse.Namespace(**kw)
