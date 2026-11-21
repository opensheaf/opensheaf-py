# Generated from literate/10-archive.md by opensheaf-literate: edit the document, not this file.
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

CONFIG_NAME = "osheaf.json"
CONFIG_NAMES = ("osheaf.json", "osheaf.yaml", "osheaf.yml")
SCHEMAS = Path(__file__).resolve().parent / "schemas"
USER_PLUGINS = Path(os.environ.get("TEXMACS_PLUGINS", Path.home() / ".TeXmacs/plugins"))

# set by configure()
ROOT = OCFL = SITE = TM_HOME = None
ARCHIVE = {}
TEXMACS = {}
INDEX = {}
LAYOUT = None
LABELS = {}
TOMBSTONES = []
OLD = False

SPEC = "0.2"
OWNER_NAME_LAYOUT = "opensheaf-owner-name-storage-layout"
HASHED_LAYOUT = "0003-hash-and-id-n-tuple-storage-layout"
LAYOUTS = {"owner-name": OWNER_NAME_LAYOUT, "hashed": HASHED_LAYOUT}
LAYOUT_FILE = "opensheaf-owner-name-storage-layout.md"
LAYOUT_TEXT = ("Lines at <owner>/<name>/, drafts at draft/<id>/: the owner-name layout of the "
               "OpenSheaf specification 0.2, section 3.2\n")
LABEL_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\Z")
TEXMACS_VERSION = "2.1.5"
REQUIRED = ("owner", "name", "baseUrl", "mainCollection", "curator", "depositor")
REBUILD = ("this archive is of specification 0.1, which these tools no longer read: rebuild it under "
           "specification 0.2 (section 16.1)")


def find_root(start=None):
    """The archive folder: START or the nearest folder above it with osheaf.json."""
    p = Path(start or Path.cwd()).resolve()
    for d in [p] + list(p.parents):
        if any((d / n).exists() for n in CONFIG_NAMES):
            return d
    sys.exit(f"no {CONFIG_NAME} in {p} or above it (use --root)")


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


def archive_owners():
    """The owner names of the owners the archive hosts, its own first."""
    out = [ARCHIVE["owner"]]
    return out + [o for o in ARCHIVE.get("owners", []) if o not in out]


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


def page_address(obj_id):
    """The address of the landing page of the line OBJ_ID below paper/ (appendix A.3): its label,
    or its name, followed by -<owner> when the archive holds several lines of that name."""
    label = label_of(obj_id)
    if label:
        return label
    _, nm, owner = obj_id.split(":")
    same = [i for i, _, _ in objects() if isinstance(i, str) and i.startswith(f"sheaf:{nm}:")]
    return nm if len(same) <= 1 else f"{nm}-{owner}"


def digest(path, algo="sha512"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(data):
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(json_bytes(data))


def now():
    return names.utc_now()


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


def load_inventory(obj_dir):
    p = obj_dir / "inventory.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (ValueError, UnicodeDecodeError):
        return None


def inventory_bytes(inv):
    """The bytes of the inventory file of INV and of its checksum file."""
    data = owners.inventory_file(owners.ordered_inventory(inv))
    return data, owners.sidecar(data)


def content_path(inv, version, logical):
    """The content path (relative to the object) of a logical path."""
    for dig, paths in inv["versions"][version]["state"].items():
        if logical in paths:
            return inv["manifest"][dig][0]
    return None


OBJ = "object.json"
OBJ_FORMAT = "opensheaf-object/0.2"
GENESIS = names.GENESIS
IDENTITY = ("datacite.json", OBJ, GENESIS)
TODAY = datetime.date.today().isoformat()


def read_json(obj_dir, inv, logical, version=None):
    p = read_logical(obj_dir, inv, logical, version)
    return json.loads(p.read_text(encoding="utf-8")) if p else None


def doc_version_of(obj_dir, inv, version):
    return read_json(obj_dir, inv, OBJ, version)["documentVersion"]


def pdf_of(obj):
    """The logical path of the PDF of a document version, from the renditions
    in its object.json, or None."""
    rs = obj.get("renditions", [])
    return next((r["path"] for r in rs if r.get("mediaType") == "application/pdf"),
                next((r["path"] for r in rs if r["path"].lower().endswith(".pdf")), None))


def default_history(obj_dir, inv, at=None):
    """Without `history`: the last object version holding each document
    version, in the order of the numbers, among the object versions up to
    AT (default: the head) (section 4.2)."""
    at = at or inv["head"]
    last = {}
    for ver in inv["versions"]:
        if int(ver[1:]) <= int(at[1:]):
            last[doc_version_of(obj_dir, inv, ver)] = ver
    return [last[n] for n in sorted(last)]


def history_of(obj_dir, inv, at=None):
    """The history as read from object version AT (default: the head)."""
    obj = read_json(obj_dir, inv, OBJ, at)
    return obj.get("history") or default_history(obj_dir, inv, at)


def current_version(obj_dir, inv, at=None):
    """The object version holding the current document version as of object
    version AT (default: the head): the last entry of its history, or without
    one the last object version holding the highest document version
    (section 4.2)."""
    return history_of(obj_dir, inv, at)[-1]


def next_object_version(inv):
    return f"v{int(inv['head'][1:]) + 1}" if inv else "v1"


def carried_files(obj_id, inv):
    """{logical path: file} of the notice files of the head, which every later
    object version keeps (section 4.2)."""
    if not inv:
        return {}
    d = obj_dir(obj_id)
    head = read_json(d, inv, OBJ)
    out = {}
    for n in head.get("notices", []):
        if n.get("path"):
            out[n["path"]] = d / content_path(inv, inv["head"], n["path"])
    return out


EVIDENCE = "parent/"


def is_evidence(logical):
    """Whether LOGICAL is a file of the evidence of a branch point (section 9.2)."""
    return logical.startswith(EVIDENCE)


def evidence_paths(inv, version=None):
    """The logical paths of the evidence of a branch point held in VERSION (default: the head)."""
    if not inv:
        return []
    state = inv["versions"][version or inv["head"]]["state"]
    return sorted(p for ps in state.values() for p in ps if is_evidence(p))


def carry_forward(prev, new, inv, new_ver, after_doc=None, obj_id=None):
    """Keep the notices of the head (they persist unchanged) and its history,
    updated for NEW, the object.json of object version NEW_VER: a new document
    version is appended (or placed after document version AFTER_DOC, which
    then writes a history); a description-only version replaces the entry of
    its document version (OBJ_ID: the object, by default the line NEW names)."""
    if prev is None:
        if after_doc:
            sys.exit("--after needs an existing document")
        return
    if prev.get("notices"):
        kept = list(prev["notices"])
        new["notices"] = kept + [n for n in new.get("notices", []) if n not in kept]
    if prev.get("history") is None and after_doc is None:
        return
    d = obj_dir(obj_id or names.object_id(new["name"], new["owner"]))
    hist = list(prev.get("history") or default_history(d, inv))
    docs = {doc_version_of(d, inv, v): v for v in hist}
    n = new["documentVersion"]
    if n in docs:                      # description-only (or completion)
        hist[hist.index(docs[n])] = new_ver
    elif after_doc is None:
        hist.append(new_ver)
    else:
        if after_doc not in docs:
            sys.exit(f"--after: no document version {after_doc}")
        hist.insert(hist.index(docs[after_doc]) + 1, new_ver)
    new["history"] = hist


def date_of(dc, *types):
    for t in types:
        for d in dc.get("dates", []):
            if d["dateType"] == t:
                return d["date"]
    return None


def set_date(dc, date_type, date, info=None):
    dates = [d for d in dc.get("dates", []) if d["dateType"] != date_type]
    entry = {"date": date, "dateType": date_type}
    if info:
        entry["dateInformation"] = info
    dc["dates"] = dates + [entry]


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


def read_logical(obj_dir, inv, logical, version=None):
    cp = content_path(inv, version or inv["head"], logical)
    return (obj_dir / cp) if cp else None


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


def install_version(obj_id, stage):
    """Add to the storage root the version that add_version(..., stage_in=STAGE) built;
    returns its inventory."""
    stage = Path(stage)
    ver = next(p.name for p in stage.iterdir() if p.is_dir() and re.match(r"^v[1-9][0-9]*\Z", p.name))
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


def key_log(owner):
    """The key log of OWNER kept in the storage root (section 6.5), or None."""
    d = obj_dir(names.object_id(owner, owner))
    if not (d / "inventory.json").exists():
        return None
    try:
        return owners.load_key_log(d)
    except owners.OwnerError as e:
        sys.exit(str(e))


def signing_keys(owner):
    """(the key log of OWNER, its latest version, the current keys of this device that sign)."""
    who = names.short(owner)
    log = key_log(owner)
    if log is None:
        stop(f"the key log of {who} is not in the storage root (section 6.5)")
    errors, _ = log.check()
    if errors:
        stop(f"the key log of {who} has errors: " + "; ".join(errors))
    latest = log.latest()
    if latest is None:
        stop(f"the owner {who} has ended (section 6.3): nothing is signed for it")
    try:
        found = keys.current_keys(owner, latest.keys["keys"])
    except keys.KeyStoreError as e:
        stop(str(e))
    need = latest.keys["threshold"]
    if len(found) < need and not os.environ.get(keys.SIGNING_KEY):
        found = pull_from_wallet(owner, latest, found)
    if len(found) < need:
        hint = ("configure a key wallet, from which each command opens them" if not keys.kept_on_device()
                else "osheaf key new makes one for this computer")
        stop(f"this computer holds {len(found)} of the current keys of {who}, and v{latest.number} "
             f"of its key log needs {need} to sign ({hint})")
    return log, latest, found


def witnesses_of(d, version):
    """{file name: bytes} of the witness folder of VERSION of the object in D."""
    w = d / sign.WITNESSES / version
    return {f.name: f.read_bytes() for f in sorted(w.iterdir()) if f.is_file()} if w.is_dir() else {}


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


def run_texmacs(calls):
    """Run Scheme CALLS in a headless TeXmacs with the private profile."""
    tm = os.environ.get("TEXMACS_BIN", "/Applications/TeXmacs.app/Contents/MacOS/TeXmacs")
    TM_HOME.mkdir(exist_ok=True)
    if not (TM_HOME / "plugins").exists():
        (TM_HOME / "plugins").symlink_to(USER_PLUGINS)
    for p in TEXMACS.get("plugins", []):
        if not (TM_HOME / "plugins" / p).exists():
            sys.exit(f"TeXmacs plugin {p} not found in {USER_PLUGINS}")
    env = dict(os.environ, LC_ALL="C.UTF-8", QT_QPA_PLATFORM="offscreen",
               TEXMACS_HOME_PATH=str(TM_HOME))
    if not (TM_HOME / "system" / "settings.scm").exists():
        # the first start sets the profile up and would discard preferences
        subprocess.run([tm, "-headless", "-x", "(quit-TeXmacs)"], env=env,
                       capture_output=True, timeout=600, cwd=tempfile.gettempdir())
    (TM_HOME / "system" / "preferences.scm").write_text(
        '("texmacs->html:images" "off")\n'
        '("texmacs->html:mathjax" "on")\n'
        '("texmacs->html:mathml" "off")\n')
    # style-clear-cache: TeXmacs caches style environments in the profile.
    init = f"(load \"{ROOT / TEXMACS['init']}\") " if TEXMACS.get("init") else ""
    cmd = (f"(begin {init}(catch #t (lambda () (style-clear-cache) {calls}) (lambda args"
           f" (display \"SCHEME-ERROR \") (write args) (newline))) (quit-TeXmacs))")
    # in a scratch folder: TeXmacs' helpers (Ghostscript) may leave files in
    # the current folder, which must not end up in the archive
    work = tempfile.mkdtemp(prefix="osheaf-texmacs-")
    try:
        out = subprocess.run([tm, "-headless", "-x", cmd], env=env, capture_output=True,
                             text=True, errors="replace", timeout=1200, cwd=work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if "SCHEME-ERROR" in out.stdout + out.stderr:
        sys.exit(out.stdout + out.stderr)


def export_calls(doc, pdf=None, html=None):
    """Scheme code exporting DOC; a PDF export typesets it first."""
    c = (f'(let ((u (string->url "{doc}"))) (load-buffer u) (switch-to-buffer u)'
         ' (update-forced)')
    if pdf:
        c += f' (export-buffer-main u (string->url "{pdf}") "pdf" (list :overwrite))'
    if html:
        c += f' (export-buffer-main u (string->url "{html}") "html" (list :overwrite))'
    return c + ")"


def with_package(text, package):
    """Add PACKAGE to the style of a TeXmacs document."""
    m = re.search(r"<style\|<tuple\|([^>]*)>>", text)
    if m:
        return text[:m.start()] + f"<style|<tuple|{m.group(1)}|{package}>>" + text[m.end():]
    m = re.search(r"<style\|([^<>|]*)>", text)
    if not m:
        sys.exit("no style line in the source")
    return text[:m.start()] + f"<style|<tuple|{m.group(1)}|{package}>>" + text[m.end():]


def typeset(source, obj_id, pdf, html_dir):
    """PDF from a plain copy of SOURCE; with an HTML package configured
    (texmacs.htmlPackage), the HTML version from another copy using it."""
    tmp = Path(tempfile.mkdtemp())
    plain, styled, out = tmp / "plain", tmp / "styled", tmp / "out"
    for d in (plain, styled, out):
        d.mkdir()
    shutil.copyfile(source, plain / f"{obj_id}.tm")
    calls = export_calls(plain / f"{obj_id}.tm", pdf=pdf)
    pkg = TEXMACS.get("htmlPackage")
    if html_dir is not None:
        text = source.read_text(encoding="latin-1")
        if pkg:
            shutil.copyfile(ROOT / pkg, styled / Path(pkg).name)
            text = with_package(text, Path(pkg).stem)
        with open(styled / f"{obj_id}.tm", "w", encoding="latin-1", newline="") as f:
            f.write(text)
        calls += " " + export_calls(styled / f"{obj_id}.tm", pdf=tmp / "styled.pdf",
                                    html=out / f"{obj_id}.html")
    run_texmacs(calls)
    if html_dir is not None:
        html_dir.mkdir(parents=True, exist_ok=True)
        for old in html_dir.iterdir():
            old.unlink()
        for f in out.iterdir():
            shutil.copyfile(f, html_dir / f.name)
        for r in TEXMACS.get("htmlResources", []):
            shutil.copyfile(TM_HOME / "plugins" / r, html_dir / Path(r).name)
    shutil.rmtree(tmp, ignore_errors=True)


def tm_balanced(s, i):
    """Index of the '>' closing the tag argument list starting at i."""
    depth, j = 0, i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "<":
            depth += 1
        elif s[j] == ">":
            if depth == 0:
                return j
            depth -= 1
        j += 1
    return j


def tm_abstract(source):
    """The paragraphs of the abstract of a TeXmacs document, as markup."""
    s = source.read_text(encoding="latin-1")
    i = s.find("<\\abstract>")
    if i >= 0:
        body = s[i + len("<\\abstract>"):s.find("</abstract>", i)]
    else:
        i = s.find("<abstract|")
        if i < 0:
            return None
        i += len("<abstract|")
        body = s[i:tm_balanced(s, i)]
    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body)]
    return [p for p in paragraphs if p]


# TeXmacs inline markup to plain text with LaTeX mathematics (the subset used
# in abstracts: symbols, scripts, brackets, blackboard bold).

def _parse(s, i=0, stop=""):
    nodes, buf = [], []

    def flush():
        if buf:
            nodes.append("".join(buf))
            buf.clear()
    while i < len(s):
        c = s[i]
        if c in stop:
            break
        if s.startswith("\\<", i):
            j = s.index("\\>", i)
            flush()
            nodes.append(("sym", s[i + 2:j]))
            i = j + 2
        elif c == "\\" and i + 1 < len(s):
            buf.append({"U": "–", "|": "|", "\\": "\\"}.get(s[i + 1], s[i + 1]))
            i += 2
        elif c == "<":
            j = i + 1
            while j < len(s) and s[j] not in "|>":
                j += 1
            name, args = s[i + 1:j], []
            while j < len(s) and s[j] == "|":
                arg, j = _parse(s, j + 1, "|>")
                args.append(arg)
            flush()
            nodes.append(("tag", name, args))
            i = j + 1
        else:
            buf.append(c)
            i += 1
    flush()
    return nodes, i


SYMBOLS_TEXT = {"less": "<", "gtr": ">", "nbsp": " ", "ldots": "..."}
SYMBOLS_MATH = {"less": "<", "gtr": ">", "ldots": "\\ldots"}


def _render(nodes, math):
    out = []
    for n in nodes:
        if isinstance(n, str):
            out.append(n)
        elif n[0] == "sym":
            table = SYMBOLS_MATH if math else SYMBOLS_TEXT
            out.append(table.get(n[1], "\\" + n[1] + " "))
        else:
            name, args = n[1], n[2]
            def r(a):
                return _render(a, math)
            if name == "math":
                out.append("$" + re.sub(r"\s+", " ", _render(args[0], True)).strip() + "$")
            elif name == "rsup":
                out.append("^{" + r(args[0]) + "}")
            elif name == "rsub":
                out.append("_{" + r(args[0]) + "}")
            elif name in ("around", "around*") and len(args) == 3:
                out.append(r(args[0]) + r(args[1]) + r(args[2]))
            elif name == "with" and args:
                inner = r(args[-1])
                if any(r(a) == "Bbb" for a in args[:-1]):
                    inner = "\\mathbb{" + inner + "}"
                out.append(inner)
            elif args:
                out.append(r(args[-1]))
    s = "".join(out)
    return re.sub(r"(\\[A-Za-z]+) (?=[^A-Za-z])", r"\1", s) if math else s


def tm_to_text(markup):
    return re.sub(r"[ \t]+", " ", _render(_parse(markup)[0], False)).strip()


def creator(spec):
    """'Family, Given|Affiliation' -> DataCite creator."""
    name, _, aff = spec.partition("|")
    family, _, given = name.partition(",")
    family, given = family.strip(), given.strip()
    c = {"name": f"{family}, {given}" if given else family, "nameType": "Personal",
         "familyName": family}
    if given:
        c["givenName"] = given
    if aff.strip():
        c["affiliation"] = [{"name": aff.strip()}]
    return c


def display_name(c):
    return (f"{c.get('givenName', '')} {c['familyName']}".strip()
            if "familyName" in c else c["name"])


def names_joined(names):
    """['A', 'B', 'C'] -> 'A, B and C'."""
    names = list(names)
    return " and ".join([", ".join(names[:-1]), names[-1]]) if len(names) > 1 else "".join(names)


def authors_of(dc):
    """The creators of a description as readers write them: 'A, B and C'."""
    return names_joined(display_name(c) for c in dc["creators"])


def related_from_args(specs):
    related = []
    for kv in specs or []:
        k, _, v = kv.partition("=")
        if k == "arxiv" and v:
            related.append({"relatedIdentifier": f"arXiv:{v}", "relatedIdentifierType": "arXiv",
                            "relationType": "IsVariantFormOf"})
            continue
        # RELATION:doi:VALUE or RELATION:arxiv:VALUE
        rel, _, rest = kv.partition(":")
        typ, _, val = rest.partition(":")
        if not (rel and typ in ("doi", "arxiv") and val):
            sys.exit(f"--related {kv}: use arxiv=ID or RELATION:doi:DOI or RELATION:arxiv:ID")
        related.append({"relatedIdentifier": f"arXiv:{val}" if typ == "arxiv" else val,
                        "relatedIdentifierType": "arXiv" if typ == "arxiv" else "DOI",
                        "relationType": rel})
    return related


SOURCE_FORMATS = {".tex": "application/x-tex", ".ltx": "application/x-tex", ".tm": "application/x-texmacs",
                  ".md": "text/markdown", ".txt": "text/plain", ".html": "text/html",
                  ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                  ".odt": "application/vnd.oasis.opendocument.text", ".zip": "application/zip"}


