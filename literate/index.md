opensheaf-py, a literate program
================================

> [!WARNING]
> **Draft.** OpenSheaf 0.1 is a draft specification: until version 1.0, a
> revision may change the format in incompatible ways, and these tools follow
> the latest draft.

This is the source of [opensheaf-py](https://github.com/opensheaf/opensheaf-py)
(the `osheaf` command), the reference tools of the
[OpenSheaf specification](https://opensheaf.org), written as a literate
program. It is meant to be read: the program is explained in the order in
which it is best understood, with the reasons for what it does and the
sections of the specification it implements. The Python files of the
package are *tangled* out of these documents (see [tangling](90-tangle.md))
and kept in the repository, so that the package installs and runs like any
other; the documents are also *woven* into this website (see
[weaving](91-weave.md)). One edits the documents, never the files.

An OpenSheaf archive is a folder of plain files: an
[OCFL](https://ocfl.io) storage root in which every document is an object,
every version of the document is kept with its sources and its PDF, fixed
by SHA-512 digests, and described by [DataCite](https://datacite.org)
metadata; collections list documents, of the same archive or of others,
pinned by digests; a discovery document and a website make it all findable.
The chapters follow that order: first the archive and its documents, then
collections and copies across archives, the website, the services the tools
talk to (arXiv and Zenodo), the command line, and the tests.

Reading the code
----------------

Code is set in grey boxes. Above each box stands the name of its chunk,
with `≡` for the first fragment of a chunk and `+≡` for the ones that
continue it; a name in angle brackets inside the code, like
⟨the syntax as patterns⟩, is a reference to another chunk, and a link to
it. Below each box: where the chunk is used, and where it continues. The
[index of chunks](chunks.html) lists them all.

The archive
-----------

1. [The archive: configuration and storage](10-archive.md): the settings,
   the OCFL storage root, inventories, object versions; the structure of
   the core module.
2. [Document versions, history and dates](11-versions.md): document
   versions as opposed to object versions, the history and the current
   version, notices carried forward, dates.
3. [TeXmacs: typesetting and reading markup](12-texmacs.md).
4. [Depositing a document](13-deposit.md).
5. [Description-only versions and completions](14-description.md):
   notices, withdrawals, relations, licences, corrections of the
   description; sources found later.
6. [The main collection](15-main-collection.md).
7. [The discovery document and the index](16-index.md).
8. [Verifying an archive](17-verify.md).
9. [Creating an archive](18-init.md).

Across archives
---------------

10. [Collections across archives](20-collections.md).
11. [Mirrors](21-mirrors.md).
12. [Accepted copies](22-accepted-copies.md).

The website
-----------

13. [The website](30-website.md): the home page, and the landing pages
    and sitemap, also written beside a TeXmacs index.
14. [The templates of the website](31-templates.md).

Services
--------

15. [Importing from arXiv: fetching](40-arxiv.md).
16. [Importing from arXiv: the metadata](41-arxiv-metadata.md).
17. [Importing from arXiv: the object versions](42-arxiv-import.md).
18. [Zenodo: DOIs for document versions](50-zenodo.md).

The command line and the tests
------------------------------

19. [The command line](60-command-line.md), with options read from YAML
    files.
20. [The tests](70-tests.md).

The literate tools
------------------

21. [Tangling: from the documents to the program](90-tangle.md).
22. [Weaving: from the documents to the website](91-weave.md).

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
