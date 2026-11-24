The command line
================

This chapter is the outer layer of opensheaf-py: the command `osheaf`,
which reads the options of a command and calls the function that does the
work. Almost nothing is decided here. Deposits, description-only versions,
the owner catalogues, the index and verification are explained in the
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
    """osheaf: keep an OpenSheaf archive (specification 0.2, https://opensheaf.org).

    The archive is the folder given with --root, or else the nearest folder above
    the current one that has an osheaf.json (see `osheaf help-config`). Lines are
    named by their labels in the archive.

    Commands:
      init                   create an archive (osheaf.json, storage root, owner, owner catalogue)
      owner init|rotate|expose|end|show   make an owner, change its keys, end it, show it
      key new                a new current key for this device
      key push|pull|list|forget   current keys to and from a key wallet (--wallet)
      key export|import --clipboard   a key to and from a password manager
      key enroll|unlock      a passkey (Touch ID) opens the keys of the wallet
      deposit LABEL [SOURCE] deposit a document (TeXmacs, or any source with --pdf);
                             --new seals a new work under a new label
      relicense LABEL        description-only version with a new licence
      relate LABEL           description-only version linking the same work elsewhere
      describe LABEL         description-only version correcting title, abstract, keywords, authors
      notice LABEL           a notice about a document version
      withdraw LABEL         withdraw a document (the content stays)
      complete LABEL         add the sources of a version deposited without them
      collect                new versions of the owner catalogues when needed (--owner: one)
      collection new|add|remove|follow|update|status|sync
                             catalogues and selections, with members of any archive
      resolve URI            find and check what a sheaf: URI names, in any archive
      mirror URI | --all     copy a line written elsewhere, with its owner's key log
      branch URI --label LABEL   a branch of a signed version of another line, or move its branch point
      accept URI --selection LABEL   an accepted copy (a branch) listed by a selection
      owner pull URL|PATH    meet another copy of a key log: extend it, or record a fork
      sign LABEL --version vN    sign again a version contested by an exposed key
      draft new|deposit|delete DRAFT   unsigned work in progress, at draft/<id>/
      seal DRAFT --label LABEL   seal the work of a draft as a new line
      takedown LABEL --reason TEXT   delete an object, leaving a tombstone
      index                  write opensheaf.json, the indexes and the website (or the TeXmacs index)
      verify                 check the archive (section 14 of the specification)
      zenodo LABEL           a DOI for the current version (sandbox, or --production)
      arxiv fetch            download papers from arXiv (no archive needed)
      arxiv import DOWNLOADS import the downloads, one signed line per paper
      help-config            describe osheaf.json and ~/.config/opensheaf/config.json

    The website (osheaf.json "index": {"html": ...}) is written again after every
    command that changes the archive.

    deposit, relicense, relate, describe and init also take their options from a
    YAML or JSON file: --from FILE (a list of entries: several, in order).

    Warning: OpenSheaf 0.2 is a draft. Until version 1.0, a revision may change
    the format in incompatible ways, and archives may have to be rebuilt.
    """

    import argparse
    import sys

    from . import __version__, core

The module imports `core` at once, since most commands are functions of
it; the other modules (resolution, collections, mirrors, branches, drafts,
takedowns, arXiv) are imported only by the commands that need them.

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

        <<the options of osheaf describe>>

        <<the options of osheaf notice>>
        <<the options of osheaf withdraw>>
        <<the options of osheaf complete>>
        <<the options of osheaf resolve>>
        <<the options of osheaf collection>>
        <<the options of osheaf mirror>>
        <<the options of osheaf branch and accept>>
        <<the options of osheaf draft and seal>>
        <<the options of osheaf takedown>>
        <<the options of osheaf collect, index and verify>>

        <<the options of osheaf zenodo>>

        <<the options of osheaf arxiv>>

        <<the options of osheaf init>>

        <<the options of osheaf owner and key>>
        sub.add_parser("help-config", help="describe osheaf.json and your own configuration (key wallets)"
                       ).set_defaults(func=None)
        return p

The names on the command line are the same everywhere: a line of the
archive, a collection among them, is named by its label, `LABEL`, as a
positional argument (`deposit`, `relicense`, `notice`, `withdraw`,
`collection new`, `sign`, `takedown`, `zenodo`, ...) or as the value of an
option (`--label`, `--selection`); a draft by its identifier, `DRAFT`. The
commands that make keys take the security level with `--keys LEVEL`, and
the `key` commands the wallet with `--wallet WALLET`.

The last command, `help-config`, prints the docstring of the core, which
describes the configuration file `osheaf.json`, and the summary of the
user's own configuration, `~/.config/opensheaf/config.json`, and of command
wallets, from [chapter 9](09-wallets.md).

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

The options come in four groups, which a deposit into a draft
([drafts](24-drafts.md)) shares, and so are added by a function of their
own; `--new` and `--owner`, which seal a new work, and `--from` belong to
`deposit` alone.

    # in the options of osheaf deposit:
    d = sub.add_parser("deposit", help="deposit a document, or a new document version",
                       description=core.deposit.__doc__)
    deposit_options(d)
    d.add_argument("--new", action="store_true",
                   help="seal a new work under the new label LABEL (section 10.2)")
    d.add_argument("--owner", help="--new: the owner of the new line, an owner the archive hosts "
                   "(default: the archive's)")
    d.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    d.set_defaults(func=core.deposit)

The function that adds the four groups:

    # in the parser of osheaf:
    RIGHTS_HELP = "an SPDX key, one of " + ", ".join(sorted(core.RIGHTS)) + ", or a statement in plain text"


    def rights_option(value):
        """--rights, checked as core.check_rights does."""
        try:
            return core.check_rights(value)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from None


    def deposit_options(d, draft=False):
        """The options of a deposit, shared by osheaf deposit and osheaf draft (DRAFT: a draft's)."""
        <<the sources and renditions of a deposit>>
        <<the description of a deposited version>>
        <<the dates and the place of a deposited version>>
        <<the licence, relations and agreement of a deposit>>

