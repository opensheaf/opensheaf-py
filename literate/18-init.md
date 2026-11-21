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
no file (section 3). A new owner whose keys are kept in a GitHub wallet
(`--keys github:OWNER/REPO`, [chapter 9](09-wallets.md)) names it in the
configuration as a hint for the owner, `"keys": {"<owner>": {"wallets":
["github:OWNER/REPO"]}}`, so that the commands of owners and of signing
find its keys there, and says so; `osheaf key wallet` changes the hints
later.

The main catalogue is sealed and signed at once, empty, kept by `collect`
(newest first). A curated main collection (`--curated`), whose members of
any archive and order are the curator's, is made empty, of order `manual`,
and kept with the commands of [collections](21-collections.md). Then the
discovery document is written, so that the new archive is complete, if
empty, and passes verification.

A new archive has a readable index, chosen by `--index`. By default it is
a website: the archive declares the profile `website` (appendix A.3), its
configuration names the folder of its templates
(`"index": {"html": {"templates": "templates"}}`), and the default
templates of the [package](31-templates.md) are copied there, to be edited;
a template already there is kept. The home page, the landing page of the
main catalogue, the owner's page and the sitemap are written at once.

With `--index texmacs` the home page is a [TeXmacs index](16-index.md)
instead, as in an archive of papers written with TeXmacs: the archive
declares the profile `texmacs` (appendix A.2), and its configuration names
the template of the index (`"index": {"template": "index-template.tm"}`).
The template is the file given with `--index-template`, copied into the
archive unless it is there already, or else a minimal one, written if
the archive has none: a document of the `notes` style whose only
paragraph after the title is `<paper-index>`. No website templates are
copied and no home page is written: the landing pages, the owner pages and
the sitemap are made from the package's templates, or from those the
archive puts in `templates/` later, and `index.tm` is written at once, its
export to `index.html`, which needs TeXmacs, being left to `osheaf index`.
The `texmacs` settings of the configuration (plugins, style packages of the
HTML versions) are added by hand, if needed (see `osheaf help-config`).

Since OpenSheaf 0.2 is a draft, `init` says so: an archive made now may
have to be rebuilt when the specification changes, as it has (section 16.1).

An archive kept in git needs its files stored and checked out byte for
byte, never converted or merged as text: an inventory whose line endings
git changed would no longer have its digest (the git companion of the
specification, section 4.1). `init` writes the `.gitattributes` that says
so, the same lines as the archive template's, unless the folder has one
already, which is left as it is. Every attribute is named, so that none of
the user's own settings (a user-wide `*.pdf filter=lfs`, say) applies.

    # in create an archive in a folder:
    GITATTRIBUTES = """# OpenSheaf archive files: stored and checked out byte for byte,
    # never merged as text (OpenSheaf archives in git, section 4.1). Every
    # attribute is named, so that no attribute of the user's own settings (a
    # user-wide `*.pdf filter=lfs`, for instance) applies to them.
    opensheaf.json -text -filter -ident -working-tree-encoding -export-subst -merge
    ocfl/**        -text -filter -ident -working-tree-encoding -export-subst -merge
    indexes.json   -text -filter -ident -working-tree-encoding -export-subst -merge
    names/**       -text -filter -ident -working-tree-encoding -export-subst -merge
    owners/**      -text -filter -ident -working-tree-encoding -export-subst -merge
    sha512/**      -text -filter -ident -working-tree-encoding -export-subst -merge
    *.pdf binary
    """

