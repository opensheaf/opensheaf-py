# Generated from literate/10-archive.md by tools/tangle.py: edit the document, not this file.
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

The index is either a TeXmacs document made from a template, as above, or
the website: "index": {"html": {"templates": "templates"}}. Both get landing
pages `paper/<id>/` and `sitemap.xml`, from the templates in the folder
`index.html.templates`, or `index.templates`, or else `templates/` if it
exists, or else the package's defaults.
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

CONFIG_NAME = "osheaf.json"
CONFIG_NAMES = ("osheaf.json", "osheaf.yaml", "osheaf.yml")
SCHEMAS = Path(__file__).resolve().parent / "schemas"
USER_PLUGINS = Path(os.environ.get("TEXMACS_PLUGINS", Path.home() / ".TeXmacs/plugins"))

# set by configure()
ROOT = OCFL = SITE = TM_HOME = None
ARCHIVE = {}
TEXMACS = {}
INDEX = {}

SPEC = "0.1"
LAYOUT = "0002-flat-direct-storage-layout"
ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEXMACS_VERSION = "2.1.5"
REQUIRED = ("archiveId", "name", "baseUrl", "mainCollection", "curator", "depositor")


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


def digest(path, algo="sha512"):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def now():
    return (datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))


def init_storage_root():
    OCFL.mkdir(exist_ok=True)
    (OCFL / "0=ocfl_1.1").write_text("ocfl_1.1\n")
    write_json(OCFL / "ocfl_layout.json", {
        "extension": LAYOUT,
        "description": "Flat direct storage layout: the object identifier is the object's folder name"})
    # the flat-direct layout has no parameters: no extensions/ folder (OCFL
    # forbids empty folders, and ocfl-py rejects a config.json for it)


def load_inventory(obj_dir):
    p = obj_dir / "inventory.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def write_inventory(obj_dir, inv):
    """Write the root inventory and its checksum file, and copies in the head
    version directory (required by OpenSheaf)."""
    for d in (obj_dir, obj_dir / inv["head"]):
        p = d / "inventory.json"
        write_json(p, inv)
        (d / "inventory.json.sha512").write_text(f"{digest(p)} inventory.json\n")


def content_path(inv, version, logical):
    """The content path (relative to the object) of a logical path."""
    for dig, paths in inv["versions"][version]["state"].items():
        if logical in paths:
            return inv["manifest"][dig][0]
    return None


OBJ = "object.json"
OBJ_FORMAT = "opensheaf-object/0.1"
TODAY = datetime.date.today().isoformat()


def read_json(obj_dir, inv, logical, version=None):
    p = read_logical(obj_dir, inv, logical, version)
    return json.loads(p.read_text()) if p else None


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
    AT (default: the head) (section 7.3)."""
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
    (section 7.3)."""
    return history_of(obj_dir, inv, at)[-1]


def next_object_version(inv):
    return f"v{int(inv['head'][1:]) + 1}" if inv else "v1"


def carried_files(obj_id, inv):
    """{logical path: file} of the notice files of the head, which every later
    object version keeps (section 7.3)."""
    if not inv:
        return {}
    d = OCFL / obj_id
    head = read_json(d, inv, OBJ)
    out = {}
    for n in head.get("notices", []):
        if n.get("path"):
            out[n["path"]] = d / content_path(inv, inv["head"], n["path"])
    return out


def carry_forward(prev, new, inv, new_ver, after_doc=None):
    """Keep the notices of the head (they persist unchanged) and its history,
    updated for NEW, the object.json of object version NEW_VER: a new document
    version is appended (or placed after document version AFTER_DOC, which
    then writes a history); a description-only version replaces the entry of
    its document version."""
    if prev is None:
        if after_doc:
            sys.exit("--after needs an existing document")
        return
    if prev.get("notices"):
        new["notices"] = list(prev["notices"])
    if prev.get("history") is None and after_doc is None:
        return
    obj_dir = OCFL / new["objectId"]
    hist = list(prev.get("history") or default_history(obj_dir, inv))
    docs = {doc_version_of(obj_dir, inv, v): v for v in hist}
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
    if OCFL.exists():
        for d in sorted(OCFL.iterdir()):
            if d.is_dir() and (d / "0=ocfl_object_1.1").exists():
                out.append((d.name, d, load_inventory(d)))
    return out


def read_logical(obj_dir, inv, logical, version=None):
    cp = content_path(inv, version or inv["head"], logical)
    return (obj_dir / cp) if cp else None


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