First the files: the main source, the PDF, or the reason why there are no
sources, and the media type of the source when its extension does not
tell it.

    # in the sources and renditions of a deposit:
    d.add_argument("id", nargs="?", metavar="DRAFT" if draft else "LABEL",
                   help="the identifier of the draft" if draft else "the label of the line in the archive")
    d.add_argument("source", nargs="?", help="the main source (.tm: typeset by the archive; "
                   "anything else: give the PDF with --pdf)")
    d.add_argument("--pdf", help="the PDF of this version (required unless the source is TeXmacs)")
    d.add_argument("--no-source", metavar="REASON",
                   help="deposit only the PDF, saying why the sources are not available")
    d.add_argument("--source-format", help="media type of the main source (default: from its extension)")

The description of the version: abstract, keywords, language, the tools
that produced the PDF (section 4.3: `toolchain`), title and authors. An
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

The dates follow section 4.4 of the specification. `--available` (also
spelt `--date`) is when this version was first made available, by default
the day of the deposit, public or not; `--created` is when a version
deposited long after was written; `--issued` is the first public appearance of the work. The stage is
one of the NISO Journal Article Versions (section 4.3). `--after N` places a
version found later after document version N in the history (section 4.2)
instead of making it the current version.

    # in the dates and the place of a deposited version:
    d.add_argument("--available", "--date", dest="available",
                   help="when this version was first made available (default: today, the deposit)")
    d.add_argument("--created", help="when this version was written, for a version deposited long after")
    d.add_argument("--issued", help="first public appearance of the work (default: as before, or --available)")
    d.add_argument("--date-info", help="how the date is known (of --created if given), e.g. 'from the file's modification time'")
    d.add_argument("--stage", choices=["AO", "SMUR", "AM", "P", "VoR", "CVoR", "EVoR"],
                   help="NISO-JAV stage of this version")
    d.add_argument("--changes", help="change note of this version")
    d.add_argument("--after", type=int, help="place this version after document version N in the"
                   " history (a version found later); otherwise it becomes the current version")

