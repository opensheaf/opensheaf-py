The archive: configuration and storage
======================================

This chapter and the nine that follow it (up to the
[commands of owners](19-owner-commands.md)) are the module `core.py`, the
heart of opensheaf-py. It knows what an OpenSheaf archive is on disk: a
folder with a configuration file, an OCFL storage root holding the objects,
a discovery document and the pages generated for readers. Everything else in
the package (the [resolution](20-resolution.md) of other archives and the
[collections](21-collections.md) across them, the
[website](30-website.md), the imports from [arXiv](40-arxiv.md), the DOIs of
[Zenodo](50-zenodo.md), the [command line](60-command-line.md)) is built on
the functions defined here.

This chapter covers the bottom layer: how the tools find and read the
archive's configuration, where the objects of the storage root are (the
storage layouts of section 3.2), how they read and write OCFL objects, and
how every new object version is signed by the owner of its line, with the
keys and key logs of the chapters on [owners](06-owners.md),
[keys](07-keys.md) and [signatures](08-signatures.md). The
[next chapter](11-versions.md) adds what OpenSheaf puts on top of OCFL:
document versions, their history and their dates.

The package
-----------

The package itself says little: its version, and the version of the
specification it implements. Both are read by the command line and by the
build. The package keeps its own version, 0.1.0, while the specification it
follows is the draft of version 0.2.

    # in src/opensheaf/__init__.py:
    """opensheaf: tools for OpenSheaf archives (https://opensheaf.org).

    The command is `osheaf` (also installed as `opensheaf`); see `osheaf --help`.
    """

    __version__ = "0.1.0"
    SPECIFICATION = "0.2"

`python -m opensheaf` runs the same command line as `osheaf`.

    # in src/opensheaf/__main__.py:
    from .cli import main

    main()

The module core.py
------------------

`core.py` is a module of plain functions over the files of one archive. The
archive is chosen once per run, by `configure()`, which sets a few module
globals (the folder, the storage root, the settings); every other function
reads them. This keeps the signatures short, at the price of one archive
per process, which is all the command line needs.

The module starts with its docstring, its imports and its constants, and
then follows the life of an archive: finding and configuring it, storing
objects and signing their versions, running TeXmacs, depositing documents,
adding description-only versions, maintaining the main catalogue, writing
the discovery document and the index, verifying, creating a new archive,
and the commands that keep an owner's key log. Each part is a chunk
explained in its own chapter.

    # in src/opensheaf/core.py:
    <<the docstring of core.py: what an archive folder holds>>

    <<the modules core.py imports>>

    <<the names of the configuration file and of the folders the tools use>>

    <<the settings of the archive, set when it is configured>>

    <<the constants of the specification and of the profiles>>


    <<locate and configure an archive>>


    <<the storage root, its objects and their versions>>


    <<sign object versions and read the statuses of lines>>


    <<run TeXmacs and read its markup>>


    <<describe a document from the deposit arguments>>


    <<deposit a document version>>


    <<the documents of the archive with their current versions>>


    <<the licences known by their SPDX identifiers>>


    <<description-only versions and the commands that make them>>


    <<maintain the main collection of the archive>>


    <<write the discovery document of the archive>>


    <<write the TeXmacs index of the archive>>


    <<verify an archive>>


    <<create an archive>>


    <<the commands of owners and their keys>>

### What an archive folder holds

The docstring of the module is also the help of the configuration: the
command `osheaf help-config` prints it. It describes `osheaf.json`, the
only file of an archive that a person writes by hand, and the files the
tools generate next to it.

The configuration is not part of the archive as the specification defines
it (section 3): readers never see it. It holds what the tools need and the
specification leaves to the archive: the owner on whose behalf the archive
signs its own collections, who deposits (the `user` of every OCFL version,
section 4.1), who curates the main catalogue, and how to run TeXmacs. The
values that readers do see (the name, the contact, the profiles, the
storage layout) are copied from it into the discovery document.