def landing_url(obj_id):
    """The address readers are sent to: the landing page, written with either
    kind of index, or else the HTML version of a TeXmacs document."""
    if INDEX.get("html") or INDEX.get("template"):
        return f"{ARCHIVE['baseUrl']}paper/{obj_id}/"
    return f"{ARCHIVE['baseUrl']}site/{obj_id}/{obj_id}.html"


def deposit(args):
    """Deposit a document, or a new document version of it: a TeXmacs source
    (typeset by the archive), or any source with its PDF (--pdf), or a PDF
    alone (--no-source REASON)."""
    obj_id = args.id
    if not ID_RE.match(obj_id) or len(obj_id) > 64:
        sys.exit("ID must match ^[a-z0-9]+(-[a-z0-9]+)*$ and have at most 64 characters")
    if len(obj_id) > 32:
        print(f"warning: {obj_id} is longer than 32 characters (section 6.3: SHOULD be short)")
    init_storage_root()
    source = Path(args.source) if args.source else None
    for f in [source, args.pdf and Path(args.pdf)] + [Path(x.partition("=")[0]) for x in args.extra_source or []]:
        if f and not f.is_file():
            sys.exit(f"no file {f}")
    obj_dir = OCFL / obj_id
    inv = load_inventory(obj_dir)
    prev_obj = prev_dc = None
    doc_version = 1
    if inv:
        prev_obj, prev_dc = read_json(obj_dir, inv, OBJ), read_json(obj_dir, inv, "datacite.json")
        if prev_obj["kind"] != "document":
            sys.exit(f"{obj_id} is not a document")
        if prev_obj.get("status") == "withdrawn":
            sys.exit(f"{obj_id} is withdrawn (section 11.1): a withdrawn document gets no new versions")
        doc_version = max(doc_version_of(obj_dir, inv, v) for v in inv["versions"]) + 1
    if args.created and args.available:
        sys.exit("give --created (a version not public at the time) or --available, not both")
    available = None if args.created else (args.available or TODAY)
    issued = args.issued or (date_of(prev_dc, "Issued") if prev_dc else None) or available

    tmp = Path(tempfile.mkdtemp())
    texmacs = source is not None and source.suffix == ".tm" and not args.pdf
    if not texmacs and not args.pdf:
        sys.exit("give the PDF of this version with --pdf (only TeXmacs sources are typeset by the archive)")
    if source is None and not args.no_source:
        sys.exit("a deposit without sources needs --no-source REASON (section 9: sourcesMissing)")
    files, formats = {}, []
    if texmacs:
        main = f"{obj_id}.tm"
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
        typeset(source, obj_id, pdf, SITE / obj_id if TEXMACS.get("htmlPackage") or not INDEX.get("html") else None)
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
        "url": landing_url(obj_id),
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
    obj = {
        "format": OBJ_FORMAT,
        "specification": SPEC,
        "kind": "document",
        "archiveId": ARCHIVE["archiveId"],
        "objectId": obj_id,
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
    carry_forward(prev_obj, obj, inv, next_object_version(inv), args.after)
    for lp, f in carried_files(obj_id, inv).items():
        files.setdefault(lp, f)
    write_json(tmp / "datacite.json", datacite)
    write_json(tmp / OBJ, obj)
    files["datacite.json"] = tmp / "datacite.json"
    files[OBJ] = tmp / OBJ
    inv = add_version(obj_id, files, args.message or f"Deposit: document version {doc_version}")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{obj_id}: {inv['head']} (document version {doc_version})")


def mirror_of(obj_dir, inv):
    """The archive whose object this one mirrors (section 10.4), or None."""
    aid = read_json(obj_dir, inv, OBJ).get("archiveId")
    return aid if aid != ARCHIVE["archiveId"] else None


def documents():
    """(obj_id, dir, inventory, current object version, its object.json and
    datacite.json) of every document."""
    out = []
    for obj_id, d, inv in objects():
        if read_json(d, inv, OBJ)["kind"] != "document" or mirror_of(d, inv):
            continue  # collections, and mirrors of other archives' objects
        cur = current_version(d, inv)
        out.append((obj_id, d, inv, cur, read_json(d, inv, OBJ, cur), read_json(d, inv, "datacite.json", cur)))
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


def description_version(obj_id, change, message, add_files=None):
    """Add a description-only version of document OBJ_ID: the files of the
    head (and ADD_FILES, {logical path: file}, such as the file of a notice),
    with datacite.json and object.json changed by CHANGE(dc, obj). The
    document version stays; datacite.json gets the Updated date."""
    obj_dir = OCFL / obj_id
    inv = load_inventory(obj_dir)
    if inv is None:
        sys.exit(f"no object {obj_id}")
    state = {p: d for d, ps in inv["versions"][inv["head"]]["state"].items() for p in ps}
    dc = read_json(obj_dir, inv, "datacite.json")
    prev = read_json(obj_dir, inv, OBJ)
    if prev["kind"] != "document":
        sys.exit(f"{obj_id} is not a document")
    obj = json.loads(json.dumps(prev))
    change(dc, obj)
    set_date(dc, "Updated", TODAY)
    carry_forward(prev, obj, inv, next_object_version(inv))
    tmp = Path(tempfile.mkdtemp())
    write_json(tmp / "datacite.json", dc)
    write_json(tmp / OBJ, obj)
    files = {p: obj_dir / inv["manifest"][d][0] for p, d in state.items()}
    for lp, f in (add_files or {}).items():
        if lp in files:
            sys.exit(f"{obj_id} has a file {lp} already")
        files[lp] = Path(f)
    files["datacite.json"], files[OBJ] = tmp / "datacite.json", tmp / OBJ
    inv = add_version(obj_id, files, message() if callable(message) else message)
    shutil.rmtree(tmp, ignore_errors=True)
    return inv


def note_from(text, file, folder):
    """A note (section 9): a text, a file of the content, or both."""
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
    """A notice about a document version (section 7.3), by a description-only
    version: kept, unchanged, in every later object version."""
    d = OCFL / args.id
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
                              f"Notice about document version {args.about} (description-only version)", add)
    print(f"{args.id}: {inv['head']} (notice about version {args.about})")