The rest: the DataCite resource type, the licence (an identifier of the
core's table `RIGHTS`, or free text), relations to the same work
elsewhere, further sources at the logical path the main source refers to,
the message of the inventory, and the record of the authors' agreement
(section 4.3: `agreement`), which a journal depositing its version of record
needs. `--licence-file` names the file of the deposit, among its sources,
that holds the full text or terms of the licence (section 4.3: `licence`), for
instance the `LICENSE` of a package of sources, or a licence without an SPDX
identifier. `--i-know` lets a deposit extend versions that are not signed,
or are contested, once the depositor has looked at them (section 7.3).

    # in the licence, relations and agreement of a deposit:
    d.add_argument("--type", default="Preprint")
    d.add_argument("--rights", type=rights_option,
                   help=RIGHTS_HELP + " (default: as the previous version, or 'All rights reserved')")
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
    d.add_argument("--i-know", dest="i_know", action="store_true",
                   help="extend versions that are not signed, or are contested, having looked at them (section 7.3)")

### Changing the description: `relicense`, `relate` and `describe`

Three commands write description-only versions (section 4.2): versions that
hold the same files and change only the description. `relicense` gives the
document a new licence, which needs the authors' agreement: `--method`
records how they agreed, and `--date` when.

```
osheaf relicense kpz-uniqueness --rights cc-by-4.0 --method "confirmed by email"
```

`--rights` takes the same values as for `deposit`: a licence the core
knows by its SPDX key, or a statement (`core.check_rights`). `argparse`
checks a value given on the command line; a value from a file is checked
again after the file is read (below).

    # in the options of osheaf relicense:
    r = sub.add_parser("relicense", help="description-only version with a new licence")
    r.add_argument("id", nargs="?", metavar="LABEL", help="the label of the line")
    r.add_argument("--rights", type=rights_option, help=RIGHTS_HELP)
    r.add_argument("--method", help="how the authors agreed, e.g. 'confirmed by email'")
    r.add_argument("--date", help="date of the agreement (default today)")
    r.add_argument("--message")
    r.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    r.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    r.set_defaults(func=core.relicense)

`relate` links the document to the same work elsewhere, on arXiv or by a
DOI (section 4.4), by default as `IsIdenticalTo`. It can also correct the
`Issued` date, which is how one records that the work first appeared
elsewhere, before its deposit here.

```
osheaf relate kpz-uniqueness --to arxiv:1508.07764 --issued 2015-08-31
```

    # in the options of osheaf relate:
    rl = sub.add_parser("relate", help="description-only version linking the same work elsewhere")
    rl.add_argument("id", nargs="?", metavar="LABEL", help="the label of the line")
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

`describe` corrects the description itself: the title, the abstract, the
keywords or the authors, each replaced by what is given, the rest kept
(the [description-only versions](14-description.md) explain the rules).
At least one must be given, and must differ from what is recorded.

```
osheaf describe phi43-pde-construction --abstract-file abstract.txt \
    --message "Abstract: \\emph removed (import of arXiv 1810.01700)"
osheaf describe fractional-phi42-mass-gap \
    --author "Duch, Paweł|Institute of Mathematics, Polish Academy of Sciences" \
    --author "Gubinelli, Massimiliano|Mathematical Institute, University of Oxford"
```

The options are those of a deposit, with the same names, so that a file of
options of a deposit can be cut down to a correction. `--abstract` and
`--abstract-file` exclude each other, which `argparse` checks on the
command line and the core again after a file is merged.

    # in the options of osheaf describe:
    ds = sub.add_parser("describe", help="description-only version correcting the title, abstract,"
                        " keywords or authors")
    ds.add_argument("id", nargs="?", metavar="LABEL", help="the label of the line")
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

### Later statements: `notice`, `withdraw` and `complete`

A document version cannot change once deposited, but things can be said
about it later. A notice (section 4.2), such as an erratum, is about one
document version, given with `--about`; it has a short text, `--text`,
always, which every page that shows the version shows, and may have a file
with the full statement besides (section 4.3).

```
osheaf notice kpz-uniqueness --about 2 --text "Theorem 2 is wrong as stated." --file erratum.pdf
```

Notices are numbered in the order they are given, from 1. A later notice
corrects or withdraws an earlier one about the same version by naming its
number, with `--replaces`; the earlier one is then no longer shown as
current:

```
osheaf notice kpz-uniqueness --about 2 --replaces 1 --text "The notice of 3 March is withdrawn: Theorem 2 is correct."
```

    # in the options of osheaf notice:
    nt = sub.add_parser("notice", help="a notice about a document version (description-only)")
    nt.add_argument("id", metavar="LABEL", help="the label of the line")
    nt.add_argument("--about", type=int, required=True, help="the document version it is about")
    nt.add_argument("--text", required=True, help="the notice (plain text)")
    nt.add_argument("--file", help="a file with the full statement (PDF, Markdown, ...)")
    nt.add_argument("--date", help="the date the notice was issued (default: today)")
    nt.add_argument("--replaces", type=int, metavar="N",
                    help="the number of an earlier notice about the same version that it corrects or withdraws")
    nt.add_argument("--message")
    nt.add_argument("--i-know", dest="i_know", action="store_true",
                     help="extend versions that are not signed, or are contested (section 7.3)")
    nt.set_defaults(func=core.notice)

A withdrawal (section 13.1) is about the whole line. Its reason is
again a note: a text, `--reason`, always, and a file besides if wanted;
the content stays, and the document gets no new versions.

```
osheaf withdraw kpz-uniqueness --reason "The main result is wrong."
```

    # in the options of osheaf withdraw:
    w = sub.add_parser("withdraw", help="withdraw a document (description-only; the content stays)")
    w.add_argument("id", metavar="LABEL", help="the label of the line")
    w.add_argument("--reason", required=True, help="why (plain text)")
    w.add_argument("--file", help="a file with the full statement")
    w.add_argument("--date", help="default: today")
    w.add_argument("--message")
    w.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    w.set_defaults(func=core.withdraw)

`complete` adds the sources of a version deposited without them (section
4.2, completion), for instance when the sources of an old paper are found
again. The version keeps its number, which is why it is given with
`--version`.

```
osheaf complete old-notes --version 1 --source notes.tex --extra-source fig1.pdf
```

    # in the options of osheaf complete:
    c = sub.add_parser("complete", help="add the sources of a version deposited without them")
    c.add_argument("id", metavar="LABEL", help="the label of the line")
    c.add_argument("--version", type=int, required=True, help="the document version")
    c.add_argument("--source", required=True, help="the main source")
    c.add_argument("--extra-source", action="append", help="FILE[=LOGICAL/PATH]")
    c.add_argument("--source-format")
    c.add_argument("--message")
    c.add_argument("--i-know", dest="i_know", action="store_true",
                    help="extend versions that are not signed, or are contested (section 7.3)")
    c.set_defaults(func=core.complete)

These three commands take no file of options: their arguments are few, and
`argparse` checks the required ones itself.

### Across archives: `resolve`, `collection`, `mirror`, `branch` and `accept`

These commands work with other archives, named by their base URLs, or, for
local work and tests, by folders; where an archive is read may be
configured apart from its base URL (`locations`,
[resolution](20-resolution.md)). Lines are named by `sheaf:` URIs
(section 12.1), whose `at` gives a first place to look; `--at` adds others.

`resolve` finds and checks what a URI names: the copies of the line found,
the latest signed version among those that agree, or the version a pin
names, with its status (section 12.3).

```
osheaf resolve "sheaf:zzgdggwl:56wo6cdp/v2" --at https://mgubi.org/papers/
```

    # in the options of osheaf resolve:
    rv = sub.add_parser("resolve", help="find and check what a sheaf: URI names (section 12.3)")
    rv.add_argument("uri", help="a sheaf: URI, possibly a short form")
    rv.add_argument("--at", action="append", metavar="URL", help="a place to look: a base URL or a folder")
    rv.add_argument("--json", action="store_true", help="print the result as JSON")
    rv.set_defaults(func=None)

`collection` keeps the catalogues and selections of the archive
([collections](21-collections.md)): `new` makes one, `add` and `remove`
change its members, `follow` sets which members of a catalogue follow
their lines, `update` follows them, `status` resolves every member and
prints its status (section 8.5), and `sync` writes a collection from a
file `collection.yaml`.

```
osheaf collection new reading --type catalogue --title "Reading list"
osheaf collection add reading "sheaf:zzgdggwl...?at=https%3A%2F%2Fmgubi.org%2Fpapers%2F" --follow
osheaf collection update
osheaf collection sync issue-1 --from issue-1.yaml
```

    # in the options of osheaf collection:
    co = sub.add_parser("collection", help="catalogues and selections, with members of any archive")
    cosub = co.add_subparsers(dest="action", required=True)
    cn = cosub.add_parser("new", help="a new, empty collection")
    cn.add_argument("label", metavar="LABEL", help="the label of the new collection")
    cn.add_argument("--type", choices=["catalogue", "selection"], required=True)
    cn.add_argument("--title", required=True)
    cn.add_argument("--description")
    cn.add_argument("--order", choices=["manual", "issued-desc", "issued-asc"])
    cn.add_argument("--owner", help="the owner of the collection, an owner the archive hosts")
    for name, helptext in (("add", "add members, or revisions of a member of a selection"),
                           ("remove", "remove members, or revisions"),
                           ("follow", "members of a catalogue that follow their lines")):
        ca = cosub.add_parser(name, help=helptext)
        ca.add_argument("collection", metavar="LABEL")
        ca.add_argument("uri", nargs="+", metavar="URI", help="a sheaf: URI, or the label of a line here")
        if name != "follow":
            ca.add_argument("--revision", type=int, action="append", metavar="N",
                            help="a document version (selections; repeatable)")
        if name == "add":
            ca.add_argument("--at", action="append", metavar="URL", help="where copies are found (repeatable)")
            ca.add_argument("--follow", action="store_true", help="follow the line (catalogues)")
        if name == "follow":
            ca.add_argument("--off", action="store_true", help="stop following")
        ca.add_argument("--message")
    cu = cosub.add_parser("update", help="follow the members that follow their lines")
    cu.add_argument("collection", nargs="*", metavar="LABEL")
    cs = cosub.add_parser("status", help="the status of every member (section 8.5)")
    cs.add_argument("collection", metavar="LABEL")
    cy = cosub.add_parser("sync", help="write a collection from collection.yaml")
    cy.add_argument("collection", metavar="LABEL")
    cy.add_argument("--from", dest="from_file", metavar="FILE", required=True)
    cy.add_argument("--message")
    co.set_defaults(func=None)

`mirror` is what a library does (section 11): it copies a line written
elsewhere, with the key log of its owner, up to its latest signed version,
and brings it up to date when run again; `--all` updates every mirror.
The archive answers for having the right to redistribute what it copies
(section 11.2): a version not under a licence known to be open is copied
with a warning, which `--licence-checked` silences.

```
osheaf mirror "sheaf:zzgdggwl...?at=https%3A%2F%2Fmgubi.org%2Fpapers%2F" --label duch-gubinelli
osheaf mirror --all
```

    # in the options of osheaf mirror:
    mi = sub.add_parser("mirror", help="copy a line written elsewhere, with its owner's key log (section 11)")
    mi.add_argument("uri", nargs="?", help="the sheaf: URI of the line")
    mi.add_argument("--at", action="append", metavar="URL", help="where copies are found (repeatable)")
    mi.add_argument("--label", help="a label for the line here")
    mi.add_argument("--all", action="store_true", help="bring every mirror up to date")
    mi.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although a licence is not one known to be open: no warning")
    mi.set_defaults(func=None)

`branch` makes a branch of a signed version of another line, under the
archive's owner or another it hosts, or moves the branch point of its
branch of that line to a later version (section 9); `accept` is what a
journal does (section 9.6): a branch, its accepted copy, listed in a
selection with the revision it holds, and with `--with-original` the
original revision set too.

```
osheaf branch "sheaf:zzgdggwl.../v2" --at https://mgubi.org/papers/ --label continued
osheaf accept "sheaf:zzgdggwl.../v2" --at https://mgubi.org/papers/ --selection issue-1 --label duch-gubinelli
```

    # in the options of osheaf branch and accept:
    for name, helptext in (("branch", "a branch of a signed version of another line (section 9)"),
                           ("accept", "an accepted copy, listed in a selection (section 9.6)")):
        b = sub.add_parser(name, help=helptext)
        b.add_argument("uri", help="the sheaf: URI of the parent version")
        b.add_argument("--at", action="append", metavar="URL", help="where copies are found (repeatable)")
        b.add_argument("--label", help="the label of the branch here")
        b.add_argument("--message")
        if name == "branch":
            b.add_argument("--owner", help="the owner of the branch, an owner the archive hosts")
        else:
            b.add_argument("--selection", required=True, help="the label of the selection")
            b.add_argument("--with-original", action="store_true",
                           help="also list the original revision set (section 9.6)")
        b.set_defaults(func=None)

### Drafts, seals and takedowns

`draft` keeps unsigned work in progress at `draft/<id>/`
([drafts](24-drafts.md)): `new` makes a draft with a first deposit,
`deposit` adds a version (or rewrites the head, `--replace`), `delete`
removes it; their options are those of a deposit. `seal` makes a new line
from the work of a draft.

```
osheaf draft new notes notes.tex --pdf notes.pdf --title "Notes" --author "Doe, Jane"
osheaf seal notes --label lecture-notes
```

    # in the options of osheaf draft and seal:
    dr = sub.add_parser("draft", help="unsigned work in progress at draft/<id>/ (section 10.1)")
    drsub = dr.add_subparsers(dest="action", required=True)
    for name, helptext in (("new", "make a draft with a first deposit"),
                           ("deposit", "deposit a new version into a draft")):
        x = drsub.add_parser(name, help=helptext)
        deposit_options(x, draft=True)
        if name == "deposit":
            x.add_argument("--replace", action="store_true", help="rewrite the head of the draft")
    x = drsub.add_parser("delete", help="delete a draft (no tombstone)")
    x.add_argument("id", metavar="DRAFT", help="the identifier of the draft")
    dr.set_defaults(func=None)
    se = sub.add_parser("seal", help="seal the work of a draft as a new line (section 10.2)")
    se.add_argument("id", metavar="DRAFT", help="the identifier of the draft")
    se.add_argument("--label", required=True, help="the label of the new line")
    se.add_argument("--owner", help="the owner of the new line, an owner the archive hosts")
    se.add_argument("--delete-draft", action="store_true", help="delete the draft once sealed")
    se.add_argument("--message")
    se.set_defaults(func=None)

`takedown` deletes an object and leaves a tombstone (section 13.2); a key
log that objects of the archive need is taken down only by law or at its
keeper's request.

```
osheaf takedown old-notes --reason "Taken down at the request of the holder of the rights."
```

    # in the options of osheaf takedown:
    td = sub.add_parser("takedown", help="delete an object, leaving a tombstone (section 13.2)")
    td.add_argument("id", metavar="LABEL", help="the label or identifier of the object")
    td.add_argument("--reason", required=True, help="a plain text, not repeating what is taken down")
    who = td.add_mutually_exclusive_group()
    who.add_argument("--by-law", action="store_true", help="a key log taken down by law")
    who.add_argument("--keeper", action="store_true", help="a key log taken down at its keeper's request")
    td.add_argument("--yes", action="store_true", help="do not ask to confirm")
    td.set_defaults(func=None)

### Keeping the archive: `collect`, `index` and `verify`

Three commands maintain the archive as a whole, and are usually run in
this order after deposits: `collect` writes a new version of the main
catalogue when a document has a new signed version; `index` writes the
discovery document `opensheaf.json`, the indexes `names/`, `owners/` and
`sha512/` (section 12.5) and the readable index, the website or a TeXmacs
index ([chapter 16](16-index.md)), which other commands also keep up to
date (below);
`verify` makes the checks of section 14 of the specification, and with
`--remote` also resolves the members of collections held in other
archives, and gives their statuses (section 14.5), and reads the keepers'
ORCID records and domains, to say whether they confirm their owners
(section 6.6).

```
osheaf collect && osheaf index && osheaf verify
```

    # in the options of osheaf collect, index and verify:
    c = sub.add_parser("collect", help="new versions of the owner catalogues when needed")
    c.add_argument("--owner", help="only the catalogue of this owner, an owner the archive hosts")
    c.set_defaults(func=core.collect)
    i = sub.add_parser("index", help="write opensheaf.json, the indexes and the readable index")
    i.add_argument("--no-html", action="store_true",
                   help="do not write the HTML of the website (opensheaf.json and the indexes only)")
    i.set_defaults(func=core.index)
    v = sub.add_parser("verify", help="check the archive")
    v.add_argument("--remote", action="store_true",
                   help="also resolve the members of collections held in other archives (section 14.5), "
                        "and check the links of owners to their keepers (section 6.6)")
    v.add_argument("--json", action="store_true", help="print the findings as JSON")
    v.set_defaults(func=core.verify)

### Services: `zenodo` and `arxiv`

The Zenodo binding (appendix A.1 of the specification) adds its own
sub-parser, so that its options stay beside the code that uses them, in the
[chapter on Zenodo](50-zenodo.md). It deposits the current document version
of a line, signed, on the sandbox unless `--production`.

```
osheaf zenodo kpz-uniqueness --production
```

    # in the options of osheaf zenodo:
    from . import zenodo
    zenodo.add_parser(sub, core)

`arxiv` has two actions, each with options of its own, parsed by the
[arXiv module](40-arxiv.md): `fetch` downloads, `import` seals one line per
paper and signs each version. The parser here only takes the action and passes everything after
it (`argparse.REMAINDER`) unparsed; `osheaf arxiv fetch --help` is then
answered by the parser of the arXiv module.

```
osheaf arxiv fetch downloads --author doe_j_1
osheaf arxiv import downloads --agreement "deposited by an author"
```

    # in the options of osheaf arxiv:
    a = sub.add_parser("arxiv", help="download from arXiv, import into the archive")
    a.add_argument("action", choices=["fetch", "import"])
    a.add_argument("rest", nargs=argparse.REMAINDER, help="see osheaf arxiv fetch|import --help")
    a.set_defaults(func=None)

### Creating an archive: `osheaf init`

`init` makes an archive in a folder (by default the current one): the
configuration `osheaf.json`, the storage root, the owner of the archive
with its key log, its owner catalogue, the discovery document and the
website, with its templates copied into `templates/`. Three
facts are needed: its name, its address and its curator, which may come
from a file, and so are not marked required here. The owner is made at
once with `--new-owner`, which takes the options of `osheaf owner init`
(below), or is an existing owner, `--owner NAME`, whose key log is copied
from the folder of its owner object (`--key-log DIR`). `--layout hashed`
chooses the hashed layout of section 3.2, for very large archives.

```
osheaf init my-papers --name "Papers of Jane Doe" --base-url https://example.org/papers/ \
    --curator "Doe, Jane" --new-owner --export /Volumes/USB/opensheaf-keys --print
```

With `--curated` the owner catalogue is a curated one, whose members, from
any archive, and order are the curator's, kept with `osheaf collection`
([collections](21-collections.md)). With `--index texmacs` the home page is
a TeXmacs index instead of the website, made from the template given with
`--index-template` or from a minimal one ([creating an archive](18-init.md)):

```
osheaf init papers --name "Papers of Jane Doe" --base-url https://example.org/papers/ \
    --curator "Doe, Jane" --new-owner --export /Volumes/USB/opensheaf-keys \
    --index texmacs --index-template old/index-template.tm
```

    # in the options of osheaf init:
    n = sub.add_parser("init", help="create an archive (osheaf.json, storage root, owner, owner catalogue)")
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
                   help="the owner catalogue is curated (osheaf collection add|sync)")
    n.add_argument("--index", choices=["website", "texmacs"],
                   help="the home page: the website (default, profile website) or a TeXmacs index "
                        "(profile texmacs)")
    n.add_argument("--index-template", metavar="FILE",
                   help="with --index texmacs: the template of the index, copied into the archive "
                        "(default: a minimal one)")
    n.add_argument("--from", dest="from_file", metavar="FILE",
                    help="take the options from a YAML or JSON file (a list: several, in order)")
    n.set_defaults(func=None)

