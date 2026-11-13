opensheaf-py, a literate program
================================

> [!WARNING]
> **Draft, and an experiment.** OpenSheaf 0.1 is a draft specification, and
> this literate form of its tools is an experiment on the branch `literate`.

This is the source of [opensheaf-py](https://github.com/opensheaf/opensheaf-py),
the reference tools of the [OpenSheaf specification](https://opensheaf.org),
written as a literate program: the program is explained in the order in
which it is best understood, and the Python files of the package are
*tangled* out of these documents (see [tangling](90-tangle.md)), which are
also *woven* into this website (see [weaving](91-weave.md)).

The documents:

1. [The core](10-core.md): the storage root, objects and their versions,
   deposits, description-only versions, the main collection, verification.
2. [Collections](20-collections.md): collections across archives, mirrors,
   accepted copies.
3. [The website](30-website.md).
4. [arXiv](40-arxiv.md): fetching and importing papers.
5. [Zenodo](50-zenodo.md): DOIs.
6. [The command line](60-command-line.md), with YAML inputs.
7. [The tests](70-tests.md).
8. [Tangling](90-tangle.md) and [weaving](91-weave.md).