def rights_list(rights, prev_dc=None):
    """The licence given (an SPDX key of RIGHTS or a statement), or else that
    of the previous version, or else 'All rights reserved'."""
    if rights:
        return [dict(RIGHTS[rights]) if rights in RIGHTS else {"rights": rights}]
    if prev_dc and prev_dc.get("rightsList"):
        return prev_dc["rightsList"]
    return [{"rights": "All rights reserved"}]


def check_rights(rights):
    """RIGHTS as --rights takes it: a key of RIGHTS, or a statement on one line; ValueError if not."""
    known = ", ".join(sorted(RIGHTS))
    if not isinstance(rights, str) or not rights.strip() or len(rights) > 1000 \
            or any(ord(c) < 32 or ord(c) == 127 for c in rights):
        raise ValueError(f"--rights is one of {known}, or a statement on one line")
    if rights not in RIGHTS and re.fullmatch(r"[a-z0-9][a-z0-9.+-]*", rights):
        raise ValueError(f"--rights {rights}: not a licence known by its SPDX key ({known}); give one of "
                         "them, or the licence as a statement, by its name or its address")
    return rights


def landing_url(label):
    """The address readers are sent to: the landing page, written with either
    kind of index, or else the HTML version of a TeXmacs document."""
    if INDEX.get("html") or INDEX.get("template"):
        return f"{ARCHIVE['baseUrl']}paper/{label}/"
    return f"{ARCHIVE['baseUrl']}site/{label}/{label}.html"


def seal(kind, owner):
    """A new genesis record of a work of OWNER, of KIND, and the identifier of its line,
    free in this archive (sections 5.3, 5.4 and 10.2)."""
    taken = set()
    for obj_id, _, _ in objects():
        taken.update((obj_id or "").split(":")[1:2])
    taken.update(t.get("genesisName") for t in TOMBSTONES)
    taken.update(t.get("name") for t in TOMBSTONES)
    while True:
        genesis = names.genesis_record(kind, originator=owner)
        nm = names.name(genesis)
        if nm not in taken:
            return genesis, names.object_id(nm, owner)


def deposit(args):
    """Deposit a document, or a new document version of it: a TeXmacs source
    (typeset by the archive), or any source with its PDF (--pdf), or a PDF
    alone (--no-source REASON)."""
    label = args.id
    new = getattr(args, "new", False)
    draft = getattr(args, "draft", False)
    if draft:
        if not label or not LABEL_RE.match(label) or len(label) > 64:
            sys.exit("the identifier of a draft matches ^[a-z0-9]+(-[a-z0-9]+)*$ and has at most 64 "
                     "characters (section 10.1)")
        obj_id, owner = f"sheaf:draft:{label}", None
        held = (obj_dir(obj_id) / "inventory.json").exists()
        if new and held:
            sys.exit(f"the draft {label} exists: osheaf draft deposit {label} adds a version to it")
        if not new and not held:
            sys.exit(f"no draft {label} in this archive (osheaf draft new {label} makes one)")
    elif label in LABELS:
        if new:
            sys.exit(f"{label} is the label of a line already: deposit a new version without --new, "
                     "or choose another label for a new work")
        obj_id = LABELS[label]
        genesis = None
    elif not new:
        sys.exit(f"no line labelled {label} in this archive: give --new to seal a new work "
                 f"(section 10.2), or check the label (osheaf verify lists them)")
    else:
        if not LABEL_RE.match(label) or len(label) > 64:
            sys.exit("a label must match ^[a-z0-9]+(-[a-z0-9]+)*$ and have at most 64 characters")
        if len(label) > 32:
            print(f"warning: {label} is longer than 32 characters (it appears in every URL of the website)",
                  file=sys.stderr)
        owner = getattr(args, "owner", None) or ARCHIVE["owner"]
        if owner not in archive_owners():
            sys.exit(f"{owner} is not an owner this archive hosts")
        obj_id = None
    init_storage_root()
    source = Path(args.source) if args.source else None
    for f in [source, args.pdf and Path(args.pdf)] + [Path(x.partition("=")[0]) for x in args.extra_source or []]:
        if f and not f.is_file():
            sys.exit(f"no file {f}")
    d = obj_dir(obj_id) if obj_id else None
    inv = load_inventory(d) if d else None
    prev_obj = prev_dc = None
    doc_version = 1
    if inv:
        prev_obj, prev_dc = read_json(d, inv, OBJ), read_json(d, inv, "datacite.json")
        if prev_obj["kind"] != "document":
            sys.exit(f"{label} is not a document")
        if prev_obj.get("status") == "withdrawn":
            sys.exit(f"{label} is withdrawn (section 13.1): a withdrawn document gets no new versions")
        doc_version = max(doc_version_of(d, inv, v) for v in inv["versions"]) + 1
        owner = prev_obj.get("owner")
    if args.created and args.available:
        sys.exit("give --created (a version not public at the time) or --available, not both")
    available = None if args.created else (args.available or TODAY)
    issued = args.issued or (date_of(prev_dc, "Issued") if prev_dc else None) or available

    tmp = Path(tempfile.mkdtemp())
    texmacs = source is not None and source.suffix == ".tm" and not args.pdf
    if not texmacs and not args.pdf:
        sys.exit("give the PDF of this version with --pdf (only TeXmacs sources are typeset by the archive)")
    if source is None and not args.no_source:
        sys.exit("a deposit without sources needs --no-source REASON (section 4.3: sourcesMissing)")
    files, formats = {}, []
    if texmacs:
        main = f"{label}.tm"
        fmt = "application/x-texmacs"
    elif source is not None:
        main = source.name
        fmt = args.source_format or SOURCE_FORMATS.get(source.suffix.lower(), "application/octet-stream")
    if source is not None:
        files[main] = source
        formats.append(fmt)
    formats.append("application/pdf")
    for spec in args.extra_source or []:
        # FILE or FILE=LOGICAL/PATH (the path the main source refers to)
        src, _, logical = spec.partition("=")
        logical = logical or Path(src).name
        parts = logical.split("/")
        if logical.startswith("/") or ".." in parts or "." in parts:
            sys.exit(f"bad logical path {logical}")
        files[logical] = Path(src)
        if logical.endswith(".bib") and "application/x-bibtex" not in formats:
            formats.append("application/x-bibtex")
    if texmacs:
        pdf = tmp / "paper.pdf"
        typeset(source, label, pdf, SITE / label if TEXMACS.get("htmlPackage") or not INDEX.get("html") else None)
    else:
        pdf = Path(args.pdf)
        if pdf.read_bytes()[:4] != b"%PDF":
            sys.exit(f"{pdf} is not a PDF")
    files["paper.pdf"] = pdf

    if args.abstract_file:
        abstract_text = Path(args.abstract_file).read_text(encoding="utf-8").strip()
    elif args.abstract:
        abstract_text = args.abstract.strip()
    elif texmacs:
        paras = tm_abstract(source)
        abstract_text = "\n\n".join(tm_to_text(p) for p in paras) if paras else None
    else:
        abstract_text = None
    if abstract_text is None and prev_dc:
        # a new version keeps the abstract and keywords unless they are given
        abstract_text = next((x["description"] for x in prev_dc.get("descriptions", [])
                              if x["descriptionType"] == "Abstract"), None)
    datacite = {
        "titles": [{"title": args.title}],
        "creators": [creator(a) for a in args.author],
        "publisher": {"name": ARCHIVE["name"]},
        "publicationYear": int((issued or args.created)[:4]),
        "types": {"resourceTypeGeneral": args.type},
        "version": str(doc_version),
        "url": landing_url(label),
        "dates": [],
        "language": args.language or "en",
        "formats": formats,
        "rightsList": rights_list(args.rights, prev_dc),
    }
    if args.keyword:
        datacite["subjects"] = [{"subject": k} for k in args.keyword]
    elif prev_dc and prev_dc.get("subjects"):
        datacite["subjects"] = prev_dc["subjects"]
    if issued:
        set_date(datacite, "Issued", issued)
    if available:
        set_date(datacite, "Available", available, args.date_info)
    else:
        set_date(datacite, "Created", args.created, args.date_info)
    if abstract_text:
        datacite["descriptions"] = [{"description": abstract_text, "descriptionType": "Abstract"}]
    related = related_from_args(args.related)
    if related:
        datacite["relatedIdentifiers"] = related
    if draft:
        datacite.pop("url")        # a draft has no landing page
    obj = {
        "format": OBJ_FORMAT,
        "specification": SPEC,
        "kind": "document",
        "name": None,
        "owner": owner,
        "documentVersion": doc_version,
    }
    if source is not None:
        obj.update(mainSource=main, sourceFormat=fmt)
    else:
        obj["sourcesMissing"] = {"text": args.no_source}
    obj["renditions"] = [{"path": "paper.pdf", "mediaType": "application/pdf"}]
    if texmacs:
        obj["toolchain"] = [{"name": "TeXmacs", "version": TEXMACS_VERSION}]
    elif args.toolchain:
        obj["toolchain"] = [{"name": n, "version": v} for n, _, v in (t.partition("=") for t in args.toolchain)]
    obj["status"] = "active"
    if args.changes:
        obj["changes"] = {"text": args.changes}
    if getattr(args, "agreement", None):
        obj["agreement"] = {"by": [c["name"] for c in datacite["creators"]],
                            "date": available or args.created or TODAY, "method": args.agreement}
    if args.stage:
        obj["stage"] = {"scheme": "NISO-JAV", "value": args.stage}
    if getattr(args, "licence_file", None):
        if args.licence_file not in files:
            sys.exit(f"--licence-file {args.licence_file} is not a file of the deposit "
                     f"(give it as the main source or with --extra-source; files: {', '.join(sorted(files))})")
        obj["licence"] = {"path": args.licence_file, "mediaType": {
            ".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain", ".html": "text/html",
        }.get(Path(args.licence_file).suffix.lower(), "text/plain")}
    if draft:
        del obj["name"], obj["owner"]
    elif obj_id is None:
        genesis, obj_id = seal("document", owner)
        files[GENESIS] = genesis
    else:
        files[GENESIS] = read_logical(d, inv, GENESIS)
    if not draft:
        obj["name"] = obj_id.split(":")[1]
    if prev_obj and prev_obj.get("parent"):
        obj["parent"] = prev_obj["parent"]
        for lp in evidence_paths(inv):
            files[lp] = read_logical(d, inv, lp)
    carry_forward(prev_obj, obj, inv, next_object_version(inv), args.after, obj_id)
    for lp, f in carried_files(obj_id, inv).items():
        files.setdefault(lp, f)
    files["datacite.json"] = json_bytes(datacite)
    inv = add_version(obj_id, files, obj, args.message or f"Deposit: document version {doc_version}",
                      acknowledged=getattr(args, "i_know", False))
    shutil.rmtree(tmp, ignore_errors=True)
    if not draft:
        LABELS[label] = obj_id
    write_discovery()
    print(f"{label}: {inv['head']} (document version {doc_version}) {obj_id}")


def documents():
    """(obj_id, dir, inventory, latest signed version, current object version, its
    object.json and datacite.json) of every document of the archive's owners."""
    out, mine = [], set(archive_owners())
    for obj_id, d, inv in objects():
        if inv is None or obj_id is None or obj_id.startswith("sheaf:draft:"):
            continue
        head = read_json(d, inv, OBJ)
        if head.get("kind") != "document" or head.get("owner") not in mine:
            continue
        signed = latest_signed(d, inv)
        if signed is None:
            print(f"warning: {label_of(obj_id) or obj_id} has no signed version (section 7.3): left out",
                  file=sys.stderr)
            continue
        cur = current_version(d, inv, signed)
        out.append((obj_id, d, inv, signed, cur, read_json(d, inv, OBJ, cur),
                    read_json(d, inv, "datacite.json", cur)))
    return out


RIGHTS = {
    "cc-by-4.0": {"rights": "Creative Commons Attribution 4.0 International",
                  "rightsUri": "https://creativecommons.org/licenses/by/4.0/",
                  "rightsIdentifier": "cc-by-4.0", "rightsIdentifierScheme": "SPDX"},
    "cc0-1.0": {"rights": "Creative Commons Zero v1.0 Universal",
                "rightsUri": "https://creativecommons.org/publicdomain/zero/1.0/",
                "rightsIdentifier": "cc0-1.0", "rightsIdentifierScheme": "SPDX"},
    "cc-by-sa-4.0": {"rights": "Creative Commons Attribution Share Alike 4.0 International",
                     "rightsUri": "https://creativecommons.org/licenses/by-sa/4.0/",
                     "rightsIdentifier": "cc-by-sa-4.0", "rightsIdentifierScheme": "SPDX"},
    "gpl-3.0-only": {"rights": "GNU General Public License v3.0 only",
                     "rightsUri": "https://www.gnu.org/licenses/gpl-3.0.html",
                     "rightsIdentifier": "gpl-3.0-only", "rightsIdentifierScheme": "SPDX"},
    "gpl-3.0-or-later": {"rights": "GNU General Public License v3.0 or later",
                         "rightsUri": "https://www.gnu.org/licenses/gpl-3.0.html",
                         "rightsIdentifier": "gpl-3.0-or-later", "rightsIdentifierScheme": "SPDX"},
}


def description_version(label, change, message, add_files=None, acknowledged=False):
    """Add a description-only version of the document LABEL: the files of the
    head (and ADD_FILES, {logical path: file}, such as the file of a notice),
    with datacite.json and object.json changed by CHANGE(dc, obj). The
    document version stays; datacite.json gets the Updated date."""
    obj_id = resolve(label)
    d = obj_dir(obj_id)
    inv = load_inventory(d)
    if inv is None:
        sys.exit(f"no object {label}")
    state = {p: dg for dg, ps in inv["versions"][inv["head"]]["state"].items() for p in ps}
    dc = read_json(d, inv, "datacite.json")
    prev = read_json(d, inv, OBJ)
    if prev["kind"] != "document":
        sys.exit(f"{label} is not a document")
    obj = json.loads(json.dumps(prev))
    change(dc, obj)
    set_date(dc, "Updated", TODAY)
    carry_forward(prev, obj, inv, next_object_version(inv))
    files = {p: d / inv["manifest"][dg][0] for p, dg in state.items() if p not in ("datacite.json", OBJ)}
    for lp, f in (add_files or {}).items():
        if lp in files:
            sys.exit(f"{label} has a file {lp} already")
        files[lp] = Path(f)
    files["datacite.json"] = json_bytes(dc)
    inv = add_version(obj_id, files, obj, message() if callable(message) else message,
                      acknowledged=acknowledged)
    write_discovery()
    return inv


def ack(args):
    return bool(getattr(args, "i_know", False))


def note_from(text, file, folder):
    """A note (section 4.3): a text, a file of the content, or both."""
    note, add = {}, {}
    if text:
        note["text"] = text
    if file:
        f = Path(file)
        lp = f"{folder}/{f.name}"
        note["path"] = lp
        note["mediaType"] = {".pdf": "application/pdf", ".md": "text/markdown", ".txt": "text/plain",
                             ".html": "text/html"}.get(f.suffix.lower(), "application/octet-stream")
        add[lp] = f
    if not note:
        sys.exit("a note needs a text, a file, or both")
    return note, add


def notice(args):
    """A notice about a document version (section 4.2), by a description-only
    version: kept, unchanged, in every later object version."""
    d = obj_dir(resolve(args.id))
    inv = load_inventory(d)
    if inv is None:
        sys.exit(f"no object {args.id}")
    numbers = {doc_version_of(d, inv, v) for v in inv["versions"]}
    if args.about not in numbers:
        sys.exit(f"{args.id} has no document version {args.about}")
    note, add = note_from(args.text, args.file, "notices")
    note.update(documentVersion=args.about, date=args.date or TODAY)

    def change(dc, obj):
        obj["notices"] = obj.get("notices", []) + [note]
    inv = description_version(args.id, change, args.message or
                              f"Notice about document version {args.about} (description-only version)", add, ack(args))
    print(f"{args.id}: {inv['head']} (notice about version {args.about})")


def withdraw(args):
    """Withdraw a document (section 13.1): a description-only version with the
    status withdrawn, the reason, and the Withdrawn date in datacite.json. The
    content stays."""
    reason, add = note_from(args.reason, args.file, "withdrawal")
    date = args.date or TODAY

    def change(dc, obj):
        if obj.get("status") == "withdrawn":
            sys.exit(f"{args.id} is withdrawn already")
        obj["status"] = "withdrawn"
        obj["withdrawal"] = {"date": date, "reason": reason}
        set_date(dc, "Withdrawn", date)
    inv = description_version(args.id, change, args.message or "Withdrawal (description-only version)", add, ack(args))
    print(f"{args.id}: {inv['head']} (withdrawn)")


def complete(args):
    """Add the sources of a document version recorded without them
    (sourcesMissing, section 4.2): a new object version holding the files of
    that document version and the sources; its number stays."""
    obj_id = resolve(args.id)
    d = obj_dir(obj_id)
    inv = load_inventory(d)
    if inv is None:
        sys.exit(f"no object {args.id}")
    last = None
    for v in inv["versions"]:
        if doc_version_of(d, inv, v) == args.version:
            last = v
    if last is None:
        sys.exit(f"{args.id} has no document version {args.version}")
    obj = read_json(d, inv, OBJ, last)
    if not obj.get("sourcesMissing"):
        sys.exit(f"{args.id}: document version {args.version} has its sources already")
    head = read_json(d, inv, OBJ)
    dc = read_json(d, inv, "datacite.json", last)
    state = {p: dg for dg, ps in inv["versions"][last]["state"].items() for p in ps}
    files = {p: d / inv["manifest"][dg][0] for p, dg in state.items() if p not in ("datacite.json", OBJ)}
    source = Path(args.source)
    main = source.name
    for lp, f in [(main, source)] + [(x.partition("=")[2] or Path(x.partition("=")[0]).name,
                                      Path(x.partition("=")[0])) for x in args.extra_source or []]:
        if lp in files:
            sys.exit(f"{args.id}: version {args.version} has a file {lp} already (completing only adds files)")
        if not f.is_file():
            sys.exit(f"no file {f}")
        files[lp] = f
    obj.pop("sourcesMissing")
    obj["mainSource"] = main
    obj["sourceFormat"] = args.source_format or SOURCE_FORMATS.get(source.suffix.lower(), "application/octet-stream")
    obj.pop("notices", None)
    obj.pop("history", None)
    carry_forward(head, obj, inv, next_object_version(inv))
    obj.pop("withdrawal", None)
    obj["status"] = head["status"]           # the state of the object is the head's
    if head.get("withdrawal"):
        obj["withdrawal"] = head["withdrawal"]
        set_date(dc, "Withdrawn", head["withdrawal"]["date"])
        if head["withdrawal"]["reason"].get("path"):
            lp = head["withdrawal"]["reason"]["path"]
            files.setdefault(lp, read_logical(d, inv, lp))
    set_date(dc, "Updated", TODAY)
    fmt = obj["sourceFormat"]
    if fmt not in dc.get("formats", []):
        dc["formats"] = [fmt] + dc.get("formats", [])
    files["datacite.json"] = json_bytes(dc)
    for lp, f in carried_files(obj_id, inv).items():     # notice files are kept
        files.setdefault(lp, f)
    inv = add_version(obj_id, files, obj, args.message or
                      f"Sources of document version {args.version} added (sourcesMissing completed)",
                      acknowledged=getattr(args, "i_know", False))
    write_discovery()
    print(f"{args.id}: {inv['head']} (sources of version {args.version})")