### Owners and keys: `osheaf owner` and `osheaf key`

The commands of owners ([chapter 19](19-owner-commands.md)) keep an
owner's key log in the archive's storage root. `owner init` makes an owner
(section 6.2), three rotation keys with a `nextThreshold` of 2 by default,
exported to `--export DIR` outside the archive, encrypted under a
passphrase asked twice (or `OPENSHEAF_PASSPHRASE`) unless
`--no-passphrase`, and printed as sheets with `--print`; the export is
confirmed by typing the check of each key, unless `--yes`.

```
osheaf owner init --export /Volumes/USB/keys --print
osheaf key new                                   # on a new laptop: prints its did:key
osheaf owner rotate --add did:key:z6Mk... --retire did:key:z6Mk... \
    --rotation-key /Volumes/USB/keys/rotation-...-a.txt --rotation-key .../rotation-...-b.txt \
    --export /Volumes/USB2/keys
osheaf owner expose did:key:z6Mk... --rotation-key ... --export ...
osheaf owner end --successor <owner name> --rotation-key ...
osheaf owner show
osheaf owner pull https://example.org/other-archive/   # a fresher copy of the key log, or a fork
osheaf sign kpz-uniqueness --version v2                # again, after an exposure
```

The keys are kept at the security level of `--keys`: `offline` (the
default and the maximum, as above), or a key wallet, `github:OWNER/REPO`
(a private repository, reached through the GitHub CLI) or `command` (a
password manager, through commands configured in `osheaf.json`), where
the rotation keys and the current keys are kept encrypted under the
passphrase, with the risk stated ([chapter 9](09-wallets.md)). Without
`--rotation-key`, the rotation keys that sign come from the wallet.