The command itself:

    # in create an archive in a folder:
    def init(args):
        """Create an archive in the folder: osheaf.json, the storage root, the owner and its
        key log (made, or copied), the empty main catalogue, the discovery document, and the
        website with its templates (to edit), or, with --index texmacs, the TeXmacs index
        with its template."""
        root = Path(args.folder or ".").resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any((root / n).exists() for n in CONFIG_NAMES):
            sys.exit(f"{root} has a configuration already")
        layout = LAYOUTS.get(getattr(args, "layout", None) or "owner-name")
        if layout is None:
            sys.exit(f"--layout is one of {', '.join(LAYOUTS)}")
        if bool(getattr(args, "new_owner", False)) == bool(getattr(args, "owner", None)):
            stop("init: give --new-owner, or --owner NAME --key-log DIR")
        family, _, given = args.curator.partition(",")
        family, given = family.strip(), given.strip()
        kind = getattr(args, "index", None) or "website"
        if kind not in ("website", "texmacs"):
            sys.exit("--index is website or texmacs")
        if getattr(args, "index_template", None) and kind != "texmacs":
            sys.exit("--index-template goes with --index texmacs")
        cfg = {
            "owner": None,
            "name": args.name,
            "contact": args.contact or args.base_url,
            "baseUrl": args.base_url if args.base_url.endswith("/") else args.base_url + "/",
            "profiles": [kind],
            "storageLayout": layout,
            "mainCollection": "main",
            "curator": {"name": f"{family}, {given}" if given else family, "givenName": given,
                        "familyName": family, "affiliation": args.affiliation or ""},
            "depositor": {"name": f"{given} {family}".strip(), "address": args.contact or args.base_url},
            "index": {"html": {"templates": "templates"}},
        }
        if kind == "texmacs":
            cfg["index"] = {"template": index_template(root, args)}
        global ARCHIVE
        set_paths(root, layout)
        ARCHIVE = dict(cfg)
        init_storage_root()
        <<the owner of a new archive>>
        cfg["owner"] = log.owner
        if getattr(args, "new_owner", False) and wallet_config(args, log.owner):
            cfg["keys"] = wallet_config(args, log.owner)
        (root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if not (root / ".gitattributes").exists():
            (root / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
        if kind == "website":
            from . import html
            (root / "templates").mkdir(exist_ok=True)
            for f in sorted(html.DEFAULTS.iterdir()):
                if f.is_file() and not (root / "templates" / f.name).exists():
                    shutil.copyfile(f, root / "templates" / f.name)
        configure(root)
        collect(args)
        index(argparse_namespace(no_html=True))
        edit = "templates/" if kind == "website" else cfg["index"]["template"]
        if cfg.get("keys"):
            print(f"The key wallet {args.keys} is recorded in {CONFIG_NAME} for {names.short(log.owner)} "
                  f"(osheaf key wallet --remove {args.keys} removes it).")
        print(f"Done: the archive is made in {root}, owned by {names.short(log.owner)}. Edit {CONFIG_NAME} and "
              f"{edit}, then deposit a paper: osheaf deposit --new LABEL ...")
        print("Note: OpenSheaf 0.2 is a draft; until version 1.0 a revision may change the format in"
              " incompatible ways, and archives may have to be rebuilt.", file=sys.stderr)

The template of a TeXmacs index is found before anything is written, so
that a wrong path stops `init` with nothing done. The template given must
have the one paragraph `<paper-index>` that the index replaces; it keeps its
name, and one already in the archive is not copied over itself. The
minimal template is written only if the archive has no
`index-template.tm`.

    # in create an archive in a folder:
    TEXMACS_INDEX_TEMPLATE = """<TeXmacs|2.1>

    <style|notes>

    <\\body>
      <chapter*|{title}>

      <paper-index>
    </body>
    """


    def index_template(root, args):
        """The template of the TeXmacs index of a new archive in ROOT, copied from
        --index-template or written: its path relative to ROOT."""
        given = getattr(args, "index_template", None)
        if not given:
            if not (root / "index-template.tm").exists():
                (root / "index-template.tm").write_text(
                    TEXMACS_INDEX_TEMPLATE.format(title=tm_escape(args.name)), encoding="latin-1")
            return "index-template.tm"
        src = Path(given).resolve()
        if not src.is_file():
            sys.exit(f"--index-template: no file {given}")
        if src.read_text(encoding="latin-1").count("  <paper-index>\n") != 1:
            sys.exit(f"--index-template: {given} must contain one paragraph <paper-index>")
        dest = root / src.name
        if dest.resolve() != src:
            if dest.exists():
                sys.exit(f"--index-template: {dest} exists already")
            shutil.copyfile(src, dest)
        return src.name

A new owner is made by the command `owner init` of the
[next chapter](19-owner-commands.md); an existing one's key log is read
from its folder, checked (it must not have ended: an archive takes no new
deposits for an ended owner, section 7.5), and written into the storage
root at the path of its identifier.

    # in the owner of a new archive:
    if getattr(args, "new_owner", False):
        log = owner_init(args, done=False)
    else:
        if not getattr(args, "key_log", None):
            stop("init --owner NAME needs --key-log DIR, the folder of its owner object")
        try:
            log = owners.load_key_log(Path(args.key_log))
        except owners.OwnerError as e:
            stop(str(e))
        errors, _ = log.check()
        if log.owner != args.owner or errors:
            stop(f"{args.key_log} is not a valid key log of {names.short(args.owner)}: " + "; ".join(errors))
        if log.ended:
            stop(f"the owner {names.short(log.owner)} has ended (section 6.3)")
        owners.write_key_log(obj_dir(log.id), log)

`init` and the commands of owners call other commands directly, which
expect the arguments of their command. A namespace with the needed
attributes stands in for them.

    # in an argparse namespace for calling a command from code:
    def argparse_namespace(**kw):
        import argparse
        return argparse.Namespace(**kw)