def relate(args):
    """Link a document to the same work elsewhere (arXiv identifier or DOI)."""
    kind, _, value = args.to.partition(":")
    if kind not in ("arxiv", "doi") or not value:
        sys.exit("--to must be arxiv:ID or doi:DOI")
    rel = {"relatedIdentifier": f"arXiv:{value}" if kind == "arxiv" else value,
           "relatedIdentifierType": "arXiv" if kind == "arxiv" else "DOI",
           "relationType": args.relation}

    def change(dc, obj):
        rels = dc.setdefault("relatedIdentifiers", [])
        if any(r["relatedIdentifier"] == rel["relatedIdentifier"] for r in rels):
            sys.exit(f"{args.id} already relates to {rel['relatedIdentifier']}")
        rels.append(rel)
        if args.issued:
            set_date(dc, "Issued", args.issued)
    inv = description_version(args.id, change, args.message or
                              f"Related: {args.relation} {rel['relatedIdentifier']} (description-only version)", None, ack(args))
    print(f"{args.id}: {inv['head']} ({args.relation} {rel['relatedIdentifier']})")


def relicense(args):
    """A description-only version with a new licence in datacite.json and the
    authors' agreement in object.json."""
    new = rights_list(check_rights(args.rights))[0]

    def change(dc, obj):
        if dc.get("rightsList") == [new]:
            sys.exit(f"{args.id} already has {args.rights}")
        dc["rightsList"] = [new]
        obj["agreement"] = {"by": [c["name"] for c in dc["creators"]],
                            "date": args.date or TODAY, "method": args.method}
    inv = description_version(args.id, change, args.message or
                              f"Licence: {new['rights']} (description-only version; content unchanged)", None, ack(args))
    print(f"{args.id}: {inv['head']} ({new['rights']})")


def describe(args):
    """Correct the description of a document (title, abstract, keywords,
    authors) by a description-only version (section 4.2)."""
    if args.abstract is not None and args.abstract_file:
        sys.exit("describe: give --abstract or --abstract-file, not both")
    abstract = (Path(args.abstract_file).read_text(encoding="utf-8") if args.abstract_file
                else args.abstract)
    abstract = abstract.strip() if abstract is not None else None
    if args.title is not None and not args.title.strip() or abstract == "":
        sys.exit("describe: a title or an abstract cannot be empty")
    changed = []

    def change(dc, obj):
        if args.title is not None and args.title.strip() != dc["titles"][0]["title"]:
            dc["titles"][0]["title"] = args.title.strip()
            changed.append("title")
        if abstract is not None:
            descs = dc.setdefault("descriptions", [])
            old = next((x for x in descs if x["descriptionType"] == "Abstract"), None)
            if old is None:
                descs.insert(0, {"description": abstract, "descriptionType": "Abstract"})
                changed.append("abstract")
            elif old["description"] != abstract:
                old["description"] = abstract
                changed.append("abstract")
        if args.keyword:
            subjects = dc.get("subjects", [])
            if [x["subject"] for x in subjects if not x.get("subjectScheme")] != args.keyword:
                dc["subjects"] = [{"subject": k} for k in args.keyword] + \
                    [x for x in subjects if x.get("subjectScheme")]
                changed.append("keywords")
        if args.author:
            creators = [creator(a) for a in args.author]
            if creators != dc["creators"]:
                dc["creators"] = creators
                changed.append("authors")
        if not changed:
            sys.exit(f"{args.id}: nothing to change in the description")
    inv = description_version(args.id, change, args.message or (
        lambda: f"Description corrected: {', '.join(changed)} (description-only version)"), None, ack(args))
    print(f"{args.id}: {inv['head']} ({', '.join(changed)} corrected)")


ORDER = "issued-desc"


def member_pins(m):
    """[(object version, inventory digest, document version or None)] of a
    member: its version in a catalogue, each revision in a
    selection (section 8.4)."""
    if "revisions" in m:
        return [(r.get("version"), r.get("inventorySha512"), r.get("documentVersion"))
                for r in m["revisions"]]
    return [(m.get("version"), m.get("inventorySha512"), None)]


def presented_version(m, obj_dir, inv):
    """The object version presentations show for member M of an object held
    in OBJ_DIR (section 8.3)."""
    if m.get("revisions"):
        return m["revisions"][-1]["version"]
    return current_version(obj_dir, inv, m["version"])


def member_order(members):
    """Section 8.2: by Issued, then Available (newest first for issued-desc),
    members with neither last, ties broken by name and then owner."""
    def key(m):
        c = m.get("cite", {})
        return (c.get("issued") or "", c.get("available") or "")
    line = lambda m: (m.get("name", ""), m.get("owner", ""))
    dated = sorted((m for m in members if any(key(m))), key=line)
    dated.sort(key=key, reverse=(ORDER == "issued-desc"))
    return dated + sorted((m for m in members if not any(key(m))), key=line)


def collect(args):
    """A new version of the main catalogue when a document has a new signed version;
    members pin the latest signed version of their line and follow it (section 8.3)."""
    init_storage_root()
    label = ARCHIVE["mainCollection"]
    coll_id = LABELS.get(label)
    coll_dir = obj_dir(coll_id) if coll_id else None
    cinv = load_inventory(coll_dir) if coll_dir else None
    if cinv and read_json(coll_dir, cinv, "members.json").get("order") == "manual":
        print(f"{label} is curated (order manual): use osheaf collection add|sync|update")
        return
    curated = cinv is None and bool(getattr(args, "curated", False))
    order = "manual" if curated else ORDER
    members = []
    for obj_id, d, inv, signed, cur, obj, dc in documents():
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "name": obj["name"], "owner": obj["owner"], "at": [ARCHIVE["baseUrl"]],
             "version": signed, "inventorySha512": digest(d / signed / "inventory.json"),
             "follow": "latest", "cite": cite}
        # the Available date only orders, it is not part of the cached citation
        m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = [] if curated else member_order(members)
    for m in members:
        m["cite"].pop("available", None)
    version, issued = 1, TODAY
    if cinv:
        old = read_json(coll_dir, cinv, "members.json")
        if old["members"] == members and old.get("type") == "catalogue":
            print(f"{label}: unchanged ({cinv['head']})")
            return
        version = read_json(coll_dir, cinv, OBJ)["documentVersion"] + 1
        issued = date_of(read_json(coll_dir, cinv, "datacite.json"), "Issued") or TODAY
    owner = ARCHIVE["owner"]
    if coll_id is None:
        genesis, coll_id = seal("collection", owner)
    else:
        genesis = read_logical(coll_dir, cinv, GENESIS).read_bytes()
    cur = ARCHIVE["curator"]
    creator_ = {"name": cur["name"], "nameType": "Personal", "familyName": cur["familyName"]}
    if cur.get("givenName"):
        creator_["givenName"] = cur["givenName"]
    if cur.get("affiliation"):
        creator_["affiliation"] = [{"name": cur["affiliation"]}]
    files = {
        "members.json": json_bytes({"format": "opensheaf-collection/0.2", "type": "catalogue",
                                    "order": order, "members": members}),
        "datacite.json": json_bytes({
            "titles": [{"title": ARCHIVE["name"]}],
            "creators": [creator_],
            "publisher": {"name": ARCHIVE["name"]},
            "publicationYear": int(issued[:4]),
            "types": {"resourceTypeGeneral": "Collection"},
            "version": str(version),
            "url": ARCHIVE["baseUrl"],
            "dates": [{"date": issued, "dateType": "Issued"}, {"date": TODAY, "dateType": "Available"}],
            "descriptions": [{"description": "The documents deposited in this archive, newest first.",
                              "descriptionType": "Abstract"}],
            "rightsList": [dict(RIGHTS["cc0-1.0"])],
        }),
        GENESIS: genesis,
    }
    obj = {"format": OBJ_FORMAT, "specification": SPEC, "kind": "collection",
           "name": coll_id.split(":")[1], "owner": owner, "documentVersion": version, "status": "active"}
    LABELS[label] = coll_id
    inv = add_version(coll_id, files, obj, f"Collection version {version}: {len(members)} documents",
                      acknowledged=bool(getattr(args, "i_know", False)))
    write_discovery()
    print(f"Done: the main catalogue {label} is at {inv['head']}, with "
          f"{plural(len(members), 'member') if members else 'no members'}.")


def line_status(d, inv, head):
    """The status of the object in D (section 13.1): that of its latest signed version, or
    else of its head; always active for a key log."""
    if head.get("kind") == "owner":
        return "active"
    signed = latest_signed(d, inv)
    return (read_json(d, inv, OBJ, signed) if signed else head).get("status", "active")


def discovery():
    objs, drafts, used = [], [], set()
    for obj_id, d, inv in objects():
        if inv is None or obj_id is None:
            continue
        head = read_json(d, inv, OBJ) or {}
        used.update(head.get("extensions") or {})
        if obj_id.startswith("sheaf:draft:"):
            drafts.append({"id": obj_id, "kind": head.get("kind"), "head": inv["head"]})
            continue
        if head.get("kind") == "owner":
            try:
                used.update(owners.load_key_log(d).extensions() or {})
            except owners.OwnerError:
                pass
        status = line_status(d, inv, head)
        entry = {"id": obj_id, "kind": head.get("kind"), "name": head.get("name"),
                 "owner": head.get("owner"), "head": inv["head"],
                 "inventorySha512": owners.sidecar_digest((d / "inventory.json.sha512").read_bytes()),
                 "status": status}
        if label_of(obj_id):
            entry["label"] = label_of(obj_id)
        objs.append(entry)
    doc = {"format": "opensheaf-archive/0.2", "specification": SPEC, "name": ARCHIVE["name"],
           "contact": ARCHIVE["contact"], "storageRoot": "ocfl/", "storageLayout": LAYOUT}
    if ARCHIVE["mainCollection"] in LABELS:
        doc["mainCollection"] = LABELS[ARCHIVE["mainCollection"]]
    doc.update(profiles=ARCHIVE["profiles"], extensions=sorted(used), owners=archive_owners(),
               indexes=dict(INDEXES), objects=objs)
    if drafts:
        doc["drafts"] = drafts
    if TOMBSTONES:
        doc["tombstones"] = TOMBSTONES
    return doc


def write_discovery():
    """Write the discovery document opensheaf.json and the indexes from the storage root."""
    write_indexes()
    write_json(ROOT / "opensheaf.json", discovery())


INDEXES = {"names": 2, "owners": 2, "sha512": 2}
INDEX_FORMAT = "opensheaf-index/0.2"
INDEX_KEY = {"names": "name", "owners": "owner", "sha512": "inventorySha512"}


def index_entries():
    """{index: [entries]} of the storage root and of its tombstones (section 12.5)."""
    out = {"names": [], "owners": [], "sha512": []}
    lines = {}
    for obj_id, d, inv in objects():
        if inv is None or obj_id is None or obj_id.startswith("sheaf:draft:"):
            continue
        head = read_json(d, inv, OBJ) or {}
        gpath = read_logical(d, inv, GENESIS)
        if gpath is None or len(obj_id.split(":")) != 3:
            continue
        genesis = gpath.read_bytes()
        try:
            rec = names.read_genesis(genesis)
        except ValueError:
            continue
        _, nm, owner = obj_id.split(":")
        status = line_status(d, inv, head)
        entry = {"name": nm, "owner": owner, "id": obj_id, "status": status,
                 "originator": owner if rec["kind"] == "owner" else rec.get("originator"),
                 "genesis": genesis.decode("utf-8")}
        if label_of(obj_id):
            entry["label"] = label_of(obj_id)
        out["names"].append(entry)
        lines.setdefault(owner, []).append(nm)
        for n in range(1, int(inv["head"][1:]) + 1):
            sc = d / f"v{n}" / "inventory.json.sha512"
            if sc.exists():
                out["sha512"].append({"inventorySha512": owners.sidecar_digest(sc.read_bytes()),
                                      "id": obj_id, "version": f"v{n}", "status": status})
        if head.get("kind") == "owner":
            try:
                log = owners.load_key_log(d)
            except owners.OwnerError:
                continue
            for v in log.versions:
                for c in (v.carried if v.fork_record else []):
                    out["sha512"].append({"inventorySha512": c.digest, "id": obj_id,
                                          "version": f"v{c.number}", "status": "active"})
    out["owners"] = [{"owner": o, "names": sorted(ns)} for o, ns in sorted(lines.items())]
    out["names"] += removed_entries("names")
    out["sha512"] += removed_entries("sha512")
    return out


def removed_entries(index):
    """The entries of the lines taken down, kept from the index files of INDEX with the status
    removed, and the tombstones' own entries when the files lack them (sections 12.5 and 13.3)."""
    gone = {t["id"]: t for t in TOMBSTONES}
    kept = [dict(e, status="removed") for e in read_index(index) if e.get("id") in gone]
    for t in gone.values():
        if index == "names" and not any(e["id"] == t["id"] for e in kept):
            kept.append({"name": t["name"], "owner": t["owner"], "id": t["id"], "status": "removed"})
        if index == "sha512" and not any(e["id"] == t["id"] and e["version"] == t["lastVersion"]
                                         for e in kept):
            kept.append({"inventorySha512": t["inventorySha512"], "id": t["id"],
                         "version": t["lastVersion"], "status": "removed"})
    return kept


def read_index(index):
    """Every entry of the files of the index INDEX held next to the discovery document."""
    out = []
    for p in sorted((ROOT / index).glob("*.json")) if (ROOT / index).is_dir() else []:
        try:
            out += json.loads(p.read_text(encoding="utf-8")).get("entries", [])
        except (ValueError, AttributeError):
            pass
    return out


def index_files(entries):
    """{index: {prefix: file contents}} of ENTRIES, by the prefixes INDEXES declares."""
    out = {}
    for index, es in entries.items():
        files = out.setdefault(index, {})
        key = INDEX_KEY[index]
        for e in sorted(es, key=lambda e: (e[key], e.get("id", ""), int(e.get("version", "v0")[1:]))):
            p = e[key][:INDEXES[index]]
            files.setdefault(p, {"format": INDEX_FORMAT, "index": index, "entries": []})["entries"].append(e)
    return out


def write_indexes():
    """Write the files of the three indexes, replacing those of the folders."""
    files = index_files(index_entries())
    for index in INDEXES:
        folder = ROOT / index
        want = files.get(index, {})
        for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            if p.stem not in want:
                p.unlink()
        for prefix, data in want.items():
            write_json(folder / f"{prefix}.json", data)


TEX_ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303",
               "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "=": "\u0304"}
TEX_LETTERS = {"o": "\u00f8", "O": "\u00d8", "ss": "ss", "aa": "\u00e5", "AA": "\u00c5",
               "l": "\u0142", "L": "\u0141", "ae": "\u00e6", "oe": "\u0153", "i": "i"}


def tex_text(s):
    """Text with TeX accents (It\\^o, H{\\o}egh) as Unicode text."""
    acc = lambda m: unicodedata.normalize("NFC", m.group(2) + TEX_ACCENTS[m.group(1)])
    s = re.sub(r"\{?\\([\'`\"^~=])\s*\{?([A-Za-z])\}?\}?", acc, s)
    s = re.sub(r"\{?\\([cvuH])\s*\{([A-Za-z])\}\}?", acc, s)
    s = re.sub(r"\{\\(o|O|ss|aa|AA|l|L|ae|oe)\}|\\(o|O|ss|aa|AA|l|L|ae|oe)\b",
               lambda m: TEX_LETTERS[m.group(1) or m.group(2)], s)
    return s


def tm_escape(s):
    """Plain text as a TeXmacs string. Accented Latin letters are written as
    their Cork bytes (the same as Latin-1 from 0xC0, except 0xD7, 0xDF, 0xF7
    and 0xFF); other characters as the symbol \\<#17A\\> (a bare <#17A> is
    read as raw data)."""
    esc = {"\\": "\\\\", "<": "<less>", ">": "<gtr>", "|": "\\|"}
    s = re.sub(r"[\\<>|]", lambda m: esc[m.group(0)], s)
    out = []
    for c in unicodedata.normalize("NFC", s):
        o = ord(c)
        if o < 128 or (0xC0 <= o <= 0xFF and o not in (0xD7, 0xDF, 0xF7, 0xFF)):
            out.append(c)
        elif c == "\u00df":
            out.append("ss")
        else:
            out.append(f"\\<#{o:X}\\>")
    return "".join(out)


def tm_with_math(s):
    """TeXmacs markup for text with LaTeX math ($...$): the math is kept as
    LaTeX, set in TeXmacs as typewriter text and in HTML as \\(...\\) for
    MathJax."""
    out = []
    for i, part in enumerate(re.split(r"(?<!\\)\$", s)):
        if i % 2 == 0 or not part:
            out.append(tm_escape(tex_text(part)))
        else:
            out.append(f"<specific|texmacs|<verbatim|{tm_escape(part)}>>"
                       f"<specific|html*|\\\\({tm_escape(part)}\\\\)>")
    return "".join(out)


def fmt_date(iso):
    """'2026-06-03' -> '3 June 2026' (approximate dates: '2019-03' -> 'March 2019')."""
    parts = iso.split("/")[0].split("-")
    if len(parts) == 3:
        d = datetime.date.fromisoformat("-".join(parts))
        return f"{d.day} {d.strftime('%B %Y')}"
    if len(parts) == 2:
        return datetime.date(int(parts[0]), int(parts[1]), 1).strftime("%B %Y")
    return parts[0]


def version_line(obj, dc, inv, ver):
    """'version 3 (arXiv v4), 27 November 2025'; a version not public at the
    time shows when it was written."""
    label = ""
    for e in obj.get("external", []):
        if e.get("role") == "source" and e.get("label"):
            label = f" ({e['service']} {e['label']})"
    line = f"version {obj['documentVersion']}{label}"
    if date_of(dc, "Available"):
        line += f", {fmt_date(date_of(dc, 'Available'))}"
    elif date_of(dc, "Created"):
        line += f", written {fmt_date(date_of(dc, 'Created'))}, not public at the time"
    else:
        line += f", deposited {fmt_date(inv['versions'][ver]['created'][:10])}"
    return line


def arxiv_id(obj, dc):
    """The arXiv identifier of a version, without version: '2607.08385'."""
    for e in obj.get("external", []):
        if e.get("service") == "arXiv" and "/abs/" in e.get("record", ""):
            return re.sub(r"v\d+$", "", e["record"].rsplit("/abs/", 1)[1])
    for r in dc.get("relatedIdentifiers", []):
        if r["relatedIdentifierType"] == "arXiv":
            return re.sub(r"v\d+$", "", r["relatedIdentifier"].split(":", 1)[1])
    return None


def changes_note(obj):
    """'arXiv comments: 61 pages', 'changes: typos corrected', or None."""
    text = obj.get("changes", {}).get("text")
    if not text:
        return None
    arxiv = any(e.get("role") == "source" and e.get("service") == "arXiv" for e in obj.get("external", []))
    return f"{'arXiv comments' if arxiv else 'changes'}: {text}"


def abstract_block(paras):
    # a fold in TeXmacs, a details element in HTML (the exporter has no
    # rendering of folded text)
    body = "\n\n".join(f"        {p}" for p in paras)
    return ("    <specific|texmacs|<\\folded>\n      Abstract\n    <|folded>\n"
            f"{body}\n    </folded>>"
            "<specific|html*|<html-tag|details|<html-tag|summary|Abstract>"
            f"<\\html-div-class|paper-abstract>\n{body}\n    </html-div-class>>>\n\n")