```
osheaf owner init --keys github:mgubi/opensheaf-keys     # rotation and current keys in the wallet
osheaf key pull                                           # on another machine: the current keys
osheaf key list                                           # what the wallet holds (no secrets)
osheaf owner rotate --keys offline --export /Volumes/USB/keys   # move up: new rotation keys offline
osheaf key forget --from-wallet --used                    # remove the used keys from the wallet
osheaf key export --clipboard                             # paste into a note of the Passwords app
osheaf key import --clipboard                             # on another machine, after copying the note
osheaf key enroll                                         # once: a passkey opens the keys of the wallet
osheaf key unlock                                         # on another Mac: Touch ID, the current keys pulled
```

`key enroll` creates a passkey for `unlock.opensheaf.org` in the browser
(the page `https://unlock.opensheaf.org/`, which shows the confirmation
code that the command prints), after the passphrase has opened the keys
of the wallet once, checks it with a second unlock, and lets it open them;
from then
on, a command that needs a key of the wallet asks the browser (Touch ID)
rather than the passphrase, which stays the way back: on an error of the
page, after two minutes without an answer, on Ctrl-C, or always with
`OPENSHEAF_UNLOCK=passphrase` or `OPENSHEAF_PASSPHRASE` set
([chapter 19](19-owner-commands.md)). `--no-browser` prints the address of
the page without opening it. `OPENSHEAF_PASSPHRASE_COMMAND` names a
command that prints the passphrase, run before it is asked. `key forget
--rp opensheaf.org` removes the locks of the passkeys made for the first
relying party, after `key enroll --new-passkey`; `--passkey CRED`, those
of one passkey.

