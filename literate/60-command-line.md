The command line
================

This chapter is the outer layer of opensheaf-py: the command `osheaf`,
which reads the options of a command and calls the function that does the
work. Almost nothing is decided here. Deposits, description-only versions,
the main collection, the index and verification are explained in the
chapters on the core; collections, mirrors and accepted copies in the
chapter on collections; arXiv and Zenodo in chapters of their own. Two
modules are tangled from this chapter: `cli.py`, the command itself, and
`inputs.py`, which reads options from YAML or JSON files, so that a deposit
can be described in a file kept beside the paper instead of in a long
command line. The tests, in the [next chapter](70-tests.md), mostly drive
the archive through this command, as a user would.

The command `osheaf`
--------------------

`cli.py` has five parts: its docstring, which is also the text of
`osheaf --help`; the parser, with one sub-parser per command; the options
that some commands need but that may come from a file; the merging of such
a file with the command line; and `main`, which sends each command to the
module that carries it out.

    # in src/opensheaf/cli.py:
    <<the docstring of osheaf>>


    <<the parser of osheaf>>


    <<the options a command needs, from the command line or a file>>


    <<the runs of a command, one per entry of its file>>


    <<the main function of osheaf>>


    if __name__ == "__main__":
        main()

The package declares `main` as the entry point of two commands, `osheaf`
and `opensheaf`; the last two lines also let one run the module directly.

### The help text

The docstring of the module is the description printed by `osheaf --help`,
so it is written for the user: how the archive is found, the list of
commands in one line each, the files of options, and the warning that the
format is a draft. The archive is the folder given with `--root`, or the
nearest folder above the current one with a configuration file; this is
`core.find_root`, explained with the configuration in the chapters on the
core.

    # in the docstring of osheaf:
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
      accept URL ID          copy one vetted version of another archive's object (a journal)
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

The module imports `core` at once, since most commands are functions of
it; the other modules (collections, arXiv, mirrors, accepted copies) are
imported only by the commands that need them.

The parser
----------

`build_parser` builds the whole parser with `argparse`: two options common
to every command, `--version` and `--root`, and then one sub-parser per
command. The description is the docstring above, printed as it is
(`RawDescriptionHelpFormatter`), since its columns are aligned by hand.

