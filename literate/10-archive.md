The archive: configuration and storage
======================================

This chapter and the eight that follow it (up to
[creating an archive](18-init.md)) are the module `core.py`, the heart of
opensheaf-py. It knows what an OpenSheaf archive is on disk: a folder with a
configuration file, an OCFL storage root holding the objects, a discovery
document and the pages generated for readers. Everything else in the package
(the [collections](20-collections.md) across archives, the
[website](30-website.md), the imports from [arXiv](40-arxiv.md), the DOIs of
[Zenodo](50-zenodo.md), the [command line](60-command-line.md)) is built on
the functions defined here.

This chapter covers the bottom layer: how the tools find and read the
archive's configuration, and how they read and write OCFL objects. The
[next chapter](11-versions.md) adds what OpenSheaf puts on top of OCFL:
document versions, their history and their dates.

The package
-----------

The package itself says little: its version, and the version of the
specification it implements. Both are read by the command line and by the
build.

    # in src/opensheaf/__init__.py:
    """opensheaf: tools for OpenSheaf archives (https://opensheaf.org).

    The command is `osheaf` (also installed as `opensheaf`); see `osheaf --help`.
    """

    __version__ = "0.6.0"
    SPECIFICATION = "0.1"

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
objects, running TeXmacs, depositing documents, adding description-only
versions, maintaining the main collection, writing the discovery document
and the index, verifying, and creating a new archive. Each part is a chunk
explained in its own chapter.

    # in src/opensheaf/core.py:
    <<the docstring of core.py: what an archive folder holds>>

    <<the modules core.py imports>>

    <<the names of the configuration file and of the folders the tools use>>

    <<the settings of the archive, set when it is configured>>

    <<the constants of the specification and of the profiles>>


    <<locate and configure an archive>>


    <<the storage root, its objects and their versions>>


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

### What an archive folder holds

The docstring of the module is also the help of the configuration: the
command `osheaf help-config` prints it. It describes `osheaf.json`, the
only file of an archive that a person writes by hand, and the files the
tools generate next to it.

The configuration is not part of the archive as the specification defines
it (section 5): readers never see it. It holds what the tools need and the
specification leaves to the archive: who deposits (the `user` of every
OCFL version, section 7.1), who curates the main collection, and how to run
TeXmacs. The values that readers do see (the identifier, the name, the
contact, the profiles, the main collection) are copied from it into the
discovery document.

    # in the docstring of core.py: what an archive folder holds:
    """The OpenSheaf archive: objects, document versions, collections, the
    discovery document, the index and the checks (specification 0.1,
    https://opensheaf.org).

    An archive is a folder with a configuration file `osheaf.json`:

        {
          "archiveId": "tag:example.org,2026:name",   the archive identifier (a URI)
          "name": "...", "contact": "https://...", "baseUrl": "https://.../",
          "profiles": ["texmacs"], "mainCollection": "collection-papers",
          "curator": {"name": "Family, Given", "givenName": "...", "familyName": "...",
                      "affiliation": "..."},
          "depositor": {"name": "Given Family", "address": "https://..."},
          "texmacs": {                                  optional: the TeXmacs profile
            "plugins": ["notes", "max-html"],           needed in ~/.TeXmacs/plugins
            "init": "texmacs-init.scm",                 loaded before each run
            "htmlPackage": "paper-html.ts",             style package of HTML versions
            "htmlResources": ["max-html/resources/max-html.css", ...]   from the plugins
          },
          "index": {"template": "index-template.tm"}    optional: the readable index
        }

    and, next to it, `ocfl/` (the OCFL 1.1 storage root), `opensheaf.json` (the
    discovery document, generated), `site/` (HTML versions) and `index.tm`,
    `index.html` (generated). TeXmacs runs headless with a private profile in
    `texmacs_home/` (not committed).
    """

The module uses only the standard library. The optional packages
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

The configuration may also be written in YAML, which is easier to edit by
hand; JSON is the default, and the name used in messages. The JSON Schemas
of the specification (appendix D) are shipped inside the package. TeXmacs
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
TeXmacs profile and of the index.

    # in the settings of the archive, set when it is configured:
    # set by configure()
    ROOT = OCFL = SITE = TM_HOME = None
    ARCHIVE = {}
    TEXMACS = {}
    INDEX = {}