The commands that make keys (`init --new-owner`, `owner init`, `rotate`,
`expose`, `end`) take the security level with `--keys LEVEL` (`offline`,
`github:OWNER/REPO` or `command`); the `key` commands, which only read or
move keys, name the wallet with `--wallet WALLET`, and otherwise use the
one configured ([chapter 9](09-wallets.md)).

`owner pull` meets the archive's copy of a key log with the copy at
another place, an archive or the folder of the owner object, as section
6.3 says ([copies](22-mirrors.md)); `sign` signs again, with current keys
not exposed, a version contested by an exposed key (section 7.1;
[chapter 19](19-owner-commands.md)).

The options of making an owner are shared by `owner init` and
`init --new-owner`.

    # in the options of osheaf owner and key:
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
    osh.add_argument("--offline", action="store_true",
                     help="do not read the keeper's ORCID record or domain to check the link (section 6.6)")
    op = osub.add_parser("pull", help="meet another copy of the key log: extend it, or record a fork")
    op.add_argument("source", metavar="URL|PATH", help="an archive, or the folder of the owner object")
    op.add_argument("--owner", help="the owner (default: the archive's)")
    ow.set_defaults(func=None)
    sg = sub.add_parser("sign", help="sign again a version contested by an exposed key (section 7.1)")
    sg.add_argument("id", metavar="LABEL", help="the label of the line")
    sg.add_argument("--version", required=True, help="the object version, e.g. v2")
    sg.add_argument("--yes", action="store_true", help="do not ask to confirm that the owner made it")
    sg.set_defaults(func=core.sign_again)
    lb = sub.add_parser("label", help="give a line a label, change it, or remove it (--unset); the old address "
                        "of its page redirects")
    lb.add_argument("line", nargs="?", metavar="LINE", help="the line: its label or identifier (with --owner, "
                    "the new label)")
    lb.add_argument("label", nargs="?", metavar="LABEL", help="the new label (section 3.1)")
    lb.add_argument("--owner", help="label the owner object of this owner instead of a line")
    lb.add_argument("--unset", action="store_true", help="remove the label")
    lb.set_defaults(func=core.label_command)
    k = sub.add_parser("key", help="current keys of this device, key wallets, password managers")
    ksub = k.add_subparsers(dest="action", required=True)
    kn = ksub.add_parser("new", help="a new current key for this device; prints its did:key")
    kn.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    kp = ksub.add_parser("push", help="put the current keys of this device into the key wallet")
    kp.add_argument("did", nargs="*", metavar="DID", help="the keys (default: the current keys of the owner)")
    kp.add_argument("--plain-current", action="store_true", help="keep them unencrypted in the wallet")
    kl = ksub.add_parser("pull", help="keep on this device the owner's current keys that the wallet holds")
    kls = ksub.add_parser("list", help="what the key wallet holds, as a table: owner, kind, key, version, locks (no secrets)")
    kw = ksub.add_parser("wallet", help="the key wallets in which the owner's keys are looked for; hint one "
                         "for the owner in osheaf.json (--add), or remove a hint (--remove)")
    kw.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    kws = ksub.add_parser("wallets", help="your key wallets, with the owners whose keys each holds and their "
                          "locks; add one to your configuration (--add), or remove one (--remove)")
    for x in (kw, kws):
        x.add_argument("--add", metavar="WALLET", help="github:OWNER/REPO" + ("" if x is kw else " or command"))
        x.add_argument("--remove", metavar="WALLET", help="a wallet named now")
    kf = ksub.add_parser("forget", help="remove keys from this device, and with --from-wallet from the wallet; "
                         "or passkey locks (--passkey, --rp)")
    kf.add_argument("did", nargs="*", metavar="DID", help="the keys to forget")
    kf.add_argument("--from-wallet", action="store_true", help="also remove them from the key wallet")
    kf.add_argument("--used", action="store_true",
                    help="with --from-wallet: remove the keys the latest version of the key log no longer needs")
    kf.add_argument("--passkey", metavar="CRED",
                    help="remove instead the passkey locks of this credential from the keys in the wallet")
    kf.add_argument("--rp", metavar="RP", help="remove instead the passkey locks of this relying party "
                    "(e.g. opensheaf.org) from the keys in the wallet")
    kf.add_argument("--force", action="store_true", help="also remove rotation keys still committed")
    kf.add_argument("--yes", action="store_true", help="do not ask to confirm the removal (scripts)")
    for x in (kp, kl, kls, kf):
        x.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
        wallet_option(x)
    ke = ksub.add_parser("export", help="copy a current key to the clipboard, for a password manager")
    ke.add_argument("did", nargs="?", metavar="DID", help="the key (default: the owner's one key on this device)")
    ke.add_argument("--owner", help="the owner (default: the archive's)")
    ke.add_argument("--clipboard", action="store_true", help="copy the key to the clipboard")
    ke.add_argument("--stdout", action="store_true", help="print the key (a secret) instead")
    ke.add_argument("--encrypt", action="store_true", help="encrypt it under the passphrase")
    ki = ksub.add_parser("import", help="keep on this device a key copied from a password manager")
    ki.add_argument("--clipboard", action="store_true", help="read the key from the clipboard")
    ki.add_argument("--stdin", action="store_true", help="read the key from the standard input")
    ki.add_argument("--owner", help="the owner, if the text does not say")
    ken = ksub.add_parser("enroll", help="let a passkey (Touch ID, in the browser) open the keys of the wallet")
    ken.add_argument("--new-passkey", action="store_true",
                     help="create another passkey, even if one opens some of the keys already")
    ku = ksub.add_parser("unlock", help="open the keys of the wallet with the passkey; pull the current keys")
    for x in (ken, ku):
        x.add_argument("--owner", help="the owner (default: the archive's)")
        wallet_option(x)
        x.add_argument("--no-browser", action="store_true", help="print the address of the page, do not open it")
    k.set_defaults(func=None)