def index_entry(member):
    obj_id = names.object_id(member["name"], member["owner"])
    d, at, label = obj_dir(obj_id), path_of(obj_id), page_address(obj_id)
    inv = load_inventory(d)
    ver = presented_version(member, d, inv)
    pin_ver, pin = member_pins(member)[-1][:2]
    obj = read_json(d, inv, OBJ, ver)
    dc = read_json(d, inv, "datacite.json", ver)
    pdf = content_path(inv, ver, pdf_of(obj)) if pdf_of(obj) else None
    src = f"ocfl/{at}/" + content_path(inv, ver, obj["mainSource"]) if obj.get("mainSource") else None
    html = f"site/{label}/{label}.html"
    texmacs = obj.get("sourceFormat") == "application/x-texmacs"
    title = tm_with_math(dc["titles"][0]["title"])
    authors = tm_escape(authors_of(dc))
    if not authors.endswith("."):
        authors += "."
    links = [f"<hlink|PDF|ocfl/{at}/{pdf}>"] if pdf else []
    if texmacs:
        # links to .tm files become .html links in the HTML export; the source
        # is linked once for TeXmacs and once (.texmacs, exported as .tm) for HTML
        links = [f"<hlink|HTML|{html}>"] + links + [
            f"<specific|texmacs|<hlink|TeXmacs source|{src}>><specific|html*|<hlink|TeXmacs"
            f" source|{src[:-3]}.texmacs>>"]
    elif src:
        links.append(f"<hlink|LaTeX source|{src}>")
    arxiv = arxiv_id(obj, dc)
    if arxiv:
        links.append(f"<hlink|arXiv:{arxiv}|https://arxiv.org/abs/{arxiv}>")
    paras = []
    for desc in dc.get("descriptions", []):
        if desc["descriptionType"] == "Abstract":
            paras = [tm_with_math(" ".join(p.split())) for p in desc["description"].split("\n\n")]
    abstract = abstract_block(paras) if paras else ""
    first = date_of(dc, "Issued")
    when = (f"first issued {fmt_date(first)}; " if first else "") + version_line(obj, dc, inv, ver)
    if changes_note(obj):
        when += f"<next-line>{tm_escape(changes_note(obj))}"
    sep = " \\<cdot\\> "
    head = f"<hlink|{title}|paper/{label}/>"
    return f"""  <\\notes-news-item>
    <with|font-series|bold|{head}>

    By {authors}

    {sep.join(links)}

{abstract}    <with|font-size|0.84|par-mode|left|{when}<next-line>pin:
    <hlink|<verbatim|{pin[:32]}...>|ocfl/{at}/{pin_ver}/inventory.json>>
  </notes-news-item>"""


def index(args):
    write_discovery()
    if INDEX.get("html") or INDEX.get("template"):
        readable_index(args)
        return
    print("opensheaf.json and the indexes written (no readable index configured)")


def main_members():
    """The members of the latest signed version of the main catalogue, or None."""
    main_id = LABELS.get(ARCHIVE["mainCollection"])
    d = obj_dir(main_id) if main_id else None
    inv = load_inventory(d) if d else None
    if inv is None:
        return None
    ver = latest_signed(d, inv)
    if ver is None:
        print(f"warning: the main catalogue has no signed version (section 7.3): nothing is presented",
              file=sys.stderr)
        return None
    return read_json(d, inv, "members.json", ver)["members"]


def readable_index(args):
    """The website, or the TeXmacs index with the landing pages of the website."""
    from . import html
    members = main_members()
    if members is None:
        return
    if INDEX.get("html"):
        featured = INDEX["html"].get("featured") if isinstance(INDEX["html"], dict) else None
        fid = None
        if featured:
            fid = LABELS.get(featured)
            if fid is None:
                sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not a label of this "
                         "archive")
            fd = obj_dir(fid)
            if (read_json(fd, load_inventory(fd), OBJ) or {}).get("kind") != "collection":
                sys.exit(f"osheaf.json: index.html.featured names {featured}, which is not a collection")
        pages = html.render(members, featured=fid)
        print(f"Done: opensheaf.json, index.html, {plural(pages, 'landing page')} and sitemap.xml written.")
        return
    template = (ROOT / INDEX["template"]).read_text(encoding="latin-1")
    line = "  <paper-index>\n"
    if template.count(line) != 1:
        sys.exit(f"{INDEX['template']} must contain one paragraph <paper-index>")
    pages = html.render(members, home=False)
    here = [m for m in members if html.held(m)]
    if len(here) < len(members):
        print(f"Warning: {plural(len(members) - len(here), 'member')} held in other archives "
              f"{'is' if len(members) - len(here) == 1 else 'are'} left out of index.tm (the website shows "
              "them).", file=sys.stderr)
    entries = "\n\n".join(index_entry(m) for m in here)
    with open(ROOT / "index.tm", "w", encoding="latin-1", newline="") as f:
        f.write(template.replace(line, entries + "\n"))
    (ROOT / ".texmacs-noconvert").touch()
    if not getattr(args, "no_html", False):
        scratch = Path(tempfile.mkdtemp())
        run_texmacs(export_calls(ROOT / "index.tm", pdf=scratch / "index.pdf",
                                 html=ROOT / "index.html"))
        shutil.rmtree(scratch, ignore_errors=True)
    print("Done: opensheaf.json, index.tm" + ("" if getattr(args, "no_html", False) else ", index.html")
          + f", {plural(pages, 'landing page')} and sitemap.xml written.")


def present():
    """Regenerate the presentation files after a change (appendix A.3), if any are configured."""
    if not (INDEX.get("html") or INDEX.get("template")) or OLD:
        return
    from . import html
    try:
        members = main_members()
        if members is None:
            return
        if INDEX.get("html"):
            readable_index(argparse_namespace(no_html=True))
        else:
            html.render(members, home=False)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - the change is made; index writes the pages again
        print(f"warning: the website was not regenerated ({e}); run osheaf index", file=sys.stderr)


class Findings(list):
    """The findings of a verifier (section 14.1), as dicts with severity, place and message."""

    def add(self, severity, place, message):
        self.append({"severity": severity, "place": place, "message": message})

    def error(self, place, message):
        self.add("error", place, message)

    def warning(self, place, message):
        self.add("warning", place, message)

    def result(self, place, message):
        self.add("result", place, message)

    def count(self, severity):
        return sum(1 for x in self if x["severity"] == severity)


def where(obj_id):
    """The place of an object in findings: its label, its owner for a key log, or its identifier."""
    parts = (obj_id or "").split(":")
    if len(parts) == 3 and parts[1] == parts[2]:
        return f"owner {parts[1]}"
    return label_of(obj_id) or obj_id or "?"


def schema_checker(f):
    """A function (place, data, schema name, severity) checking DATA against a schema of 0.2."""
    try:
        import jsonschema
        formats = jsonschema.FormatChecker()
    except ImportError:
        f.warning("archive", "the JSON Schemas are not checked: jsonschema is not installed"
                  " (pip install 'opensheaf[validate]')")
        return lambda *a, **k: None
    if "uri" not in formats.checkers:
        f.warning("archive", "the formats uri and uri-reference are not checked: rfc3986-validator is not"
                  " installed (pip install 'opensheaf[validate]')")
    validators = {}

    def check(place, data, name, severity="error"):
        if name not in validators:
            schema = json.loads((SCHEMAS / f"opensheaf-{name}-0.2.schema.json").read_text(encoding="utf-8"))
            validators[name] = jsonschema.Draft202012Validator(schema, format_checker=formats)
        for e in validators[name].iter_errors(data):
            f.add(severity, place, e.message)
    return check


def document_version_errors(obj_id, d, inv):
    """Section 4.2: numbering without gaps, the same files for the same
    document version (a version with sourcesMissing may be completed by adding
    files), the history, and notices kept unchanged."""
    errors = []
    seen, files_of, missing_of, highest, first = {}, {}, {}, 0, 1
    had_history, notices = False, []
    for ver, vinfo in inv["versions"].items():
        obj = read_json(d, inv, OBJ, ver)
        if obj is None or obj.get("kind") != "document":
            return errors
        n = obj["documentVersion"]
        notes = {x["path"] for x in obj.get("notices", []) if x.get("path")}
        if obj.get("withdrawal", {}).get("reason", {}).get("path"):
            notes.add(obj["withdrawal"]["reason"]["path"])
        if (obj.get("licence") or {}).get("path"):
            notes.add(obj["licence"]["path"])
        own = {p: dig for dig, ps in vinfo["state"].items() for p in ps
               if p not in IDENTITY and not is_evidence(p) and p not in notes}
        change = (obj.get("changes") or {}).get("text")
        if not seen and obj.get("parent"):
            highest, first = n - 1, n    # a branch numbers on from its branch point (section 9.4)
        if n in seen:
            before, mis = files_of[n], missing_of[n]
            if mis:
                if any(before.get(p) not in (None, dig) for p, dig in own.items()) or not set(before) <= set(own):
                    errors.append(f"{ver} changes files of document version {n} (only additions allowed)")
            elif own != before or change != seen[n]:
                errors.append(f"{ver} has other files than document version {n}")
            missing_of[n] = bool(obj.get("sourcesMissing"))
            files_of[n] = own
        else:
            if n != highest + 1:
                errors.append(f"{ver} document version {n} breaks the numbering (expected {highest + 1})")
            m = next((k for k in seen if files_of[k] == own and seen[k] == change), None)
            if m is not None:
                errors.append(f"{ver} document version {n} holds the same files and change note "
                              f"as document version {m}, whose number it keeps")
            highest = max(highest, n)
            seen[n], files_of[n], missing_of[n] = change, own, bool(obj.get("sourcesMissing"))
        hist = obj.get("history")
        if had_history and hist is None:
            errors.append(f"{ver} lacks the history of earlier versions")
        if hist is not None:
            had_history = True
            known = [v for v in inv["versions"] if int(v[1:]) <= int(ver[1:])]
            if any(h not in known for h in hist):
                errors.append(f"{ver} history names unknown object versions")
            else:
                docs = [read_json(d, inv, OBJ, h)["documentVersion"] for h in hist]
                if len(set(docs)) != len(docs) or set(docs) != set(range(first, highest + 1)):
                    errors.append(f"{ver} history does not list each document version once")
                for h, k in zip(hist, docs):
                    later = [v for v in known if int(v[1:]) > int(h[1:])
                             and read_json(d, inv, OBJ, v)["documentVersion"] == k]
                    if later:
                        errors.append(f"{ver} history entry {h} is not the last object version of {k}")
        cur = obj.get("notices", [])
        if any(x not in cur for x in notices):
            errors.append(f"{ver} drops or changes an earlier notice")
        notices = cur
    return errors


def description_errors(d, inv, ver):
    """The breaches of sections 4.3 and 4.4 in the descriptions of VER of the object in D."""
    out = []
    logical = {p for ps in inv["versions"][ver]["state"].values() for p in ps}
    obj = read_json(d, inv, OBJ, ver) if OBJ in logical else None
    dc = read_json(d, inv, "datacite.json", ver) if "datacite.json" in logical else None
    if obj is None or dc is None:
        return out
    if str(obj.get("documentVersion")) != dc.get("version"):
        out.append("datacite.json and object.json disagree on the version")
    if obj.get("status") == "withdrawn" and date_of(dc, "Withdrawn") != obj.get("withdrawal", {}).get("date"):
        out.append("withdrawal dates disagree")
    for k in ("titles", "creators", "publicationYear", "types", "version", "publisher"):
        if k not in dc:
            out.append(f"datacite.json lacks {k}")
    for r in dc.get("rightsList", []):
        if r.get("rightsIdentifier") is None and r.get("rights", "").lower().startswith(("creative", "arxiv")) \
                and not r.get("rightsUri"):
            out.append("licence without SPDX identifier and without rightsUri")
    for note in [obj.get("changes"), obj.get("sourcesMissing"), obj.get("licence")] + \
            obj.get("notices", []) + [obj.get("withdrawal", {}).get("reason")]:
        if note and note.get("path") and note["path"] not in logical:
            out.append(f"note file {note['path']} not in the version")
    if obj.get("kind") == "document":
        if obj.get("mainSource") and obj["mainSource"] not in logical:
            out.append("main source not in the version")
        if obj.get("sourcesMissing") and obj.get("mainSource"):
            out.append("sourcesMissing together with a main source")
        for r in obj.get("renditions", []):
            if r["path"] not in logical:
                out.append(f"rendition {r['path']} not in the version")
    elif obj.get("kind") == "collection" and "members.json" not in logical:
        out.append("collection without members.json")
    return out


def check_storage(f, schema, disc):
    """The checks of section 14.2; returns {identifier: (folder, inventory)} of the objects."""
    if not (OCFL / "0=ocfl_1.1").exists():
        f.error("ocfl", "no OCFL 1.1 storage root (0=ocfl_1.1)")
    if disc and disc.get("storageLayout") != LAYOUT:
        f.error("opensheaf.json", f"storageLayout is {disc.get('storageLayout')}, the configuration says {LAYOUT}")
    if LAYOUT == OWNER_NAME_LAYOUT:
        if (OCFL / "ocfl_layout.json").exists():
            f.error("ocfl", "ocfl_layout.json names only registered layouts: the owner-name layout has none "
                    "(section 3.2)")
        if not (OCFL / LAYOUT_FILE).exists():
            f.warning("ocfl", f"{LAYOUT_FILE}, which describes the layout, is missing (section 3.2)")
    else:
        try:
            ext = json.loads((OCFL / "ocfl_layout.json").read_text(encoding="utf-8")).get("extension")
        except (OSError, ValueError):
            ext = None
        if ext != HASHED_LAYOUT:
            f.error("ocfl", f"ocfl_layout.json must name the extension {HASHED_LAYOUT} (section 3.2)")
        cfg = OCFL / "extensions" / HASHED_LAYOUT / "config.json"
        if cfg.exists():
            c = json.loads(cfg.read_text(encoding="utf-8"))
            if (c.get("digestAlgorithm", "sha256"), c.get("tupleSize", 3), c.get("numberOfTuples", 3)) != \
                    ("sha256", 3, 3):
                f.error("ocfl", "the hashed layout keeps its default parameters (section 3.2)")
    found = {}
    for obj_id, d, inv in objects():
        rel = d.relative_to(OCFL).as_posix()
        if inv is None or obj_id is None:
            f.error(f"ocfl/{rel}", "an object without a readable inventory")
            continue
        try:
            expected = path_of(obj_id)
        except ValueError as e:
            f.error(f"ocfl/{rel}", str(e))
            continue
        if rel != expected:
            f.error(where(obj_id), f"is at ocfl/{rel}, and its identifier puts it at ocfl/{expected} (section 3.2)")
        if obj_id in found:
            f.error(where(obj_id), "two objects of the storage root have this identifier (section 4)")
        found[obj_id] = (d, inv)
        check_object_storage(f, schema, obj_id, d, inv)
    try:
        import ocfl
        from ocfl.validator import Validator
    except ImportError:
        f.warning("ocfl", "the storage root is not checked by an OCFL validator: ocfl-py is not installed"
                  " (pip install 'opensheaf[validate]')")
    else:
        for obj_id, (d, inv) in found.items():
            v = Validator(log_warnings=False, log_errors=True)
            if not v.validate_object(str(d)):
                f.error(where(obj_id), f"OCFL validator: {v.status_str()}")
        if not ocfl.StorageRoot(root=str(OCFL)).validate(log_warnings=False):
            f.error("ocfl", "the OCFL validator rejects the storage root")
    return found


def check_logical_path(p):
    """Whether the logical path P follows the rules of section 4.1."""
    parts = p.split("/")
    return (unicodedata.normalize("NFC", p) == p and "\\" not in p
            and all(x not in ("", ".", "..") for x in parts))


def check_object_storage(f, schema, obj_id, d, inv):
    place = where(obj_id)
    if inv.get("digestAlgorithm") != "sha512":
        f.error(place, "the digest algorithm is not sha512 (section 4.1)")
    root = (d / "inventory.json").read_bytes()
    sc = d / "inventory.json.sha512"
    if not sc.exists() or owners.sidecar_digest(sc.read_bytes()) != names.sha512_hex(root):
        f.error(place, "the checksum file of the inventory does not state its digest")
    head = inv.get("head", "")
    if not (d / head / "inventory.json").exists() or (d / head / "inventory.json").read_bytes() != root:
        f.error(place, f"the inventory of {head} is not the root inventory")
    for dig, paths in inv.get("manifest", {}).items():
        for cp in paths:
            if not (d / cp).exists():
                f.error(place, f"missing {cp}")
            elif digest(d / cp) != dig:
                f.error(place, f"{cp} does not have the digest of the manifest")
    versions = sorted(inv.get("versions", {}), key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)
    kind = (read_json(d, inv, OBJ) or {}).get("kind")
    draft = obj_id.startswith("sheaf:draft:")
    for n, ver in enumerate(versions, 1):
        at = f"{place} {ver}"
        if ver != f"v{n}":
            f.error(at, "versions are numbered v1, v2, ... without zero padding (section 4.1)")
            continue
        copy_path = d / ver / "inventory.json"
        if not copy_path.exists() or not (d / ver / "inventory.json.sha512").exists():
            f.error(at, "no copy of the inventory with its checksum file in the version folder (section 4.1)")
        else:
            if owners.sidecar_digest((d / ver / "inventory.json.sha512").read_bytes()) != digest(copy_path):
                f.error(at, "the checksum file of the inventory copy does not state its digest")
            try:
                copy = json.loads(copy_path.read_text(encoding="utf-8"))
            except ValueError:
                copy = {}
            upto = versions[:n]
            if copy.get("head") != ver:
                f.error(at, f"the inventory copy has the head {copy.get('head')}")
            if sorted(copy.get("versions") or {}) != sorted(upto):
                f.error(at, f"the inventory copy does not record exactly the versions v1 to {ver}")
            elif any(copy["versions"][v] != inv["versions"][v] for v in upto):
                f.error(at, "the inventory copy disagrees with the inventory about the versions it records")
        vinfo = inv["versions"][ver]
        if not (kind == "owner" and n == 1) and (not vinfo.get("user", {}).get("name") or not vinfo.get("message")):
            f.error(at, "a version has a user with a name, and a message (section 4.1)")
        logical = {p for ps in vinfo.get("state", {}).values() for p in ps}
        for p in sorted(logical):
            if not check_logical_path(p):
                f.error(at, f"the logical path {p!r} breaks the rules of section 4.1")
        needed = [OBJ] + (["datacite.json"] if kind != "owner" else []) + ([] if draft else [GENESIS])
        for name in needed:
            if name not in logical:
                f.error(at, f"has no {name} (section 4.1)")
        obj = read_json(d, inv, OBJ, ver) if OBJ in logical else None
        if obj is None:
            continue
        if kind != "owner":
            schema(f"{at}/{OBJ}", obj, "object")
            if n == 1 or draft:
                if "previous" in obj:
                    f.error(at, "a first version, or a draft, has no previous (section 4.3)")
            else:
                sc = d / f"v{n - 1}" / "inventory.json.sha512"
                expected = owners.sidecar_digest(sc.read_bytes()) if sc.exists() else None
                if "previous" not in obj:
                    f.error(at, "object.json has no previous (section 4.3)")
                elif obj["previous"] != expected:
                    f.error(at, f"previous is not the digest of the inventory of v{n - 1} (section 4.3)")


def check_key_logs(f, found, schema):
    """The checks of section 14.3; returns {owner name: KeyLog} of the key logs held."""
    logs = {}
    for obj_id, (d, inv) in found.items():
        if (read_json(d, inv, OBJ) or {}).get("kind") != "owner":
            continue
        place = where(obj_id)
        try:
            log = owners.load_key_log(d)
        except owners.OwnerError as e:
            f.error(place, str(e))
            continue
        errors, warnings = log.check()
        for e in errors:
            f.error(place, e)
        for w in warnings:
            f.warning(place, w)
        try:
            schema(f"{place} v1/{GENESIS}", json.loads(log.genesis), "genesis")
        except ValueError:
            pass
        for v in log.versions:
            if v.keys is not None:
                schema(f"{place} v{v.number}/keys.json", v.keys, "keys")
        logs[log.owner] = log
        latest = [v for v in log.versions if v.is_version]
        if latest:
            f.result(place, f"key log of {log.owner}: latest version v{latest[-1].number}")
        for did in sorted(log.exposed_keys()):
            f.result(place, f"exposed key {did}")
        if log.fork_point:
            f.result(place, f"ended by a fork of its key log at v{log.fork_point} (section 6.3)")
        elif log.ended:
            f.result(place, "ended (section 6.3)" + (f", successor {log.successor} (named by the ending "
                                                      "version)" if log.successor else ""))
    return logs


