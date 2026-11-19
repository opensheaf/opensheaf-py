# Generated from literate/60-command-line.md by opensheaf-literate: edit the document, not this file.
"""osheaf: keep an OpenSheaf archive (specification 0.2, https://opensheaf.org).

The archive is the folder given with --root, or else the nearest folder above
the current one that has an osheaf.json (see `osheaf help-config`). Lines are
named by their labels in the archive.

Commands:
  init                   create an archive (osheaf.json, storage root, owner, main catalogue)
  owner init|rotate|expose|end|show   make an owner, change its keys, end it, show it
  key new                a new current key for this device
  deposit LABEL [SOURCE] deposit a document (TeXmacs, or any source with --pdf);
                         --new seals a new work under a new label
  relicense LABEL        description-only version with a new licence
  relate LABEL           description-only version linking the same work elsewhere
  describe LABEL         description-only version correcting title, abstract, keywords, authors
  notice LABEL           a notice about a document version
  withdraw LABEL         withdraw a document (the content stays)
  complete LABEL         add the sources of a version deposited without them
  collect                new version of the main catalogue when needed
  index                  write opensheaf.json (the readable index: not yet for 0.2)
  verify                 check the archive (section 14 of the specification)
  arxiv fetch            download papers from arXiv (no archive needed)
  help-config            describe osheaf.json

Not yet available for specification 0.2: accept, mirror, collection, zenodo,
arxiv import, the website.

deposit, relicense, relate, describe and init also take their options from a
YAML or JSON file: --from FILE (a list of entries: several, in order).

Warning: OpenSheaf 0.2 is a draft. Until version 1.0, a revision may change
the format in incompatible ways, and archives may have to be rebuilt.
"""

import argparse
import sys

from . import __version__, core