def withdraw(args):
    """Withdraw a document (section 11.1): a description-only version with the
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
    inv = description_version(args.id, change, args.message or "Withdrawal (description-only version)", add)
    print(f"{args.id}: {inv['head']} (withdrawn)")


def complete(args):
    """Add the sources of a document version recorded without them
    (sourcesMissing, section 7.3): a new object version holding the files of
    that document version and the sources; its number stays."""
    d = OCFL / args.id
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
    tmp = Path(tempfile.mkdtemp())
    write_json(tmp / "datacite.json", dc)
    write_json(tmp / OBJ, obj)
    files["datacite.json"], files[OBJ] = tmp / "datacite.json", tmp / OBJ
    for lp, f in carried_files(args.id, inv).items():     # notice files are kept
        files.setdefault(lp, f)
    inv = add_version(args.id, files, args.message or
                      f"Sources of document version {args.version} added (sourcesMissing completed)")
    shutil.rmtree(tmp, ignore_errors=True)
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
                              f"Related: {args.relation} {rel['relatedIdentifier']} (description-only version)")
    print(f"{args.id}: {inv['head']} ({args.relation} {rel['relatedIdentifier']})")


def relicense(args):
    """A description-only version with a new licence in datacite.json and the
    authors' agreement in object.json."""
    new = RIGHTS[args.rights]

    def change(dc, obj):
        if dc.get("rightsList") == [new]:
            sys.exit(f"{args.id} already has {args.rights}")
        dc["rightsList"] = [new]
        obj["agreement"] = {"by": [c["name"] for c in dc["creators"]],
                            "date": args.date or TODAY, "method": args.method}
    inv = description_version(args.id, change, args.message or
                              f"Licence: {new['rights']} (description-only version; content unchanged)")
    print(f"{args.id}: {inv['head']} ({new['rights']})")


def describe(args):
    """Correct the description of a document (title, abstract, keywords,
    authors) by a description-only version (section 7.3)."""
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
        lambda: f"Description corrected: {', '.join(changed)} (description-only version)"))
    print(f"{args.id}: {inv['head']} ({', '.join(changed)} corrected)")


ORDER = "issued-desc"


def member_pins(m):
    """[(object version, inventory digest, document version or None)] of a
    member: its version in an archive collection, each revision in a
    selection (section 10.2)."""
    if "revisions" in m:
        return [(r.get("version"), r.get("inventorySha512"), r.get("documentVersion"))
                for r in m["revisions"]]
    return [(m.get("version"), m.get("inventorySha512"), None)]


def presented_version(m, obj_dir, inv):
    """The object version presentations show for member M of an object held
    in OBJ_DIR (section 10.2)."""
    if m.get("revisions"):
        return m["revisions"][-1]["version"]
    return current_version(obj_dir, inv, m["version"])


