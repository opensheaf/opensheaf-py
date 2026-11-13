"""osheaf: keep an OpenSheaf archive (specification 0.1, https://opensheaf.org).

The archive is the folder given with --root, or else the nearest folder above
the current one that has an osheaf.json (see `osheaf help-config`).

Commands:
  init                   create an archive (osheaf.json, storage root) in the folder
  deposit ID [SOURCE]    deposit a document (TeXmacs, or any source with --pdf)
  relicense ID           description-only version with a new licence
  relate ID              description-only version linking the same work elsewhere
  collect                new version of the main collection when needed
  index                  write opensheaf.json and the readable index
  verify                 check the archive (section 14 of the specification)
  zenodo ID              deposit the current document version on Zenodo
  arxiv fetch            download papers from arXiv (no archive needed)
  arxiv import           import downloaded arXiv papers into the archive
  help-config            describe osheaf.json
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
    d.add_argument("id")
    d.add_argument("source", nargs="?", help="the main source (.tm: typeset by the archive; "
                   "anything else: give the PDF with --pdf)")
    d.add_argument("--pdf", help="the PDF of this version (required unless the source is TeXmacs)")
    d.add_argument("--no-source", metavar="REASON",
                   help="deposit only the PDF, saying why the sources are not available")
    d.add_argument("--source-format", help="media type of the main source (default: from its extension)")
    d.add_argument("--abstract", help="the abstract (plain text, mathematics in $...$)")
    d.add_argument("--abstract-file", help="a UTF-8 file with the abstract (paragraphs separated by blank lines)")
    d.add_argument("--keyword", action="append", help="a keyword (repeatable)")
    d.add_argument("--language", default="en")
    d.add_argument("--toolchain", action="append", metavar="NAME=VERSION",
                   help="a tool that produced the PDF (repeatable), e.g. pdflatex=TeX Live 2025")
    d.add_argument("--title", required=True)
    d.add_argument("--author", action="append", required=True,
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
    d.set_defaults(func=core.deposit)

    r = sub.add_parser("relicense", help="description-only version with a new licence")
    r.add_argument("id")
    r.add_argument("--rights", required=True, choices=sorted(core.RIGHTS))
    r.add_argument("--method", required=True, help="how the authors agreed, e.g. 'confirmed by email'")
    r.add_argument("--date", help="date of the agreement (default today)")
    r.add_argument("--message")
    r.set_defaults(func=core.relicense)

    rl = sub.add_parser("relate", help="description-only version linking the same work elsewhere")
    rl.add_argument("id")
    rl.add_argument("--to", required=True, help="arxiv:ID or doi:DOI")
    rl.add_argument("--relation", default="IsIdenticalTo",
                    choices=["IsIdenticalTo", "IsVariantFormOf", "IsPreprintOf", "IsVersionOf"])
    rl.add_argument("--issued", help="also correct the Issued date (first public appearance)")
    rl.add_argument("--message")
    rl.set_defaults(func=core.relate)

    sub.add_parser("collect", help="new version of the main collection when needed").set_defaults(func=core.collect)
    i = sub.add_parser("index", help="write opensheaf.json and the readable index")
    i.add_argument("--no-html", action="store_true")
    i.set_defaults(func=core.index)
    sub.add_parser("verify", help="check the archive").set_defaults(func=core.verify)

    from . import zenodo
    zenodo.add_parser(sub, core)

    a = sub.add_parser("arxiv", help="download from arXiv, import into the archive")
    a.add_argument("action", choices=["fetch", "import"])
    a.add_argument("rest", nargs=argparse.REMAINDER, help="see osheaf arxiv fetch|import --help")
    a.set_defaults(func=None)

    n = sub.add_parser("init", help="create an archive (osheaf.json, storage root, website templates)")
    n.add_argument("folder", nargs="?", help="where (default: the current folder)")
    n.add_argument("--archive-id", required=True,
                   help="a URI that does not change when the archive moves, e.g. tag:example.org,2026:name")
    n.add_argument("--name", required=True, help="the name of the archive, e.g. 'Papers of Jane Doe'")
    n.add_argument("--base-url", required=True, help="where the archive is served, e.g. https://example.org/papers/")
    n.add_argument("--curator", required=True, help='"Family, Given"')
    n.add_argument("--affiliation")
    n.add_argument("--contact", help="a URL or mailto: address")
    n.set_defaults(func=None)
    sub.add_parser("help-config", help="describe osheaf.json").set_defaults(func=None)
    return p


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    p = build_parser()
    args = p.parse_args(argv)
    if args.cmd == "help-config":
        print(core.__doc__)
        return
    if args.cmd == "init":
        return core.init(args)
    if args.cmd == "arxiv" and args.action == "fetch":
        from . import arxiv
        return arxiv.fetch_main(args.rest)
    core.configure(core.find_root(args.root))
    if args.cmd == "arxiv":
        from . import arxiv
        return arxiv.main(args.rest)
    args.func(args)


if __name__ == "__main__":
    main()