def check_keepers(f, logs, remote, fetch=None):
    """The links of the owners of the key logs LOGS to their keepers (section 6.6), read with FETCH
    when REMOTE."""
    for log in logs.values():
        keeper = owners.keeper_of(log)
        if keeper is None:
            continue
        place = where(log.id)
        if not remote:
            f.result(place, f"keeper {keeper}: not checked (osheaf verify --remote reads its ORCID record "
                     "or domain, section 6.6)")
            continue
        link = owners.keeper_link(log, fetch)
        if link.status == owners.NOT_CHECKED:
            f.warning(place, f"keeper {keeper}: not checked ({link.reason})")
            continue
        f.result(place, f"keeper {keeper}: {link.status} ({link.reason}; section 6.6)")
        claim = owners.successor_claim(log, link)
        if claim:
            f.result(place, f"successor {link.successor} {claim}")


def check_lines(f, found, logs, schema, disc, resolver=None):
    """The checks of sections 14.4 and 14.5; returns {identifier: statuses} of the lines."""
    statuses, genesis_names = {}, {}
    tombstoned = {t.get("id") for t in disc.get("tombstones", []) if isinstance(t, dict)}
    for obj_id, (d, inv) in found.items():
        head = read_json(d, inv, OBJ) or {}
        if head.get("kind") == "owner":
            continue
        place = where(obj_id)
        if obj_id.startswith("sheaf:draft:"):
            if any(k in head for k in ("name", "owner", "parent")) or read_logical(d, inv, GENESIS):
                f.error(place, "a draft has no genesis record, and no name, owner or parent (section 10.1)")
            continue
        _, nm, owner = obj_id.split(":")
        genesis = None
        for ver in inv["versions"]:
            p = read_logical(d, inv, GENESIS, ver)
            g = p.read_bytes() if p else None
            obj = read_json(d, inv, OBJ, ver) or {}
            if (obj.get("name"), obj.get("owner")) != (nm, owner):
                f.error(f"{place} {ver}", "object.json does not record the line of the identifier (section 4.3)")
            if g is None:
                continue
            if genesis is None:
                genesis = g
            elif g != genesis:
                f.error(f"{place} {ver}", "genesis.json differs from that of v1 (section 5.1)")
        rec = None
        if genesis is not None:
            try:
                rec = names.read_genesis(genesis)
                schema(f"{place} {GENESIS}", json.loads(genesis), "genesis")
            except ValueError as e:
                f.error(place, f"{GENESIS}: {e}")
        if rec is not None:
            genesis_names.setdefault(names.name(genesis), []).append((obj_id, "parent" in head))
            if rec["kind"] != head.get("kind"):
                f.error(place, f"its genesis record is of kind {rec['kind']}, its object.json of kind {head.get('kind')}")
            if not names.is_name_of(nm, genesis):
                f.error(place, "its name is not a name of its genesis record (section 5.2)")
            elif rec.get("originator") != owner:
                if "parent" in head:
                    check_branch(f, place, obj_id, d, inv, genesis, logs, found, tombstoned, resolver)
                else:
                    f.error(place, "a line of another owner than the originator is a branch, and declares its "
                            "parent (section 5.3)")
            elif names.algorithm(nm) != 0:
                f.error(place, "the originator's line is named by algorithm 0 (section 5.3)")
            elif any("parent" in (read_json(d, inv, OBJ, v) or {}) for v in inv["versions"]):
                f.error(place, "the originator's line has no parent: an originator never owns a branch of its own "
                        "work (sections 5.3 and 9)")
        for ver in inv["versions"]:
            for message in description_errors(d, inv, ver):
                f.error(f"{place} {ver}", message)
        if head.get("kind") == "document":
            for message in document_version_errors(obj_id, d, inv):
                f.error(place, message)
        log = logs.get(owner)
        if log is None:
            owner_id = names.object_id(owner, owner)
            (f.warning if owner_id in tombstoned else f.error)(
                place, f"the key log of its owner {owner} is not in the storage root (section 6.5)")
        judgements, sts = line_statuses(d, inv, log)
        statuses[obj_id] = sts
        for i, (js, s) in enumerate(zip(judgements, sts), 1):
            at = f"{place} v{i}"
            for j in js:
                if j.status != sign.GOOD:
                    f.warning(at, f"{j.file}: {j.status}: {j.reason}")
            others = [n for n in witnesses_of(d, f"v{i}") if not (n.startswith("signature-") and n.endswith(".json"))]
            for n in others:
                f.warning(at, f"{n}: not a witness these tools know (section 7.2)")
            if s in (sign.UNSIGNED, sign.INVALID):
                f.warning(at, f"not a version of the line: {s} (sections 7.3 and 7.5)")
            elif s == sign.UNCHECKED:
                f.warning(at, "unchecked: the version of the key log its signatures name is not reached (section 7.3)")
            elif s == sign.CONTESTED:
                f.result(at, "contested (section 7.3)")
        wdir = d / sign.WITNESSES
        for x in (sorted(wdir.iterdir()) if wdir.is_dir() else []):
            if not (x.is_dir() and x.name in inv["versions"]):
                f.warning(place, f"{sign.WITNESSES}/{x.name}: not the folder of a version (section 7.2)")
        signed = sign.latest_signed(sts)
        if signed is None:
            f.warning(place, "the line has no signed version (section 7.3)")
        else:
            f.result(place, f"latest signed version v{signed}")
            if (read_json(d, inv, OBJ, f"v{signed}") or {}).get("status") == "withdrawn":
                f.result(place, "withdrawn (section 13.1)")
    for gname, ids in genesis_names.items():
        lines = [i for i, branch in ids if not branch]
        if len(lines) > 1:
            f.error(", ".join(where(i) for i in lines), "objects with the same genesis record: only the "
                    "originator's line and its branches may share one (section 5.4)")
    kept = {}
    for obj_id, (d, inv) in found.items():
        if (read_json(d, inv, OBJ) or {}).get("kind") == "collection" and obj_id in statuses:
            check_members(f, found, logs, statuses, tombstoned, schema, obj_id, d, inv, resolver)
            check_accepted_copies(f, found, obj_id, d, inv, kept)
    return statuses


def check_branch(f, place, obj_id, d, inv, genesis, logs, found, tombstoned, resolver=None):
    from . import branch
    _, nm, owner = obj_id.split(":")
    prev_obj = prev_ev = None
    verdicts = []
    for ver in sorted(inv["versions"], key=lambda v: int(v[1:])):
        at = f"{place} {ver}"
        obj = read_json(d, inv, OBJ, ver) or {}
        state = {p: dig for dig, ps in inv["versions"][ver]["state"].items() for p in ps}
        ev = {p: dig for p, dig in state.items() if is_evidence(p) or p == GENESIS}
        p = obj.get("parent")
        if not isinstance(p, dict):
            f.error(at, "every version of a branch has parent (section 9.1)")
            continue
        if prev_obj is not None and p == prev_obj.get("parent"):
            if ev != prev_ev:
                f.error(at, "the identity files change without moving the branch point (section 9.4)")
        else:
            v, problems = branch.verdict(branch.level_of_version(d, inv, ver), obj, genesis, logs.get)
            verdicts.append(v)
            if v == branch.INCONSISTENT:
                f.error(at, "inconsistent branch point: " + "; ".join(problems))
            elif v == branch.UNCHECKED:
                f.warning(at, "unchecked branch point: " + "; ".join(problems))
            if prev_obj is not None and v != branch.INCONSISTENT:
                old = prev_obj["parent"]
                pinv_old = json.loads(read_logical(d, inv, "parent/inventory.json", f"v{int(ver[1:]) - 1}").read_bytes())
                pinv_new = json.loads(read_logical(d, inv, "parent/inventory.json", ver).read_bytes())
                if (p.get("owner"), p.get("name")) != (old.get("owner"), old.get("name")):
                    f.error(at, "a branch point moves only to a version of the same parent line (section 9.4)")
                elif int(p["objectVersion"][1:]) <= int(old["objectVersion"][1:]) or \
                        p.get("documentVersion") == old.get("documentVersion"):
                    f.error(at, "a branch point moves only to a higher object version, holding another document "
                            "version (section 9.4)")
                if pinv_old.get("id") != pinv_new.get("id") or any(
                        pinv_new.get("versions", {}).get(v) != e for v, e in pinv_old.get("versions", {}).items()) or any(
                        dg not in pinv_new.get("manifest", {}) for e in pinv_old.get("versions", {}).values()
                        for dg in e.get("state", {})):
                    f.error(at, "the new parent inventory does not continue the previous one (section 9.4)")
        prev_obj, prev_ev = obj, ev
    if not verdicts:
        return
    verdict = max(verdicts, key=branch.ORDER.get)
    p = prev_obj["parent"]
    pid = names.object_id(p["name"], p["owner"])
    f.result(place, f"a branch of {where(pid)}: {verdict} (section 9.3)")
    if pid in found:
        pd, pinv = found[pid]
        signed = latest_signed(pd, pinv, logs.get(p["owner"]))
        status = (read_json(pd, pinv, OBJ, signed) or {}).get("status") if signed else None
        f.result(place, "the parent's line is held here" + (", withdrawn" if status == "withdrawn" else ""))
    elif pid in tombstoned:
        f.result(place, "the parent's line is removed: a tombstone in this archive (section 13.3)")
    elif resolver is not None:
        res = resolver.latest(p["name"], p["owner"], resolver.archive_of(p["url"]) if p.get("url") else [])
        f.result(place, f"the parent's line: {res.status}" + (f" at {res.copy.where}" if res.copy else ""))
    else:
        f.result(place, "the parent's line is not held here (osheaf verify --remote looks for it)")
    rec = names.read_genesis(genesis)
    if nm != p["name"] and names.algorithm(nm) > names.algorithm(p["name"]):
        gone = {t.get("name") for t in TOMBSTONES if t.get("owner") == owner}
        for k in range(names.algorithm(p["name"]), names.algorithm(nm)):
            other = names.name(genesis, k)
            if names.object_id(other, owner) not in found and other not in gone:
                f.warning(place, f"renamed by algorithm {names.algorithm(nm)}, though algorithm {k} gives a "
                          "line free here (section 5.3)")
                break
    if owner == rec.get("originator"):
        f.error(place, "an originator never owns a branch of its own work (section 5.3)")


def check_members(f, found, logs, statuses, tombstoned, schema, obj_id, d, inv, resolver=None):
    for ver in inv["versions"]:
        at = f"{where(obj_id)} {ver}"
        mem = read_json(d, inv, "members.json", ver)
        if mem is None:
            continue
        schema(f"{at}/members.json", mem, "collection")
        kind = mem.get("type")
        if kind not in ("catalogue", "selection"):
            f.error(at, "members.json has no valid type (catalogue or selection)")
        for m in mem.get("members", []):
            mid = names.object_id(m.get("name"), m.get("owner"))
            who = f"{at} member {where(mid)}"
            if kind == "catalogue" and (not m.get("version") or not m.get("inventorySha512") or "revisions" in m):
                f.error(who, "a member of a catalogue needs version and inventorySha512, and no revisions")
            if kind == "selection":
                revs = m.get("revisions")
                if any(k in m for k in ("version", "inventorySha512", "follow")):
                    f.error(who, "a member of a selection has no version, inventorySha512 or follow")
                if not isinstance(revs, list) or not revs or any(
                        not all(r.get(k) for k in ("documentVersion", "version", "inventorySha512")) for r in revs):
                    f.error(who, "a member of a selection needs revisions, each with documentVersion, "
                            "version and inventorySha512")
                elif len({r["documentVersion"] for r in revs}) != len(revs):
                    f.error(who, "a document version is vetted twice")
            if mid in found:
                md, minv = found[mid]
                sts = statuses.get(mid, [])
                for pv, pin, n in member_pins(m):
                    p = md / str(pv) / "inventory.json"
                    if not p.exists():
                        f.warning(f"{who} {pv}", "unavailable: the copy held here lacks this version")
                        continue
                    if digest(p) != pin:
                        f.error(f"{who} {pv}", "mismatch: the inventory held here has another digest (section 8.5)")
                        continue
                    pobj = read_json(md, minv, OBJ, pv) or {}
                    if (pobj.get("kind"), pobj.get("name"), pobj.get("owner")) != (m.get("kind"), m.get("name"), m.get("owner")):
                        f.error(f"{who} {pv}", "kind, name and owner are not those of the version pinned (section 8.5)")
                    if n is not None and pobj.get("documentVersion") != n:
                        f.error(f"{who} {pv}", f"does not hold document version {n}")
                    s = sts[int(pv[1:]) - 1] if 0 < int(pv[1:]) <= len(sts) else None
                    if s in (sign.UNSIGNED, sign.INVALID):
                        f.error(f"{who} {pv}", "not a version: a collection pins only signed versions (section 8.5)")
                    elif s in (sign.UNCHECKED, sign.CONTESTED):
                        f.warning(f"{who} {pv}", f"{s} (section 8.5)")
                if kind == "selection" and sts:
                    signed = sign.latest_signed(sts)
                    hist = history_of(md, minv, f"v{signed}" if signed else None)
                    order = [doc_version_of(md, minv, h) for h in hist]
                    vetted = [r.get("documentVersion") for r in m.get("revisions") or []]
                    pos = [order.index(x) for x in vetted if x in order]
                    if pos != sorted(pos):
                        f.error(who, "revisions not in the order of the history (section 8.4)")
            elif ver == inv["head"]:
                if resolver is not None:
                    for pv, pin, n in member_pins(m):
                        res = resolver.pin(m.get("name"), m.get("owner"), pv, pin, m.get("at", []))
                        if res.copy is not None:
                            pobj = res.copy.read(OBJ, int(pv[1:])) or {}
                            if (pobj.get("kind"), pobj.get("name"), pobj.get("owner")) != \
                                    (m.get("kind"), m.get("name"), m.get("owner")) or (n is not None and pobj.get("documentVersion") != n):
                                f.error(f"{who} {pv}", "the version pinned is not of the kind, line and document version the "
                                        "member gives (section 8.5)")
                        if res.status == "not a version":
                            f.error(f"{who} {pv}", "not a version: a collection pins only signed versions (section 8.5)")
                        elif res.status == "verified":
                            f.result(f"{who} {pv}", f"verified at {res.copy.where} (section 8.5)")
                        else:
                            f.warning(f"{who} {pv}", f"{res.status} (section 8.5)")
                elif mid in tombstoned:
                    f.result(who, "removed: a tombstone in this archive (section 13.3)")
                else:
                    f.warning(who, "not held in this archive: not resolved (osheaf verify --remote resolves "
                              "it, section 14.5)")


def check_accepted_copies(f, found, obj_id, d, inv, kept):
    mem = read_json(d, inv, "members.json") or {}
    if mem.get("type") != "selection":
        return
    owner = obj_id.split(":")[2]
    for m in mem.get("members", []):
        mid = names.object_id(m.get("name"), m.get("owner"))
        if m.get("owner") != owner or mid not in found:
            continue
        md, minv = found[mid]
        if "parent" not in (read_json(md, minv, OBJ) or {}):
            continue
        g = read_logical(md, minv, GENESIS, "v1")
        key = (owner, names.name(g.read_bytes()) if g else mid)
        other, other_copy = kept.setdefault(key, (obj_id, mid))
        if other_copy != mid:
            f.error(where(obj_id), f"keeps an accepted copy of a document of which {where(other)}, a selection "
                    "of the same owner, keeps another: selections keeping different accepted copies of one "
                    "document have different owners (section 9.6)")


def check_indexes(f, schema, disc):
    declared = disc.get("indexes") or {}
    if not declared:
        f.warning("opensheaf.json", "no indexes declared (section 12.5)")
        return
    expected = index_entries()
    gone = {t.get("id"): t for t in disc.get("tombstones", []) if isinstance(t, dict)}
    for index, length in declared.items():
        if index not in INDEX_KEY:
            continue
        key, held = INDEX_KEY[index], []
        for p in sorted((ROOT / index).glob("*.json")) if (ROOT / index).is_dir() else []:
            place = f"{index}/{p.name}"
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except ValueError as e:
                f.error(place, f"not JSON: {e}")
                continue
            schema(place, data, "index")
            if data.get("index") != index:
                f.error(place, f"an index file of {index}/ names the index {data.get('index')}")
            for e in data.get("entries", []):
                if not isinstance(e, dict) or str(e.get(key, ""))[:length] != p.stem or len(p.stem) != length:
                    f.error(place, f"an entry not in the file of its prefix ({str(e)[:60]}...)")
                held.append(e)
        want = [e for e in expected[index] if e.get("status") != "removed"]
        for e in want:
            if e not in held:
                f.error(f"{index}/", f"no entry, or a stale one, for {e.get('id', e.get('owner'))} "
                        f"{e.get('version', '')} (section 12.5)")
        for e in held:
            if e in want:
                continue
            if e.get("id") in gone and e.get("status") == "removed":
                continue
            f.error(f"{index}/", f"an entry the storage root does not justify: {e.get('id', e.get('owner'))} "
                    f"{e.get('version', '')} (section 12.5)")
        for tid, t in gone.items():
            if index in ("names", "sha512") and not any(e.get("id") == tid and e.get("status") == "removed"
                                                        for e in held):
                f.error(f"{index}/", f"no entry with the status removed for the tombstone {tid} (section 12.5)")
            if index == "owners" and any(e.get("owner") == t.get("owner") and t.get("name") in e.get("names", [])
                                         for e in held):
                f.error(f"{index}/", f"owners/ lists {tid}, which is taken down (section 12.5)")


def check_archive(f, found, statuses, disc):
    """The checks of section 14.6 on the discovery document and its tombstones."""
    if not disc:
        return
    listed = {}
    for o in disc.get("objects", []):
        if not isinstance(o, dict):
            continue
        if o.get("id") in listed:
            f.error("opensheaf.json", f"lists {where(o.get('id'))} twice")
        listed[o.get("id")] = o
    now_disc = discovery()
    expected = {o["id"]: o for o in now_disc["objects"]}
    fields = ("kind", "name", "owner", "head", "inventorySha512", "status")
    for obj_id, e in expected.items():
        o = listed.get(obj_id)
        if o is None:
            f.error("opensheaf.json", f"does not list {where(obj_id)}, an object of the storage root (section 3.1)")
            continue
        stale = [k for k in fields if o.get(k) != e.get(k)]
        if stale:
            f.error("opensheaf.json", f"the entry of {where(obj_id)} is stale: " +
                    ", ".join(f"{k} {o.get(k)} instead of {e.get(k)}" for k in stale))
    for obj_id in listed:
        if obj_id not in expected:
            f.error("opensheaf.json", f"lists {obj_id}, which is not an object of the storage root (section 3.1)")
    labels = [o["label"] for o in listed.values() if o.get("label")]
    for lb in sorted({x for x in labels if labels.count(x) > 1}):
        f.error("opensheaf.json", f"the label {lb} is given twice (section 3.1)")
    main = disc.get("mainCollection")
    if main is None:
        f.warning("opensheaf.json", "no mainCollection (section 3.1)")
    elif main not in listed or listed[main].get("kind") != "collection":
        f.error("opensheaf.json", f"mainCollection {main} is not a collection it lists")
    elif main in found:
        md, minv = found[main]
        mem = read_json(md, minv, "members.json") or {}
        if mem.get("type") != "catalogue":
            f.error("opensheaf.json", "mainCollection is not a catalogue (section 8.1)")
        if "owners" in disc:
            for m in mem.get("members", []):
                if m.get("owner") not in disc["owners"]:
                    f.warning("opensheaf.json", f"the main catalogue lists {m.get('name')}, a line of an owner "
                              "that owners does not list (section 8.1)")
    for o in disc.get("owners", []):
        if names.object_id(o, o) not in found:
            f.warning("opensheaf.json", f"owners lists {o}, whose key log is not held here (section 3.1)")
    drafts = {o["id"]: o for o in now_disc.get("drafts", [])}
    for dr in disc.get("drafts", []):
        if dr.get("id") not in drafts or drafts[dr["id"]]["head"] != dr.get("head"):
            f.error("opensheaf.json", f"drafts lists {dr.get('id')}, which is not a draft held with that head")
    missing = set(now_disc.get("extensions", [])) - set(disc.get("extensions", []))
    for e in sorted(missing):
        f.warning("opensheaf.json", f"extensions does not list {e}, which objects use (section 3.1)")
    seen = set()
    needed = {names.object_id(i.split(":")[2], i.split(":")[2]) for i in found if not i.startswith("sheaf:draft:")}
    for t in disc.get("tombstones", []):
        tid = t.get("id")
        if tid != names.object_id(t.get("name"), t.get("owner")):
            f.error("opensheaf.json", f"the tombstone {tid} is not the line of its name and owner (section 13.3)")
        if tid in seen:
            f.error("opensheaf.json", f"two tombstones of {tid}")
        seen.add(tid)
        if tid in found or tid in listed:
            f.error("opensheaf.json", f"{tid} has a tombstone, and is an object of the archive (section 13.3)")
        elif t.get("kind") == "owner" and tid in needed:
            f.warning("opensheaf.json", f"a tombstone stands for the key log {tid}, which lines of the archive "
                      "need: only the law or its keeper justifies it (section 13.2)")
        else:
            f.result("opensheaf.json", f"removed: {tid} ({t.get('date')}: {t.get('reason')})")