def build_parser():
    p = argparse.ArgumentParser(prog="osheaf", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"opensheaf {__version__}")
    p.add_argument("--root", help="the archive folder (default: found from the current folder)")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("deposit", help="deposit a document, or a new document version",
                       description=core.deposit.__doc__)
    d.add_argument("id", nargs="?", metavar="LABEL", help="the label of the line in the archive")
    d.add_argument("source", nargs="?", help="the main source (.tm: typeset by the archive; "
                   "anything else: give the PDF with --pdf)")
    d.add_argument("--pdf", help="the PDF of this version (required unless the source is TeXmacs)")
    d.add_argument("--no-source", metavar="REASON",
                   help="deposit only the PDF, saying why the sources are not available")
    d.add_argument("--source-format", help="media type of the main source (default: from its extension)")
    d.add_argument("--abstract", help="the abstract (plain text, mathematics in $...$)")
    d.add_argument("--abstract-file", help="a UTF-8 file with the abstract (paragraphs separated by blank lines)")
    d.add_argument("--keyword", action="append", help="a keyword (repeatable)")
    d.add_argument("--language", help="default: en")
    d.add_argument("--toolchain", action="append", metavar="NAME=VERSION",
                   help="a tool that produced the PDF (repeatable), e.g. pdflatex=TeX Live 2025")
    d.add_argument("--title")
    d.add_argument("--author", action="append",
                   help='"Family, Given|Affiliation", as printed in the document')
    d.add_argument("--available", "--date", dest="available",
                   help="when this version first became public (default: today, the deposit)")
    d.add_argument("--created", help="when this version was written, for a version not public at the time")
    d.add_argument("--issued", help="first public appearance of the work (default: as before, or --available)")
    d.add_argument("--date-info", help="how the date is known, e.g. 'from the file's modification time'")
    d.add_argument("--stage", choices=["AO", "SMUR", "AM", "P", "VoR", "CVoR", "EVoR"],
                   help="NISO-JAV stage of this version")
    d.add_argument("--changes", help="change note of this version")
    d.add_argument("--after", type=int, help="place this version after document version N in the"
                   " history (a version found later); otherwise it becomes the current version")
    d.add_argument("--type", default="Preprint")
    d.add_argument("--rights", help="free text, or one of " + ", ".join(sorted(core.RIGHTS))
                   + " (default: as the previous version, or 'All rights reserved')")
    d.add_argument("--related", action="append",
                   help="arxiv=ID (IsVariantFormOf), or RELATION:doi:DOI, RELATION:arxiv:ID")
    d.add_argument("--extra-source", action="append",
                   help="FILE[=LOGICAL/PATH], another source at the path the main source refers to")
    d.add_argument("--message")
    d.add_argument("--agreement", metavar="METHOD",
                   help="record the authors' agreement (object.json), e.g. a journal's publication terms")
    d.add_argument("--licence-file", metavar="PATH",
                   help="the file of the deposit that holds the full text or terms of the licence "
                        "(the main source or an --extra-source, by its path in the deposit, e.g. LICENSE): "
                        "object.json licence")
    d.add_argument("--new", action="store_true",
                   help="seal a new work under the new label LABEL (section 10.2)")
    d.add_argument("--owner", help="--new: the owner of the new line, an owner the archive hosts "
                   "(default: the archive's)")
    d.add_argument("--i-know", dest="i_know", action="store_true",
                   help="extend versions that are not signed, or are contested, having looked at them (section 7.3)")
    d.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    d.set_defaults(func=core.deposit)

    r = sub.add_parser("relicense", help="description-only version with a new licence")
    r.add_argument("id", nargs="?")
    r.add_argument("--rights", choices=sorted(core.RIGHTS))
    r.add_argument("--method", help="how the authors agreed, e.g. 'confirmed by email'")
    r.add_argument("--date", help="date of the agreement (default today)")
    r.add_argument("--message")
    r.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    r.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    r.set_defaults(func=core.relicense)

    rl = sub.add_parser("relate", help="description-only version linking the same work elsewhere")
    rl.add_argument("id", nargs="?")
    rl.add_argument("--to", help="arxiv:ID or doi:DOI")
    rl.add_argument("--relation", default="IsIdenticalTo",
                    choices=["IsIdenticalTo", "IsVariantFormOf", "IsPreprintOf", "IsVersionOf"])
    rl.add_argument("--issued", help="also correct the Issued date (first public appearance)")
    rl.add_argument("--message")
    rl.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    rl.add_argument("--i-know", dest="i_know", action="store_true",
                     help="extend versions that are not signed, or are contested (section 7.3)")
    rl.set_defaults(func=core.relate)

    ds = sub.add_parser("describe", help="description-only version correcting the title, abstract,"
                        " keywords or authors")
    ds.add_argument("id", nargs="?")
    ds.add_argument("--title", help="the corrected title (plain text, mathematics in $...$)")
    abstract = ds.add_mutually_exclusive_group()
    abstract.add_argument("--abstract", help="the corrected abstract (plain text, mathematics in $...$)")
    abstract.add_argument("--abstract-file", help="a UTF-8 file with the corrected abstract")
    ds.add_argument("--keyword", action="append", help="a keyword (repeatable): replaces the keywords")
    ds.add_argument("--author", action="append",
                    help='"Family, Given|Affiliation" (repeatable): replaces the authors')
    ds.add_argument("--message")
    ds.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    ds.add_argument("--i-know", dest="i_know", action="store_true",
                     help="extend versions that are not signed, or are contested (section 7.3)")
    ds.set_defaults(func=core.describe)

    nt = sub.add_parser("notice", help="a notice about a document version (description-only)")
    nt.add_argument("id")
    nt.add_argument("--about", type=int, required=True, help="the document version it is about")
    nt.add_argument("--text", help="the notice (plain text)")
    nt.add_argument("--file", help="a file with the full statement (PDF, Markdown, ...)")
    nt.add_argument("--date", help="default: today")
    nt.add_argument("--message")
    nt.add_argument("--i-know", dest="i_know", action="store_true",
                     help="extend versions that are not signed, or are contested (section 7.3)")
    nt.set_defaults(func=core.notice)
    w = sub.add_parser("withdraw", help="withdraw a document (description-only; the content stays)")
    w.add_argument("id")
    w.add_argument("--reason", help="why (plain text)")
    w.add_argument("--file", help="a file with the full statement")
    w.add_argument("--date", help="default: today")
    w.add_argument("--message")
    w.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    w.set_defaults(func=core.withdraw)
    c = sub.add_parser("complete", help="add the sources of a version deposited without them")
    c.add_argument("id")
    c.add_argument("--version", type=int, required=True, help="the document version")
    c.add_argument("--source", required=True, help="the main source")
    c.add_argument("--extra-source", action="append", help="FILE[=LOGICAL/PATH]")
    c.add_argument("--source-format")
    c.add_argument("--message")
    c.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    c.set_defaults(func=core.complete)
    ac = sub.add_parser("accept", help="copy one vetted version of another archive's object into a "
                        "document of this archive (a journal)")
    ac.add_argument("url", help="the archive's base URL (or a local folder)")
    ac.add_argument("id")
    ac.add_argument("--version", required=True, help="the object version that was vetted, e.g. v2")
    ac.add_argument("--as", dest="as_id", help="the identifier here (default: the same)")
    ac.add_argument("--stage", choices=["AO", "SMUR", "AM", "P", "VoR", "CVoR", "EVoR"])
    ac.add_argument("--type", help="resourceTypeGeneral, e.g. JournalArticle (default: as the source)")
    ac.add_argument("--available", help="when this archive published it (default: today)")
    ac.add_argument("--agreement", metavar="METHOD", help="record the authors' agreement")
    ac.add_argument("--changes", help="the change note (default: says what was accepted)")
    ac.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although the licence is not an open one")
    ac.add_argument("--message")
    ac.set_defaults(func=None)
    mi = sub.add_parser("mirror", help="copy another archive's object (with open licences) into this archive")
    mi.add_argument("url", help="the archive's base URL (or a local folder)")
    mi.add_argument("id")
    mi.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although a licence is not an open one")
    mi.set_defaults(func=None)
    co = sub.add_parser("collection", help="curated collections (catalogues or selections), "
                        "with members from any archive")
    co.add_argument("action", choices=["sync", "update"])
    co.add_argument("collection", nargs="?", help="the collection object (default: the main collection)")
    co.add_argument("--from", dest="from_file", metavar="FILE", help="sync: collection.yaml")
    co.add_argument("--message")
    co.set_defaults(func=None)
    sub.add_parser("collect", help="new version of the main collection when needed").set_defaults(func=core.collect)
    i = sub.add_parser("index", help="write opensheaf.json and the readable index")
    i.add_argument("--no-html", action="store_true")
    i.set_defaults(func=core.index)
    v = sub.add_parser("verify", help="check the archive")
    v.add_argument("--remote", action="store_true",
                   help="also fetch the members of collections from their archives and check their pins "
                   "(not yet available for specification 0.2)")
    v.add_argument("--json", action="store_true", help="print the findings as JSON")
    v.set_defaults(func=core.verify)

    from . import zenodo
    zenodo.add_parser(sub, core)

    a = sub.add_parser("arxiv", help="download from arXiv, import into the archive")
    a.add_argument("action", choices=["fetch", "import"])
    a.add_argument("rest", nargs=argparse.REMAINDER, help="see osheaf arxiv fetch|import --help")
    a.set_defaults(func=None)

    n = sub.add_parser("init", help="create an archive (osheaf.json, storage root, owner, main catalogue)")
    n.add_argument("folder", nargs="?", help="where (default: the current folder)")
    n.add_argument("--name", help="the name of the archive, e.g. 'Papers of Jane Doe'")
    n.add_argument("--base-url", help="where the archive is served, e.g. https://example.org/papers/")
    n.add_argument("--curator", help='"Family, Given"')
    n.add_argument("--affiliation")
    n.add_argument("--contact", help="a URL or mailto: address")
    n.add_argument("--layout", choices=["owner-name", "hashed"], help="the storage layout (default: owner-name)")
    n.add_argument("--owner", help="the owner name of an existing owner, with --key-log")
    n.add_argument("--key-log", help="the folder of the owner object of --owner, in another archive")
    n.add_argument("--new-owner", action="store_true", help="make a new owner (see osheaf owner init)")
    owner_init_options(n)
    n.add_argument("--curated", action="store_true",
                   help="the main collection is curated (osheaf collection sync; not yet for 0.2)")
    n.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    n.set_defaults(func=None)

    ow = sub.add_parser("owner", help="make an owner, change its keys, end it, show its key log")
    osub = ow.add_subparsers(dest="action", required=True)
    oi = osub.add_parser("init", help="make an owner: current key, rotation keys exported, key log")
    owner_init_options(oi)
    for name, helptext in (("rotate", "a new version of the key log: add or retire current keys"),
                           ("expose", "a new version of the key log exposing stolen or leaked keys")):
        o = osub.add_parser(name, help=helptext)
        if name == "expose":
            o.add_argument("exposed", nargs="+", metavar="DID", help="the did:key URIs of the keys exposed")
        o.add_argument("--add", action="append", metavar="DID", help="a current key to add (repeatable)")
        if name == "rotate":
            o.add_argument("--retire", action="append", metavar="DID", help="a current key to retire (repeatable)")
        o.add_argument("--threshold", type=int, help="the number of current keys that sign (default: as before)")
        o.add_argument("--rotation", type=int, help="the number of new rotation keys (default: as before)")
        o.add_argument("--next-threshold", type=int, help="how many of them sign the next version (default: as before)")
        rotation_options(o)
    oe = osub.add_parser("end", help="the last version of the key log (section 6.3)")
    oe.add_argument("--successor", help="the owner name of the owner that continues the work")
    oe.add_argument("--expose", action="append", metavar="DID", help="also expose a key (repeatable)")
    rotation_options(oe, export=False)
    osh = osub.add_parser("show", help="the key log of the owner")
    osh.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    ow.set_defaults(func=None)
    k = sub.add_parser("key", help="current keys of this device")
    ksub = k.add_subparsers(dest="action", required=True)
    kn = ksub.add_parser("new", help="a new current key for this device; prints its did:key")
    kn.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    k.set_defaults(func=None)
    sub.add_parser("help-config", help="describe osheaf.json").set_defaults(func=None)
    return p