def member_order(members):
    """Section 10.2: by Issued, then Available (newest first for issued-desc),
    members with neither last, ties broken by object identifier."""
    def key(m):
        c = m.get("cite", {})
        return (c.get("issued") or "", c.get("available") or "")
    dated = sorted((m for m in members if any(key(m))), key=lambda m: m["id"])
    dated.sort(key=key, reverse=(ORDER == "issued-desc"))
    return dated + sorted((m for m in members if not any(key(m))), key=lambda m: m["id"])


def collect(args):
    """A new version of the main collection when a document has a new object
    version; members pin the head of their object and follow it (an archive
    collection, section 10.2)."""
    init_storage_root()
    coll_id = ARCHIVE["mainCollection"]
    cinv = load_inventory(OCFL / coll_id)
    if cinv and read_json(OCFL / coll_id, cinv, "members.json").get("order") == "manual":
        print(f"{coll_id} is curated (order manual): use osheaf collection sync|update")
        return
    members = []
    for obj_id, d, inv, cur, obj, dc in documents():
        cite = {"title": dc["titles"][0]["title"],
                "creators": [display_name(c) for c in dc["creators"]],
                "year": dc["publicationYear"]}
        if date_of(dc, "Issued"):
            cite["issued"] = date_of(dc, "Issued")
        m = {"kind": "document", "archive": ARCHIVE["archiveId"], "archiveUrl": ARCHIVE["baseUrl"],
             "id": obj_id, "version": inv["head"], "inventorySha512": digest(d / inv["head"] / "inventory.json"),
             "follow": "latest", "cite": cite}
        # the Available date only orders, it is not part of the cached citation
        m["cite"]["available"] = date_of(dc, "Available", "Created")
        members.append(m)
    members = member_order(members)
    for m in members:
        m["cite"].pop("available", None)
    coll_dir = OCFL / coll_id
    inv = load_inventory(coll_dir)
    version, issued = 1, TODAY
    if inv:
        old = read_json(coll_dir, inv, "members.json")
        if old["members"] == members and old.get("type") == "archive":
            print(f"{coll_id}: unchanged ({inv['head']})")
            return
        version = read_json(coll_dir, inv, OBJ)["documentVersion"] + 1
        issued = date_of(read_json(coll_dir, inv, "datacite.json"), "Issued") or TODAY
    cur = ARCHIVE["curator"]
    tmp = Path(tempfile.mkdtemp())
    write_json(tmp / "members.json", {"format": "opensheaf-collection/0.1", "type": "archive",
                                      "order": ORDER, "members": members})
    write_json(tmp / "datacite.json", {
        "titles": [{"title": ARCHIVE["name"]}],
        "creators": [{"name": cur["name"], "nameType": "Personal", "givenName": cur["givenName"],
                      "familyName": cur["familyName"], "affiliation": [{"name": cur["affiliation"]}]}],
        "publisher": {"name": ARCHIVE["name"]},
        "publicationYear": int(issued[:4]),
        "types": {"resourceTypeGeneral": "Collection"},
        "version": str(version),
        "url": ARCHIVE["baseUrl"],
        "dates": [{"date": issued, "dateType": "Issued"}, {"date": TODAY, "dateType": "Available"}],
        "descriptions": [{"description": "The documents deposited in this archive, newest first.",
                          "descriptionType": "Abstract"}],
        "rightsList": [dict(RIGHTS["cc0-1.0"])],
    })
    write_json(tmp / OBJ, {
        "format": OBJ_FORMAT, "specification": SPEC, "kind": "collection",
        "archiveId": ARCHIVE["archiveId"], "objectId": coll_id, "documentVersion": version,
        "status": "active",
    })
    inv = add_version(coll_id, {n: tmp / n for n in ("members.json", "datacite.json", OBJ)},
                      f"Collection version {version}: {len(members)} documents")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{coll_id}: {inv['head']} ({len(members)} members)")