def check_presentation(f, disc):
    """Appendix A.3: the home page shows the pin of every member of the latest signed
    version of the main catalogue, and each member held here has a landing page giving the
    full sheaf: URI of its line; errors under the profile website, warnings for an archive
    that presents pages without declaring it."""
    profiles = disc.get("profiles") or []
    website = "website" in profiles
    home = ROOT / "index.html"
    landing_pages = ("texmacs" in profiles or bool(INDEX.get("html") or INDEX.get("template"))
                     or (ROOT / "paper").is_dir())
    if not (website or home.exists() or landing_pages):
        return
    report = f.error if website else f.warning
    note = "" if website else " (the archive does not declare the profile website)"
    members = main_members() or []
    page = home.read_text(encoding="utf-8", errors="replace") if home.exists() else None
    if page is None and website:
        report("index.html", "the home page is missing (appendix A.3)")
    gone = {t.get("id") for t in TOMBSTONES}
    for m in members:
        if f"sheaf:{m.get('name')}:{m.get('owner')}" in gone:
            continue
        pin = (member_pins(m)[-1][1] or "")
        if page is not None and pin[:32] not in page:
            report("index.html", f"does not show the pin of {m.get('name')}" + note)
        try:
            obj_id = names.object_id(m.get("name"), m.get("owner"))
            held_here = (obj_dir(obj_id) / "inventory.json").is_file()
        except (ValueError, TypeError):
            continue
        if held_here:
            landing = ROOT / "paper" / page_address(obj_id) / "index.html"
            text = landing.read_text(encoding="utf-8", errors="replace") if landing.is_file() else ""
            if not landing_names(text, m["name"], m["owner"], obj_id):
                report(landing.relative_to(ROOT).as_posix(), f"no landing page giving the sheaf: URI of "
                       f"{where(obj_id)} (appendix A.3)" + note)


def landing_names(text, nm, owner, obj_id):
    """Whether the landing page TEXT gives the sheaf: URI of the line (NM, OWNER), in canonical form
    or with its owner part."""
    if f"sheaf:{nm}:{owner}" in text:
        return True
    g = read_logical(obj_dir(obj_id), load_inventory(obj_dir(obj_id)), GENESIS, "v1")
    try:
        originator = names.read_genesis(g.read_bytes()).get("originator") if g else None
    except ValueError:
        return False
    return originator == owner and re.search(rf"sheaf:{nm}(?![a-z0-9:/])", text) is not None


def look_for_keys(f):
    """Warn of the files of the archive that look like private keys (section 15.4)."""
    rotation_name = re.compile(r"^rotation-[a-z2-7]{16}-[a-z2-7]{16}\.txt\Z")
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] == ".git" or rel.parts[0].startswith(".staging-") or p.is_symlink() or not p.is_file():
            continue
        looks = rotation_name.match(p.name) or p.suffix == ".key"
        if not looks and p.stat().st_size < 4096:
            text = p.read_bytes().decode("ascii", "replace")
            if text.startswith((keys.ROTATION_FORMAT, keys.SHEET_TITLE)):
                looks = True
            else:
                try:
                    import base64
                    looks = len(base64.b64decode(text.strip(), validate=True)) == 32
                except ValueError:
                    looks = False
        if looks:
            f.warning(rel.as_posix(), "looks like a private key: keys are never kept in an archive "
                      "(section 15.4)")


def verify_findings(remote=False, keeper_fetch=None):
    """The findings of the checks of section 14 on the archive, in the order of 14.2 to 14.6;
    REMOTE: also resolve the members of other archives (section 14.5) and read the places of
    keepers (section 6.6), with KEEPER_FETCH (owners.fetch_json by default)."""
    f = Findings()
    if OLD:
        f.error("archive", "specification 0.1: rebuild (section 16.1)")
        return f
    schema = schema_checker(f)
    disc_path, disc = ROOT / "opensheaf.json", {}
    if not disc_path.exists():
        f.error("opensheaf.json", "the discovery document is missing (section 3.1)")
    else:
        try:
            disc = json.loads(disc_path.read_text(encoding="utf-8"))
        except ValueError as e:
            f.error("opensheaf.json", f"not JSON: {e}")
        if disc.get("specification") == "0.1":
            f.error("archive", "specification 0.1: rebuild (section 16.1)")
            return f
        schema("opensheaf.json", disc, "archive")
    found = check_storage(f, schema, disc)
    logs = check_key_logs(f, found, schema)
    check_keepers(f, logs, remote, keeper_fetch)
    resolver = None
    if remote:
        from . import remote as remote_
        resolver = remote_.Resolver()
    try:
        statuses = check_lines(f, found, logs, schema, disc, resolver)
        if resolver is not None:
            for severity, message in resolver.notes:
                f.add(severity, "resolution", message)
    finally:
        if resolver is not None:
            resolver.__exit__(None, None, None)
    check_archive(f, found, statuses, disc)
    check_indexes(f, schema, disc)
    check_presentation(f, disc)
    look_for_keys(f)
    return f


def verify_errors():
    """The errors of verify_findings(), as 'place: message'."""
    return [f"{x['place']}: {x['message']}" for x in verify_findings() if x["severity"] == "error"]


def verify(args):
    found = verify_findings(remote=getattr(args, "remote", False))
    if getattr(args, "json", False):
        print(json.dumps(found, indent=2, ensure_ascii=False))
    else:
        for x in found:
            print(f"{x['severity']}: {x['place']}: {x['message']}")
        e, w, r = (found.count(s) for s in ("error", "warning", "result"))
        print(("OK" if not e else f"{e} error(s)") + f", {w} warning(s), {r} result(s)")
    sys.exit(1 if found.count("error") else 0)


GITATTRIBUTES = """# OpenSheaf archive files: stored and checked out byte for byte,
# never merged as text (OpenSheaf archives in git, section 4.1). Every
# attribute is named, so that no attribute of the user's own settings (a
# user-wide `*.pdf filter=lfs`, for instance) applies to them.
opensheaf.json -text -filter -ident -working-tree-encoding -export-subst -merge
ocfl/**        -text -filter -ident -working-tree-encoding -export-subst -merge
indexes.json   -text -filter -ident -working-tree-encoding -export-subst -merge
names/**       -text -filter -ident -working-tree-encoding -export-subst -merge
owners/**      -text -filter -ident -working-tree-encoding -export-subst -merge
sha512/**      -text -filter -ident -working-tree-encoding -export-subst -merge
*.pdf binary
"""