Two helpers add the options shared by several of these commands: those of
making an owner, and those of signing a version of the key log with
rotation keys and committing new ones.

    # in the parser of osheaf:
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
        level_options(p)


    def level_options(p, new_keys=True):
        p.add_argument("--keys", metavar="LEVEL",
                       help="the security level: offline (default: the rotation keys to --export only), or a "
                       "key wallet, github:OWNER/REPO or command, which keeps the keys encrypted (a lower level)"
                       if new_keys else "the key wallet that keeps the rotation keys (default: the one configured)")
        if new_keys:
            p.add_argument("--plain-current", action="store_true",
                           help="in a wallet, keep the current keys unencrypted")


    def wallet_option(p):
        p.add_argument("--wallet", metavar="WALLET", help="the key wallet, github:OWNER/REPO or command "
                       "(default: the one configured)")


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
        level_options(p, new_keys=export)

Running a command
-----------------

### Required options and files of options

Five commands take a file of options with `--from`: `deposit`,
`relicense`, `relate`, `describe` and `init`. For them an option may be given on the
command line or in the file, so `argparse` cannot require it. The table
`REQUIRED` lists, for each, the options that must have a value once the
two are merged; its keys are also how `main` recognises these commands.

    # in the options a command needs, from the command line or a file:
    REQUIRED = {"deposit": ("id", "title", "author"), "relicense": ("id", "rights", "method"),
                "relate": ("id", "to"), "describe": ("id",),
                "init": ("name", "base_url", "curator")}

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
            if args.cmd in ("deposit", "relicense") and getattr(ns, "rights", None) is not None:
                try:
                    core.check_rights(ns.rights)
                except ValueError as e:
                    p.error(f"{args.cmd}: {e}")
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
- `arxiv fetch` only downloads into a folder, and needs no archive; nor
  does the help of `arxiv import`;
- `resolve` works in an archive, whose storage root and locations it then
  uses, or anywhere else;
- `key list`, `key import`, `key export`, `key enroll`, `key unlock`,
  `key wallet` (to show the wallets of an owner) and `key wallets` work in
  an archive or outside
  one, as `resolve` does: a wallet or a key may be needed on a machine that
  has no copy of the archive;
- every other command configures the archive. An archive of specification
  0.1 is told apart then, and every command but `verify` stops, saying that
  it must be rebuilt (section 16.1); `verify` reports it as its one error.
  Then come `owner` and `key`, dispatched by their action (`KEY_ACTIONS`
  names the functions of `key`), the commands of
  the modules imported lazily, and the function recorded by the
  sub-parser of the others.