def discovery():
    objs = []
    for obj_id, d, inv in objects():
        obj = read_json(d, inv, OBJ)
        entry = {"id": obj_id, "kind": obj["kind"], "head": inv["head"],
                 "inventorySha512": (d / "inventory.json.sha512").read_text().split()[0],
                 "status": obj["status"]}
        if mirror_of(d, inv):
            entry["mirrorOf"] = mirror_of(d, inv)
        objs.append(entry)
    return {"format": "opensheaf-archive/0.1", "specification": SPEC,
            "archiveId": ARCHIVE["archiveId"], "name": ARCHIVE["name"],
            "contact": ARCHIVE["contact"], "storageRoot": "ocfl/", "storageLayout": LAYOUT,
            "mainCollection": ARCHIVE["mainCollection"], "profiles": ARCHIVE["profiles"],
            "objects": objs}


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
    obj_id = member["id"]
    d = OCFL / obj_id
    inv = load_inventory(d)
    ver = presented_version(member, d, inv)
    pin_ver, pin = member_pins(member)[-1][:2]
    obj = read_json(d, inv, OBJ, ver)
    dc = read_json(d, inv, "datacite.json", ver)
    pdf = content_path(inv, ver, pdf_of(obj)) if pdf_of(obj) else None
    src = f"ocfl/{obj_id}/" + content_path(inv, ver, obj["mainSource"]) if obj.get("mainSource") else None
    html = f"site/{obj_id}/{obj_id}.html"
    texmacs = obj.get("sourceFormat") == "application/x-texmacs"
    title = tm_with_math(dc["titles"][0]["title"])
    authors = tm_escape(authors_of(dc))
    if not authors.endswith("."):
        authors += "."
    links = [f"<hlink|PDF|ocfl/{obj_id}/{pdf}>"] if pdf else []
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
    head = f"<hlink|{title}|paper/{obj_id}/>"
    return f"""  <\\notes-news-item>
    <with|font-series|bold|{head}>

    By {authors}

    {sep.join(links)}

{abstract}    <with|font-size|0.84|par-mode|left|{when}<next-line>pin:
    <hlink|<verbatim|{pin[:32]}...>|ocfl/{obj_id}/{pin_ver}/inventory.json>>
  </notes-news-item>"""


def index(args):
    write_json(ROOT / "opensheaf.json", discovery())
    coll_dir = OCFL / ARCHIVE["mainCollection"]
    inv = load_inventory(coll_dir)
    members = json.loads(read_logical(coll_dir, inv, "members.json").read_text())["members"]
    if INDEX.get("html"):
        from . import html
        html.render(members)
        local = sum(1 for m in members if m.get("archive") == ARCHIVE["archiveId"])
        print(f"opensheaf.json, index.html, {local} landing pages and sitemap.xml written")
        return
    if not INDEX.get("template"):
        print("opensheaf.json written (no index configured)")
        return
    template = (ROOT / INDEX["template"]).read_text(encoding="latin-1")
    line = "  <paper-index>\n"
    if template.count(line) != 1:
        sys.exit(f"{INDEX['template']} must contain one paragraph <paper-index>")
    from . import html
    pages = html.render(members, home=False)
    entries = "\n\n".join(index_entry(m) for m in members)
    with open(ROOT / "index.tm", "w", encoding="latin-1", newline="") as f:
        f.write(template.replace(line, entries + "\n"))
    (ROOT / ".texmacs-noconvert").touch()
    if not args.no_html:
        scratch = Path(tempfile.mkdtemp())
        run_texmacs(export_calls(ROOT / "index.tm", pdf=scratch / "index.pdf",
                                 html=ROOT / "index.html"))
        shutil.rmtree(scratch, ignore_errors=True)
    print("opensheaf.json, index.tm" + ("" if args.no_html else ", index.html")
          + f", {pages} landing pages and sitemap.xml written")