Each sub-parser records, with `set_defaults(func=...)`, the function of
the core that carries out its command, which receives the parsed options
as its only argument. Commands whose function lives in a module imported
lazily, or that need some preparation first, have `func=None` and are
dispatched by name in `main`. The order in which the commands are added is
the order in which `osheaf --help` lists them.

    # in the parser of osheaf:
    def build_parser():
        p = argparse.ArgumentParser(prog="osheaf", description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
        p.add_argument("--version", action="version", version=f"opensheaf {__version__}")
        p.add_argument("--root", help="the archive folder (default: found from the current folder)")
        sub = p.add_subparsers(dest="cmd", required=True)

        <<the options of osheaf deposit>>

        <<the options of osheaf relicense>>

        <<the options of osheaf relate>>

        <<the options of osheaf notice>>
        <<the options of osheaf withdraw>>
        <<the options of osheaf complete>>
        <<the options of osheaf accept>>
        <<the options of osheaf mirror>>
        <<the options of osheaf collection>>
        <<the options of osheaf collect, index and verify>>

        <<the options of osheaf zenodo>>

        <<the options of osheaf arxiv>>

        <<the options of osheaf init>>
        sub.add_parser("help-config", help="describe osheaf.json").set_defaults(func=None)
        return p

The last command, `help-config`, prints the docstring of the core, which
describes the configuration file `osheaf.json`.

### Depositing: `osheaf deposit`

A deposit adds a document, or a new document version of a document, to
the archive (the chapter on deposits explains how). Its options follow the
three ways a version can arrive: a TeXmacs source, which the archive
typesets itself; any other source with its PDF, given with `--pdf`; or a
PDF alone, with `--no-source` saying why the sources are not available
(section 7.2 of the specification).

```
osheaf deposit kpz-uniqueness paper.tex --pdf paper.pdf \
    --title "Energy solutions of KPZ are unique" --author "Doe, Jane|Example University" \
    --extra-source refs.bib --rights cc-by-4.0 --available 2015-08-31
osheaf deposit old-notes --pdf notes.pdf --no-source "the sources are lost" \
    --title "Old notes" --author "Doe, Jane"
```

The identifier and the source are optional for `argparse`, since both may
come from a file given with `--from` (below); whether the identifier, the
title and an author are there is checked after the file is read. The
description of the command is the docstring of `core.deposit`, so that the
help and the function say the same thing.

The options come in four groups:

    # in the options of osheaf deposit:
    <<the sources and renditions of a deposit>>
    <<the description of a deposited version>>
    <<the dates and the place of a deposited version>>
    <<the licence, relations and agreement of a deposit>>

First the files: the main source, the PDF, or the reason why there are no
sources, and the media type of the source when its extension does not
tell it.

    # in the sources and renditions of a deposit:
    d = sub.add_parser("deposit", help="deposit a document, or a new document version",
                       description=core.deposit.__doc__)
    d.add_argument("id", nargs="?")
    d.add_argument("source", nargs="?", help="the main source (.tm: typeset by the archive; "
                   "anything else: give the PDF with --pdf)")
    d.add_argument("--pdf", help="the PDF of this version (required unless the source is TeXmacs)")
    d.add_argument("--no-source", metavar="REASON",
                   help="deposit only the PDF, saying why the sources are not available")
    d.add_argument("--source-format", help="media type of the main source (default: from its extension)")

The description of the version: abstract, keywords, language, the tools
that produced the PDF (section 9: `toolchain`), title and authors. An
author is written as `Family, Given|Affiliation`, as printed in the
document; the options that may be repeated (`action="append"`) give
lists.

    # in the description of a deposited version:
    d.add_argument("--abstract", help="the abstract (plain text, mathematics in $...$)")
    d.add_argument("--abstract-file", help="a UTF-8 file with the abstract (paragraphs separated by blank lines)")
    d.add_argument("--keyword", action="append", help="a keyword (repeatable)")
    d.add_argument("--language", help="default: en")
    d.add_argument("--toolchain", action="append", metavar="NAME=VERSION",
                   help="a tool that produced the PDF (repeatable), e.g. pdflatex=TeX Live 2025")
    d.add_argument("--title")
    d.add_argument("--author", action="append",
                   help='"Family, Given|Affiliation", as printed in the document')

The dates follow section 8 of the specification. `--available` (also
spelt `--date`) is when this version first became public, by default the
day of the deposit; `--created` is for a version that was not public at the
time; `--issued` is the first public appearance of the work. The stage is
one of the NISO Journal Article Versions (section 9). `--after N` places a
version found later after document version N in the history (section 7.3)
instead of making it the current version.

    # in the dates and the place of a deposited version:
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

The rest: the DataCite resource type, the licence (an identifier of the
core's table `RIGHTS`, or free text), relations to the same work
elsewhere, further sources at the logical path the main source refers to,
the message of the inventory, and the record of the authors' agreement
(section 9: `agreement`), which a journal depositing its version of record
needs. Finally `--from` names a file of options, and the function of the
command is `core.deposit`.

    # in the licence, relations and agreement of a deposit:
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

### Changing the description: `relicense` and `relate`

Two commands write description-only versions (section 7.3): versions that
hold the same files and change only the description. `relicense` gives the
document a new licence, which needs the authors' agreement: `--method`
records how they agreed, and `--date` when.

```
osheaf relicense kpz-uniqueness --rights cc-by-4.0 --method "confirmed by email"
```

Here `--rights` must be one of the licences the core knows. `argparse`
checks the choice only for a value given on the command line; a value from
a file is checked again after the file is read (below).

    # in the options of osheaf relicense:
    r = sub.add_parser("relicense", help="description-only version with a new licence")
    r.add_argument("id", nargs="?")
    r.add_argument("--rights", choices=sorted(core.RIGHTS))
    r.add_argument("--method", help="how the authors agreed, e.g. 'confirmed by email'")
    r.add_argument("--date", help="date of the agreement (default today)")
    r.add_argument("--message")
    r.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    r.set_defaults(func=core.relicense)

`relate` links the document to the same work elsewhere, on arXiv or by a
DOI (section 8.1), by default as `IsIdenticalTo`. It can also correct the
`Issued` date, which is how one records that the work first appeared
elsewhere, before its deposit here.

```
osheaf relate kpz-uniqueness --to arxiv:1508.07764 --issued 2015-08-31
```

    # in the options of osheaf relate:
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

### Later statements: `notice`, `withdraw` and `complete`

A document version cannot change once deposited, but things can be said
about it later. A notice (section 7.3), such as an erratum, is about one
document version, given with `--about`; it has a short text, a file with
the full statement, or both, as every note of section 9.

```
osheaf notice kpz-uniqueness --about 2 --text "Theorem 2 is wrong as stated." --file erratum.pdf
```

    # in the options of osheaf notice:
    nt = sub.add_parser("notice", help="a notice about a document version (description-only)")
    nt.add_argument("id")
    nt.add_argument("--about", type=int, required=True, help="the document version it is about")
    nt.add_argument("--text", help="the notice (plain text)")
    nt.add_argument("--file", help="a file with the full statement (PDF, Markdown, ...)")
    nt.add_argument("--date", help="default: today")
    nt.add_argument("--message")
    nt.set_defaults(func=core.notice)

A withdrawal (section 11.1) is about the whole document. Its reason is
again a note, a text or a file; the content stays, and the document gets
no new versions.

```
osheaf withdraw kpz-uniqueness --reason "The main result is wrong."
```

    # in the options of osheaf withdraw:
    w = sub.add_parser("withdraw", help="withdraw a document (description-only; the content stays)")
    w.add_argument("id")
    w.add_argument("--reason", help="why (plain text)")
    w.add_argument("--file", help="a file with the full statement")
    w.add_argument("--date", help="default: today")
    w.add_argument("--message")
    w.set_defaults(func=core.withdraw)

`complete` adds the sources of a version deposited without them (section
7.3, completion), for instance when the sources of an old paper are found
again. The version keeps its number, which is why it is given with
`--version`.

```
osheaf complete old-notes --version 1 --source notes.tex --extra-source fig1.pdf
```

    # in the options of osheaf complete:
    c = sub.add_parser("complete", help="add the sources of a version deposited without them")
    c.add_argument("id")
    c.add_argument("--version", type=int, required=True, help="the document version")
    c.add_argument("--source", required=True, help="the main source")
    c.add_argument("--extra-source", action="append", help="FILE[=LOGICAL/PATH]")
    c.add_argument("--source-format")
    c.add_argument("--message")
    c.set_defaults(func=core.complete)

These three commands take no file of options: their arguments are few, and
`argparse` checks the required ones itself.

### Copies from other archives: `accept`, `mirror` and `collection`

The next three commands work with other archives, given by their base URL
or, for tests and local work, by a folder. They are explained in the
chapter on collections; here are their options.

`accept` is what a journal does (section 10.5): it copies exactly one
version of another archive's object, the version it vetted, into a
document of its own archive, with the stage and the agreement it records.
Only that version needs an open licence, or `--licence-checked`.

```
osheaf accept https://example.org/papers/ kpz-uniqueness --version v2 --stage VoR \
    --agreement "the journal's publication terms"
```

    # in the options of osheaf accept:
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

`mirror` is what a library does (section 10.4): it copies the whole
object, every version, under the same identifier. Every version must then
allow redistribution.

```
osheaf mirror https://example.org/papers/ kpz-uniqueness
```

    # in the options of osheaf mirror:
    mi = sub.add_parser("mirror", help="copy another archive's object (with open licences) into this archive")
    mi.add_argument("url", help="the archive's base URL (or a local folder)")
    mi.add_argument("id")
    mi.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although a licence is not an open one")
    mi.set_defaults(func=None)

`collection` keeps curated collections, whose members may belong to any
archive. `sync` writes a collection from a file `collection.yaml`, which
lists its members in the curator's order; `update` moves the members that
follow their objects to their current versions. The collection is by
default the main collection of the archive.

```
osheaf collection sync --from collection.yaml
osheaf collection update
```

Its `--from` is not the file of options of the other commands but the
description of the collection, read by the collections module.

    # in the options of osheaf collection:
    co = sub.add_parser("collection", help="curated collections, with members from any archive")
    co.add_argument("action", choices=["sync", "update"])
    co.add_argument("collection", nargs="?", help="the collection object (default: the main collection)")
    co.add_argument("--from", dest="from_file", metavar="FILE", help="sync: collection.yaml")
    co.add_argument("--message")
    co.set_defaults(func=None)

### Keeping the archive: `collect`, `index` and `verify`

Three commands maintain the archive as a whole, and are usually run in
this order after deposits: `collect` writes a new version of the main
collection when a document has a new current version; `index` writes the
discovery document `opensheaf.json` and the readable index (the website,
unless `--no-html`); `verify` makes the checks of section 14 of the
specification, and with `--remote` also fetches the members of
collections from their archives to check their pins.

```
osheaf collect && osheaf index && osheaf verify
```

    # in the options of osheaf collect, index and verify:
    sub.add_parser("collect", help="new version of the main collection when needed").set_defaults(func=core.collect)
    i = sub.add_parser("index", help="write opensheaf.json and the readable index")
    i.add_argument("--no-html", action="store_true")
    i.set_defaults(func=core.index)
    v = sub.add_parser("verify", help="check the archive")
    v.add_argument("--remote", action="store_true",
                   help="also fetch the members of collections from their archives and check their pins")
    v.set_defaults(func=core.verify)

### Services: `zenodo` and `arxiv`

The Zenodo binding (appendix A of the specification) adds its own
sub-parser, so that its options stay beside the code that uses them, in the
chapter on Zenodo. It deposits the current document version of a
document, on the sandbox unless `--production`.

```
osheaf zenodo kpz-uniqueness --production
```

    # in the options of osheaf zenodo:
    from . import zenodo
    zenodo.add_parser(sub, core)

`arxiv` has two actions, each with options of its own, parsed by the arXiv
module. The parser here only takes the action and passes everything after
it (`argparse.REMAINDER`) unparsed; `osheaf arxiv fetch --help` is then
answered by the parser of the arXiv module.

```
osheaf arxiv fetch downloads --author doe_j_1
osheaf arxiv import downloads
```

    # in the options of osheaf arxiv:
    a = sub.add_parser("arxiv", help="download from arXiv, import into the archive")
    a.add_argument("action", choices=["fetch", "import"])
    a.add_argument("rest", nargs=argparse.REMAINDER, help="see osheaf arxiv fetch|import --help")
    a.set_defaults(func=None)

### Creating an archive: `osheaf init`

`init` makes an archive in a folder (by default the current one): the
configuration `osheaf.json`, the storage root, the templates of the
website, the main collection and the first pages. Four facts are needed:
the identifier of the archive (a URI that stays when the archive moves,
section 6.2), its name, its address and its curator. They are not marked
required here, since they may come from a file.

```
osheaf init my-papers --archive-id tag:example.org,2026:my-papers \
    --name "Papers of Jane Doe" --base-url https://example.org/papers/ --curator "Doe, Jane"
```

With `--curated` the main collection is a curated one, kept with
`osheaf collection sync`: this is how one makes an archive whose purpose
is to collect the documents of other archives.

    # in the options of osheaf init:
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

Running a command
-----------------

### Required options and files of options

Four commands take a file of options with `--from`: `deposit`,
`relicense`, `relate` and `init`. For them an option may be given on the
command line or in the file, so `argparse` cannot require it. The table
`REQUIRED` lists, for each, the options that must have a value once the
two are merged; its keys are also how `main` recognises these commands.

    # in the options a command needs, from the command line or a file:
    REQUIRED = {"deposit": ("id", "title", "author"), "relicense": ("id", "rights", "method"),
                "relate": ("id", "to"), "init": ("archive_id", "name", "base_url", "curator")}

A file may hold a list of entries, each making one run of the command:
several deposits, in order, from one file. `runs` turns the parsed command
line into the list of these runs. Without `--from` there is one run, with
an empty entry. Each entry is merged with the command line (the command
line wins, see `merge` below), and then checked: a missing option is an
error named as on the command line (`base-url`, not `base_url`), and the
licence of `relicense` must be one the core knows, since a file escapes
the `choices` of `argparse`. All entries are checked before any is run, so
that a mistake in the last entry of a file stops the command before the
first deposit.

    # in the runs of a command, one per entry of its file:
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

### Dispatching

`main` parses the arguments (those of the process, or a list, which is how
the tests call it) and sends the command where it belongs. The order of
the cases matters, because most commands need the archive to be found and
configured first (`core.configure`, which reads `osheaf.json` and sets the
paths of the core), and a few must not:

- `help-config` only prints the description of the configuration;
- the commands with files of options run once per entry. `init` creates
  the archive, so it is run before any archive is configured, and only on
  the first entry: one archive per command. The others configure the
  archive once and run every entry;
- `arxiv fetch` only downloads into a folder, and needs no archive;
- every other command configures the archive, then runs `arxiv import`,
  `accept`, `mirror` or `collection` from their modules, imported only now,
  or else the function recorded by its sub-parser.

`collection sync` needs its `collection.yaml`; this is checked here
rather than by `argparse`, because `update` takes none.

    # in the main function of osheaf:
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

`accept` and `mirror` configure the archive a second time, which is
harmless: `configure` only reads the configuration and sets the paths.

Options from a file
-------------------

A deposit has many options, and the same paper is deposited again with
each new version. It is more convenient, and leaves a record, to write
them in a file beside the paper:

```
osheaf deposit --from paper.yaml
```

`inputs.py` reads such files. Its docstring describes the format, with an
example; the rest of the module is three tables and three functions.

    # in src/opensheaf/inputs.py:
    <<the docstring of the inputs from files>>

    <<the names of the options in files>>


    <<loading a file of options>>


    <<normalising an entry of a file of options>>


    <<merging an entry with the command line>>

### The format

A file holds the options of one run, as a mapping, or of several, as a
list of mappings. The names are those of the command line without the
dashes, and a few have plural forms, more natural for a list (`authors`,
`keywords`). Paths are relative to the file, not to the current folder, so
that the file can be used from anywhere.

The choice of reader matters. A YAML reader that converts values would
turn the arXiv identifier `2611.14296` into a number, a version `1.10`
into `1.1`, and a date into a `datetime.date`. PyYAML's `BaseLoader`
keeps every value as text, as it is written, which is what the command
line would have given.

    # in the docstring of the inputs from files:
    """Inputs from YAML (or JSON) files: `osheaf deposit --from paper.yaml`.

    A file holds the same options as the command line, with their names (`title`,
    `author` or `authors`, `extra-source` or `extra-sources`, `keyword` or
    `keywords`, `abstract`, `abstract-file`, `available`, ...); a list of such
    mappings makes several deposits, in order. Options given on the command line
    override the file. Paths are relative to the file.

    YAML is read with every value kept as text (PyYAML's BaseLoader), so that
    nothing is converted silently: `2611.14296` stays an arXiv identifier,
    `2025-01-02` a date, `1.10` a version. The metadata the tools write stays
    JSON.

        id: kpz-uniqueness
        source: paper.tex
        pdf: paper.pdf
        extra-sources:
          - refs.bib
          - {file: figures/fig1.pdf, path: figures/fig1.pdf}
        title: Energy solutions of KPZ are unique
        authors:
          - Doe, Jane|Example University
          - {name: "Roe, Richard", affiliation: Another University}
        abstract: |
          We prove uniqueness of energy solutions of $\\partial_t h = \\Delta h + \\xi$.

          A second paragraph.
        keywords: [KPZ, energy solutions]
        rights: cc-by-4.0
        available: 2015-08-31
        related: ["IsIdenticalTo:arxiv:1508.07764"]
    """

    import json
    import sys
    from pathlib import Path

### The names of the options

Three tables say how the keys of a file become options. `ALIASES` maps the
other spellings to the name of the option (its `dest` in `argparse`):
plurals, `relations` for `related`, `tools` for `toolchain`. `PATHS` lists
the options that are files, to be read relative to the file of options;
`LISTS` those that are repeated on the command line, and so lists, where a
single value is accepted for a list of one.

    # in the names of the options in files:
    ALIASES = {"authors": "author", "keywords": "keyword", "extra_sources": "extra_source",
               "relations": "related", "tools": "toolchain"}
    PATHS = ("source", "pdf", "abstract_file", "folder")
    LISTS = ("author", "keyword", "extra_source", "related", "toolchain")

One more spelling depends on the command: `date` is the name of
`--available` in a deposit (`--date` on the command line), but its own
option, the date of the agreement, in `relicense`. It is therefore not an
alias here; `merge`, which knows the options of the command, reads `date`
as `available` only for a command that has `available` and no `date`.

### Loading

`load` reads a file, JSON if its name ends in `.json` and YAML otherwise,
and returns its entries, normalised. PyYAML is imported only here, so that
the rest of the tools work without it. A YAML error gets a hint, because
the usual cause is a title or an abstract with `: ` or starting with a
special character, which YAML reads as structure unless quoted.

    # in loading a file of options:
    def load(path):
        """The entries of a YAML or JSON file: a list of mappings."""
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".json":
            data = json.loads(text)
        else:
            try:
                import yaml
            except ImportError:
                sys.exit("reading YAML needs PyYAML: pip install pyyaml")
            try:
                data = yaml.load(text, Loader=yaml.BaseLoader)
            except yaml.YAMLError as e:
                sys.exit(f"{path}: not valid YAML: {e}\n(texts with ': ' or starting with a"
                         " special character need quotes)")
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
            sys.exit(f"{path}: expected a mapping of options, or a list of them")
        return [normalise(x, p.parent) for x in data]

### Normalising an entry

`normalise` makes an entry look like what `argparse` would have produced
from the command line. A key is lowered, its dashes become underscores,
and an alias becomes the name of its option; a single value of a list
option becomes a list of one. Then some values are rewritten:

- an author may be a mapping with `name` and `affiliation`, which becomes
  the string `Family, Given|Affiliation` of `--author`;
- an extra source may be a string `FILE` or `FILE=LOGICAL/PATH`, or a
  mapping with `file` and `path`; only the file part is relative to the
  file of options, the logical path inside the document stays as it is;
- a tool may be a string `NAME=VERSION` or a mapping of one name to its
  version;
- a path is made relative to the folder of the file;
- `after` becomes an integer, as `--after` has `type=int`, since YAML
  gave text.

Unknown keys are kept: they are refused when the entry is merged, where
the options of the command are known.

    # in normalising an entry of a file of options:
    def normalise(entry, base):
        out = {}
        for k, v in entry.items():
            k = str(k).strip().lower().replace("-", "_")
            k = ALIASES.get(k, k)
            if k in LISTS and not isinstance(v, list):
                v = [v]
            if k == "author":
                v = [a if isinstance(a, str) else
                     a["name"] + (f"|{a['affiliation']}" if a.get("affiliation") else "") for a in v]
            elif k == "extra_source":
                v = [str(base / x) if isinstance(x, str) and "=" not in x else
                     (str(base / x.partition("=")[0]) + "=" + x.partition("=")[2]) if isinstance(x, str) else
                     str(base / x["file"]) + (f"={x['path']}" if x.get("path") else "") for x in v]
            elif k == "toolchain":
                v = [x if isinstance(x, str) else "=".join(next(iter(x.items()))) for x in v]
            elif k in PATHS and isinstance(v, str):
                v = str(base / v)
            elif k == "after":
                v = int(v)
            out[k] = v
        return out

### Merging with the command line

`merge` returns a new namespace, leaving the parsed command line as it is
for the next entry. A key that is not an option of the command is an error
(a typing mistake such as `titel` would otherwise be silently ignored);
so are the names `argparse` uses for its own bookkeeping (`cmd`, `func`,
`from_file`), which no file should set.

A value of the file is taken unless the option was given on the command
line, which is when its value differs from its default. The defaults are
those of the command's sub-parser, found among the actions of the parser
(`--root`, an option of the parser itself, has the default `None` for the
sub-parser too). So the command line overrides the file, which lets one
deposit from a file with, say, a corrected title, and an option with a
default, such as `--type` of `deposit` (`Preprint`) or `--relation` of
`relate` (`IsIdenticalTo`), takes the value of the file. The one case
this cannot tell apart is an option given on the command line with its
default value: the file then wins, which only matters when the two
disagree.

    # in merging an entry with the command line:
    def merge(args, entry, parser, command):
        """A copy of ARGS with the values of ENTRY for the options the command line
        did not give."""
        import argparse
        ns = argparse.Namespace(**vars(args))
        known = set(vars(args)) - {"cmd", "func", "from_file"}
        if "date" in entry and "date" not in known and "available" in known:
            entry = {("available" if k == "date" else k): v for k, v in entry.items()}
        unknown = [k for k in entry if k not in known]
        if unknown:
            parser.error(f"{command}: unknown option(s) in the file: {', '.join(sorted(unknown))}")
        sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices[command]
        for k, v in entry.items():
            if getattr(ns, k) == sub.get_default(k):
                setattr(ns, k, v)
        return ns