After a command that may have changed the archive, the presentation files
are written again (`core.present`, in [chapter 16](16-index.md)), as the
website profile asks after every change (appendix A.3): a deposit appears
on the website at once, a takedown leaves it at once. Commands that only
read (`verify`, `resolve`, `owner show`, `collection status`, `key new`,
`arxiv fetch`, a trial of `zenodo` on the sandbox, which works on a copy)
and those that write the pages themselves (`index`, `init`) are left out. A
command that fails stops before, and changes nothing that the pages show.
The passphrase of the keys, asked at most once by a command, is forgotten
when it ends.

    # in the main function of osheaf:
    READ_ONLY = {"help-config", "verify", "resolve", "index", "init", "key"}
    READ_ONLY_ACTIONS = {("owner", "show"), ("collection", "status"), ("arxiv", "fetch")}


    def changes_archive(args):
        """Whether the command ARGS may have changed the archive."""
        if args.cmd in READ_ONLY or (args.cmd, getattr(args, "action", None)) in READ_ONLY_ACTIONS:
            return False
        return not (args.cmd == "zenodo" and not getattr(args, "production", False))


    def main(argv=None):
        argv = sys.argv[1:] if argv is None else argv
        p = build_parser()
        args = p.parse_args(argv)
        core.forget_passphrase()
        try:
            result = dispatch(p, args)
        except core.UnsafePath as e:
            sys.exit(f"{e}: nothing is read from it (repair the inventory, from a copy of the object)")
        finally:
            core.forget_passphrase()
        if changes_archive(args) and core.ROOT is not None:
            core.present()
        return result


    OWNER_ACTIONS = {"init": "owner_init_command", "rotate": "owner_rotate", "expose": "owner_expose",
                     "end": "owner_end", "show": "owner_show"}
    KEY_ACTIONS = {"new": "key_new", "push": "key_push", "pull": "key_pull", "list": "key_list",
                   "export": "key_export", "import": "key_import", "forget": "key_forget",
                   "enroll": "key_enroll", "unlock": "key_unlock", "wallet": "key_wallet",
                   "wallets": "key_wallets"}
    LAZY = {"collection": ("collections", None), "mirror": ("mirror", "main"), "branch": ("branch", "main"),
            "accept": ("branch", "accept"), "draft": ("drafts", None), "seal": ("drafts", "seal"),
            "takedown": ("takedown", "main")}


    def dispatch(p, args):
        """Run the command ARGS."""
        if args.cmd == "help-config":
            from . import wallet
            print(core.__doc__)
            print(wallet.CONFIG_HELP)
            return
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
        if args.cmd == "arxiv" and ({"-h", "--help"} & set(args.rest)):
            from . import arxiv
            return arxiv.main(args.rest)
        if args.cmd == "resolve":
            from . import remote
            try:
                configure(args)
            except SystemExit:
                if args.root:
                    raise
            return remote.main(args)
        if args.cmd == "key" and args.action in ("list", "import", "export", "enroll", "unlock", "wallet",
                                                    "wallets"):
            try:
                configure(args)
            except SystemExit:
                if args.root:
                    raise
            getattr(core, KEY_ACTIONS[args.action])(args)
            return
        configure(args)
        if args.cmd == "owner" and args.action == "pull":
            from . import mirror
            return mirror.owner_pull(args)
        if args.cmd == "owner":
            getattr(core, OWNER_ACTIONS[args.action])(args)
            return
        if args.cmd == "key":
            getattr(core, KEY_ACTIONS[args.action])(args)
            return
        if args.cmd == "arxiv":
            from . import arxiv
            return arxiv.main(args.rest)
        if args.cmd in LAZY:
            import importlib
            module, name = LAZY[args.cmd]
            m = importlib.import_module(f".{module}", __package__)
            if args.cmd == "draft":
                return m.delete(args) if args.action == "delete" else m.deposit(args, new=args.action == "new")
            return getattr(m, name or args.action)(args)
        args.func(args)

The commands of the modules imported lazily are in `LAZY`, with the
function that carries each out; `collection` calls the function named by
its action, and `draft` that of its action, a deposit for `new` and
`deposit`.

Configuring is where an archive of specification 0.1 is recognised, and
where a command that writes (one that changes the archive, or `index`)
stops when a page of objects could not be read, before it changes
anything (see [the archive](10-archive.md)).

    # in the main function of osheaf:
    def configure(args):
        core.configure(core.find_root(args.root))
        if core.OLD and args.cmd != "verify":
            sys.exit(core.REBUILD)
        if changes_archive(args) or args.cmd == "index":
            core.refuse_unread_pages()

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
- a path is made relative to the folder of the file.

The other values are converted when the entry is merged, as the command
line converts them (`after` becomes an integer, as `--after` has
`type=int`).

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
        actions = {a.dest: a for a in sub._actions}
        for k, v in entry.items():
            if getattr(ns, k) == sub.get_default(k):
                setattr(ns, k, value_of(actions[k], v, parser, command) if k in actions else v)
        return ns

A file of YAML holds text only (it is read with `BaseLoader`), and the
command line would have converted it: `no-passphrase: false` is the text
`false`, which Python takes for true, and `stage: BOGUS` would pass where
`--stage BOGUS` is refused. `value_of` converts each value as `argparse`
does for its option. A switch (`store_true`, `store_false`) takes `true`,
`yes`, `false` or `no` exactly (or a boolean of JSON); `true` gives the
option, `false` leaves it out, and any other value is an error. An option
with a type (`int`, the licence of `--rights`) gets its value through the
type, an option with choices one of them, and a repeated option a list,
each item converted. A list or a mapping where one value is expected is an
error, and a number of JSON where text is expected becomes its text.

    # in merging an entry with the command line:
    BOOLEAN = {"true": True, "yes": True, "false": False, "no": False}


    def value_of(action, v, parser, command):
        """The value V of a file of options for ACTION, converted as argparse converts it."""
        import argparse
        name = action.dest.replace("_", "-")

        def bad(why):
            parser.error(f"{command}: {name} in the file: {why}")

        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction,
                               argparse._StoreConstAction)):
            b = v if isinstance(v, bool) else BOOLEAN.get(v) if isinstance(v, str) else None
            if b is None:
                bad(f"true or false, not {v!r}")
            return action.const if b else action.default

        def one(x):
            if isinstance(x, (list, dict)) or isinstance(x, bool) and action.type is None:
                bad(f"a value, not {x!r}")
            if action.type is not None:
                try:
                    x = action.type(x if isinstance(x, int) and action.type is int else str(x))
                except (ValueError, TypeError, argparse.ArgumentTypeError) as e:
                    bad(f"not {x!r} ({e})")
            elif not isinstance(x, str):
                x = str(x)
            if action.choices is not None and x not in action.choices:
                bad(f"one of {', '.join(map(str, action.choices))}, not {x!r}")
            return x

        if isinstance(action, argparse._AppendAction) or action.nargs in ("*", "+"):
            return [one(x) for x in (v if isinstance(v, list) else [v])]
        return one(v)