def init(args):
    """Create an archive in the folder: osheaf.json, the storage root, the owner and its
    key log (made, or copied), the empty main catalogue, the discovery document, and the
    website with its templates (to edit), or, with --index texmacs, the TeXmacs index
    with its template."""
    root = Path(args.folder or ".").resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any((root / n).exists() for n in CONFIG_NAMES):
        sys.exit(f"{root} has a configuration already")
    layout = LAYOUTS.get(getattr(args, "layout", None) or "owner-name")
    if layout is None:
        sys.exit(f"--layout is one of {', '.join(LAYOUTS)}")
    if bool(getattr(args, "new_owner", False)) == bool(getattr(args, "owner", None)):
        stop("init: give --new-owner, or --owner NAME --key-log DIR")
    family, _, given = args.curator.partition(",")
    family, given = family.strip(), given.strip()
    kind = getattr(args, "index", None) or "website"
    if kind not in ("website", "texmacs"):
        sys.exit("--index is website or texmacs")
    if getattr(args, "index_template", None) and kind != "texmacs":
        sys.exit("--index-template goes with --index texmacs")
    cfg = {
        "owner": None,
        "name": args.name,
        "contact": args.contact or args.base_url,
        "baseUrl": args.base_url if args.base_url.endswith("/") else args.base_url + "/",
        "profiles": [kind],
        "storageLayout": layout,
        "mainCollection": "main",
        "curator": {"name": f"{family}, {given}" if given else family, "givenName": given,
                    "familyName": family, "affiliation": args.affiliation or ""},
        "depositor": {"name": f"{given} {family}".strip(), "address": args.contact or args.base_url},
        "index": {"html": {"templates": "templates"}},
    }
    if kind == "texmacs":
        cfg["index"] = {"template": index_template(root, args)}
    global ARCHIVE
    set_paths(root, layout)
    ARCHIVE = dict(cfg)
    init_storage_root()
    if getattr(args, "new_owner", False):
        log = owner_init(args, done=False)
    else:
        if not getattr(args, "key_log", None):
            stop("init --owner NAME needs --key-log DIR, the folder of its owner object")
        try:
            log = owners.load_key_log(Path(args.key_log))
        except owners.OwnerError as e:
            stop(str(e))
        errors, _ = log.check()
        if log.owner != args.owner or errors:
            stop(f"{args.key_log} is not a valid key log of {names.short(args.owner)}: " + "; ".join(errors))
        if log.ended:
            stop(f"the owner {names.short(log.owner)} has ended (section 6.3)")
        owners.write_key_log(obj_dir(log.id), log)
    cfg["owner"] = log.owner
    if getattr(args, "new_owner", False) and wallet_config(args):
        cfg["keys"] = wallet_config(args)
    (root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not (root / ".gitattributes").exists():
        (root / ".gitattributes").write_text(GITATTRIBUTES, encoding="utf-8")
    if kind == "website":
        from . import html
        (root / "templates").mkdir(exist_ok=True)
        for f in sorted(html.DEFAULTS.iterdir()):
            if f.is_file() and not (root / "templates" / f.name).exists():
                shutil.copyfile(f, root / "templates" / f.name)
    configure(root)
    collect(args)
    index(argparse_namespace(no_html=True))
    edit = "templates/" if kind == "website" else cfg["index"]["template"]
    print(f"Done: the archive is made in {root}, owned by {names.short(log.owner)}. Edit {CONFIG_NAME} and "
          f"{edit}, then deposit a paper: osheaf deposit --new LABEL ...")
    print("Note: OpenSheaf 0.2 is a draft; until version 1.0 a revision may change the format in"
          " incompatible ways, and archives may have to be rebuilt.", file=sys.stderr)


TEXMACS_INDEX_TEMPLATE = """<TeXmacs|2.1>

<style|notes>

<\\body>
  <chapter*|{title}>

  <paper-index>
</body>
"""


def index_template(root, args):
    """The template of the TeXmacs index of a new archive in ROOT, copied from
    --index-template or written: its path relative to ROOT."""
    given = getattr(args, "index_template", None)
    if not given:
        if not (root / "index-template.tm").exists():
            (root / "index-template.tm").write_text(
                TEXMACS_INDEX_TEMPLATE.format(title=tm_escape(args.name)), encoding="latin-1")
        return "index-template.tm"
    src = Path(given).resolve()
    if not src.is_file():
        sys.exit(f"--index-template: no file {given}")
    if src.read_text(encoding="latin-1").count("  <paper-index>\n") != 1:
        sys.exit(f"--index-template: {given} must contain one paragraph <paper-index>")
    dest = root / src.name
    if dest.resolve() != src:
        if dest.exists():
            sys.exit(f"--index-template: {dest} exists already")
        shutil.copyfile(src, dest)
    return src.name


def argparse_namespace(**kw):
    import argparse
    return argparse.Namespace(**kw)


def owner_of(args):
    """The owner name a command is about, and its key log in the storage root."""
    if ROOT is None:
        stop("no archive here (no osheaf.json in this folder or above it): give --root")
    owner = getattr(args, "owner", None) or ARCHIVE["owner"]
    log = key_log(owner)
    if log is None:
        stop(f"the key log of {names.short(owner)} is not in the storage root")
    return owner, log


def depositor():
    return {"name": ARCHIVE["depositor"]["name"], "address": ARCHIVE["depositor"]["address"]}


PASSPHRASE = "OPENSHEAF_PASSPHRASE"
PASSPHRASE_COMMAND = "OPENSHEAF_PASSPHRASE_COMMAND"
_ASKED = {}


def passphrase(confirm=True, where=None):
    """The passphrase of the keys (of the wallet WHERE, if given), asked once per command."""
    if os.environ.get(PASSPHRASE):
        return os.environ[PASSPHRASE]
    if "passphrase" in _ASKED:
        return _ASKED["passphrase"]
    command = os.environ.get(PASSPHRASE_COMMAND, "").strip()
    if command:
        r = subprocess.run(command, shell=True, capture_output=True, text=True)
        given = r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout
        if r.returncode == 0 and given:
            _ASKED["passphrase"] = given
            return given
        warn(f"{PASSPHRASE_COMMAND} gave no passphrase: {r.stderr.strip()}")
    import getpass
    first = getpass.getpass(f"Passphrase of the keys in {where}: " if where else "Passphrase of the keys: ")
    if not first:
        stop("an empty passphrase: give --no-passphrase to export the keys without a passphrase lock")
    if confirm and getpass.getpass("The passphrase again: ") != first:
        stop("the two passphrases differ")
    _ASKED["passphrase"] = first
    return first


def forget_passphrase():
    _ASKED.clear()
    keys.forget_seen()


def archive_repositories():
    from . import wallet
    return wallet.archive_repositories(ROOT, ARCHIVE.get("baseUrl"))


def configured_wallet():
    """The wallet configured for the archive (OPENSHEAF_WALLET, or "keys" of osheaf.json), or None."""
    from . import wallet
    try:
        return wallet.configured(ARCHIVE.get("keys"), forbidden=archive_repositories())
    except wallet.WalletError as e:
        stop(str(e))


def level_wallet(args):
    """The wallet of the security level --keys (or of --wallet), or None for offline (the default)."""
    from . import wallet
    spec = getattr(args, "keys", None) or getattr(args, "wallet", None) or wallet.OFFLINE
    try:
        if spec == "command":
            w = configured_wallet()
            return w if isinstance(w, wallet.CommandWallet) else wallet.parse(spec)
        return wallet.parse(spec, forbidden=archive_repositories())
    except wallet.WalletError as e:
        stop(str(e))


def wallet_for(args):
    """The wallet a command reads or moves keys with: that of --wallet (--keys), or the configured one."""
    from . import wallet
    w = level_wallet(args) or configured_wallet()
    if w is None:
        stop("no key wallet: give --wallet github:OWNER/REPO (or command), or configure one in "
             f'{wallet.user_config_path()} or osheaf.json ("keys": {{"wallet": ...}}) or in OPENSHEAF_WALLET')
    return w


def export_and_confirm(rotation, owner, version, args):
    """Export the rotation keys ROTATION of OWNER, committed in VERSION, and have the
    owner confirm that they are kept; stops if not."""
    secret = None if getattr(args, "no_passphrase", False) else passphrase()
    try:
        paths = keys.export_rotation_keys(rotation, owner, version, args.export, passphrase=secret,
                                          archive_root=ROOT)
        for key, path in zip(rotation, paths):
            if keys.read_rotation_key(path, secret).key.did != key.did:
                raise keys.KeyStoreError(f"{path} does not read back")
    except keys.KeyStoreError as e:
        stop(str(e))
    lock = "locked with your passphrase" if secret else "with no lock (--no-passphrase)"
    print(f"Exported {plural(len(rotation), 'rotation key')} of {names.short(owner)} to {paths[0].parent}, "
          f"{lock}:")
    for key, path in zip(rotation, paths):
        print(f"  {key_label(keys.ROTATION, key.did)}  {path.name}  check {keys.sheet_check(key.seed)}")
    if getattr(args, "print", False):
        for key in rotation:
            print(keys.rotation_key_sheet(key, owner, version))
    if getattr(args, "yes", False):
        return
    print("Put the files (or the printed sheets) away, apart from this computer and from each other.")
    for key, path in zip(rotation, paths):
        typed = input(f"Type the check of {path.name} to confirm: ").strip().upper()
        if typed != keys.sheet_check(key.seed):
            stop("not confirmed: nothing was written to the key log (the exported files may be deleted)")


def keep_in_wallet(w, owner, rotation, version, args, current=()):
    """Keep the rotation keys ROTATION of OWNER, committed in VERSION, and the current keys CURRENT
    ([(key, version listing it)]) in the wallet W; stops if it fails."""
    from . import wallet
    warn(wallet.risk(w.name, owner))
    unlocked = unlocked_passkeys(owner)
    secret = wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
    try:
        w.check_writable()
        todo = [(key, keys.ROTATION, version) for key in rotation]
        todo += [(key, keys.CURRENT, v) for key, v in current if w.read(owner, key.id, keys.CURRENT) is None]
        n = len(todo)
        print(f"Saving {the_keys(n)} of {names.short(owner)} to {w.name}…", file=sys.stderr)
        for i, (key, kind, v) in enumerate(todo, 1):
            plain = kind == keys.CURRENT and getattr(args, "plain_current", False)
            wallet.put_key(w, owner, key, kind, v, None if plain else secret, unlocked)
            print(f"  {i}/{n} {key_label(kind, key.did)}  saved", file=sys.stderr)
    except wallet.WalletError as e:
        stop(f"{e}: nothing was written to the key log")
    enroll_hint(owner, unlocked)


def lock_words(locks):
    """What opens a key with the locks LOCKS (wallet.locks), for a person: "your passkey
    (unlock.opensheaf.org) and your passphrase"."""
    words = [f"your {x}" for x in locks if x.startswith("passkey")] + \
            [f"your {x}" for x in locks if not x.startswith("passkey")]
    return " and ".join(words) or "no passphrase or passkey (they have no lock)"


def kept_where(args, w):
    """Where the new rotation keys are kept: the folder of --export, the wallet W, or both."""
    places = ([str(Path(args.export).resolve())] if getattr(args, "export", None) else []) + \
             ([w.name] if w is not None else [])
    return " and in ".join(places)


def rotation_line(n, next_threshold, where, new=False):
    """The line of a summary on the rotation keys: N (NEW) of them, kept in WHERE."""
    verb = "signs" if next_threshold == 1 else "sign"
    more = "" if n == 1 else f"; any {next_threshold} of them {verb} the next version of the key log"
    return f"  rotation keys  {n}{' new' if new else ''}, kept in {where}{more}"


def plural(n, noun):
    """N NOUN, in the singular or the plural ("1 key", "2 keys")."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def the_keys(n, noun="key"):
    """"the key" or "the N keys"."""
    return f"the {noun}" if n == 1 else f"the {n} {noun}s"


def key_label(kind, did):
    """A key in a line of progress: its kind and its short did:key, in columns."""
    return f"{kind + ' key':<14}{names.short(did)}"


LOWER_NAMES = ("gh", "osheaf", "command")


def sentence(text):
    """TEXT as a sentence: its first word capitalized, unless it is a name (of a program, a wallet,
    an owner, a key, an option or a file), and a final period."""
    m = re.match(r"([a-z][a-z']{0,14})(?=[ ,;])", text)
    if m and m.group(1) not in LOWER_NAMES:
        text = text[0].upper() + text[1:]
    return text if text.endswith((".", "?", "!", ":", "…")) else text + "."


def stop(text):
    """End the command with the message TEXT, a sentence."""
    sys.exit(sentence(text))


def warn(text):
    """Say TEXT, a warning, on the standard error."""
    print("Warning: " + sentence(text), file=sys.stderr)


def confirmed(word, args=None):
    """Whether the user typed WORD to confirm what was listed (always, with --yes)."""
    if args is not None and getattr(args, "yes", False):
        return True
    return input(f"Type {word} to confirm: ").strip() == word


def store_name(store):
    """Where a current key kept in STORE is, for a person."""
    return STORE_NAMES.get(store, store)


def version_listing(log, did):
    """The number of the first version of LOG whose current keys list DID, or None."""
    return next((v.number for v in log.side() if v.keys and did in v.keys.get("keys", [])), None)


def rotation_keys(files, owner):
    """The rotation keys of OWNER read from FILES."""
    out = []
    for f in files:
        try:
            try:
                rk = keys.read_rotation_key(Path(f))
            except keys.PassphraseNeeded:
                rk = keys.read_rotation_key(Path(f), passphrase(confirm=False))
        except (keys.KeyStoreError, OSError) as e:
            stop(f"{f}: {e}")
        if rk.owner not in (None, owner):
            stop(f"{f} is a rotation key of {names.short(rk.owner)}, not of {names.short(owner)}")
        out.append(rk.key)
    return out


def rotation_signers(args, owner, prev):
    """(the rotation keys that sign the version after PREV, the wallet they come from or None)."""
    files = getattr(args, "rotation_key", None)
    if files:
        return rotation_keys(files, owner), None
    from . import wallet
    w = configured_wallet() or level_wallet(args)
    if w is None:
        stop("give the rotation keys that sign the new version of the key log (--rotation-key FILE), "
             "or the wallet that keeps them (--keys github:OWNER/REPO)")
    need, out = prev.keys["nextThreshold"], []
    print(f"Reading {the_keys(need, 'rotation key')} of v{prev.number} of {names.short(owner)} that sign "
          f"from {w.name}…", file=sys.stderr)
    try:
        for digest in prev.keys["next"]:
            key = unlock_key(w, owner, digest[:16], keys.ROTATION)
            if key is not None and key.digest == digest:
                out.append(key)
                print(f"  {len(out)}/{need} {key_label(keys.ROTATION, key.did)}  opened", file=sys.stderr)
            if len(out) == need:
                break
    except wallet.WalletError as e:
        stop(str(e))
    if len(out) < need:
        stop(f"the wallet {w.name} holds {len(out)} of the rotation keys of v{prev.number} of the key log of "
             f"{names.short(owner)}, and {need} sign the next version: give them with --rotation-key FILE")
    print(f"Read {plural(len(out), 'rotation key')} of v{prev.number} from {w.name}.", file=sys.stderr)
    return out, w


def owner_init(args, done=True):
    """Make an owner (section 6.2): its current key on this device, its rotation keys,
    exported outside the archive, and the first version of its key log, in the storage root."""
    single = bool(getattr(args, "single_rotation_key", False))
    n_rot = 1 if single else int(getattr(args, "rotation", None) or 3)
    next_threshold = 1 if single else int(getattr(args, "next_threshold", None) or n_rot // 2 + 1)
    others = list(getattr(args, "key", None) or [])
    threshold = int(getattr(args, "threshold", None) or 1)
    if not 1 <= next_threshold <= n_rot or not 1 <= threshold <= 1 + len(others):
        stop("a threshold is at least 1, and at most the number of keys (section 6.1, rule 1)")
    keeper = getattr(args, "keeper", None)
    if keeper and not names.keeper_valid(keeper):
        stop(f"a keeper is an ORCID iD (with its check digit) or https://<domain>/: {keeper}")
    w = level_wallet(args)
    if w is None and not getattr(args, "export", None):
        stop("give --export DIR, a folder outside the archive where the rotation keys are written "
             "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
    if w is not None and getattr(args, "no_passphrase", False):
        stop("--no-passphrase: the keys in a wallet are always locked with a passphrase")
    if w is None and not keys.kept_on_device():
        stop(f"{keys.KEY_STORE}=none keeps no current key on this computer: keep the keys in a "
             "wallet (--keys github:OWNER/REPO|command)")
    for did in others:
        try:
            names.did_key_public(did)
        except ValueError:
            stop(f"not a did:key URI of an Ed25519 key: {did}")
    current = keys.new_key()
    rotation = [keys.new_key() for _ in range(n_rot)]
    while True:
        try:
            log = owners.new_owner([current] + others, rotation, threshold=threshold,
                                   next_threshold=next_threshold, keeper=keeper)
        except (ValueError, owners.OwnerError) as e:
            stop(str(e))
        if not obj_dir(log.id).exists():
            break
    if next_threshold == 1:
        warn(owners.SINGLE_ROTATION_RISK)
    if getattr(args, "export", None):
        export_and_confirm(rotation, log.owner, 1, args)
    if w is not None:
        keep_in_wallet(w, log.owner, rotation, 1, args, current=[(current, 1)])
    try:
        store = keys.store_current_key(log.owner, current)
    except (keys.KeyStoreError, OSError) as e:
        stop(str(e))
    owners.write_key_log(obj_dir(log.id), log)
    kept = f"{w.name} only ({keys.KEY_STORE}=none)" if store == keys.NONE else store_name(store)
    print(f"{'Done: the' if done else 'The'} owner {names.short(log.owner)} is made, with v1 of its key log:")
    print(f"  owner          {log.owner}")
    print(f"  current key    {current.did}, kept in {kept}")
    for did in others:
        print(f"  current key    {did}, of another device")
    print(rotation_line(n_rot, next_threshold, kept_where(args, w)))
    warn(owners.ROTATION_KEYS_WARNING)
    return log


def owner_init_command(args):
    log = owner_init(args)
    cfg_path = ROOT / CONFIG_NAME
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        changed = False
        if log.owner not in [cfg.get("owner")] + cfg.get("owners", []):
            cfg["owners"] = cfg.get("owners", []) + [log.owner]
            ARCHIVE.setdefault("owners", []).append(log.owner)
            changed = True
        if wallet_config(args) and "keys" not in cfg:
            cfg["keys"] = ARCHIVE["keys"] = wallet_config(args)
            changed = True
        if changed:
            cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_discovery()


def wallet_config(args):
    """The `keys` of osheaf.json naming the GitHub wallet of --keys, or None."""
    spec = getattr(args, "keys", None) or ""
    return {"wallet": spec} if spec.startswith("github:") else None


MOVED_UP = ("Moved up to the maximum security level: the rotation keys kept in {w} are used up and sign "
            "nothing more (section 6.2), and the new ones are kept offline only. To remove the used ones "
            "from {w}: osheaf key forget --from-wallet --used. The current keys kept in {w} still sign until "
            "a version of the key log retires them (osheaf owner rotate --retire DID); then osheaf key "
            "forget --from-wallet DID removes them.")


def owner_rotate(args, exposed=()):
    """A new version of the key log changing the current keys (section 6.2) or exposing
    some (section 6.3), signed by rotation keys, committing new rotation keys."""
    owner, log = owner_of(args)
    who = names.short(owner)
    prev = log.latest()
    if prev is None:
        stop(f"the owner {who} has ended (section 6.3): its key log takes no new version")
    w = level_wallet(args)
    if w is None and not getattr(args, "export", None):
        stop("give --export DIR, a folder outside the archive where the new rotation keys are written "
             "(or keep them in a wallet, a lower security level: --keys github:OWNER/REPO|command)")
    if w is not None and getattr(args, "no_passphrase", False):
        stop("--no-passphrase: the keys in a wallet are always locked with a passphrase")
    signers, source = rotation_signers(args, owner, prev)
    n_rot = int(getattr(args, "rotation", None) or len(prev.keys["next"]))
    next_threshold = int(getattr(args, "next_threshold", None) or min(prev.keys["nextThreshold"], n_rot))
    for did in list(getattr(args, "add", None) or []) + list(getattr(args, "retire", None) or []) + list(exposed):
        try:
            names.did_key_public(did)
        except ValueError:
            stop(f"not a did:key URI of an Ed25519 key: {did}")
    new = [keys.new_key() for _ in range(n_rot)]
    try:
        v = log.rotate(signers, next_keys=new, next_threshold=next_threshold,
                       add=getattr(args, "add", None) or (), retire=getattr(args, "retire", None) or (),
                       exposed=exposed, threshold=getattr(args, "threshold", None),
                       message=getattr(args, "message", None) or ("Keys exposed" if exposed else "Keys changed"),
                       user=depositor())
    except owners.OwnerError as e:
        stop(str(e))
    if next_threshold == 1:
        warn(owners.SINGLE_ROTATION_RISK)
    if getattr(args, "export", None):
        export_and_confirm(new, owner, v.number, args)
    if w is not None:
        try:
            here = keys.current_keys(owner, v.keys["keys"])
        except keys.KeyStoreError:
            here = []
        keep_in_wallet(w, owner, new, v.number, args, current=[(k, version_listing(log, k.did)) for k in here])
    owners.write_key_log(obj_dir(log.id), log)
    write_discovery()
    print(f"Done: v{v.number} of the key log of {who}, signed by {plural(len(signers), 'rotation key')} "
          f"of v{prev.number}:")
    for did in v.keys["keys"]:
        print(f"  current key    {did}")
    for did in exposed:
        print(f"  exposed key    {did}")
    print(rotation_line(n_rot, next_threshold, kept_where(args, w), new=True))
    if exposed:
        print("What an exposed key alone signed is contested (section 7.3): osheaf sign signs it again.")
    if source is not None and w is None:
        print(MOVED_UP.format(w=source.name), file=sys.stderr)


def owner_expose(args):
    owner_rotate(args, exposed=list(args.exposed))


def owner_end(args):
    """The ending version of the key log (section 6.3)."""
    owner, log = owner_of(args)
    who = names.short(owner)
    successor = getattr(args, "successor", None)
    if successor is not None and not names.OWNER_NAME.match(successor):
        stop(f"the successor is an owner name: {successor}")
    if log.latest() is None:
        stop(f"the owner {who} has ended (section 6.3): its key log takes no new version")
    signers, _ = rotation_signers(args, owner, log.latest())
    try:
        v = log.end(signers, successor=successor, exposed=getattr(args, "expose", None) or (),
                    message=getattr(args, "message", None) or "Owner ended", user=depositor())
    except owners.OwnerError as e:
        stop(str(e))
    owners.write_key_log(obj_dir(log.id), log)
    write_discovery()
    print(f"Done: the owner {who} has ended, at v{v.number} of its key log" +
          (f"; its successor is {successor}." if successor else "."))


def owner_show(args):
    owner, log = owner_of(args)
    latest, here = log.latest(), []
    if latest is not None:
        try:
            here = [k.did for k in keys.current_keys(owner, latest.keys["keys"])]
        except keys.KeyStoreError as e:
            warn(str(e))
    if getattr(args, "offline", False):
        link = owners.KeeperLink(owners.keeper_of(log), owners.NOT_CHECKED, "offline: --offline given")
    else:
        link = owners.keeper_link(log)
    for line in owners.describe(log, here, link):
        print(line)


def key_new(args):
    owner = getattr(args, "owner", None) or ARCHIVE["owner"]
    if not keys.kept_on_device():
        stop(NOT_KEPT)
    key = keys.new_key()
    try:
        store = keys.store_current_key(owner, key)
    except (keys.KeyStoreError, OSError) as e:
        stop(str(e))
    print(f"New current key of {names.short(owner)}, kept in {store_name(store)}:")
    print(f"  {key.did}")
    print(f"It signs once a version of the key log adds it: osheaf owner rotate --add {key.did} "
          "--rotation-key FILE ... --export DIR")
    return key


def key_push(args):
    """Put the current keys of this device into the wallet."""
    from . import wallet
    owner, log = owner_of(args)
    who = names.short(owner)
    latest = log.latest()
    if latest is None:
        stop(f"the owner {who} has ended (section 6.3)")
    w = wallet_for(args)
    dids = list(getattr(args, "did", None) or latest.keys["keys"])
    try:
        here = keys.current_keys(owner, dids)
    except keys.KeyStoreError as e:
        stop(str(e))
    if not here:
        stop(f"this computer holds none of the keys {', '.join(names.short(d) for d in dids)} of {who}")
    try:
        w.check_writable()
        there = {k.did for k in here if w.read(owner, k.id, keys.CURRENT) is not None}
    except wallet.WalletError as e:
        stop(str(e))
    n = len(here)
    if len(there) == n:
        print(f"{'The current key' if n == 1 else f'The {n} current keys'} of {who} "
              f"{'is' if n == 1 else 'are'} already in {w.name}.")
        return
    warn(wallet.risk(w.name, owner))
    plain = getattr(args, "plain_current", False)
    unlocked = [] if plain else unlocked_passkeys(owner)
    secret = None if plain else wallet_passphrase(w, owner) if unlocked else passphrase(where=w.name)
    print(f"Saving {the_keys(n, 'current key')} of {who} to {w.name}…", file=sys.stderr)
    try:
        for i, key in enumerate(here, 1):
            if key.did in there:
                print(f"  {i}/{n} {key_label(keys.CURRENT, key.did)}  already there", file=sys.stderr)
                continue
            wallet.put_key(w, owner, key, keys.CURRENT, version_listing(log, key.did), secret, unlocked)
            print(f"  {i}/{n} {key_label(keys.CURRENT, key.did)}  saved", file=sys.stderr)
    except wallet.WalletError as e:
        stop(str(e))
    saved = n - len(there)
    lock = "with no lock (--plain-current)" if plain else \
        "locked with your passkey and your passphrase" if unlocked else "locked with your passphrase"
    print(f"Done: {plural(saved, 'current key')} of {who} saved to {w.name}, {lock}.")


def key_pull(args):
    """Keep on this device the current keys of the owner that the wallet holds."""
    owner, log = owner_of(args)
    latest = log.latest()
    if latest is None:
        stop(f"the owner {names.short(owner)} has ended (section 6.3)")
    w = wallet_for(args)
    if not keys.kept_on_device():
        print(not_kept(w, owner))
        return
    try:
        have = {k.did for k in keys.current_keys(owner, latest.keys["keys"])}
    except keys.KeyStoreError as e:
        stop(str(e))
    pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
    print(pull_summary(w, owner, latest, have, pulled))


STORE_NAMES = {"keyring": "the keychain" if sys.platform == "darwin" else "the system keyring",
               "security": "the keychain", "file": "a file of this computer",
               keys.NONE: "memory, for this command only"}
NOT_KEPT = (f"No current key is kept on this computer ({keys.KEY_STORE}=none), so a new one would be "
            "lost when the command ends")


def not_kept(w, owner):
    """The sentence that says why nothing is pulled with OPENSHEAF_KEY_STORE=none."""
    return (f"The current keys of {names.short(owner)} are not kept on this computer, by choice "
            f"({keys.KEY_STORE}=none): each command that signs opens them in {w.name}.")


def pull_current_keys(w, owner, dids):
    """[(key, store)]: the keys DIDS of OWNER that the wallet W holds, kept on this device in STORE."""
    from . import wallet
    out = []
    if dids:
        print(f"Pulling {the_keys(len(dids), 'current key')} of {names.short(owner)} from {w.name}…",
              file=sys.stderr)
    try:
        for did in dids:
            key = unlock_key(w, owner, names.key_id(did), keys.CURRENT)
            if key is None:
                print(f"  {key_label(keys.CURRENT, did)}  not in {w.name}", file=sys.stderr)
                continue
            if key.did != did:
                stop(f"the wallet {w.name} holds another key than {did} under its name")
            store = keys.store_current_key(owner, key)
            print(f"  {key_label(keys.CURRENT, did)}  kept in {store_name(store)}", file=sys.stderr)
            out.append((key, store))
    except (wallet.WalletError, keys.KeyStoreError, OSError) as e:
        stop(str(e))
    return out


def pull_summary(w, owner, latest, have, pulled):
    """The sentence that says what a pull did: HAVE, the did:keys held before, PULLED, [(key, store)]."""
    total, held, who = len(latest.keys["keys"]), len(have) + len(pulled), names.short(owner)
    if pulled:
        stores = sorted({store_name(s) for _, s in pulled})
        out = f"Pulled {plural(len(pulled), 'current key')} of {who} from {w.name} into {' and '.join(stores)}."
        return out + (f" This computer holds {held} of its {total} current keys." if held < total else "")
    if held == total:
        return (f"The current key of {who} is already on this computer." if total == 1
                else f"The {total} current keys of {who} are already on this computer.")
    return (f"The wallet {w.name} holds no current key of {who} that this computer lacks: this computer "
            f"holds {held} of the {total}.")


def pull_from_wallet(owner, latest, found):
    """FOUND, the current keys of OWNER on this device, with those the configured wallet adds."""
    w = configured_wallet()
    if w is None:
        return found
    held = {k.did for k in found}
    return found + [k for k, _ in pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in held])]


def key_list(args):
    """What the wallet holds, as a table: the owner, kind, key, version and locks of each key."""
    from . import wallet
    w = wallet_for(args)
    owner = getattr(args, "owner", None)
    try:
        rows = wallet.listing(w, owner)
    except wallet.WalletError as e:
        stop(str(e))
    whose = f" of {names.short(owner)}" if owner else ""
    if not rows:
        print(f"The wallet {w.name} holds no key{whose}.")
        return
    print(f"The wallet {w.name} holds {plural(len(rows), 'key')}{whose}:")
    table = [("Owner", "Kind", "Key", "Version", "Locks")] + [
        (names.short(o), kind, names.short(did), version or "-", ", ".join(locks) or "none")
        for o, _, kind, did, version, locks in rows]
    widths = [max(len(r[i]) for r in table) for i in range(4)]
    for r in table:
        print("  " + "  ".join(c.ljust(n) for c, n in zip(r, widths)) + "  " + r[4])


def passkey_keks(owner, wraps, force=False):
    """{cred: key-encryption key} of the passkeys among WRAPS of OWNER unlocked in this command,
    asking the browser if none is; None to use the passphrase."""
    from . import passkey
    cache = _ASKED.setdefault("passkeys", {})
    _ASKED.setdefault("seen", set()).add(owner)
    failed = _ASKED.setdefault("failed", set())
    salt = keys.passkey_salt(owner)
    wraps = [p for p in wraps if p.salt == salt]
    if any(p.rp == keys.OLD_PASSKEY_RP for p in wraps) and owner not in _ASKED.setdefault("old rp", set()):
        _ASKED["old rp"].add(owner)
        print(f"A passkey of {names.short(owner)} was enrolled on {keys.OLD_PASSKEY_RP}, which osheaf no longer "
              f"asks: run osheaf key enroll --new-passkey to move it to {keys.PASSKEY_RP} (then osheaf key "
              f"forget --rp {keys.OLD_PASSKEY_RP}).", file=sys.stderr)
    wraps = [p for p in wraps if p.rp == keys.PASSKEY_RP]
    if not wraps:
        return None
    if any(p.cred in cache for p in wraps):
        return {c: p.kek for c, p in cache.items()}
    if not force and (os.environ.get(PASSPHRASE) or os.environ.get(passkey.UNLOCK, "") == "passphrase"
                      or owner in failed):
        return None
    creds = list(dict.fromkeys(p.cred for p in wraps))
    try:
        cred, prf = passkey.unlock(owner, creds, no_browser=_ASKED.get("no_browser", False),
                                   ctrl_c="stop" if force else "type the passphrase instead")
    except passkey.UnlockFailed as e:
        failed.add(owner)
        if force:
            stop(f"the passkey did not unlock the keys of {names.short(owner)}: {e}")
        print(f"The passkey did not open the keys ({e}): osheaf asks for the passphrase instead.",
              file=sys.stderr)
        return None
    kek = keys.passkey_kek(prf)
    opened = [c for c in ([cred] if cred else creds) if any(p.cred == c and p.opens(kek) for p in wraps)]
    if not opened:
        failed.add(owner)
        if force:
            stop(f"the passkey's answer opens no key of {names.short(owner)}: nothing was unlocked")
        print("The passkey's answer opens no key: osheaf asks for the passphrase instead.", file=sys.stderr)
        return None
    for c in opened[:1]:
        cache[c] = keys.Passkey(c, salt, kek=kek)
    return {c: p.kek for c, p in cache.items()}


def unlock_key(w, owner, kid, kind):
    """The key KID of OWNER, of KIND, from the wallet W, unlocked by a passkey or the passphrase."""
    from . import wallet
    return wallet.get_key(w, owner, kid, kind, lambda: passphrase(confirm=False, where=w.name), passkey_keks)


def unlocked_passkeys(owner):
    """The passkeys of OWNER unlocked in this command."""
    salt = keys.passkey_salt(owner)
    return [p for p in _ASKED.get("passkeys", {}).values() if p.salt == salt]


def wallet_passphrase(w, owner):
    """The passphrase, for keys written after a passkey has opened others: asked once, and checked
    against a key of OWNER in the wallet W, so that the new keys are under the same passphrase."""
    from . import wallet
    if os.environ.get(PASSPHRASE) or "passphrase" in _ASKED:
        return passphrase(where=w.name)
    try:
        texts = [t for _, t in wallet_entries(w, owner) if keys.wraps_of(t)]
    except SystemExit:
        texts = []
    if not texts:
        return passphrase(where=w.name)
    secret = passphrase(confirm=False, where=w.name)
    try:
        keys.read_key(texts[0], secret)
    except keys.KeyStoreError as e:
        stop(f"{e}: this is not the passphrase of the keys of {names.short(owner)} in {w.name}")
    return secret


def enroll_hint(owner, unlocked):
    if not unlocked and owner in _ASKED.get("seen", set()):
        print(f"The new keys of {names.short(owner)} open with your passphrase only: run osheaf key enroll "
              "so that your passkey opens them too.", file=sys.stderr)


def wallet_entries(w, owner):
    """[(kid, text)] of the keys of OWNER in the wallet W."""
    from . import wallet
    try:
        return [(kid, wallet.read_any(w, o, kid)) for o, kid in w.entries(owner)]
    except wallet.WalletError as e:
        stop(str(e))


def encrypted_entries(w, owner):
    out = [(kid, t) for kid, t in wallet_entries(w, owner)
           if any(x.startswith("encryption ") and x.split()[1:2] != ["none"] for x in t.splitlines())]
    if not out:
        stop(f"the wallet {w.name} holds no key of {names.short(owner)} locked with a passphrase")
    return out


def key_owner(args):
    owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
    if not owner or not names.OWNER_NAME.match(owner):
        stop("give --owner NAME, or run the command in an archive")
    return owner


def key_enroll(args):
    """Let a passkey open the keys of the owner in the wallet."""
    import hmac
    from . import passkey, wallet
    owner, w = key_owner(args), wallet_for(args)
    _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
    try:
        w.check_writable()
    except wallet.WalletError as e:
        stop(str(e))
    who = names.short(owner)
    print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
    entries = encrypted_entries(w, owner)
    salt = keys.passkey_salt(owner)
    known = list(dict.fromkeys(p.cred for _, t in entries for p in keys.passkeys_of(t)
                               if p.salt == salt and p.rp == keys.PASSKEY_RP))
    new = bool(getattr(args, "new_passkey", False)) or not known
    todo = entries if new else [(kid, t) for kid, t in entries
                                if not {p.cred for p in keys.passkeys_of(t)} & set(known)]
    if not todo:
        print(f"Every key of {who} in {w.name} already opens with your passkey.")
        return
    secret = passphrase(confirm=False, where=w.name)
    n = len(todo)
    print(f"Opening {the_keys(n)} of {who} in {w.name} with the passphrase…", file=sys.stderr)
    for i, (kid, t) in enumerate(todo, 1):
        try:
            rk = keys.read_key(t, secret)
        except keys.KeyStoreError as e:
            stop(f"{w.name} {kid}: {e}: nothing was changed")
        print(f"  {i}/{n} {key_label(rk.kind, rk.key.did)}  opened", file=sys.stderr)
    halt = "stop: nothing is changed"
    try:
        if new:
            cred, prf = passkey.enroll(owner, known, no_browser=_ASKED["no_browser"], ctrl_c=halt)
            print("The passkey is made. Once more, to check it…", file=sys.stderr)
            again, prf2 = passkey.unlock(owner, [cred], no_browser=_ASKED["no_browser"], ctrl_c=halt)
            if again not in (None, cred) or not hmac.compare_digest(prf, prf2):
                stop("the new passkey did not give the same secret twice: nothing was changed")
        else:
            cred, prf = passkey.unlock(owner, known, no_browser=_ASKED["no_browser"], ctrl_c=halt)
    except passkey.UnlockFailed as e:
        stop(f"no passkey: {e}; nothing was changed")
    kek = keys.passkey_kek(prf)
    if not new:
        opened = [c for c in ([cred] if cred else known)
                  if any(_opens(t, c, kek) for _, t in entries if c in {p.cred for p in keys.passkeys_of(t)})]
        if not opened:
            stop("the passkey used does not open the keys it is enrolled for: nothing was changed")
        cred = opened[0]
    unlocked = keys.Passkey(cred, salt, kek=kek)
    print(f"Adding a passkey lock to {the_keys(n)} of {who} in {w.name}…", file=sys.stderr)
    try:
        for i, (kid, _) in enumerate(todo, 1):
            kind, did = wallet.add_passkey(w, owner, kid, secret, unlocked)
            print(f"  {i}/{n} {key_label(kind, did)}  lock added", file=sys.stderr)
    except wallet.WalletError as e:
        stop(str(e))
    print(f"Done: {the_keys(n)} of {who} {'opens' if n == 1 else 'open'} with your passkey (Touch ID) "
          "and still with your passphrase.")


def _opens(text, cred, kek):
    try:
        keys.read_key(text, keks={cred: kek})
        return True
    except keys.KeyStoreError:
        return False


def key_unlock(args):
    """Open with the passkey the keys of the owner in the wallet; in an archive, pull its current keys."""
    owner, w = key_owner(args), wallet_for(args)
    _ASKED["no_browser"] = bool(getattr(args, "no_browser", False))
    who = names.short(owner)
    print(f"Reading the keys of {who} in {w.name}…", file=sys.stderr)
    entries = [(kid, t) for kid, t in wallet_entries(w, owner) if keys.passkeys_of(t)]
    if not entries:
        stop(f"no key of {who} in {w.name} has a passkey lock: run osheaf key enroll")
    keks = passkey_keks(owner, [p for _, t in entries for p in keys.passkeys_of(t)], force=True)
    if not keks:
        stop(f"no passkey of {who} to unlock with")
    opened, n = sum(1 for _, t in entries if any(_opens(t, c, k) for c, k in keks.items())), len(entries)
    if opened == n:
        print(f"{'The key' if n == 1 else 'Both keys' if n == 2 else f'All {n} keys'} of {who} opened "
              "with your passkey.")
    else:
        print(f"{opened} of the {n} keys of {who} opened with your passkey; the others need the passphrase.")
    log = key_log(owner) if ROOT is not None else None
    latest = log.latest() if log is not None else None
    if latest is not None and not keys.kept_on_device():
        print(not_kept(w, owner))
    elif latest is not None:
        try:
            have = {k.did for k in keys.current_keys(owner, latest.keys["keys"])}
        except keys.KeyStoreError as e:
            stop(str(e))
        pulled = pull_current_keys(w, owner, [d for d in latest.keys["keys"] if d not in have])
        print(pull_summary(w, owner, latest, have, pulled))


def key_export(args):
    """Copy a current key of this device to the clipboard (or print it, --stdout)."""
    from . import wallet
    if not getattr(args, "clipboard", False) and not getattr(args, "stdout", False):
        stop("give --clipboard, or --stdout to print the key")
    owner = getattr(args, "owner", None) or ARCHIVE.get("owner")
    if not owner:
        stop("give --owner NAME, or run the command in an archive")
    who = names.short(owner)
    if getattr(args, "did", None):
        dids = [args.did]
    else:
        latest = key_log(owner).latest() if ROOT is not None and key_log(owner) else None
        if latest is None:
            stop(f"name the key to export, by its did:key (no key log of {who} here)")
        dids = latest.keys["keys"]
    try:
        here = keys.current_keys(owner, dids)
    except keys.KeyStoreError as e:
        stop(str(e))
    if not here:
        stop(f"this computer holds none of the keys {', '.join(names.short(d) for d in dids)} of {who}")
    if len(here) > 1:
        stop(f"this computer holds {len(here)} current keys of {who}: name the one to export by its did:key, "
             "one of " + ", ".join(k.did for k in here))
    key = here[0]
    locked = getattr(args, "encrypt", False)
    text = keys.key_text(key, owner, keys.CURRENT, passphrase() if locked else None)
    if getattr(args, "stdout", False):
        sys.stdout.write(text)
    else:
        try:
            wallet.to_clipboard(text)
        except wallet.WalletError as e:
            stop(str(e))
        wallet.clear_later(text)
        print(f"The current key {names.short(key.did)} of {who}"
              f"{', locked with your passphrase,' if locked else ''} is on the clipboard: paste it into a note "
              f"of your password manager (the Passwords app) within {int(wallet.CLEAR_AFTER)} seconds; then "
              "osheaf clears the clipboard if it still holds the key.", file=sys.stderr)
        warn("any program of yours can read the clipboard, and Universal Clipboard may send it to your "
             "other Apple devices nearby")
    warn("a current key kept in a password manager is on every device that it syncs with, while section 6.2 "
         "has one key per device")


def key_import(args):
    """Keep on this device a key copied from a password manager (the clipboard, or the standard input)."""
    from . import wallet
    if bool(getattr(args, "clipboard", False)) == bool(getattr(args, "stdin", False)):
        stop("give --clipboard or --stdin")
    if not keys.kept_on_device():
        stop(NOT_KEPT)
    try:
        text = wallet.from_clipboard() if args.clipboard else sys.stdin.read()
    except wallet.WalletError as e:
        stop(str(e))
    try:
        try:
            rk = keys.read_key(text)
        except keys.PassphraseNeeded:
            rk = keys.read_key(text, passphrase(confirm=False))
    except keys.KeyStoreError as e:
        stop(str(e))
    if rk.kind != keys.CURRENT:
        stop("a rotation key is never kept on a device: give its file to the command it signs "
             "(--rotation-key FILE), or keep it in a wallet")
    owner = rk.owner or getattr(args, "owner", None) or ARCHIVE.get("owner")
    if getattr(args, "owner", None) and rk.owner and args.owner != rk.owner:
        stop(f"the key is one of {names.short(rk.owner)}, not of {names.short(args.owner)}")
    if not owner or not names.OWNER_NAME.match(owner):
        stop("the text names no owner: give --owner NAME")
    who = names.short(owner)
    log = key_log(owner) if ROOT is not None else None
    latest = log.latest() if log is not None else None
    if latest is not None and rk.key.did not in latest.keys["keys"]:
        warn(f"{rk.key.did} is not a current key of v{latest.number} of the key log of {who}: it signs "
             f"nothing until a version adds it (osheaf owner rotate --add {rk.key.did})")
    try:
        if keys.current_keys(owner, [rk.key.did]):
            print(f"The current key {names.short(rk.key.did)} of {who} is already on this computer.")
            return
        store = keys.store_current_key(owner, rk.key)
    except (keys.KeyStoreError, OSError) as e:
        stop(str(e))
    print(f"The current key {names.short(rk.key.did)} of {who} is now kept in {store_name(store)}.")


def forget_here(owner, dids):
    """Remove the current keys DIDS of OWNER from this computer, and say so."""
    for did in dids:
        keys.forget_current_key(owner, did)
    if dids:
        print(f"This computer no longer holds {the_keys(len(dids), 'current key')} "
              f"{', '.join(names.short(d) for d in dids)} of {names.short(owner)}.")


def key_forget(args):
    """Remove keys from this device, and with --from-wallet from the wallet; or passkey locks."""
    from . import wallet
    if getattr(args, "passkey", None) or getattr(args, "rp", None):
        return forget_passkey_wraps(args)
    owner, log = owner_of(args)
    who = names.short(owner)
    latest = log.latest()
    listed = set(latest.keys["keys"]) if latest else set()
    committed = {d[:16] for d in latest.keys["next"]} if latest else set()
    dids = list(getattr(args, "did", None) or [])
    if getattr(args, "used", False):
        if not getattr(args, "from_wallet", False) or dids:
            stop("--used goes with --from-wallet, and names no key")
    elif not dids:
        stop("name the keys to forget, by their did:key")
    for did in dids:
        try:
            names.did_key_public(did)
        except ValueError:
            stop(f"not a did:key URI of an Ed25519 key: {did}")
    if not getattr(args, "from_wallet", False):
        forget_here(owner, dids)
        return
    w = wallet_for(args)
    try:
        rows = wallet.listing(w, owner)
    except wallet.WalletError as e:
        stop(str(e))
    if getattr(args, "used", False):
        gone = [r for r in rows if r[3] not in listed and r[1] not in committed]
    else:
        gone = [r for r in rows if r[3] in dids]
    needed = [r for r in gone if r[1] in committed]
    if needed and not getattr(args, "force", False):
        stop(f"{', '.join(names.short(r[3]) for r in needed)}: "
             f"{'a rotation key' if len(needed) == 1 else 'rotation keys'} of the latest version of the key log, "
             "kept (an owner without enough of them to sign the next version can never change its keys, "
             "section 6.2); --force removes them")
    n = len(gone)
    if gone:
        here = f", and {the_keys(len(dids), 'current key')} from this computer" if dids else ""
        print(f"Removing {plural(n, 'key')} of {who} from {w.name}{here}:", file=sys.stderr)
        for r in gone:
            print(f"  {key_label(r[2], r[3])}", file=sys.stderr)
        if not confirmed("forget", args):
            stop("not confirmed: nothing was removed")
    forget_here(owner, dids)
    if not gone:
        print(f"The wallet {w.name} holds none of these keys of {who}.")
        return
    try:
        for i, (o, kid, kind, did, _, _) in enumerate(gone, 1):
            w.forget(o, kid, kind)
            print(f"  {i}/{n} {key_label(kind, did)}  removed", file=sys.stderr)
    except wallet.WalletError as e:
        stop(str(e))
    print(f"Done: {plural(n, 'key')} of {who} removed from {w.name}.")


def forget_passkey_wraps(args):
    """Remove the passkey locks (wrap lines) of --passkey CRED or --rp RP from the keys of the owner
    in the wallet."""
    from collections import Counter
    from . import wallet
    cred, rp = getattr(args, "passkey", None), getattr(args, "rp", None)
    if getattr(args, "did", None) or getattr(args, "used", False):
        stop("--passkey and --rp remove passkey locks, and name no key")
    owner, w = key_owner(args), wallet_for(args)
    who = names.short(owner)
    try:
        w.check_writable()
    except wallet.WalletError as e:
        stop(str(e))
    todo = []
    for kid, text in wallet_entries(w, owner):
        try:
            new = keys.remove_passkeys(text, cred, rp)
        except keys.KeyStoreError as e:
            stop(f"{w.name} {kid}: {e}: nothing was changed")
        if new.strip() != text.strip():
            todo.append((kid, wallet.describe(text), new))
    what = (f"the {rp} lock of the passkey {cred}" if cred and rp else
            f"the {rp} passkey lock" if rp else f"the lock of the passkey {cred}")
    if not todo:
        print(f"No key of {who} in {w.name} has {what}.")
        return
    n = len(todo)
    print(f"Removing {what} from {plural(n, 'key')} of {who} in {w.name}:", file=sys.stderr)
    for _, f, _ in todo:
        print(f"  {key_label(f.get('kind', '?'), f.get('key', '?'))}", file=sys.stderr)
    if not confirmed("forget", args):
        stop("not confirmed: nothing was removed")
    try:
        for i, (kid, f, new) in enumerate(todo, 1):
            kind = f.get("kind", keys.CURRENT)
            w.write(owner, kid, kind, new)
            if (w.read(owner, kid, kind) or "").strip() != new.strip():
                raise wallet.WalletError(f"{w.name} did not keep the {kind} key {f.get('key')}")
            print(f"  {i}/{n} {key_label(kind, f.get('key', kid))}  lock removed", file=sys.stderr)
    except wallet.WalletError as e:
        stop(str(e))
    groups = Counter(tuple(wallet.locks(new)) for _, _, new in todo)
    said = [f"{the_keys(k) if len(groups) == 1 else plural(k, 'key')} {'opens' if k == 1 else 'open'} with "
            f"{lock_words(locks)}" for locks, k in groups.items()]
    print("Done: " + "; ".join(said) + ".")


def sign_again(args):
    """Sign again a version of a line contested by an exposed key (sections 6.4 and 7.1)."""
    obj_id = resolve(args.id)
    d = obj_dir(obj_id)
    inv = load_inventory(d)
    ver = args.version
    if ver not in inv["versions"]:
        stop(f"{args.id} has no object version {ver}")
    owner = obj_id.split(":")[2]
    who = names.short(owner)
    if owner not in archive_owners():
        stop(f"{args.id} is a line of an owner this archive does not host: only its owner signs it")
    log, latest, signers = signing_keys(owner)
    statuses = line_statuses(d, inv, log)[1]
    status = statuses[int(ver[1:]) - 1]
    if status != sign.CONTESTED:
        stop(f"{args.id} {ver} is {status}: signing again is for a version contested by an exposed key "
             "(section 7.1)")
    held = set(witnesses_of(d, ver))
    fresh = [k for k in signers if k.did not in log.exposed_keys() and sign.file_name(k.did) not in held]
    if len(fresh) < latest.keys["threshold"]:
        stop(f"this computer holds {plural(len(fresh), 'current key')} of {who} that "
             f"{'has' if len(fresh) == 1 else 'have'} not signed {ver}, and "
             f"v{latest.number} of the key log needs {latest.keys['threshold']}")
    dig = names.sha512_hex((d / ver / "inventory.json").read_bytes())
    if not getattr(args, "yes", False):
        print(f"Signing {args.id} {ver} again, with {plural(len(fresh), 'current key')} of {who}:")
        print(f"  document version {doc_version_of(d, inv, ver)}, deposited {inv['versions'][ver]['created']}"
              + (f": {inv['versions'][ver]['message']}" if inv["versions"][ver].get("message") else ""))
        print(f"Sign it again only if {who} made this version.")
        if not confirmed(dig[:8]):
            stop("not confirmed: nothing was signed")
    wdir = d / sign.WITNESSES / ver
    wdir.mkdir(parents=True, exist_ok=True)
    pin = log.pin(latest.number)
    for key in fresh:
        with open(wdir / sign.file_name(key.did), "xb") as f:
            f.write(sign.signature_file(key, obj_id, ver, dig, owner, pin))
    write_discovery()
    print(f"Done: {args.id} {ver} signed again by {plural(len(fresh), 'key')} of {who}, under v{latest.number} "
          f"of the key log; it is now {line_statuses(d, inv, log)[1][int(ver[1:]) - 1]}.")
