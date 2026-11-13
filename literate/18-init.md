Creating an archive
===================

The last part of `core.py` is `osheaf init`, which creates a new archive.
It comes last because it uses most of the others: it writes a
[configuration](10-archive.md), creates the storage root, the empty
[main collection](15-main-collection.md) and the
[discovery document and index](16-index.md), after which the archive
[verifies](17-verify.md) and is ready for its first
[deposit](13-deposit.md).

    # in create an archive:
    <<create an archive in a folder>>


    <<an argparse namespace for calling a command from code>>

What a new archive is
---------------------

A new archive follows the website profile (appendix C): its index is the
[website](30-website.md), made from templates that `init` copies into the
archive for the owner to edit. TeXmacs archives, with a TeXmacs index, are
configured by hand. The main collection is called `collection-main`.

The configuration is built from a few answers: the archive identifier (a
`tag:` URI, section 6.2), the name, the base URL (to which a final `/` is
added, since URLs of the archive are made by appending to it), the
contact, and the curator, written `Family, Given`. The curator is also the
depositor, by default, with the contact as address; both can be changed in
the file afterwards. An existing configuration is never overwritten.

The main collection is created empty, either kept by `collect` (newest
first) or, with `--curated`, as a curated collection, whose members (of
any archive) and order are the curator's (see
[collections](20-collections.md)). Then the discovery document and the
pages are written, so that the new archive is complete, if empty, and
passes verification.

Since OpenSheaf 0.1 is a draft, `init` says so: an archive made now may
have to be rebuilt when the specification changes, as it has (section 12).

    # in create an archive in a folder:
    def init(args):
        """Create an archive in the folder: osheaf.json, the storage root, the
        templates of the website (to edit), the empty main collection, the
        discovery document and the pages."""
        root = Path(args.folder or ".").resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any((root / n).exists() for n in CONFIG_NAMES):
            sys.exit(f"{root} has a configuration already")
        family, _, given = args.curator.partition(",")
        family, given = family.strip(), given.strip()
        cfg = {
            "archiveId": args.archive_id,
            "name": args.name,
            "contact": args.contact or args.base_url,
            "baseUrl": args.base_url if args.base_url.endswith("/") else args.base_url + "/",
            "profiles": ["website"],
            "mainCollection": "collection-main",
            "curator": {"name": f"{family}, {given}" if given else family, "givenName": given,
                        "familyName": family, "affiliation": args.affiliation or ""},
            "depositor": {"name": f"{given} {family}".strip(), "address": args.contact or args.base_url},
            "index": {"html": {"templates": "templates"}},
        }
        (root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        from . import html
        (root / "templates").mkdir(exist_ok=True)
        for f in html.DEFAULTS.iterdir():
            if not (root / "templates" / f.name).exists():
                shutil.copyfile(f, root / "templates" / f.name)
        configure(root)
        init_storage_root()
        if str(getattr(args, "curated", "")).lower() in ("1", "true", "yes"):
            # a curated collection: members from any archive, in the curator's order
            from . import collections
            collections.write(cfg["mainCollection"], [], args.name, "A collection of documents.", "manual",
                              "Collection created (curated)")
        else:
            collect(None)
        index(argparse_namespace(no_html=False))
        print(f"archive created in {root}: edit {CONFIG_NAME} and templates/, then deposit")
        print("note: OpenSheaf 0.1 is a draft; until version 1.0 a revision may change the format in"
              " incompatible ways, and archives may have to be rebuilt or migrated")

`init` calls `index()` directly, which expects the arguments of its
command. A namespace with the needed attributes stands in for them.

    # in an argparse namespace for calling a command from code:
    def argparse_namespace(**kw):
        import argparse
        return argparse.Namespace(**kw)
