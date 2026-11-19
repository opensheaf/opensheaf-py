# opensheaf-py

[![tests](https://github.com/opensheaf/opensheaf-py/actions/workflows/tests.yml/badge.svg)](https://github.com/opensheaf/opensheaf-py/actions/workflows/tests.yml)
[![pages](https://github.com/opensheaf/opensheaf-py/actions/workflows/pages.yml/badge.svg)](https://github.com/opensheaf/opensheaf-py/actions/workflows/pages.yml)
[![archive examples](https://github.com/opensheaf/archive-template/actions/workflows/examples.yml/badge.svg)](https://github.com/opensheaf/archive-template/actions/workflows/examples.yml)
[![Python](https://img.shields.io/badge/python-3.9%E2%80%933.13-blue)](pyproject.toml)
[![licence: GPL v3+](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue)](LICENSE)

> [!WARNING]
> **Draft.** OpenSheaf 0.2 is a draft specification. Until version 1.0, any
> revision may change the format in incompatible ways. Archives and collections made now
> may have to be rebuilt or migrated, and the tools follow the latest draft.
> Do not rely on it yet for anything you cannot redo.

The unit tests run on Python 3.9 and 3.13; the testing grounds of the two
templates build archives and collections from the
[example papers](https://github.com/opensheaf/example-papers) and go through
every workflow, on every push and every week.

Python tools for [OpenSheaf](https://opensheaf.org) archives: archives of
scholarly documents kept as plain files (an OCFL 1.1 storage root with
DataCite metadata), checkable by anyone and combinable into collections. This
is the reference implementation of the
[specification](https://github.com/opensheaf/opensheaf.github.io), version 0.2 (draft).

On this branch the tools are being ported to version 0.2 (owners, key logs,
signatures, names from genesis records, the owner-name layout). Done: `init`
(with a new or an existing owner), `owner` and `key`, `deposit` (`--new`
seals a new work), the description-only versions, `collect`, the discovery
document with the indexes, `verify`; and the work across archives:
`resolve`, `collection`, `mirror`, `branch` and `accept`, `owner pull`,
`sign`, `draft` and `seal`, `takedown`. Not yet: the website, arXiv import
and Zenodo, which stop with a message saying so; the sections on them still
describe version 0.1.

The package is `opensheaf`; its command is `osheaf` (also installed as
`opensheaf`).

## Installation

```
pipx install "opensheaf[validate] @ git+https://github.com/opensheaf/opensheaf-py"
```

(or `pip install` in a virtual environment). Python 3.9 or later (PyYAML is installed with it). The extra
`validate` adds `jsonschema`, `rfc3986-validator` and `ocfl-py`, with which
`osheaf verify` also validates the JSON files against the schemas (with
their formats, URIs included) and the storage root with an independent OCFL
validator; without the first two, it says which schema checks it skipped.
Depositing TeXmacs documents needs [GNU TeXmacs](https://www.texmacs.org) (`TEXMACS_BIN`, by default the macOS
application).

## An archive

The quickest start is the template
[opensheaf/archive-template](https://github.com/opensheaf/archive-template):
a ready website, published with GitHub Pages. Or create one anywhere:

```
osheaf init my-papers --name "Papers of Jane Doe" --base-url https://example.org/papers/ \
  --curator "Doe, Jane" --new-owner --export /Volumes/USB/opensheaf-keys --print
```

An archive is a folder with a configuration file `osheaf.json` (its owner,
name, address, curator, depositor, the website or the TeXmacs profile;
`osheaf help-config` describes it). The tools find it from the current folder
or from `--root`. They maintain:

- `ocfl/`: the storage root (section 3.2), one OCFL object per line at
  `<owner>/<name>/`: the documents, the collections, the key logs of the
  owners (at `<owner>/<owner>/`), copies of lines written elsewhere with
  their owners' key logs, and drafts at `draft/<id>/`;
- `opensheaf.json`: the discovery document, with the labels of the lines,
  the drafts and the tombstones of objects taken down;
- `names/`, `owners/`, `sha512/`: the indexes (section 12.5);
- the website (appendix C): `index.html`, a landing page `paper/<id>/` per
  document (current version, every version in the order of the history,
  notices, files, DOI, the `citation_*` tags read by Google Scholar, JSON-LD,
  Signposting links) and `sitemap.xml`, from the templates in `templates/`
  (`{{name}}` placeholders; MathJax renders `$...$`);
- or, with the TeXmacs profile, `site/<id>/` (HTML versions of TeXmacs
  documents) and an index made from a TeXmacs template, with the same
  landing pages `paper/<id>/` and `sitemap.xml` as the website (from the
  archive's own `templates/paper.html`, if it has one).

## Commands

```
osheaf init FOLDER --name NAME --base-url URL --curator "Family, Given" --new-owner --export DIR
osheaf deposit ID SOURCE --pdf PAPER.pdf --title T --author "Family, Given|Affiliation" ...
osheaf deposit ID SOURCE.tm --title T --author ...           (TeXmacs: typeset by the archive)
osheaf deposit ID --pdf PAPER.pdf --no-source REASON ...
osheaf deposit ... --stage VoR --agreement "the journal's publication terms"
osheaf notice ID --about N --text "..." [--file erratum.pdf]
osheaf withdraw ID --reason "..."
osheaf complete ID --version N --source paper.tex [--extra-source ...]
osheaf relicense ID --rights cc-by-4.0 --method "..."
osheaf relate ID --to arxiv:ID|doi:DOI [--relation IsIdenticalTo]
osheaf describe ID [--title T] [--abstract TEXT | --abstract-file F] [--keyword K ...] [--author A ...]
osheaf collect
osheaf resolve URI [--at URL]... [--json]
osheaf collection new LABEL --type catalogue|selection --title T [--description D] [--order manual]
osheaf collection add LABEL URI... [--at URL]... [--follow] [--revision N]...
osheaf collection remove|follow LABEL URI... ; collection update [LABEL...] ; collection status LABEL
osheaf collection sync LABEL --from collection.yaml
osheaf mirror URI [--at URL]... [--label L] [--licence-checked] | --all
osheaf branch URI [--at URL]... --label L [--owner OWNER]
osheaf accept URI [--at URL]... --selection S [--label L] [--with-original]
osheaf owner pull URL|PATH [--owner OWNER]
osheaf sign LABEL --version vN
osheaf draft new|deposit ID [SOURCE] [the options of deposit] ; draft delete ID
osheaf seal ID --label L [--delete-draft]
osheaf takedown LABEL --reason TEXT [--by-law | --keeper]
osheaf index
osheaf verify [--remote]
osheaf zenodo ID [--production]
osheaf arxiv fetch DOWNLOADS --author AUTHOR-ID | ARXIV-ID ...
osheaf arxiv import DOWNLOADS [ARXIV-ID ...] [--update] [--versions v1,v3]
```

- **deposit** a document, or a new document version of it: any source (LaTeX,
  Markdown, ...) with its PDF (`--pdf`; other sources with `--extra-source`,
  the abstract with `--abstract` or `--abstract-file`), a PDF alone
  (`--no-source REASON`), or a TeXmacs source, typeset by the archive. Files
  are copied byte for byte. Dates follow the specification (`--available`, or
  `--created` for a version not public at the time; `--issued`), with
  `--stage` (NISO-JAV), `--changes`, and `--after N` for a version found
  later, which writes the history. A new version keeps the abstract, keywords
  and licence of the previous one unless they are given.
- **--from FILE.yaml** (deposit, relicense, relate, describe, init): the options from a
  YAML or JSON file, with the same names (`title`, `authors`, `abstract`,
  `extra-sources`, `available`, ...; paths relative to the file); a list
  makes several deposits in order, and the command line overrides the file.
  YAML is read with every value kept as text, so that nothing is converted
  silently (`2611.14296`, `2025-01-02` and `1.10` stay as written). The
  settings may also be `osheaf.yaml`. Example:

  ```yaml
  id: kpz-uniqueness
  source: paper.tex
  pdf: paper.pdf
  extra-sources: [refs.bib, {file: figures/fig1.pdf, path: figures/fig1.pdf}]
  title: Energy solutions of KPZ are unique
  authors:
    - Doe, Jane|Example University
    - {name: "Roe, Richard", affiliation: Another University}
  abstract: |
    We prove that energy solutions of the KPZ equation are unique.
  rights: cc-by-4.0
  available: 2015-08-31
  related: ["IsIdenticalTo:arxiv:1508.07764"]
  ```
- **notice**, **withdraw**: later statements about a version (an erratum, by
  a description-only version; notices stay in every later version) and the
  withdrawal of a document (the content stays; no new versions).
- **complete**: adds the sources of a version deposited without them
  (`--no-source`); its number stays.
- **resolve**: finds and checks what a `sheaf:` URI names (section 12.3):
  a line, a document version (`/v3`), an object version by its pin
  (`?sha512=`), a key log (`sheaf:<owner>`). Other archives are named by
  their base URLs, read through their discovery documents over HTTP, or
  from folders; the `at` of a URI is tried first, then `--at`, then the
  archive's own storage root. Every copy found is checked (its name
  against its genesis record, its versions against the owner's key log
  kept beside it, met with every other copy of it found), and the URI
  resolves to the latest signed version among the copies that agree; a
  fork of the line, or of the key log, is reported. Where a base URL is
  read can be configured apart, under `locations` in `osheaf.json` or in
  `OPENSHEAF_LOCATIONS` (`URL=FOLDER-OR-URL;...`), for a clone on disk.
- **collection**: catalogues and selections (section 8), lines of their
  curator owner, whose members are lines of any archive, each named by
  `name` and `owner`, located by `at` (base URLs) and pinned (`version`
  and `inventorySha512` in a catalogue, which may `follow` the line;
  `revisions` in a selection, the document versions vetted). `new` makes
  one, `add` resolves members given by URIs (or labels of this archive) and
  pins only verified versions, `remove` and `follow` change members,
  `update` follows the members that follow their lines to the latest
  signed version extending their pin (never a contested one, never after a
  fork of the owner's key log) and reports for a selection the versions not
  vetted, `status` gives each member's status (verified, contested,
  mismatch, unchecked, not a version, unavailable, removed; section 8.5),
  and `sync` writes a collection from a file:

  ```yaml
  title: Reading list
  type: catalogue            # or selection
  members:
    - {uri: "sheaf:<name>:<owner>?at=https%3A%2F%2Fexample.org%2Fpapers%2F", follow: yes}
    - {label: my-paper}
  ```

  `osheaf init --curated` makes an archive whose main catalogue is curated
  so; `osheaf verify --remote` resolves every member of other archives.
- **mirror** (a library, a preservation copy; section 11): copies a line
  written elsewhere, up to its latest signed version, byte for byte, each
  file checked, with the key log of its owner beside it; refused unless
  every version is under an open licence (CC BY, CC BY-SA, CC0, GPL), or
  `--licence-checked`. Run again (or `mirror --all`), it adds the owner's
  signed versions from copies that agree; never a contested version, never
  a version of an owner whose key log forks (the owner is frozen), and a
  copy that does not agree is a fork of the line, reported. Nothing marks a
  mirror: it is listed like any line.
- **branch** (section 9): a line of this archive's owner continuing a signed
  version of another owner's line: the parent version's files, its
  genesis record and the evidence of the branch point (`parent.inventory.json`,
  `parent.object.json`, `parent.signatures/`, and `parent.chain/` for a
  branch of a branch), with the parents' key logs kept beside it; named by
  the work's genesis name, or renamed by the next algorithm number after a
  clash. Branching a later version of the same parent moves the branch
  point. `verify` checks every branch point (consistent, confirmed,
  unchecked).
- **accept** (a journal; section 9.6): an accepted copy, a branch under the
  selection's owner, listed by the selection with the revision it holds
  (and with `--with-original`, the authors' revision set). Accepting a
  later version moves the branch point and adds the revision. A journal
  that typesets its own version of record deposits it as a later version
  of the accepted copy (`deposit` with `--stage VoR` and `--agreement`).
- **owner pull**: meets this archive's copy of an owner's key log with the
  copy at another archive (or the folder of the owner object): extends it,
  or, when the two differ at a version, keeps its own side and appends a
  fork record carrying the other side, which ends the owner (section 6.3).
- **sign**: signs again, with current keys not exposed, a version contested
  by a key the owner's key log exposes (section 7.1), while the owner is
  not ended.
- **draft**, **seal**: a draft is unsigned work in progress at
  `draft/<id>/`, deposited into with the options of `deposit` (`draft new`,
  `draft deposit`, `--replace` rewriting its head), listed apart in the
  discovery document, and deleted without a tombstone (`draft delete`);
  `seal` makes a new line from its head, document version 1, signed
  (section 10).
- **takedown**: deletes an object and its witnesses, with a tombstone in
  the discovery document (section 13.3); the key logs it needs stay, and a
  key log that lines of the archive need is taken down only by law or at
  its keeper's request (`--by-law`, `--keeper`). A line taken down returns
  from a copy holding the version its tombstone pins (`mirror`).
- **relicense**, **relate**: description-only versions (a new licence with the
  authors' agreement; a link to the same work elsewhere).
- **describe**: a description-only version correcting the title, the abstract
  (`--abstract` or `--abstract-file`), the keywords (`--keyword`, repeated,
  replacing the keywords; arXiv categories stay) or the authors (`--author`,
  repeated, as in a deposit, replacing the list); the other fields are kept,
  and a correction that changes nothing is refused.
- **collect**: a new version of the main catalogue when a document of the
  archive's owners has a new signed version; members are ordered
  `issued-desc`, pin the latest signed version of their line and follow it.
- **index**: the discovery document, the indexes `names/`, `owners/` and
  `sha512/` (also written by every command that changes an object), and
  the readable index (not yet for 0.2): the website, or
  the TeXmacs index (`index.tm`, exported to `index.html`) with the landing
  pages and the sitemap of the website. No `robots.txt` is written: an archive
  in a folder of a larger site adds `Sitemap: <baseUrl>sitemap.xml` to the
  site's own.
- **verify**: the checks of section 14 of the specification (the layout,
  inventories and digests, key logs, names and signatures, `object.json`
  and `datacite.json`, numbering of document versions, history and notices,
  branch points, collections and their pins, the discovery document,
  tombstones and indexes; with `--remote`, the members of collections held
  in other archives, resolved, with their statuses).
- **zenodo**: the Zenodo binding (appendix A): deposits the current document
  version (on the sandbox, on a copy of the object, unless `--production`).
  Tokens are read from `ZENODO_TOKEN` / `ZENODO_SANDBOX_TOKEN`, or from the
  system's credential store under `zenodo-token` / `zenodo-sandbox-token`
  (through keyring, `pip install 'opensheaf[zenodo]'`; on macOS also the
  keychain directly).
- **arxiv fetch / import**: download papers from arXiv (every version, with
  each version's licence and comments; one request every 3 seconds) and
  import them, one document version per arXiv version, with arXiv's files
  byte for byte. Object identifiers come from `identifiers.json` in the
  downloads folder, chosen by the depositor. The tools only append versions:
  a version that is not on arXiv is placed by importing up to the arXiv
  version before it, depositing it, and continuing with `--update`.

## A literate program

The source of these tools is a literate program: the Markdown documents in
[literate/](literate/index.md) explain the code in the order in which it is
best understood, and the Python files under `src/` and `tests/` are
*tangled* out of them (in the style of Kragen Sitaker's
[handaxeweb](https://github.com/kragen/peg-bootstrap/blob/master/handaxeweb.md)).
The tangled files are kept in the repository, so the package installs as
usual. Tangling and weaving are done by
[opensheaf-literate](https://github.com/opensheaf/literate) (the `literate`
command; its own literate program is at
[opensheaf.org/literate](https://opensheaf.org/literate/)), pinned in
`requirements-literate.txt` and configured by `literate.json`. To change
the code, edit the documents (never the tangled files: see
[AGENTS.md](AGENTS.md)) and run

```
pip install -r requirements-literate.txt   # once
literate tangle         # write the files out of literate/
literate tangle --check # nothing differs (what the continuous integration checks)
literate weave          # the website, in site/
```

The website is published at
[opensheaf.org/opensheaf-py](https://opensheaf.org/opensheaf-py/).
`literate tangle --where FILE:LINE` tells which line of which document a
line of a tangled file comes from.

## The first archive

[mgubi.org/papers](https://mgubi.org/papers/)
([repository](https://github.com/mgubi/papers)) is kept with these tools.

## Licence

GNU General Public License, version 3 or later. The JSON Schemas in
`src/opensheaf/schemas/` are those of the specification, dedicated to the
public domain under CC0 1.0. The OpenSheaf symbol, `literate/opensheaf-symbol.svg`
(used by the woven website), is licensed under CC BY 4.0, and its use as a mark follows
the OpenSheaf
[trademark policy](https://github.com/opensheaf/opensheaf.github.io/blob/main/TRADEMARKS.md).
