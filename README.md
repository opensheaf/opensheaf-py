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

The tools follow version 0.2: works are *lines* named by `sheaf:` URIs,
digests of genesis records; every version of a line is signed by its
*owner*, a keyed identity with a key log of current and rotation keys; the
storage root is in the owner-name layout (`<owner>/<name>/`). Archives of
version 0.1 are not read: `osheaf verify` says "specification 0.1: rebuild".

The package is `opensheaf`; its command is `osheaf` (also installed as
`opensheaf`).

## Installation

```
pipx install "opensheaf[validate,keys] @ git+https://github.com/opensheaf/opensheaf-py"
```

(or `pip install` in a virtual environment). Python 3.9 or later (PyYAML is installed with it). The extra
`validate` adds `jsonschema`, `rfc3986-validator` and `ocfl-py`, with which
`osheaf verify` also validates the JSON files against the schemas (with
their formats, URIs included) and the storage root with an independent OCFL
validator; without the first two, it says which schema checks it skipped.
The extra `keys` adds `keyring`, for the keys kept in the system keychain
(below).
Depositing TeXmacs documents needs [GNU TeXmacs](https://www.texmacs.org) (`TEXMACS_BIN`, by default the macOS
application).

### Running without installing

[uv](https://docs.astral.sh/uv/) runs `osheaf` without installing it. Name
the Python, so that uv uses the same interpreter of its own every time:

```
uvx --python 3.13 --from "opensheaf[validate,keys] @ git+https://github.com/opensheaf/opensheaf-py" osheaf ...
uvx --refresh --python 3.13 --from "opensheaf[validate,keys] @ git+https://github.com/opensheaf/opensheaf-py" osheaf ...   # to update
```

or, once, in your shell's configuration:

```
alias osheaf='uvx --python 3.13 --from "opensheaf[validate,keys] @ git+https://github.com/opensheaf/opensheaf-py" osheaf'
```

The extra `keys` installs keyring, which keeps the current keys in the
macOS keychain. The keychain lets the program that wrote a key read it
without asking, and asks for any other: "python3.13 wants to use your
confidential information stored in opensheaf-current-key". Answer **Always
Allow** (with your login password), and that Python is never asked again.
A Python that changes, as it does when uvx picks whichever one it finds,
is asked anew, which is why the line above names one. osheaf reads each key
at most once per command, so it asks at most once per command and key. If
you would rather not keep the current key on the computer at all, set
`OPENSHEAF_KEY_STORE=none` ([Keys and security levels](#keys-and-security-levels)).

## A walk through

An archive, from its creation to a DOI. The owner is made with the archive:
a current key for this device, kept in the system's credential store, and
three rotation keys (two of which sign a change of keys), exported once,
encrypted under a passphrase, to a folder outside the archive (here a USB
stick), with a printed sheet (section 6.2). Keep them apart from the
device.

```
osheaf init my-papers --name "Papers of Jane Doe" --base-url https://example.org/papers/ \
  --curator "Doe, Jane" --new-owner --export /Volumes/USB/opensheaf-keys --print
cd my-papers
```

A new work is sealed by `--new` with a label of your choice, which names its
line in this archive and its landing page, `paper/<label>/`; its permanent
name is its `sheaf:` URI, printed by the deposit. Each version is signed
with the current key, and records the digest of the version before.

```
osheaf deposit kpz-uniqueness paper.tex --pdf paper.pdf --new \
  --title "Energy solutions of KPZ are unique" --author "Doe, Jane|Example University" \
  --abstract-file abstract.txt --rights cc-by-4.0 --available 2015-08-31
osheaf deposit kpz-uniqueness paper.tex --pdf paper.pdf --changes "Typos corrected." \
  --title "Energy solutions of KPZ are unique" --author "Doe, Jane|Example University"
osheaf notice kpz-uniqueness --about 1 --text "Lemma 2 is wrong as stated; see version 2."
osheaf collect          # new versions of the owner catalogues, pinning the latest signed versions
osheaf index            # opensheaf.json, the indexes, the website
osheaf verify
```

The website (appendix A.3) is written again after every command that
changes the archive; `osheaf index` writes everything. Collections gather
lines of any archive, pinned, by their `sheaf:` URIs:

```
osheaf collection new reading --type selection --title "Reading list"
osheaf collection add reading "sheaf:<name>:<owner>/v2?at=https%3A%2F%2Fother.example%2F" --revision 2
osheaf collection update            # followed members of catalogues move to their latest signed version
```

Feature it on the home page with `"index": {"html": {"templates":
"templates", "featured": "reading"}}` in `osheaf.json`. Papers already on
arXiv are imported, one signed line per paper, labelled as
`identifiers.json` says:

```
osheaf arxiv fetch downloads --author doe_j_1
echo '{"1508.07764": "kpz-uniqueness"}' > downloads/identifiers.json
osheaf arxiv import downloads --agreement "deposited by an author"
```

A DOI for the current version comes from Zenodo (appendix A.1): first on the
sandbox, which works on a copy and leaves the archive unchanged, then for
real; the version recording the DOI is built and signed before the upload,
and added once Zenodo has published it.

```
osheaf zenodo kpz-uniqueness                 # the sandbox
osheaf zenodo kpz-uniqueness --production
```

When a device is lost, or a key may have leaked, the owner exposes it and
adds a new one, signed by two rotation keys; what the exposed key alone
signed is contested, and the owner signs it again (section 6.3):

```
osheaf key new                                         # on the new device: prints its did:key
osheaf owner expose did:key:OLD --add did:key:NEW \
  --rotation-key /Volumes/USB/opensheaf-keys/rotation-...-1.txt \
  --rotation-key /Volumes/USB/opensheaf-keys/rotation-...-2.txt --export /Volumes/USB/new-keys
osheaf sign kpz-uniqueness --version v3
```

In continuous integration (the archive template on GitHub), a dedicated
current key of the owner, added with `osheaf owner rotate --add`, is given
in the secret `OPENSHEAF_SIGNING_KEY` (the base64 seed), and the commands
sign with it.

## Keys and security levels

An owner has current keys, which sign its documents, and rotation keys,
which alone change the current keys (section 6.2 of the specification).
Where they are kept is the owner's *security level*, chosen with `--keys`
on `osheaf init --new-owner`, `owner init` and `owner rotate`:

- **`offline`, the default and the maximum.** The rotation keys are
  exported once, encrypted under a passphrase, to `--export DIR` (USB
  sticks, kept apart) and to printed sheets (`--print`), and never kept on
  a device; each device makes its own current key (`osheaf key new`),
  which a rotation adds.
- **`github:OWNER/REPO`, a key wallet in a private GitHub repository.** The
  rotation keys and the current keys are kept as files
  `<owner>/<k>.key.enc` of a private repository of their own (never the
  archive's: the tools refuse a public repository and the archive's own,
  and never create one), encrypted under the passphrase, and read and
  written through the GitHub CLI (`gh auth login` once). A new machine
  pulls the current key (`osheaf key pull`, or by itself when it first
  signs) and keeps it in its credential store. Rotations read the rotation
  keys from the wallet, with no USB stick.
- **`command`, a key wallet in your password manager** (1Password `op`,
  Bitwarden `bw`, `pass`): the same, through a `read` and a `write` command
  configured in your own configuration file (below; chapter 9 of the
  literate program has examples for the three).

A wallet trades security for convenience, and the tools say so each time
they put keys in one: whoever controls the wallet *and* knows the
passphrase controls the owner, and a current key in a wallet is on every
machine that pulls it. Keep the passphrase somewhere else than the wallet:
in the Passwords app of macOS, for instance, so that GitHub and Apple
would both have to fail. Move up at any time with one rotation: `osheaf
owner rotate --keys offline --export DIR` signs with the rotation keys of
the wallet and exports the new ones offline only, after which those in the
wallet are used up (`osheaf key forget --from-wallet --used` removes them).

```
gh repo create me/opensheaf-keys --private        # once, by hand: the tools never create it
osheaf init my-papers --name "Papers of Jane Doe" --base-url https://example.org/papers/ \
  --curator "Doe, Jane" --new-owner --keys github:me/opensheaf-keys
osheaf key list                                   # a table: owner, kind, key, version, locks; no secret
osheaf key pull                                   # on another machine
osheaf owner rotate --add did:key:NEW             # rotation keys read from the wallet
osheaf owner rotate --keys offline --export /Volumes/USB/opensheaf-keys --print   # move up
osheaf key forget --from-wallet --used
```

The `key` commands name the wallet with `--wallet github:OWNER/REPO` (or
`--wallet command`); otherwise it is configured. Wallets and owners are
many to many: a wallet may hold the keys of several owners (an
institution's), several people may share one owner's keys in one wallet
(each with a passkey of their own), and an owner's keys may be in several
wallets. Your configuration file `~/.config/opensheaf/config.json`
(`$XDG_CONFIG_HOME/opensheaf/config.json`) lists the wallets you read,
`{"wallets": ["github:me/opensheaf-keys", "github:institute/keys"]}`
(`osheaf key wallets --add|--remove`); the archive's `osheaf.json` hints,
for each owner, the wallets that hold its keys, `"keys": {"<owner>":
{"wallets": [...]}}` (written by `init`, `owner init|rotate --keys` and
`key push --wallet`, changed with `osheaf key wallet --owner O
--add|--remove`). The keys of an owner are looked for in your wallets
first, then in those `osheaf.json` hints for it, in order: the first that
holds keys of the owner is used. The environment variable
`OPENSHEAF_WALLET` (text, or JSON as below) wins over both. `osheaf key
wallet` lists the wallets of an owner in order; `osheaf key wallets` lists
yours with the owners each holds and how their keys are locked. In your
file, `"keys": {"wallet": ...}` is still read, after your `wallets`; in
`osheaf.json`, the earlier form `"keys": {"wallet": ...}`, one wallet for
the whole archive, is refused, with the entries to write instead. A
command wallet is configured only in your file or the environment, as in

```json
{"keys": {"wallet": "command",
          "read": "op read 'op://Private/opensheaf-{owner}-{k}/notesPlain'",
          "write": "op item create --vault Private --category 'Secure Note' --title 'opensheaf-{owner}-{k}' \"notesPlain=$(cat)\""}}
```

where `{owner}`, `{k}` and `{kind}` stand for the owner name, the key's 16
characters and `current` or `rotation`; `read` prints the key file, `write`
receives it on its standard input, and the optional `list` and `forget`
list and remove keys. These commands run on your machine, so `osheaf`
never takes them from an archive's `osheaf.json`, which anyone may have
written: an `osheaf.json` with a command wallet is refused. The passphrase is asked once per command, or taken from
`OPENSHEAF_PASSPHRASE`. A current key also goes to and from a password
manager through the clipboard: `osheaf key export --clipboard` (paste it
into a note of the Passwords app; `--encrypt` encrypts it under the
passphrase) and, on another machine, `osheaf key import --clipboard`.

Where a machine keeps its current keys is `OPENSHEAF_KEY_STORE`: by
default the system's credential store (the macOS keychain, through the
extra `keys`), else the keychain through the `security` command, else a
file of `~/.config/opensheaf/keys` readable only by you; `keyring`,
`security` or `file` uses that one alone. **`OPENSHEAF_KEY_STORE=none`**
keeps no current key on the computer: each command that signs opens the
key from the wallet, with your passkey (one Touch ID per command that
signs) or the passphrase, and forgets it when it ends; `osheaf key pull`
says that the keys are not kept on this computer, by choice. It suits
development with `uvx`, whose Python environments come and go: the
keychain never asks (see [Running without installing](#running-without-installing)).
It needs a wallet.

### Passkey unlock

Instead of typing the passphrase on every machine, let a **passkey** open
the keys of a wallet, with Touch ID:

```
osheaf key enroll        # once: asks the passphrase, then creates the passkey in the browser
osheaf key unlock        # on another Mac: Touch ID, and the current keys are pulled
```

`osheaf key enroll` asks the passphrase once, then opens the page
<https://unlock.opensheaf.org/> in the browser, which creates a passkey for
`unlock.opensheaf.org` ("OpenSheaf owner …") and derives a secret from it
(the WebAuthn PRF extension, in browsers with X25519 in WebCrypto: known
to work in Safari 17+, Chrome 133+ and Firefox 130+, with iCloud Keychain,
Google Password Manager, 1Password or a security key that supports PRF).
The page hands the secret to `osheaf` on your own computer, by going to
`http://127.0.0.1:<port>/callback`, a listener that answers once, to the
one page it opened. `osheaf` then opens the page a second time, to unlock
with the new passkey alone and check that it gives the same secret, and
only then gives every key of the owner in the wallet a second lock, under
that secret, besides the passphrase. From then on, whenever `osheaf` needs
a key of the wallet, it opens the page; a passkey in iCloud Keychain is on
all your Macs. Run `osheaf key enroll` again after a rotation that did not
unlock with the passkey, so that it opens the new keys too;
`osheaf key enroll --new-passkey` adds a passkey of another provider (the
page refuses to make a second one on a provider that has one already).

**Check the code.** Each time, `osheaf` prints "Check that the browser
shows the code 123 456", and the page shows a code too: the page does
nothing until you tick "The terminal shows the same code". A page that
shows another code was not opened by this `osheaf`: close it.

The passphrase stays the way back: `osheaf` asks for it when the page
reports an error, after two minutes without an answer, when you press
Ctrl-C at "Waiting for the browser…", when the browser's answer does not
open a key, and always with `OPENSHEAF_UNLOCK=passphrase` or
`OPENSHEAF_PASSPHRASE` set (scripts). `OPENSHEAF_PASSPHRASE_COMMAND` names
a command that prints it, run before it is asked, e.g. `security
find-generic-password -w -s opensheaf-passphrase` (the macOS keychain) or
`op read op://Private/opensheaf/password`. Writing new keys into the
wallet still needs the passphrase.

**Passkeys enrolled on `opensheaf.org`.** The first version of the page
was at `opensheaf.org/manager/unlock.html`, and made passkeys for
`opensheaf.org`. Their locks still open with the passphrase, but `osheaf`
no longer asks the browser for them, and says so. Move once:

```
osheaf key enroll --new-passkey          # a passkey for unlock.opensheaf.org
osheaf key forget --rp opensheaf.org     # then remove the old locks (the passphrase lock stays)
```

The second lists the keys that lose their `opensheaf.org` lock, asks you to
type `forget` to confirm, and ends with "Done: the 4 keys open with your
passkey (unlock.opensheaf.org) and your passphrase."

What you trust: the page at unlock.opensheaf.org (served by GitHub Pages
from [opensheaf/unlock](https://github.com/opensheaf/unlock), plain
JavaScript, an origin that serves nothing else), which sees the secret,
and the browser. The secret opens the wallet only together with the
wallet's files, which stay behind your GitHub sign-in; it is never
stored, by the page or by `osheaf`, and `osheaf` keeps it, for the rest of
the command, only once it has opened a key.

The secret never travels in clear, not even to `127.0.0.1`: `osheaf` puts
a one-time X25519 public key in the fragment of the page's address (after
`#`, which the browser sends to no server, and which the page takes out of
the address at once); the page makes its own one-time X25519 key pair, and
sends back its public key, the secret XOR an encryption key, and an
HMAC-SHA256 tag over the request (mode, owner, credential, both public
keys) and the ciphertext, both keys from HKDF-SHA256 of the shared X25519
secret (with the state of the request as the salt). Only `osheaf`, while
it waits, can open it, and anything changed on the way is refused. It is
not a form: Safari warns that a form sent from an `https` page to
`http://127.0.0.1` is "a non-secure form", and the address that the page
goes to instead stays in the browser's history; it holds only a ciphertext,
useless once `osheaf` has ended and forgotten its key.

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
  the owners hosted with their owner catalogues (`owners`), the drafts and
  the tombstones of objects taken down;
- `names/`, `owners/`, `sha512/`: the indexes (section 12.5);
- the website (the profile `website`, appendix A.3): `index.html`,
  presenting the latest signed version of each owner catalogue, in the order
  of `owners`, with the pin of every member (and a featured collection
  first, if one is set); a landing page `paper/<label>/` per line held
  (`paper/<name>/` without a label, with `-<owner>` added when several lines
  share the name; its full `sheaf:` URI in canonical form and a short form,
  its owner and keeper, marked confirmed when the keeper's ORCID record or
  domain links the owner, the current version, every signed document version
  in the order of the history with its status, contested ones marked,
  notices, files, pins, DOI, the withdrawal if any, the `citation_*` tags
  read by Google Scholar, JSON-LD, Signposting links); a page
  `owner/<owner>/` per owner, summarising its key log (current keys,
  rotations, exposed keys, an end, a successor, the keeper); and
  `sitemap.xml`; from the templates in `templates/` (`{{name}}`
  placeholders; MathJax renders `$...$`), copied there by `init`;
- or, with a TeXmacs index (`osheaf init --index texmacs [--index-template
  FILE]`), `site/<label>/` (HTML versions of TeXmacs
  documents) and an index made from a TeXmacs template, with the same
  landing pages, owner pages and `sitemap.xml` as the website (from the
  archive's own `templates/paper.html`, if it has one).

`init` also writes a `.gitattributes`, unless the folder has one, which
keeps the archive files byte for byte in git (never converted or merged as
text; OpenSheaf archives in git, section 4.1), as the archive template's
does.

## Commands

```
osheaf init FOLDER --name NAME --base-url URL --curator "Family, Given" --new-owner --export DIR
osheaf init FOLDER ... --owner OWNER --key-log DIR             (an existing owner)
osheaf init FOLDER ... --index texmacs --index-template FILE   (a TeXmacs index, profile texmacs)
osheaf owner init|rotate|expose|end|show ; owner pull URL|PATH ; key new
osheaf owner init|rotate|expose|end ... --keys offline|github:OWNER/REPO|command [--plain-current]
osheaf key push|pull|list|enroll|unlock [--wallet WALLET] ; key forget [--from-wallet [--used]] DID...
osheaf key enroll [--new-passkey] ; key unlock ; key forget --rp opensheaf.org | --passkey CRED
osheaf key export --clipboard|--stdout [DID] [--encrypt] ; key import --clipboard|--stdin
osheaf key wallet [--owner OWNER] [--add|--remove github:OWNER/REPO]   (the hints of osheaf.json)
osheaf key wallets [--add|--remove WALLET]                    (your wallets, the owners each holds)
osheaf label LINE LABEL | label --owner OWNER LABEL ; label LINE --unset   (old addresses redirect)
osheaf deposit LABEL SOURCE --pdf PAPER.pdf --title T --author "Family, Given|Affiliation" --new ...
osheaf deposit LABEL SOURCE --pdf PAPER.pdf ...               (a new version of the line LABEL)
osheaf deposit LABEL SOURCE.tm --title T --author ...         (TeXmacs: typeset by the archive)
osheaf deposit LABEL --pdf PAPER.pdf --no-source REASON ...
osheaf deposit ... --stage VoR --agreement "the journal's publication terms"
osheaf notice LABEL --about N --text "..." [--file erratum.pdf]
osheaf withdraw LABEL --reason "..."
osheaf complete LABEL --version N --source paper.tex [--extra-source ...]
osheaf relicense LABEL --rights cc-by-4.0|"a statement" --method "..."
osheaf relate LABEL --to arxiv:ID|doi:DOI [--relation IsIdenticalTo]
osheaf describe LABEL [--title T] [--abstract TEXT | --abstract-file F] [--keyword K ...] [--author A ...]
osheaf collect
osheaf resolve URI [--at URL]... [--json]
osheaf collection new LABEL --type catalogue|selection --title T [--description D] [--order manual]
osheaf collection add LABEL URI... [--at URL]... [--follow] [--revision N]...
osheaf collection remove|follow LABEL URI... ; collection update [LABEL...] ; collection status LABEL
osheaf collection sync LABEL --from collection.yaml
osheaf mirror URI [--at URL]... [--label LABEL] [--licence-checked] | --all
osheaf branch URI [--at URL]... --label LABEL [--owner OWNER]
osheaf accept URI [--at URL]... --selection LABEL [--label LABEL] [--with-original]
osheaf owner pull URL|PATH [--owner OWNER]
osheaf sign LABEL --version vN
osheaf draft new|deposit DRAFT [SOURCE] [the options of deposit] ; draft delete DRAFT
osheaf seal DRAFT --label LABEL [--delete-draft]
osheaf takedown LABEL --reason TEXT [--by-law | --keeper]
osheaf index [--no-html]
osheaf verify [--remote]
osheaf help-config                                            (osheaf.json, ~/.config/opensheaf/config.json)
osheaf zenodo LABEL [--production]
osheaf arxiv fetch DOWNLOADS --author AUTHOR-ID | ARXIV-ID ...
osheaf arxiv import DOWNLOADS [ARXIV-ID ...] [--update] [--versions v1,v3] [--agreement METHOD]
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
  new: yes
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
- **--rights** (deposit, relicense): a licence known by its SPDX key
  (`cc-by-4.0`, `cc-by-sa-4.0`, `cc0-1.0`, `gpl-3.0-only`,
  `gpl-3.0-or-later`), or a statement in plain text, such as the address of
  another licence; a lower-case word that is not a known key is refused as
  a likely typo.
- **notice**, **withdraw**: later statements about a version (an erratum, by
  a description-only version; notices stay in every later version) and the
  withdrawal of a line (the content stays; every page showing it shows the
  withdrawal; a later deposit of a new document version reinstates the
  line, and the versions withdrawn stay withdrawn, section 13.1).
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

  `osheaf init --curated` makes an archive whose owner catalogue is curated
  so; `osheaf verify --remote` resolves every member of other archives.
- **mirror** (a library, a preservation copy; section 11): copies a line
  written elsewhere, up to its latest signed version, byte for byte, each
  file checked, with the key log of its owner beside it; a version whose
  licence is not one known to be open (CC BY, CC BY-SA, CC0, GPL) is
  copied with a warning that the archive answers for the copy (section
  11.2), which `--licence-checked` silences. Run again (or `mirror --all`), it adds the owner's
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
- **collect**: a new version of the owner catalogue of each owner the
  archive hosts (or of `--owner`) when a document of that owner, a branch
  included, has a new signed version; each owner has its own catalogue,
  sealed when it is set up (`osheaf init`, `osheaf owner init`), and signs
  only it; members are ordered
  `issued-desc`, pin the latest signed version of their line and follow it.
- **index**: the discovery document, the indexes `names/`, `owners/` and
  `sha512/` (also written by every command that changes an object), and
  the readable index: the website, or the TeXmacs index (`index.tm`,
  exported to `index.html`) with the landing pages, owner pages and sitemap
  of the website. The website is also written again after every command that
  changes the archive (with a TeXmacs index, all but `index.tm`). No
  `robots.txt` is written: an archive in a folder of a larger site adds
  `Sitemap: <baseUrl>sitemap.xml` to the site's own.
- **verify**: the checks of section 14 of the specification (the layout,
  inventories and digests, key logs, names and signatures, `object.json`
  and `datacite.json`, numbering of document versions, history and notices,
  branch points, collections and their pins, the discovery document,
  tombstones and indexes, and, under the profile website, that the home page
  shows the pin of every member of the owner catalogues and each landing page
  the `sheaf:` URI of its line; with `--remote`, the members of collections
  held in other archives, resolved, with their statuses, and the link of
  each owner to its keeper, confirmed or claimed only, read from the
  keeper's ORCID record or `https://<domain>/.well-known/opensheaf`).
- **zenodo**: the Zenodo binding (appendix A.1): deposits the current
  document version of a line, signed (on the sandbox, on a copy of the line
  and of its owner's key log, unless `--production`). The version recording
  the DOI (in `datacite.json`, and in `external` of `object.json`) is built
  and signed in `zenodo-staging/<owner>/<name>/` before the upload, the
  uploads are compared with the MD5 of its inventory, and it is added once
  Zenodo has published; an interrupted deposit locks the line until the
  next run adds the version, signing it again if a key that signed it was
  exposed meanwhile. Branches are not deposited yet. Tokens are read from
  `ZENODO_TOKEN` / `ZENODO_SANDBOX_TOKEN`, or from the system's credential
  store under `zenodo-token` / `zenodo-sandbox-token` (through keyring,
  `pip install 'opensheaf[zenodo]'`; on macOS also the keychain directly).
- **arxiv fetch / import**: download papers from arXiv (every version, with
  each version's licence and comments; one request every 3 seconds) and
  import them: one line of the archive's owner per paper, sealed at its
  first import, one signed object version per arXiv version, with arXiv's
  files byte for byte. Labels come from `identifiers.json` in the downloads
  folder (arXiv identifier to label), chosen by the depositor; a paper is
  found in the archive by its label or by an arXiv relation or record.
  `--agreement` and `--agreed-by` record on what grounds it is deposited.
  The tools only append versions: a version that is not on arXiv is placed
  by importing up to the arXiv version before it, depositing it, and
  continuing with `--update`.

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