def document_version_errors(obj_id, d, inv):
    """Section 7.3: numbering without gaps, the same files for the same
    document version (a version with sourcesMissing may be completed by adding
    files), the history, and notices kept unchanged."""
    errors, where = [], f"ocfl/{obj_id}"
    seen, files_of, missing_of, highest = {}, {}, {}, 0
    had_history, notices = False, []
    for ver, vinfo in inv["versions"].items():
        obj = read_json(d, inv, OBJ, ver)
        if obj is None or obj.get("kind") != "document":
            return errors
        n = obj["documentVersion"]
        notes = {x["path"] for x in obj.get("notices", []) if x.get("path")}
        if obj.get("withdrawal", {}).get("reason", {}).get("path"):
            notes.add(obj["withdrawal"]["reason"]["path"])
        own = {p: dig for dig, ps in vinfo["state"].items() for p in ps
               if p not in ("datacite.json", OBJ) and p not in notes}
        change = (obj.get("changes") or {}).get("text")
        if n in seen:
            before, mis = files_of[n], missing_of[n]
            if mis:
                if any(before.get(p) not in (None, dig) for p, dig in own.items()) or not set(before) <= set(own):
                    errors.append(f"{where}: {ver} changes files of document version {n} (only additions allowed)")
            elif own != before or change != seen[n]:
                errors.append(f"{where}: {ver} has other files than document version {n}")
            missing_of[n] = bool(obj.get("sourcesMissing"))
            files_of[n] = own
        else:
            if n != highest + 1:
                errors.append(f"{where}: {ver} document version {n} breaks the numbering (expected {highest + 1})")
            highest = max(highest, n)
            seen[n], files_of[n], missing_of[n] = change, own, bool(obj.get("sourcesMissing"))
        hist = obj.get("history")
        if had_history and hist is None:
            errors.append(f"{where}: {ver} lacks the history of earlier versions")
        if hist is not None:
            had_history = True
            known = [v for v in inv["versions"] if int(v[1:]) <= int(ver[1:])]
            if any(h not in known for h in hist):
                errors.append(f"{where}: {ver} history names unknown object versions")
            else:
                docs = [read_json(d, inv, OBJ, h)["documentVersion"] for h in hist]
                if len(set(docs)) != len(docs) or set(docs) != set(range(1, highest + 1)):
                    errors.append(f"{where}: {ver} history does not list each document version once")
                for h, k in zip(hist, docs):
                    later = [v for v in known if int(v[1:]) > int(h[1:])
                             and read_json(d, inv, OBJ, v)["documentVersion"] == k]
                    if later:
                        errors.append(f"{where}: {ver} history entry {h} is not the last object version of {k}")
        cur = obj.get("notices", [])
        if any(x not in cur for x in notices):
            errors.append(f"{where}: {ver} drops or changes an earlier notice")
        notices = cur
    return errors