Version 0.1 named an archive by an identifier of its own, `archiveId`, and
every object by an identifier chosen by the archive. Version 0.2 names
neither: no file of an object names the archive that holds it (section 3),
and an object is named by its line, `sheaf:<name>:<owner>` (section 4). The
configuration names instead the archive's *owner* (section 6), by its owner
name, and the readable *labels* that the archive gives its lines
(section 3.1) are kept in the discovery document, where readers find them
too.

    # in the docstring of core.py: what an archive folder holds:
    """The OpenSheaf archive: objects, document versions, collections, the
    discovery document, the index and the checks (specification 0.2,
    https://opensheaf.org).

    An archive is a folder with a configuration file `osheaf.json`:

        {
          "owner": "<owner name>",           the owner of the archive (section 6), who signs
                                             its documents and its main catalogue
          "owners": ["<owner name>", ...],   optional: other owners it hosts
          "name": "...", "contact": "https://...", "baseUrl": "https://.../",
          "profiles": ["website", "texmacs"],
          "storageLayout": "opensheaf-owner-name-storage-layout",   or
                           "0003-hash-and-id-n-tuple-storage-layout" (section 3.2)
          "mainCollection": "main",          the label of the main catalogue
          "curator": {"name": "Family, Given", "givenName": "...", "familyName": "...",
                      "affiliation": "..."},
          "depositor": {"name": "Given Family", "address": "https://..."},
          "texmacs": {                                  optional: the TeXmacs profile
            "plugins": ["notes", "max-html"],           needed in ~/.TeXmacs/plugins
            "init": "texmacs-init.scm",                 loaded before each run
            "htmlPackage": "paper-html.ts",             style package of HTML versions
            "htmlResources": ["max-html/resources/max-html.css", ...]   from the plugins
          },
          "index": {"template": "index-template.tm"},   optional: the readable index
          "keys": {"wallet": "github:OWNER/REPO"}       optional: the GitHub key wallet (a command
                                             wallet only in ~/.config/opensheaf/config.json)
        }

    and, next to it, `ocfl/` (the OCFL 1.1 storage root), `opensheaf.json` (the
    discovery document, rewritten whenever an object changes, which also keeps
    the labels of the lines: `osheaf deposit LABEL`), `site/` (HTML versions)
    and `index.tm`, `index.html` (generated). TeXmacs runs headless with a
    private profile in `texmacs_home/` (not committed).

    The private keys of the owner are never in the archive (section 15.4): the
    current key of this device is kept in the system's credential store (or in
    ~/.config/opensheaf/keys/), the rotation keys in files exported once to a
    folder outside the archive (`osheaf owner init --export DIR`), unless the owner
    chooses a lower security level, a key wallet, which keeps them encrypted
    under a passphrase (`--keys github:OWNER/REPO`, a private repository, or
    `--keys command`); OPENSHEAF_WALLET or ~/.config/opensheaf/config.json override
    "keys", and only they may configure a command wallet.

    The index is either a TeXmacs document made from a template, as above, which
    osheaf init --index texmacs sets up, or the website (the profile website,
    appendix A.3), which osheaf init sets up by default:
    "index": {"html": {"templates": "templates", "featured": "<label>"}}, featured
    optional. Either way the website writes the landing pages paper/<label>/, the
    owner pages owner/<owner>/ and sitemap.xml, after every change, and osheaf index
    writes everything again.
    """

The module uses the standard library and the modules of identity: names,
owners and their key logs, keys and signatures. The optional packages
(`jsonschema` and `ocfl-py` for verification, `yaml` for a configuration in
YAML) are imported where they are used, so that the tools run without them.

    # in the modules core.py imports:
    import datetime
    import hashlib
    import json
    import os
    import re
    import shutil
    import subprocess
    import sys
    import tempfile
    import unicodedata
    from pathlib import Path

    from . import keys, names, owners, sign

The configuration may also be written in YAML, which is easier to edit by
hand; JSON is the default, and the name used in messages. The JSON Schemas
of the specification (appendix B) are shipped inside the package. TeXmacs
plugins are looked for in the user's TeXmacs profile, unless
`TEXMACS_PLUGINS` says otherwise.

    # in the names of the configuration file and of the folders the tools use:
    CONFIG_NAME = "osheaf.json"
    CONFIG_NAMES = ("osheaf.json", "osheaf.yaml", "osheaf.yml")
    SCHEMAS = Path(__file__).resolve().parent / "schemas"
    USER_PLUGINS = Path(os.environ.get("TEXMACS_PLUGINS", Path.home() / ".TeXmacs/plugins"))

These globals are the state of a run. `ROOT` is the archive folder, `OCFL`
its storage root, `SITE` the folder of the HTML versions of TeXmacs
documents, `TM_HOME` the private TeXmacs profile; `ARCHIVE` holds the
settings that describe the archive, `TEXMACS` and `INDEX` those of the
TeXmacs profile and of the index. `LAYOUT` is the storage layout,
`LABELS` maps the labels of the archive's lines to their identifiers,
`TOMBSTONES` holds the tombstones of the discovery document (section 13.3),
which nothing else keeps, and `OLD` says that the folder is an archive of specification 0.1, which these
tools no longer read (below).

    # in the settings of the archive, set when it is configured:
    # set by configure()
    ROOT = OCFL = SITE = TM_HOME = None
    ARCHIVE = {}
    TEXMACS = {}
    INDEX = {}
    LAYOUT = None
    LABELS = {}
    TOMBSTONES = []
    OLD = False

The fixed values: the version of the specification written into every file;
the two storage layouts of section 3.2, by their names in the discovery
document, and the plain text file that describes the first; the form of
labels (section 3.1), which drafts share (section 10.1); the version of
TeXmacs recorded in the toolchain of typeset documents when the
configuration does not give one; and the settings without which an archive
cannot work.

    # in the constants of the specification and of the profiles:
    SPEC = "0.2"
    OWNER_NAME_LAYOUT = "opensheaf-owner-name-storage-layout"
    HASHED_LAYOUT = "0003-hash-and-id-n-tuple-storage-layout"
    LAYOUTS = {"owner-name": OWNER_NAME_LAYOUT, "hashed": HASHED_LAYOUT}
    LAYOUT_FILE = "opensheaf-owner-name-storage-layout.md"
    LAYOUT_TEXT = ("Lines at <owner>/<name>/, drafts at draft/<id>/: the owner-name layout of the "
                   "OpenSheaf specification 0.2, section 3.2\n")
    LABEL_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    TEXMACS_VERSION = "2.1.5"
    REQUIRED = ("owner", "name", "baseUrl", "mainCollection", "curator", "depositor")
    REBUILD = ("this archive is of specification 0.1, which these tools no longer read: rebuild it under "
               "specification 0.2 (section 16.1)")