def owner_init_options(p):
    p.add_argument("--threshold", type=int, help="how many current keys sign (default 1)")
    p.add_argument("--key", action="append", metavar="DID",
                   help="the current key of another device, made there with osheaf key new (repeatable)")
    p.add_argument("--rotation", type=int, help="the number of rotation keys (default 3)")
    p.add_argument("--next-threshold", type=int, help="how many rotation keys sign the next version "
                   "of the key log (default 2 of 3)")
    p.add_argument("--single-rotation-key", action="store_true",
                   help="one rotation key, nextThreshold 1: the minimal setup, with its risk (section 6.2)")
    p.add_argument("--keeper", help="who answers for the owner: an ORCID iD or https://<domain>/ (section 6.6)")
    export_options(p)


def export_options(p):
    p.add_argument("--export", metavar="DIR", help="where to write the rotation keys, outside the archive")
    p.add_argument("--no-passphrase", action="store_true", help="export the rotation keys unencrypted")
    p.add_argument("--print", action="store_true", help="also print each rotation key as a sheet")
    p.add_argument("--yes", action="store_true", help="do not ask to confirm the export (scripts)")


def rotation_options(p, export=True):
    p.add_argument("--rotation-key", action="append", metavar="FILE",
                   help="a rotation key of the latest version of the key log, its file or typed sheet "
                   "(repeatable: nextThreshold of them)")
    p.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    p.add_argument("--message")
    if export:
        export_options(p)