def verify_errors():
    errors = []
    try:
        import jsonschema
    except ImportError:
        jsonschema = None

    def check_schema(where, data, name):
        if jsonschema is None:
            return
        schema = json.loads((SCHEMAS / name).read_text())
        v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
        for e in v.iter_errors(data):
            errors.append(f"{where}: {e.message}")

    disc_path = ROOT / "opensheaf.json"
    if not disc_path.exists():
        return ["opensheaf.json is missing"]
    disc = json.loads(disc_path.read_text())
    check_schema("opensheaf.json", disc, "opensheaf-archive-0.1.schema.json")
    if disc.get("storageLayout") != LAYOUT or not (OCFL / "0=ocfl_1.1").exists():
        errors.append("storage root missing or with another layout")
    listed = {o["id"]: o for o in disc.get("objects", [])}
    found = {obj_id: (d, inv) for obj_id, d, inv in objects()}
    for obj_id in set(listed) ^ set(found):
        errors.append(f"opensheaf.json and the storage root disagree about {obj_id}")
    for obj_id, (d, inv) in found.items():
        if obj_id in listed and listed[obj_id].get("mirrorOf") != mirror_of(d, inv):
            errors.append(f"opensheaf.json: {obj_id} " + (f"is a mirror of {mirror_of(d, inv)}, without mirrorOf"
                          if mirror_of(d, inv) else "is listed as a mirror, and is not one"))

    for obj_id, (d, inv) in found.items():
        where = f"ocfl/{obj_id}"
        if inv.get("id") != obj_id or not ID_RE.match(obj_id) or len(obj_id) > 64:
            errors.append(f"{where}: bad identifier")
        if inv.get("digestAlgorithm") != "sha512":
            errors.append(f"{where}: digest algorithm is not sha512")
        side = (d / "inventory.json.sha512").read_text().split()[0]
        if side != digest(d / "inventory.json"):
            errors.append(f"{where}: inventory checksum file does not match")
        lst = listed.get(obj_id)
        if lst and (lst["head"] != inv["head"] or lst["inventorySha512"] != side):
            errors.append(f"opensheaf.json: stale entry for {obj_id}")
        for dig, paths in inv["manifest"].items():
            for cp in paths:
                if not (d / cp).exists():
                    errors.append(f"{where}: missing {cp}")
                elif digest(d / cp) != dig:
                    errors.append(f"{where}: digest mismatch for {cp}")
        for ver, vinfo in inv["versions"].items():
            if not (d / ver / "inventory.json").exists() or not (d / ver / "inventory.json.sha512").exists():
                errors.append(f"{where}: {ver} has no inventory copy")
            if not vinfo.get("user", {}).get("name") or not vinfo.get("message"):
                errors.append(f"{where}: {ver} lacks a user name or a message")
            logical = {p for ps in vinfo["state"].values() for p in ps}
            for p in logical:
                parts = p.split("/")
                if p.startswith("/") or ".." in parts or "." in parts:
                    errors.append(f"{where}: bad logical path {p}")
            missing = [n for n in ("datacite.json", OBJ) if n not in logical]
            for n in missing:
                errors.append(f"{where}: {ver} has no {n}")
            if missing:
                continue
            obj = read_json(d, inv, OBJ, ver)
            dc = read_json(d, inv, "datacite.json", ver)
            check_schema(f"{where}/{ver}/{OBJ}", obj, "opensheaf-object-0.1.schema.json")
            if obj.get("objectId") != obj_id:
                errors.append(f"{where}: {ver} object.json names another object")
            elif obj.get("archiveId") != (mirror_of(d, inv) or disc.get("archiveId")):
                errors.append(f"{where}: {ver} object.json names another archive")
            if str(obj.get("documentVersion")) != dc.get("version"):
                errors.append(f"{where}: {ver} datacite.json and object.json disagree on the version")
            if obj.get("status") == "withdrawn" and date_of(dc, "Withdrawn") != obj.get("withdrawal", {}).get("date"):
                errors.append(f"{where}: {ver} withdrawal dates disagree")
            for k in ("titles", "creators", "publicationYear", "types", "version", "publisher"):
                if k not in dc:
                    errors.append(f"{where}: {ver} datacite.json lacks {k}")
            for r in dc.get("rightsList", []):
                if r.get("rightsIdentifier") is None and r.get("rights", "").lower().startswith(("creative", "arxiv")) \
                        and not r.get("rightsUri"):
                    errors.append(f"{where}: {ver} licence without SPDX identifier and without rightsUri")
            for note in [obj.get("changes"), obj.get("sourcesMissing"), obj.get("licence")] + \
                    obj.get("notices", []) + [obj.get("withdrawal", {}).get("reason")]:
                if note and note.get("path") and note["path"] not in logical:
                    errors.append(f"{where}: {ver} note file {note['path']} not in the version")
            if obj.get("kind") == "document":
                if obj.get("mainSource") and obj["mainSource"] not in logical:
                    errors.append(f"{where}: {ver} main source not in the version")
                if obj.get("sourcesMissing") and obj.get("mainSource"):
                    errors.append(f"{where}: {ver} sourcesMissing together with a main source")
                for r in obj.get("renditions", []):
                    if r["path"] not in logical:
                        errors.append(f"{where}: {ver} rendition {r['path']} not in the version")
            elif "members.json" not in logical:
                errors.append(f"{where}: {ver} collection without members.json")
            else:
                mem = read_json(d, inv, "members.json", ver)
                check_schema(f"{where}/{ver}/members.json", mem, "opensheaf-collection-0.1.schema.json")
                kind = mem.get("type")
                if kind not in ("archive", "selection"):
                    errors.append(f"{where}: {ver} members.json has no valid type (archive or selection)")
                for m in mem.get("members", []):
                    who = f"{where}: {ver} member {m.get('id')}"
                    if kind == "archive" and (not m.get("version") or not m.get("inventorySha512") or "revisions" in m):
                        errors.append(f"{who}: a member of an archive collection needs version and inventorySha512, "
                                      "and no revisions")
                    if kind == "selection":
                        revs = m.get("revisions")
                        if any(k in m for k in ("version", "inventorySha512", "follow")):
                            errors.append(f"{who}: a member of a selection has no version, inventorySha512 or follow")
                        if not isinstance(revs, list) or not revs or any(
                                not all(r.get(k) for k in ("documentVersion", "version", "inventorySha512")) for r in revs):
                            errors.append(f"{who}: a member of a selection needs revisions, each with documentVersion, "
                                          "version and inventorySha512")
                        elif len({r["documentVersion"] for r in revs}) != len(revs):
                            errors.append(f"{who}: a document version is vetted twice")
                for m in mem.get("members", []):
                    if m.get("archive") != disc.get("archiveId") or mirror_of(d, inv):
                        continue  # members of other archives: resolved as in section 6.4
                    for pv, pin, n in member_pins(m):
                        md = OCFL / str(m.get("id")) / str(pv) / "inventory.json"
                        if not md.exists():
                            errors.append(f"{where}: {ver} member {m['id']} {pv}: unavailable")
                        elif digest(md) != pin:
                            errors.append(f"{where}: {ver} member {m['id']} {pv}: mismatch")
                        elif n is not None and doc_version_of(OCFL / m["id"], load_inventory(OCFL / m["id"]), pv) != n:
                            errors.append(f"{where}: {ver} member {m['id']} {pv} does not hold document version {n}")
                    if kind == "selection" and (OCFL / str(m.get("id"))).exists():
                        md = OCFL / m["id"]
                        order = [doc_version_of(md, load_inventory(md), h) for h in history_of(md, load_inventory(md))]
                        vetted = [r.get("documentVersion") for r in m.get("revisions") or []]
                        pos = [order.index(x) for x in vetted if x in order]
                        if pos != sorted(pos):
                            errors.append(f"{where}: {ver} member {m['id']}: revisions not in the order of the history")
        errors += document_version_errors(obj_id, d, inv)

    # an independent OCFL validator, when installed
    try:
        import ocfl
        from ocfl.validator import Validator
    except ImportError:
        ocfl = None
    if ocfl is not None:
        for obj_id, (d, inv) in found.items():
            v = Validator(log_warnings=False, log_errors=True)
            if not v.validate_object(str(d)):
                errors.append(f"ocfl/{obj_id}: OCFL validator: {v.status_str()}")
        if not ocfl.StorageRoot(root=str(OCFL)).validate(log_warnings=False):
            errors.append("ocfl: the OCFL validator rejects the storage root")

    # the presentation shows the current pins
    coll = found.get(disc.get("mainCollection"))
    if coll and (ROOT / "index.html").exists():
        html = (ROOT / "index.html").read_text(encoding="utf-8", errors="replace")
        mem = json.loads(read_logical(coll[0], coll[1], "members.json").read_text())
        for m in mem["members"]:
            if (member_pins(m)[-1][1] or "")[:32] not in html:
                errors.append(f"index.html does not show the pin of {m['id']}")
    return errors