Locating and configuring an archive
-----------------------------------

The commands work on the archive containing the current folder, as git
does with repositories, unless `--root` names another one.

    # in locate and configure an archive:
    <<find the archive folder above a folder>>


    <<read the configuration file of an archive>>


    <<load the configuration and set the paths of the archive>>

The archive folder is the nearest folder, going up, that holds a
configuration file.

    # in find the archive folder above a folder:
    def find_root(start=None):
        """The archive folder: START or the nearest folder above it with osheaf.json."""
        p = Path(start or Path.cwd()).resolve()
        for d in [p] + list(p.parents):
            if any((d / n).exists() for n in CONFIG_NAMES):
                return d
        sys.exit(f"no {CONFIG_NAME} in {p} or above it (use --root)")

A YAML configuration is read with every value as text (the `BaseLoader`),
as are all the YAML inputs of the tools (see the
[command line](60-command-line.md)): YAML would otherwise turn a version
`1.10` into a number, or `no` into `False`.

    # in read the configuration file of an archive:
    def read_config(root):
        """osheaf.json, or osheaf.yaml (read with every value as text)."""
        for n in CONFIG_NAMES:
            p = Path(root) / n
            if p.exists():
                if n.endswith(".json"):
                    return json.loads(p.read_text(encoding="utf-8"))
                import yaml
                return yaml.load(p.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        sys.exit(f"no {CONFIG_NAME} or osheaf.yaml in {root}")

Configuring splits the configuration into its three parts. Everything
that is not the TeXmacs profile or the index describes the archive; the
contact defaults to the base URL, the profiles to none, the layout to the
owner-name layout that section 3.2 recommends. The configuration may name
the TeXmacs version the archive uses, which then goes into the toolchain of
every typeset document. The labels and the tombstones are read from the
discovery document, which keeps them (sections 3.1 and 13.3).

An archive made under version 0.1 is recognised by its configuration,
which names an `archiveId`, or by its discovery document. Section 16.1
says that such archives remain readable as 0.1, by its text, and move to
0.2 by being rebuilt; these tools read only 0.2. Configuring such an
archive succeeds, so that `osheaf verify` can say what to do, and every
other command stops with that message (see the
[command line](60-command-line.md)).

    # in load the configuration and set the paths of the archive:
    def set_paths(root, layout=OWNER_NAME_LAYOUT):
        """Set the folders of the archive in ROOT and its storage layout."""
        global ROOT, OCFL, SITE, TM_HOME, LAYOUT
        ROOT = Path(root).resolve()
        OCFL, SITE, TM_HOME = ROOT / "ocfl", ROOT / "site", ROOT / "texmacs_home"
        LAYOUT = layout


    def configure(root):
        """Load the archive configuration and set the paths."""
        global ARCHIVE, TEXMACS, INDEX, TEXMACS_VERSION, LABELS, TOMBSTONES, OLD
        cfg = read_config(root)
        disc_path = Path(root) / "opensheaf.json"
        disc = json.loads(disc_path.read_text(encoding="utf-8")) if disc_path.exists() else {}
        OLD = "archiveId" in cfg or disc.get("specification") == "0.1"
        set_paths(root, cfg.get("storageLayout", OWNER_NAME_LAYOUT))
        ARCHIVE = {k: v for k, v in cfg.items() if k not in ("texmacs", "index")}
        if OLD:
            return ROOT
        missing = [k for k in REQUIRED if k not in cfg]
        if missing:
            sys.exit(f"{CONFIG_NAME} lacks {', '.join(missing)}")
        if LAYOUT not in LAYOUTS.values():
            sys.exit(f"{CONFIG_NAME}: storageLayout is one of {', '.join(LAYOUTS.values())}")
        ARCHIVE.setdefault("profiles", [])
        ARCHIVE.setdefault("contact", ARCHIVE["baseUrl"])
        TEXMACS = cfg.get("texmacs", {})
        TEXMACS_VERSION = TEXMACS.get("version", TEXMACS_VERSION)
        INDEX = cfg.get("index", {})
        LABELS = {o["label"]: o["id"] for o in disc.get("objects", []) if o.get("label")}
        TOMBSTONES = list(disc.get("tombstones", []))
        return ROOT

The owners of the archive are the owner of the configuration and the
others it hosts: the main catalogue lists the documents of their lines
(section 8.1), and the discovery document names them in `owners`
(section 3.1).

    # in load the configuration and set the paths of the archive:
    def archive_owners():
        """The owner names of the owners the archive hosts, its own first."""
        out = [ARCHIVE["owner"]]
        return out + [o for o in ARCHIVE.get("owners", []) if o not in out]

Commands name lines by their labels; a full identifier is accepted too.

    # in load the configuration and set the paths of the archive:
    def resolve(label):
        """The identifier of the line labelled LABEL (or LABEL itself, an identifier held here)."""
        if label in LABELS:
            return LABELS[label]
        if label.startswith("sheaf:") and (obj_dir(label) / "inventory.json").exists():
            return label
        sys.exit(f"no line labelled {label} in this archive (osheaf deposit --new {label} seals a new work)")


    def label_of(obj_id):
        """The label of the line OBJ_ID, or None."""
        return next((lb for lb, i in LABELS.items() if i == obj_id), None)

The storage root
----------------

An archive keeps its objects in an OCFL 1.1 storage root, the folder
`ocfl/`. OCFL (the Oxford Common File Layout) is a simple, well specified
way of keeping versioned objects as plain files: an object is a folder with
an *inventory*, `inventory.json`, listing every version of the object and,
for each, the *state*: which logical paths it holds, by the SHA-512 digest
of their content. The content itself is stored once, in the folder of the
version that first added it, and the *manifest* maps each digest to that
place. A version that changes one file of ten stores one file.

opensheaf-py writes OCFL itself, in a few hundred lines, rather than through
a library: it needs only to create objects and add versions, never to change
or remove them, and the OpenSheaf rules (section 4.1) fit in directly. An
independent validator checks the result, when installed (see
[verification](17-verify.md)).

This part of the module is a list of small functions; those about document
versions and dates are explained in the [next chapter](11-versions.md).

    # in the storage root, its objects and their versions:
    <<the SHA-512 digest of a file>>


    <<write a JSON file of the archive>>


    <<the time of an object version>>


    <<the folder of an object in the storage layout>>


    <<create the OCFL storage root>>


    <<read the inventory of an object>>


    <<write the inventory of an object and its copy in the head version>>


    <<the content path of a logical path>>


    <<the names of object.json and of its format>>


    <<read a JSON file of an object version>>


    <<the document version an object version holds>>


    <<the PDF of a document version>>


    <<the history of a document without a history in object.json>>


    <<the history of a document as its head states it>>


    <<the object version holding the current version of a document>>


    <<the name of the next object version>>


    <<the notice files that every later object version keeps>>


    <<carry the notices and the history to a new object version>>


    <<read a date of a DataCite description>>


    <<set a date of a DataCite description>>


    <<the objects of the storage root>>


    <<the file holding a logical path>>


    <<add a version to an OCFL object>>


    <<move the staged version into the storage root>>

### Digests, JSON and time

Every digest of OpenSheaf is SHA-512, as OCFL recommends and section 4.1
requires; MD5 and SHA-256 are computed only for the `fixity` block of the
inventories, to compare with services that report them (Zenodo reports MD5,
appendix A). Files are read in blocks, since a PDF may be large.

    # in the SHA-512 digest of a file:
    def digest(path, algo="sha512"):
        h = hashlib.new(algo)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()

Every JSON file is written the same way: indented, in UTF-8 without
escaping non-ASCII characters, with Unix line ends whatever the system and a
final newline. This matters more than it seems. The files of the storage
root are fixed by their digests and must be served byte for byte
(section 3); writing them identically everywhere makes the same deposit
produce the same bytes. `json_bytes` gives the bytes, for files that are
staged before they are written.

    # in write a JSON file of the archive:
    def json_bytes(data):
        return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(json_bytes(data))

Times are in UTC, to the second, with a `Z`, as OCFL writes the `created`
time of a version.

    # in the time of an object version:
    def now():
        return names.utc_now()

### Where an object is: the storage layouts

Version 0.1 put every object in a folder named by its identifier, the flat
direct layout of OCFL. Identifiers are now lines, `sheaf:<name>:<owner>`,
of more than a hundred characters, and section 3.2 offers two layouts. The
default, the *owner-name layout*, puts the line `sheaf:<name>:<owner>` at
`<owner>/<name>/`: the folder of an owner holds its key log, at
`<owner>/<owner>/`, and every line of it, so that an owner moving to
another archive copies one folder (section 6.5). A draft `sheaf:draft:<id>`
is at `draft/<id>/`; any other identifier is an error.

The *hashed layout* is OCFL's extension `0003-hash-and-id-n-tuple-storage-layout`
with its default parameters, for archives too large for one folder per
owner: the SHA-256 digest of the identifier gives three folders of three
characters, and the identifier, percent-encoded as the extension says
(every character but letters, digits, `-` and `_`, in lowercase
hexadecimal), names the object's folder; an encoded identifier longer than
100 characters, which every line has, is cut to 100 and followed by `-`
and the whole digest. Readers compute the path, and never decode it.
Appendix C gives the path of its paper in this layout, which the
[tests](70-tests.md) compute again.

    # in the folder of an object in the storage layout:
    def path_of(obj_id, layout=None):
        """The path, in the storage root, of the object OBJ_ID in LAYOUT (default: the archive's)."""
        layout = layout or LAYOUT
        if layout == HASHED_LAYOUT:
            h = hashlib.sha256(obj_id.encode("utf-8")).hexdigest()
            enc = "".join(c if re.match(r"[A-Za-z0-9_-]", c) else "".join(f"%{b:02x}" for b in c.encode("utf-8"))
                          for c in obj_id)
            if len(enc) > 100:
                enc = enc[:100] + "-" + h
            return f"{h[0:3]}/{h[3:6]}/{h[6:9]}/{enc}"
        parts = obj_id.split(":")
        if len(parts) == 3 and parts[0] == "sheaf":
            if parts[1] == "draft" and LABEL_RE.match(parts[2]) and len(parts[2]) <= 64:
                return f"draft/{parts[2]}"
            if names.NAME.match(parts[1]) and names.OWNER_NAME.match(parts[2]):
                return f"{parts[2]}/{parts[1]}"
        raise ValueError(f"{obj_id}: not the identifier of a line or of a draft (sections 3.2 and 4)")


    def obj_dir(obj_id):
        """The folder of the object OBJ_ID in the storage root."""
        return OCFL / path_of(obj_id)

### The storage root and the inventories

A storage root is marked by its *namaste* file `0=ocfl_1.1`. OCFL's
`ocfl_layout.json` may name only a layout registered as an OCFL extension,
so the storage root has one for the hashed layout only; the owner-name
layout is not registered, and section 3.2 asks instead for the plain text
file `opensheaf-owner-name-storage-layout.md`, which describes it, as OCFL
allows for local extensions. The discovery document, which names the
layout, is authoritative. Creating the root is idempotent.

    # in create the OCFL storage root:
    def init_storage_root():
        OCFL.mkdir(parents=True, exist_ok=True)
        (OCFL / "0=ocfl_1.1").write_text("ocfl_1.1\n")
        if LAYOUT == HASHED_LAYOUT:
            write_json(OCFL / "ocfl_layout.json", {
                "extension": HASHED_LAYOUT,
                "description": "Hashed n-tuple storage layout with its default parameters "
                               "(OpenSheaf 0.2, section 3.2)"})
        elif not (OCFL / LAYOUT_FILE).exists():
            (OCFL / LAYOUT_FILE).write_text(LAYOUT_TEXT, encoding="utf-8")

The root inventory of an object, or `None` for an object not yet created
or one whose inventory cannot be read, which [verification](17-verify.md)
reports.

    # in read the inventory of an object:
    def load_inventory(obj_dir):
        p = obj_dir / "inventory.json"
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except (ValueError, UnicodeDecodeError):
            return None

Inventories are written by one function, as bytes, with their *checksum
file* (the sidecar), whose line is the digest, two spaces and the name of
the inventory, as the computed key logs of [chapter 6](06-owners.md) and
appendix C write it, and as OCFL accepts. The members of an inventory are
in the order the key logs use (`owners.ordered_inventory`): its keys in
alphabetical order, the manifest by version, the versions by number; so
that the inventories of every kind of object, and the examples computed
from them, are written alike. OCFL keeps a copy of the inventory in each
version folder as a recommendation; OpenSheaf requires it (section 4.1),
because a pin is the digest of that copy, and a reader fetches
`v3/inventory.json` to check the pin without trusting the root inventory,
which changes with every new version.

    # in write the inventory of an object and its copy in the head version:
    def inventory_bytes(inv):
        """The bytes of the inventory file of INV and of its checksum file."""
        data = owners.inventory_file(owners.ordered_inventory(inv))
        return data, owners.sidecar(data)

Inside an object, files have two names: the *logical path*, under which the
version holds it (`paper.pdf`), and the *content path*, where it is stored
(`v2/content/paper.pdf`, or the path in an earlier version if the content
did not change). The state of a version maps digests to logical paths, the
manifest digests to content paths; going from one to the other passes
through the digest.

    # in the content path of a logical path:
    def content_path(inv, version, logical):
        """The content path (relative to the object) of a logical path."""
        for dig, paths in inv["versions"][version]["state"].items():
            if logical in paths:
                return inv["manifest"][dig][0]
        return None

The file of a logical path in a version (by default the head), as a path on
disk.

    # in the file holding a logical path:
    def read_logical(obj_dir, inv, logical, version=None):
        cp = content_path(inv, version or inv["head"], logical)
        return (obj_dir / cp) if cp else None

Most files the tools read are JSON: `object.json`, `datacite.json`,
`members.json`. Reading one of a given version is the common case.

    # in read a JSON file of an object version:
    def read_json(obj_dir, inv, logical, version=None):
        p = read_logical(obj_dir, inv, logical, version)
        return json.loads(p.read_text(encoding="utf-8")) if p else None

The objects of the storage root are its folders marked as OCFL objects,
wherever the layout puts them: the storage root is walked, without
following symbolic links (section 15.2), and without entering an object
or the storage root's own `extensions/`. Each is given with the identifier
its inventory states, the [verifier](17-verify.md) checking that the
layout puts it where it is, and sorted by identifier so that every listing
is reproducible.

    # in the objects of the storage root:
    def objects():
        """(id, object dir, inventory) of every object of the storage root."""
        out = []

        def walk(d):
            for c in sorted(d.iterdir()):
                if not c.is_dir() or c.is_symlink():
                    continue
                if (c / "0=ocfl_object_1.1").exists():
                    inv = load_inventory(c)
                    out.append(((inv or {}).get("id"), c, inv))
                elif not (d == OCFL and c.name == "extensions"):
                    walk(c)
        if OCFL is not None and OCFL.exists():
            walk(OCFL)
        return sorted(out, key=lambda o: (str(o[0]), str(o[1])))

### Adding an object version

All writing into the storage root, except that of key logs (which the
[owners' module](06-owners.md) writes, through
[the commands of owners](19-owner-commands.md)), goes through one function.
It receives the complete state of the new version, as a map from logical
paths to files on disk (or to their bytes), with its `object.json` apart,
and a message. The function

1. reads the inventory; an object that does not exist yet is created, with
   its namaste file;
2. checks, for an existing line, the versions the new one would extend
   (section 7.3, below), and finds the keys that sign it;
3. sets `previous` in `object.json`: the SHA-512 digest of the inventory
   file of the version before, as its checksum file states it, in every
   version of a line after the first, and never in a first version
   (section 4.3), so that signing the new version fixes the bytes of every
   earlier inventory;
4. stores each file whose digest is new to the object, in the version
   folder, and lists the others only in the state; records when the
   version was made, by whom (the depositor of the configuration,
   section 4.1) and why;
5. signs the new version: one signature file per current key of the
   owner found on this device, each naming the latest version of the key
   log (sections 7.1 and 7.2), in the witness folder;
6. moves the version into place.

A draft (section 10.1) goes through the same function, with three
differences: it is never signed, so no key is needed and no witness folder
is written; it has no `previous`, since its versions may be rewritten; and
nothing is checked before extending it, since nothing relies on it. Its
identifier, `sheaf:draft:<id>`, tells it apart.

Everything is first written in a staging folder of the archive, outside the
storage root, and moved into the storage root at the end: a new object by
renaming its folder, which is atomic; a new version of an existing object
by renaming its version folder and its witness folder, then replacing the
root inventory and its checksum file, each by an atomic rename. An error
before the moves leaves the storage root as it was; one between them, which
only a failing disk would cause, leaves a version folder that the root
inventory does not yet list, which [verification](17-verify.md) reports.

Versions are numbered `v1`, `v2`, ... without zero padding, which section
4.1 requires. Since no other function writes inventories of lines, an
object only grows: a version, once written, never changes.

A deposit with Zenodo (appendix A.1) needs the version built and signed
before it is added: its files are uploaded, and only once Zenodo has
published them is the version added to the storage root. With `stage_in`,
a folder that does not exist yet, the function builds and signs the version
there, and stops before the moves; `install_version` makes them later.
Meanwhile the line is locked: a Zenodo deposit that was published but not
yet added leaves its state in `zenodo-staging/<path of the line>/`, and no
other version of the line is added until `osheaf zenodo` completes it, as
appendix A.1 requires.

    # in add a version to an OCFL object:
    def add_version(obj_id, files, obj, message, *, acknowledged=False, stage_in=None):
        """Add an object version of the line OBJ_ID whose state is FILES ({logical path:
        file or bytes}) and OBJ as object.json, signed by the owner of the line; unchanged
        content is not stored again. Returns the inventory. With STAGE_IN (a new folder),
        the version is built and signed there, and install_version adds it later."""
        d = obj_dir(obj_id)
        inv = load_inventory(d)
        draft = obj_id.startswith("sheaf:draft:")
        if stage_in is None and zenodo_pending(obj_id):
            sys.exit(f"{label_of(obj_id) or obj_id}: a Zenodo deposit was published and its version is not "
                     f"added yet: osheaf zenodo {label_of(obj_id) or obj_id} completes it first (appendix A.1)")
        log, latest, signers = (None, None, []) if draft else signing_keys(obj["owner"])
        obj = {k: v for k, v in obj.items() if k != "previous"}
        if inv is None:
            if d.exists():
                sys.exit(f"{d} exists, and is not an object")
            inv = {"id": obj_id, "type": owners.INVENTORY_TYPE, "digestAlgorithm": "sha512",
                   "head": "v0", "manifest": {}, "versions": {}, "fixity": {"md5": {}, "sha256": {}}}
        elif not draft:
            check_before_extending(obj_id, d, inv, acknowledged)
            obj["previous"] = owners.sidecar_digest((d / inv["head"] / "inventory.json.sha512").read_bytes())
        ver = f"v{int(inv['head'][1:]) + 1}"
        if stage_in is not None:
            stage = Path(stage_in)
            stage.mkdir(parents=True)
        else:
            stage = Path(tempfile.mkdtemp(dir=ROOT, prefix=".staging-"))
        try:
            content = dict(files, **{OBJ: json_bytes(obj)})
            state = {}
            for logical, src in sorted(content.items()):
                data = src if isinstance(src, bytes) else Path(src).read_bytes()
                dig = names.sha512_hex(data)
                state.setdefault(dig, []).append(logical)
                if dig not in inv["manifest"]:
                    cp = f"{ver}/content/{logical}"
                    (stage / cp).parent.mkdir(parents=True, exist_ok=True)
                    (stage / cp).write_bytes(data)
                    inv["manifest"][dig] = [cp]
                    inv.setdefault("fixity", {}).setdefault("md5", {}).setdefault(
                        hashlib.md5(data).hexdigest(), []).append(cp)
                    inv["fixity"].setdefault("sha256", {}).setdefault(
                        hashlib.sha256(data).hexdigest(), []).append(cp)
            inv["head"] = ver
            inv["versions"][ver] = {
                "created": now(),
                "message": message,
                "user": {"name": ARCHIVE["depositor"]["name"], "address": ARCHIVE["depositor"]["address"]},
                "state": state,
            }
            inv = owners.ordered_inventory(inv)
            data, sidecar = inventory_bytes(inv)
            (stage / ver).mkdir(exist_ok=True)
            (stage / ver / "inventory.json").write_bytes(data)
            (stage / ver / "inventory.json.sha512").write_bytes(sidecar)
            wdir = stage / "witnesses"
            wdir.mkdir()
            pin, dig = (log.pin(latest.number) if log else None), names.sha512_hex(data)
            for key in signers:
                (wdir / sign.file_name(key.did)).write_bytes(
                    sign.signature_file(key, obj_id, ver, dig, obj["owner"], pin))
            if stage_in is None:
                move_staged(d, stage, ver, draft)
        finally:
            if stage_in is None:
                shutil.rmtree(stage, ignore_errors=True)
        return inv

The moves. A new object is assembled whole in the staging folder and
renamed into place; an existing one receives the version folder, then the
witness folder of the version, then the new root inventory.

    # in move the staged version into the storage root:
    def move_staged(d, stage, ver, draft):
        """Move the version VER built in STAGE into the object folder D."""
        data = (stage / ver / "inventory.json").read_bytes()
        sidecar = (stage / ver / "inventory.json.sha512").read_bytes()
        wdir = stage / "witnesses"
        if ver == "v1":
            new = stage / "object"
            new.mkdir()
            (new / "0=ocfl_object_1.1").write_text("ocfl_object_1.1\n")
            os.rename(stage / ver, new / ver)
            if not draft:
                (new / sign.WITNESSES).parent.mkdir(parents=True)
                (new / sign.WITNESSES).mkdir()
                os.rename(wdir, new / sign.WITNESSES / ver)
            (new / "inventory.json").write_bytes(data)
            (new / "inventory.json.sha512").write_bytes(sidecar)
            d.parent.mkdir(parents=True, exist_ok=True)
            os.rename(new, d)
        else:
            os.rename(stage / ver, d / ver)
            if not draft:
                (d / sign.WITNESSES).mkdir(parents=True, exist_ok=True)
                os.rename(wdir, d / sign.WITNESSES / ver)
            for name, b in (("inventory.json", data), ("inventory.json.sha512", sidecar)):
                (stage / name).write_bytes(b)
                os.replace(stage / name, d / name)

A version built in a staging folder is added only if the line has not
moved meanwhile: its head must still be the version before. The staging
folder holds the version folder, named by its number, and the witness
folder. The lock that keeps the line from moving is the state file of a
Zenodo deposit published and not yet added.

    # in move the staged version into the storage root:
    def install_version(obj_id, stage):
        """Add to the storage root the version that add_version(..., stage_in=STAGE) built;
        returns its inventory."""
        stage = Path(stage)
        ver = next(p.name for p in stage.iterdir() if p.is_dir() and re.match(r"^v[1-9][0-9]*$", p.name))
        inv = json.loads((stage / ver / "inventory.json").read_text(encoding="utf-8"))
        d = obj_dir(obj_id)
        before = load_inventory(d)
        if (before["head"] if before else "v0") != f"v{int(ver[1:]) - 1}":
            sys.exit(f"{obj_id}: the line has moved since {ver} was built in {stage}: it cannot be added")
        move_staged(d, stage, ver, obj_id.startswith("sheaf:draft:"))
        shutil.rmtree(stage, ignore_errors=True)
        return inv


    def zenodo_pending(obj_id):
        """Whether a Zenodo deposit of OBJ_ID was published and its version not yet added."""
        try:
            p = ROOT / "zenodo-staging" / path_of(obj_id) / "state.json"
        except ValueError:
            return False
        try:
            return p.is_file() and json.loads(p.read_text(encoding="utf-8")).get("phase") == "published"
        except ValueError:
            return False

Signing object versions
-----------------------

Every sealed version of a line is signed by its owner when it is made
(section 7.1): by at least `threshold` distinct current keys of one version
of the owner's key log, each in its own signature file, which names that
key-log version. These tools name the latest version of the key log held in
the archive, which is the one the signer knows best. The key log is the
owner object kept beside every line in the same storage root (section 6.5):
in this archive the owner object `sheaf:<owner>:<owner>` serves every line
of that owner, which is where the owner-name layout puts it, next to them.

    # in sign object versions and read the statuses of lines:
    <<the key log of an owner in the storage root>>


    <<the keys that sign for an owner on this device>>


    <<the witness files of an object version>>


    <<the statuses of the versions of a line>>


    <<show the versions a new version would extend>>

The key log of an owner is read from its owner object, or is absent.

    # in the key log of an owner in the storage root:
    def key_log(owner):
        """The key log of OWNER kept in the storage root (section 6.5), or None."""
        d = obj_dir(names.object_id(owner, owner))
        if not (d / "inventory.json").exists():
            return None
        try:
            return owners.load_key_log(d)
        except owners.OwnerError as e:
            sys.exit(str(e))

Signing needs the key log and the current keys. Nothing is signed for an
owner that has ended, by an ending version or a fork of its key log
(section 6.3), nor against a key log with errors. The current keys are
found by `keys.current_keys`, among those of the latest version of the key
log: in `OPENSHEAF_SIGNING_KEY`, in the credential store, or in a file of
the user's configuration ([chapter 7](07-keys.md)). A device that holds
fewer than `threshold` of them, in an archive with a key wallet, pulls the
others from the wallet ([chapter 19](19-owner-commands.md)), and keeps them,
so that it calls the wallet once (with `OPENSHEAF_KEY_STORE=none`, in the
memory of the command only, so that each command calls it once). A device holding fewer
than `threshold` of them cannot sign alone: an owner whose threshold needs
the keys of several members (section 6.2) signs on one device holding them
all, which these tools do not yet organise otherwise.

    # in the keys that sign for an owner on this device:
    def signing_keys(owner):
        """(the key log of OWNER, its latest version, the current keys of this device that sign)."""
        log = key_log(owner)
        if log is None:
            sys.exit(f"the key log of {owner} is not in the storage root (section 6.5)")
        errors, _ = log.check()
        if errors:
            sys.exit(f"the key log of {owner} has errors: " + "; ".join(errors))
        latest = log.latest()
        if latest is None:
            sys.exit(f"the owner {owner} has ended (section 6.3): nothing is signed for it")
        try:
            found = keys.current_keys(owner, latest.keys["keys"])
        except keys.KeyStoreError as e:
            sys.exit(str(e))
        need = latest.keys["threshold"]
        if len(found) < need and not os.environ.get(keys.SIGNING_KEY):
            found = pull_from_wallet(owner, latest, found)
        if len(found) < need:
            hint = ("configure a key wallet, from which each command opens them" if not keys.kept_on_device()
                    else "osheaf key new makes one for this device")
            sys.exit(f"this device holds {len(found)} of the current keys of {owner}, and v{latest.number} "
                     f"of its key log needs {need} to sign ({hint})")
        return log, latest, found

The witness files of a version, by name: the signature files and anything
else a host may have put there.

    # in the witness files of an object version:
    def witnesses_of(d, version):
        """{file name: bytes} of the witness folder of VERSION of the object in D."""
        w = d / sign.WITNESSES / version
        return {f.name: f.read_bytes() for f in sorted(w.iterdir()) if f.is_file()} if w.is_dir() else {}

### The statuses of a line

The status of each version of a line (section 7.3) is computed by
`sign.line_statuses_of`, from the signature files of every version and the
key log of the owner, against the inventory of each version as its version
folder holds it. Without the key log every signature is unchecked. The
*latest signed version*, signed and not contested, gives the line's
history, current version and status (sections 4.2 and 13.1).

    # in the statuses of the versions of a line:
    def line_statuses(d, inv, log=False):
        """(judgements, statuses) of the versions v1 to the head of the line held in D, against
        LOG, the owner's key log (default: the one in the storage root)."""
        owner = read_json(d, inv, OBJ, "v1").get("owner")
        if log is False:
            log = key_log(owner) if owner else None
        versions = []
        for n in range(1, int(inv["head"][1:]) + 1):
            p = d / f"v{n}" / "inventory.json"
            versions.append((f"v{n}", names.sha512_hex(p.read_bytes()) if p.exists() else "",
                             witnesses_of(d, f"v{n}")))
        if log is None:
            judgements = [sign.judge_folder(w, object_id=inv["id"], version=v, inventory=dg, owner=owner,
                                            lookup=lambda n, dg: None) for v, dg, w in versions]
            return judgements, sign.line_statuses(judgements)
        return sign.line_statuses_of(inv["id"], owner, versions, log)


    def latest_signed(d, inv, log=False):
        """The latest signed version of the line held in D, not contested, as 'vN', or None."""
        n = sign.latest_signed(line_statuses(d, inv, log)[1])
        return f"v{n}" if n else None

### Before extending a line

An owner tool MUST show the owner, before signing a new version, the
versions it would extend that are not signed, or that need an exposed key,
so that an owner never takes a thief's version into its line unknowingly
(section 7.3). The tools stop there, listing them; the depositor who has
looked and knows what they are says so with `--i-know`, and the deposit
goes on, the list being shown again. Section 7.5 forbids an archive to add
a version that is not signed and not contested once added: the new version,
signed with current keys of the latest version of the key log, which never
lists an exposed key (section 6.1, rule 2), is signed and not contested
itself, and vouches for the versions before it, which is why the owner must
know what they are.

    # in show the versions a new version would extend:
    def check_before_extending(obj_id, d, inv, acknowledged=False):
        """Show the versions of the line OBJ_ID that a new version would extend and that are
        not signed or not contested (section 7.3); stop unless ACKNOWLEDGED."""
        _, statuses = line_statuses(d, inv)
        doubtful = [(f"v{i + 1}", s) for i, s in enumerate(statuses) if s not in (sign.SIGNED, sign.VOUCHED)]
        if not doubtful:
            return
        lines = "\n".join(f"  {v}: {s}" for v, s in doubtful)
        if not acknowledged:
            sys.exit(f"{obj_id}: the new version would extend versions that are not signed, or are "
                     f"contested (section 7.3):\n{lines}\nlook at them; give --i-know to extend them anyway")
        print(f"warning: {obj_id}: extending versions that are not signed, or are contested:\n{lines}",
              file=sys.stderr)