The fixed values: the version of the specification written into every file,
the storage layout the specification requires (section 5), the form of
object identifiers (section 6.3), the version of TeXmacs recorded in the
toolchain of typeset documents when the configuration does not give one,
and the settings without which an archive cannot work.

    # in the constants of the specification and of the profiles:
    SPEC = "0.1"
    LAYOUT = "0002-flat-direct-storage-layout"
    ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    TEXMACS_VERSION = "2.1.5"
    REQUIRED = ("archiveId", "name", "baseUrl", "mainCollection", "curator", "depositor")

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

Configuring checks the required settings and splits the configuration into
its three parts. Everything that is not the TeXmacs profile or the index
describes the archive; the contact defaults to the base URL, the profiles
to none. The configuration may name the TeXmacs version the archive uses,
which then goes into the toolchain of every typeset document.

    # in load the configuration and set the paths of the archive:
    def configure(root):
        """Load the archive configuration and set the paths."""
        global ROOT, OCFL, SITE, TM_HOME, ARCHIVE, TEXMACS, INDEX, TEXMACS_VERSION
        ROOT = Path(root).resolve()
        cfg = read_config(ROOT)
        missing = [k for k in REQUIRED if k not in cfg]
        if missing:
            sys.exit(f"{CONFIG_NAME} lacks {', '.join(missing)}")
        ARCHIVE = {k: v for k, v in cfg.items() if k not in ("texmacs", "index")}
        ARCHIVE.setdefault("profiles", [])
        ARCHIVE.setdefault("contact", ARCHIVE["baseUrl"])
        TEXMACS = cfg.get("texmacs", {})
        TEXMACS_VERSION = TEXMACS.get("version", TEXMACS_VERSION)
        INDEX = cfg.get("index", {})
        OCFL, SITE, TM_HOME = ROOT / "ocfl", ROOT / "site", ROOT / "texmacs_home"
        return ROOT

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

opensheaf-py writes OCFL itself, in a hundred lines, rather than through a
library: it needs only to create objects and add versions, never to change
or remove them, and the OpenSheaf rules (section 7.1) fit in directly. An
independent validator checks the result, when installed (see
[verification](17-verify.md)).

This part of the module is a list of small functions; those about document
versions and dates are explained in the [next chapter](11-versions.md).

    # in the storage root, its objects and their versions:
    <<the SHA-512 digest of a file>>


    <<write a JSON file of the archive>>


    <<the time of an object version>>


    <<create the OCFL storage root>>


    <<read the inventory of an object>>


    <<write the inventory of an object and its copy in the head version>>


    <<the content path of a logical path>>


    <<the names of object.json and of its format>>


    <<read a JSON file of an object version>>


    <<the document version an object version holds>>


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

### Digests, JSON and time

Every digest of OpenSheaf is SHA-512, as OCFL recommends and section 7.1
requires; MD5 and SHA-256 are computed only for the `fixity` block of the
inventories, to compare with services that report them (Zenodo reports MD5,
appendix A). Files are read in blocks, since a PDF may be large.

    # in the SHA-512 digest of a file:
    # ---------------------------------------------------------------------------
    # Digests and OCFL

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
(section 5); writing them identically everywhere makes the same deposit
produce the same bytes.

    # in write a JSON file of the archive:
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

Times are in UTC, to the second, with a `Z`, as OCFL writes the `created`
time of a version.

    # in the time of an object version:
    def now():
        return (datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
                .isoformat().replace("+00:00", "Z"))

### The storage root and the inventories