def verify(args):
    errors = verify_errors()
    if getattr(args, "remote", False):
        from . import collections
        for obj_id, d, inv in objects():
            if read_json(d, inv, OBJ)["kind"] == "collection" and not mirror_of(d, inv):
                errors += [f"{obj_id}: {e}" for e in
                           collections.check_remote(read_json(d, inv, "members.json")["members"])]
        errors += collections.check_accepted_copies()
    for e in errors:
        print(e)
    print("OK" if not errors else f"{len(errors)} problem(s)")
    sys.exit(1 if errors else 0)


def init(args):
    """Create an archive in the folder: osheaf.json, the storage root, the
    templates of the website (to edit), the empty main collection, the
    discovery document and the pages."""
    root = Path(args.folder or ".").resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any((root / n).exists() for n in CONFIG_NAMES):
        sys.exit(f"{root} has a configuration already")
    family, _, given = args.curator.partition(",")
    family, given = family.strip(), given.strip()
    cfg = {
        "archiveId": args.archive_id,
        "name": args.name,
        "contact": args.contact or args.base_url,
        "baseUrl": args.base_url if args.base_url.endswith("/") else args.base_url + "/",
        "profiles": ["website"],
        "mainCollection": "collection-main",
        "curator": {"name": f"{family}, {given}" if given else family, "givenName": given,
                    "familyName": family, "affiliation": args.affiliation or ""},
        "depositor": {"name": f"{given} {family}".strip(), "address": args.contact or args.base_url},
        "index": {"html": {"templates": "templates"}},
    }
    (root / CONFIG_NAME).write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    from . import html
    (root / "templates").mkdir(exist_ok=True)
    for f in html.DEFAULTS.iterdir():
        if not (root / "templates" / f.name).exists():
            shutil.copyfile(f, root / "templates" / f.name)
    configure(root)
    init_storage_root()
    if str(getattr(args, "curated", "")).lower() in ("1", "true", "yes"):
        # a curated collection: members from any archive, in the curator's order
        from . import collections
        collections.write(cfg["mainCollection"], [], args.name, "A collection of documents.", "manual",
                          "Collection created (curated)")
    else:
        collect(None)
    index(argparse_namespace(no_html=False))
    print(f"archive created in {root}: edit {CONFIG_NAME} and templates/, then deposit")
    print("note: OpenSheaf 0.1 is a draft; until version 1.0 a revision may change the format in"
          " incompatible ways, and archives may have to be rebuilt or migrated")


def argparse_namespace(**kw):
    import argparse
    return argparse.Namespace(**kw)
