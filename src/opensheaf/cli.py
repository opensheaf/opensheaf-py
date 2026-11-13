"""osheaf: keep an OpenSheaf archive (specification 0.1, https://opensheaf.org).

The archive is the folder given with --root, or else the nearest folder above
the current one that has an osheaf.json (see `osheaf help-config`).

Commands:
  init                   create an archive (osheaf.json, storage root) in the folder
  deposit ID [SOURCE]    deposit a document (TeXmacs, or any source with --pdf)
  relicense ID           description-only version with a new licence
  relate ID              description-only version linking the same work elsewhere
  notice ID              a notice about a document version
  withdraw ID            withdraw a document (the content stays)
  complete ID            add the sources of a version deposited without them
  mirror URL ID          copy another archive's object (open licences only)
  collection sync|update curated collections, with members from any archive
  collect                new version of the main collection when needed
  index                  write opensheaf.json and the readable index
  verify                 check the archive (section 14 of the specification)
  zenodo ID              deposit the current document version on Zenodo
  arxiv fetch            download papers from arXiv (no archive needed)
  arxiv import           import downloaded arXiv papers into the archive
  help-config            describe osheaf.json

deposit, relicense, relate and init also take their options from a YAML or
JSON file: --from FILE (a list of entries: several, in order).

Warning: OpenSheaf 0.1 is a draft. Until version 1.0, a revision may change
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
    d.add_argument("id", nargs="?")
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
    rl.set_defaults(func=core.relate)

    nt = sub.add_parser("notice", help="a notice about a document version (description-only)")
    nt.add_argument("id")
    nt.add_argument("--about", type=int, required=True, help="the document version it is about")
    nt.add_argument("--text", help="the notice (plain text)")
    nt.add_argument("--file", help="a file with the full statement (PDF, Markdown, ...)")
    nt.add_argument("--date", help="default: today")
    nt.add_argument("--message")
    nt.set_defaults(func=core.notice)
    w = sub.add_parser("withdraw", help="withdraw a document (description-only; the content stays)")
    w.add_argument("id")
    w.add_argument("--reason", help="why (plain text)")
    w.add_argument("--file", help="a file with the full statement")
    w.add_argument("--date", help="default: today")
    w.add_argument("--message")
    w.set_defaults(func=core.withdraw)
    c = sub.add_parser("complete", help="add the sources of a version deposited without them")
    c.add_argument("id")
    c.add_argument("--version", type=int, required=True, help="the document version")
    c.add_argument("--source", required=True, help="the main source")
    c.add_argument("--extra-source", action="append", help="FILE[=LOGICAL/PATH]")
    c.add_argument("--source-format")
    c.add_argument("--message")
    c.set_defaults(func=core.complete)
    mi = sub.add_parser("mirror", help="copy another archive's object (with open licences) into this archive")
    mi.add_argument("url", help="the archive's base URL (or a local folder)")
    mi.add_argument("id")
    mi.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although a licence is not an open one")
    mi.set_defaults(func=None)
    co = sub.add_parser("collection", help="curated collections, with members from any archive")
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
                   help="also fetch the members of collections from their archives and check their pins")
    v.set_defaults(func=core.verify)

    from . import zenodo
    zenodo.add_parser(sub, core)

    a = sub.add_parser("arxiv", help="download from arXiv, import into the archive")
    a.add_argument("action", choices=["fetch", "import"])
    a.add_argument("rest", nargs=argparse.REMAINDER, help="see osheaf arxiv fetch|import --help")
    a.set_defaults(func=None)

    n = sub.add_parser("init", help="create an archive (osheaf.json, storage root, website templates)")
    n.add_argument("folder", nargs="?", help="where (default: the current folder)")
    n.add_argument("--archive-id",
                   help="a URI that does not change when the archive moves, e.g. tag:example.org,2026:name")
    n.add_argument("--name", help="the name of the archive, e.g. 'Papers of Jane Doe'")
    n.add_argument("--base-url", help="where the archive is served, e.g. https://example.org/papers/")
    n.add_argument("--curator", help='"Family, Given"')
    n.add_argument("--affiliation")
    n.add_argument("--contact", help="a URL or mailto: address")
    n.add_argument("--curated", action="store_true",
                   help="the main collection is curated (osheaf collection sync), e.g. for an archive of "
                   "collections of other archives' documents")
    n.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    n.set_defaults(func=None)
    sub.add_parser("help-config", help="describe osheaf.json").set_defaults(func=None)
    return p


REQUIRED = {"deposit": ("id", "title", "author"), "relicense": ("id", "rights", "method"),
            "relate": ("id", "to"), "init": ("archive_id", "name", "base_url", "curator")}


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


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = build_parser()
    args = p.parse_args(argv)
    if args.cmd == "help-config":
        print(core.__doc__)
        return
    if args.cmd in REQUIRED:
        todo = runs(p, args)
        if args.cmd == "init":
            return core.init(todo[0])
        core.configure(core.find_root(args.root))
        for ns in todo:
            ns.func(ns)
        return
    if args.cmd == "arxiv" and args.action == "fetch":
        from . import arxiv
        return arxiv.fetch_main(args.rest)
    core.configure(core.find_root(args.root))
    if args.cmd == "arxiv":
        from . import arxiv
        return arxiv.main(args.rest)
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


if __name__ == "__main__":
    main()
