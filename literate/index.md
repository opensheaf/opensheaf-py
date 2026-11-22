opensheaf-py, a literate program
================================

> [!WARNING]
> **Draft.** OpenSheaf 0.2 is a draft specification: until version 1.0, a
> revision may change the format in incompatible ways, and these tools follow
> the latest draft.

This is the source of [opensheaf-py](https://github.com/opensheaf/opensheaf-py)
(the `osheaf` command), the reference tools of the
[OpenSheaf specification](https://opensheaf.org), written as a literate
program. It is meant to be read: the program is explained in the order in
which it is best understood, with the reasons for what it does and the
sections of the specification it implements. The Python files of the
package are *tangled* out of these documents and kept in the repository, so
that the package installs and runs like any other; the documents are also
*woven* into this website. One edits the documents, never the files. The
tangler and the weaver are a package of their own,
[opensheaf-literate](https://opensheaf.org/literate/) (the `literate`
command), written for OpenSheaf and itself a literate program: its chapters
explain the syntax of these documents and
[tangling](https://opensheaf.org/literate/10-tangle.html), and
[weaving](https://opensheaf.org/literate/20-weave.html). This project
pins a version of it in `requirements-literate.txt` and describes itself to
it in `literate.json`; `literate tangle --where FILE:LINE` tells which line
of which chapter a line of a tangled file comes from.

An OpenSheaf archive is a folder of plain files: an
[OCFL](https://ocfl.io) storage root in which every document is an object,
every version of the document is kept with its sources and its PDF, fixed
by SHA-512 digests, and described by [DataCite](https://datacite.org)
metadata; collections list documents, of the same archive or of others,
pinned by digests; a discovery document and a website make it all findable.
The chapters follow that order, after the identity that version 0.2 of the
specification gives works and owners: names, owners and their keys, key wallets,
signatures; then the archive and its documents; the work across archives
(resolution, collections, copies, branches) with drafts and takedowns; the
website, the services the tools talk to (arXiv and Zenodo), the command
line, and the tests.

Reading the code
----------------

Code is set in grey boxes. Above each box stands the name of its chunk,
with `≡` for the first fragment of a chunk and `+≡` for the ones that
continue it; a name in angle brackets inside the code, like
⟨locate and configure an archive⟩, is a reference to another chunk, and a link to
it. Below each box: where the chunk is used, and where it continues. The
[index of chunks](chunks.html) lists them all.

The OpenSheaf symbol on these pages, `literate/opensheaf-symbol.svg` (a
copy of `resources/brand/opensheaf-symbol.svg` of the specification's
repository), is not under the GPL of this program: it is licensed under
CC BY 4.0, and its use as a mark follows the OpenSheaf
[trademark policy](https://github.com/opensheaf/opensheaf.github.io/blob/main/TRADEMARKS.md).

Identity
--------

1. [Names: genesis records, digests and sheaf: URIs](05-names.md).
2. [Owners and their key logs](06-owners.md).
3. [Keys: making them, keeping them, exporting them](07-keys.md).
4. [Signatures and the statuses of versions](08-signatures.md).
5. [Key wallets: keys kept for convenience](09-wallets.md): security
   levels, a private GitHub repository, a password manager, passkey unlock.

The archive
-----------

6. [The archive: configuration and storage](10-archive.md): the settings,
   the OCFL storage root, inventories, object versions; the structure of
   the core module.
7. [Document versions, history and dates](11-versions.md): document
   versions as opposed to object versions, the history and the current
   version, notices carried forward, dates.
8. [TeXmacs: typesetting and reading markup](12-texmacs.md).
9. [Depositing a document](13-deposit.md).
10. [Description-only versions and completions](14-description.md):
   notices, withdrawals, relations, licences, corrections of the
   description; sources found later.
11. [The owner catalogues](15-owner-catalogues.md).
12. [The discovery document and the index](16-index.md).
13. [Verifying an archive](17-verify.md).
14. [Creating an archive](18-init.md).
15. [The commands of owners and their keys](19-owner-commands.md).

Across archives
---------------

16. [Resolution: other archives and sheaf: URIs](20-resolution.md).
17. [Collections across archives](21-collections.md).
18. [Copies: mirrors and key logs](22-mirrors.md).
19. [Branches and accepted copies](23-branches.md).
20. [Drafts and sealing](24-drafts.md).
21. [Takedowns and tombstones](25-takedown.md).

The website
-----------

22. [The website](30-website.md): the home page, the landing pages of
    the lines, with their `sheaf:` URIs, owners and signed versions, the
    pages of the owners and the sitemap, also written beside a TeXmacs
    index.
23. [The templates of the website](31-templates.md).

Services
--------

24. [Importing from arXiv: fetching](40-arxiv.md).
25. [Importing from arXiv: the metadata](41-arxiv-metadata.md).
26. [Importing from arXiv: the signed versions](42-arxiv-import.md).
27. [Zenodo: DOIs for document versions](50-zenodo.md), built and signed
    before the upload.

The command line and the tests
------------------------------

28. [The command line](60-command-line.md), with options read from YAML
    files.
29. [The tests](70-tests.md),
30. [the tests of names, owners, keys and signatures](71-tests-identity.md),
31. [the tests across archives](72-tests-across.md), and
32. [the tests of key wallets](73-tests-wallets.md).

The literate tools, tangling and weaving, are described in their own
literate program, [opensheaf-literate](https://opensheaf.org/literate/).

What writing it down found
--------------------------

Explaining a program to a reader is also reading it carefully. Writing
these chapters, with the code left exactly as it was, brought up a lag of
the tools behind the specification as amended on 13 November 2026
(collections of two kinds, selections, `mirrorOf`, the main collection
pinning heads), a mirror that `collection update` did not refresh, and a
resolution that did not try the mirrors of an archive's discovery
document. These have since been dealt with, in the chapters where they
occur; nothing found remains open.