A storage root is marked by its *namaste* file `0=ocfl_1.1` and states its
layout in `ocfl_layout.json`. OpenSheaf requires the flat direct layout
(section 5): the folder of an object is its identifier, so that a reader
finds an object from its identifier alone, without a table. Creating the
root is idempotent, and every command that may add an object calls it.

    # in create the OCFL storage root:
    def init_storage_root():
        OCFL.mkdir(exist_ok=True)
        (OCFL / "0=ocfl_1.1").write_text("ocfl_1.1\n")
        write_json(OCFL / "ocfl_layout.json", {
            "extension": LAYOUT,
            "description": "Flat direct storage layout: the object identifier is the object's folder name"})
        # the flat-direct layout has no parameters: no extensions/ folder (OCFL
        # forbids empty folders, and ocfl-py rejects a config.json for it)

The root inventory of an object, or `None` for an object not yet created.

    # in read the inventory of an object:
    def load_inventory(obj_dir):
        p = obj_dir / "inventory.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

An inventory is written with its *sidecar*, the file holding its digest.
OCFL keeps a copy of the inventory in each version folder as a
recommendation; OpenSheaf requires it (section 7.1), because a collection
pins an object version by the digest of that copy, and a reader fetches
`v3/inventory.json` to check the pin without trusting the root inventory,
which changes with every new version.

    # in write the inventory of an object and its copy in the head version:
    def write_inventory(obj_dir, inv):
        """Write the root inventory and its checksum file, and copies in the head
        version directory (required by OpenSheaf)."""
        for d in (obj_dir, obj_dir / inv["head"]):
            p = d / "inventory.json"
            write_json(p, inv)
            (d / "inventory.json.sha512").write_text(f"{digest(p)} inventory.json\n")

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
        return json.loads(p.read_text()) if p else None

The objects of the storage root are its folders marked as OCFL objects,
sorted by identifier so that every listing is reproducible.

    # in the objects of the storage root:
    def objects():
        """(id, object dir, inventory) of every object of the storage root."""
        out = []
        if OCFL.exists():
            for d in sorted(OCFL.iterdir()):
                if d.is_dir() and (d / "0=ocfl_object_1.1").exists():
                    out.append((d.name, d, load_inventory(d)))
        return out

### Adding an object version

All writing into the storage root goes through one function. It receives
the complete state of the new version, as a map from logical paths to files
on disk, and a message. An object that does not exist yet is created, with
its namaste file and an empty inventory at the version `v0` (which is never
written: the first version is `v1`). Each file is stored only if its digest
is new to the object; a file unchanged since an earlier version is only
listed in the state. The version records when it was made, by whom (the
depositor of the configuration, section 7.1) and why.

Versions are numbered `v1`, `v2`, ... without zero padding, which OCFL
allows and section 7.1 forbids. Since no other function writes inventories,
an object only grows: a version, once written, never changes.

    # in add a version to an OCFL object:
    def add_version(obj_id, files, message):
        """Add an object version whose state is FILES ({logical path: source
        file}); unchanged content is not stored again. Returns the inventory."""
        obj_dir = OCFL / obj_id
        inv = load_inventory(obj_dir)
        if inv is None:
            obj_dir.mkdir(parents=True)
            (obj_dir / "0=ocfl_object_1.1").write_text("ocfl_object_1.1\n")
            inv = {"id": obj_id, "type": "https://ocfl.io/1.1/spec/#inventory",
                   "digestAlgorithm": "sha512", "head": "v0", "contentDirectory": "content",
                   "manifest": {}, "versions": {}, "fixity": {"md5": {}, "sha256": {}}}
        ver = f"v{int(inv['head'][1:]) + 1}"
        state = {}
        for logical, src in sorted(files.items()):
            dig = digest(src)
            state.setdefault(dig, []).append(logical)
            if dig not in inv["manifest"]:
                cp = f"{ver}/content/{logical}"
                dest = obj_dir / cp
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
                inv["manifest"][dig] = [cp]
                inv["fixity"]["md5"].setdefault(digest(dest, "md5"), []).append(cp)
                inv["fixity"]["sha256"].setdefault(digest(dest, "sha256"), []).append(cp)
        inv["head"] = ver
        inv["versions"][ver] = {
            "created": now(),
            "message": message,
            "user": {"name": ARCHIVE["depositor"]["name"], "address": ARCHIVE["depositor"]["address"]},
            "state": state,
        }
        write_inventory(obj_dir, inv)
        return inv
