# Generated from literate/60-command-line.md by opensheaf-literate: edit the document, not this file.
"""osheaf: keep an OpenSheaf archive (specification 0.2, https://opensheaf.org).

The archive is the folder given with --root, or else the nearest folder above
the current one that has an osheaf.json (see `osheaf help-config`). Lines are
named by their labels in the archive.

Commands:
  init                   create an archive (osheaf.json, storage root, owner, main catalogue)
  owner init|rotate|expose|end|show   make an owner, change its keys, end it, show it
  key new                a new current key for this device
  key push|pull|list|forget   current keys to and from a key wallet (--keys)
  key export|import --clipboard   a key to and from a password manager
  deposit LABEL [SOURCE] deposit a document (TeXmacs, or any source with --pdf);
                         --new seals a new work under a new label
  relicense LABEL        description-only version with a new licence
  relate LABEL           description-only version linking the same work elsewhere
  describe LABEL         description-only version correcting title, abstract, keywords, authors
  notice LABEL           a notice about a document version
  withdraw LABEL         withdraw a document (the content stays)
  complete LABEL         add the sources of a version deposited without them
  collect                new version of the main catalogue when needed
  collection new|add|remove|follow|update|status|sync
                         catalogues and selections, with members of any archive
  resolve URI            find and check what a sheaf: URI names, in any archive
  mirror URI | --all     copy a line written elsewhere, with its owner's key log
  branch URI --label L   a branch of a signed version of another line, or move its branch point
  accept URI --selection S   an accepted copy (a branch) listed by a selection
  owner pull URL|PATH    meet another copy of a key log: extend it, or record a fork
  sign LABEL --version vN    sign again a version contested by an exposed key
  draft new|deposit|delete ID   unsigned work in progress, at draft/<id>/
  seal ID --label L      seal the work of a draft as a new line
  takedown LABEL --reason TEXT   delete an object, leaving a tombstone
  index                  write opensheaf.json, the indexes and the website (or the TeXmacs index)
  verify                 check the archive (section 14 of the specification)
  zenodo LABEL           a DOI for the current version (sandbox, or --production)
  arxiv fetch            download papers from arXiv (no archive needed)
  arxiv import DOWNLOADS import the downloads, one signed line per paper
  help-config            describe osheaf.json

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


def build_parser():
    p = argparse.ArgumentParser(prog="osheaf", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"opensheaf {__version__}")
    p.add_argument("--root", help="the archive folder (default: found from the current folder)")
    sub = p.add_subparsers(dest="cmd", required=True)

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
    rv = sub.add_parser("resolve", help="find and check what a sheaf: URI names (section 12.3)")
    rv.add_argument("uri", help="a sheaf: URI, possibly a short form")
    rv.add_argument("--at", action="append", metavar="URL", help="a place to look: a base URL or a folder")
    rv.add_argument("--json", action="store_true", help="print the result as JSON")
    rv.set_defaults(func=None)
    co = sub.add_parser("collection", help="catalogues and selections, with members of any archive")
    cosub = co.add_subparsers(dest="action", required=True)
    cn = cosub.add_parser("new", help="a new, empty collection")
    cn.add_argument("label")
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
    mi = sub.add_parser("mirror", help="copy a line written elsewhere, with its owner's key log (section 11)")
    mi.add_argument("uri", nargs="?", help="the sheaf: URI of the line")
    mi.add_argument("--at", action="append", metavar="URL", help="where copies are found (repeatable)")
    mi.add_argument("--label", help="a label for the line here")
    mi.add_argument("--all", action="store_true", help="bring every mirror up to date")
    mi.add_argument("--licence-checked", action="store_true",
                    help="redistribution is allowed although a licence is not an open one")
    mi.set_defaults(func=None)
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
    dr = sub.add_parser("draft", help="unsigned work in progress at draft/<id>/ (section 10.1)")
    drsub = dr.add_subparsers(dest="action", required=True)
    for name, helptext in (("new", "make a draft with a first deposit"),
                           ("deposit", "deposit a new version into a draft")):
        x = drsub.add_parser(name, help=helptext)
        deposit_options(x)
        if name == "deposit":
            x.add_argument("--replace", action="store_true", help="rewrite the head of the draft")
    x = drsub.add_parser("delete", help="delete a draft (no tombstone)")
    x.add_argument("id", metavar="ID")
    dr.set_defaults(func=None)
    se = sub.add_parser("seal", help="seal the work of a draft as a new line (section 10.2)")
    se.add_argument("id", metavar="DRAFT")
    se.add_argument("--label", required=True, help="the label of the new line")
    se.add_argument("--owner", help="the owner of the new line, an owner the archive hosts")
    se.add_argument("--delete-draft", action="store_true", help="delete the draft once sealed")
    se.add_argument("--message")
    se.set_defaults(func=None)
    td = sub.add_parser("takedown", help="delete an object, leaving a tombstone (section 13.2)")
    td.add_argument("id", metavar="LABEL", help="the label or identifier of the object")
    td.add_argument("--reason", required=True, help="a plain text, not repeating what is taken down")
    who = td.add_mutually_exclusive_group()
    who.add_argument("--by-law", action="store_true", help="a key log taken down by law")
    who.add_argument("--keeper", action="store_true", help="a key log taken down at its keeper's request")
    td.add_argument("--yes", action="store_true", help="do not ask to confirm")
    td.set_defaults(func=None)
    sub.add_parser("collect", help="new version of the main collection when needed").set_defaults(func=core.collect)
    i = sub.add_parser("index", help="write opensheaf.json, the indexes and the readable index")
    i.add_argument("--no-html", action="store_true")
    i.set_defaults(func=core.index)
    v = sub.add_parser("verify", help="check the archive")
    v.add_argument("--remote", action="store_true",
                   help="also resolve the members of collections held in other archives (section 14.5)")
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
                   help="the main catalogue is curated (osheaf collection add|sync)")
    n.add_argument("--index", choices=["website", "texmacs"],
                   help="the home page: the website (default, profile website) or a TeXmacs index "
                        "(profile texmacs)")
    n.add_argument("--index-template", metavar="FILE",
                   help="with --index texmacs: the template of the index, copied into the archive "
                        "(default: a minimal one)")
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
    op = osub.add_parser("pull", help="meet another copy of the key log: extend it, or record a fork")
    op.add_argument("source", metavar="URL|PATH", help="an archive, or the folder of the owner object")
    op.add_argument("--owner", help="the owner (default: the archive's)")
    ow.set_defaults(func=None)
    sg = sub.add_parser("sign", help="sign again a version contested by an exposed key (section 7.1)")
    sg.add_argument("id", metavar="LABEL")
    sg.add_argument("--version", required=True, help="the object version, e.g. v2")
    sg.add_argument("--yes", action="store_true", help="do not ask to confirm that the owner made it")
    sg.set_defaults(func=core.sign_again)
    k = sub.add_parser("key", help="current keys of this device, key wallets, password managers")
    ksub = k.add_subparsers(dest="action", required=True)
    kn = ksub.add_parser("new", help="a new current key for this device; prints its did:key")
    kn.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
    kp = ksub.add_parser("push", help="put the current keys of this device into the key wallet")
    kp.add_argument("did", nargs="*", metavar="DID", help="the keys (default: the current keys of the owner)")
    kp.add_argument("--plain-current", action="store_true", help="keep them unencrypted in the wallet")
    kl = ksub.add_parser("pull", help="keep on this device the owner's current keys that the wallet holds")
    kls = ksub.add_parser("list", help="what the key wallet holds: owner, key, kind, did:key (no secrets)")
    kf = ksub.add_parser("forget", help="remove keys from this device, and with --wallet from the wallet")
    kf.add_argument("did", nargs="*", metavar="DID", help="the keys to forget")
    kf.add_argument("--wallet", action="store_true", help="also remove them from the key wallet")
    kf.add_argument("--used", action="store_true",
                    help="with --wallet: remove the keys the latest version of the key log no longer needs")
    kf.add_argument("--force", action="store_true", help="also remove rotation keys still committed")
    kf.add_argument("--yes", action="store_true", help="do not ask to confirm the removal (scripts)")
    for x in (kp, kl, kls, kf):
        x.add_argument("--owner", help="an owner the archive hosts (default: the archive's)")
        x.add_argument("--keys", metavar="WALLET", help="the key wallet, github:OWNER/REPO or command "
                       "(default: the one configured)")
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
    k.set_defaults(func=None)
    sub.add_parser("help-config", help="describe osheaf.json").set_defaults(func=None)
    return p


def deposit_options(d):
    """The options of a deposit, shared by osheaf deposit and osheaf draft."""
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
    d.add_argument("--i-know", dest="i_know", action="store_true",
                   help="extend versions that are not signed, or are contested, having looked at them (section 7.3)")


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
    finally:
        core.forget_passphrase()
    if changes_archive(args) and core.ROOT is not None:
        core.present()
    return result


OWNER_ACTIONS = {"init": "owner_init_command", "rotate": "owner_rotate", "expose": "owner_expose",
                 "end": "owner_end", "show": "owner_show"}
KEY_ACTIONS = {"new": "key_new", "push": "key_push", "pull": "key_pull", "list": "key_list",
               "export": "key_export", "import": "key_import", "forget": "key_forget"}
LAZY = {"collection": ("collections", None), "mirror": ("mirror", "main"), "branch": ("branch", "main"),
        "accept": ("branch", "accept"), "draft": ("drafts", None), "seal": ("drafts", "seal"),
        "takedown": ("takedown", "main")}


def dispatch(p, args):
    """Run the command ARGS."""
    if args.cmd == "help-config":
        print(core.__doc__)
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
    if args.cmd == "resolve":
        from . import remote
        try:
            configure(args)
        except SystemExit:
            if args.root:
                raise
        return remote.main(args)
    if args.cmd == "key" and args.action in ("list", "import", "export"):
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


def configure(args):
    core.configure(core.find_root(args.root))
    if core.OLD and args.cmd != "verify":
        sys.exit(core.REBUILD)


if __name__ == "__main__":
    main()