REQUIRED = {"deposit": ("id", "title", "author"), "relicense": ("id", "rights", "method"),
            "relate": ("id", "to"), "describe": ("id",),
            "init": ("name", "base_url", "curator")}


def runs(p, args):
    """The runs of a command: one, or one per entry of its --from file."""
    from . import inputs
    entries = inputs.load(args.from_file) if getattr(args, "from_file", None) else [{}]
    out = []
    for entry in entries:
        ns = inputs.merge(args, entry, p, args.cmd)
        missing = [k for k in REQUIRED.get(args.cmd, ()) if getattr(ns, k, None) in (None, [])]
        if missing:
            p.error(f"{args.cmd}: missing " + ", ".join(m.replace("_", "-") for m in missing))
        if args.cmd == "relicense" and ns.rights not in core.RIGHTS:
            p.error(f"relicense: rights must be one of {', '.join(sorted(core.RIGHTS))}")
        out.append(ns)
    return out


NOT_YET = ("accept", "mirror", "collection", "zenodo")
OWNER_ACTIONS = {"init": "owner_init_command", "rotate": "owner_rotate", "expose": "owner_expose",
                 "end": "owner_end", "show": "owner_show"}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = build_parser()
    args = p.parse_args(argv)
    if args.cmd == "help-config":
        print(core.__doc__)
        return
    if args.cmd in NOT_YET or (args.cmd == "arxiv" and args.action == "import"):
        name = args.cmd + (" import" if args.cmd == "arxiv" else "")
        sys.exit(f"osheaf {name}: not yet available for specification 0.2")
    if args.cmd in REQUIRED:
        todo = runs(p, args)
        if args.cmd == "init":
            return core.init(todo[0])
        configure(args)
        for ns in todo:
            ns.func(ns)
        return
    if args.cmd == "arxiv" and args.action == "fetch":
        from . import arxiv
        return arxiv.fetch_main(args.rest)
    configure(args)
    if args.cmd == "owner":
        getattr(core, OWNER_ACTIONS[args.action])(args)
        return
    if args.cmd == "key":
        core.key_new(args)
        return
    if args.cmd == "arxiv":
        from . import arxiv
        return arxiv.main(args.rest)
    if args.cmd == "accept":
        from . import accept
        core.configure(core.find_root(args.root))
        return accept.accept(args)
    if args.cmd == "mirror":
        from . import mirror
        core.configure(core.find_root(args.root))
        return mirror.main(args)
    if args.cmd == "collection":
        from . import collections
        if args.action == "sync":
            if not args.from_file:
                p.error("collection sync needs --from collection.yaml")
            return collections.sync(args)
        return collections.update(args)
    args.func(args)


def configure(args):
    core.configure(core.find_root(args.root))
    if core.OLD and args.cmd != "verify":
        sys.exit(core.REBUILD)


if __name__ == "__main__":
    main()
