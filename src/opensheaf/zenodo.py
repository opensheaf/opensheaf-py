# Generated from literate/50-zenodo.md by opensheaf-literate: edit the document, not this file.
"""Zenodo binding of OpenSheaf 0.2 (appendix A.1 of the specification).

    osheaf zenodo LABEL [--production] [--keep]

Deposits the current document version of the line LABEL (the last of the
history of its latest signed version, section 4.2) on Zenodo and adds a
description-only object version holding it, signed by the owner, whose
datacite.json carries the version DOI and whose object.json records the Zenodo
record under `external` (role `deposit`).

The first deposit of a line creates a Zenodo record (its concept DOI stands for
the line); later document versions are new versions of that record, linked
IsNewVersionOf the DOI of the version before them in the history. Zenodo orders
record versions by publication, so a document version that is not the current
one (an earlier version found later) is not deposited as a new version of the
record (appendix A.1). Files of notices are not uploaded: the files of a
published record version are fixed. A version that was not public at the time
gets its Available date when Zenodo publishes it. Order of operations (appendix
A.1): create the draft (Zenodo reserves its DOI), build the object version with
that DOI in a staging folder and sign it, upload the files and compare their MD5
checksums with the inventory's fixity, publish, then add the object version
with its signatures and rewrite opensheaf.json.

Without --production the Zenodo sandbox is used, and everything is done on a
temporary copy of the line and of its owner's key log, so that test DOIs never
enter the archive; the copy is printed and removed unless --keep is given.

Tokens: the environment variable ZENODO_TOKEN (production) or
ZENODO_SANDBOX_TOKEN (sandbox); otherwise the system's credential store,
under the service name zenodo-token or zenodo-sandbox-token and the login
name, read through the Python package keyring (pip install
'opensheaf[zenodo]': macOS keychain, Windows Credential Manager, Secret
Service on Linux); on macOS also the keychain directly. To store a token:
    keyring set zenodo-token "$USER"                              (any system)
    security add-generic-password -a "$USER" -s zenodo-token -w   (macOS)

If publication succeeds and adding the version fails, the staging folder
zenodo-staging/<owner>/<name>/ is kept, the line takes no other version, and
the next run adds the version from it before anything else, signing it again
if a key that signed it was exposed meanwhile (appendix A.1).
"""

import datetime
import getpass
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

SERVICES = {
    False: {"api": "https://sandbox.zenodo.org/api", "records": "https://sandbox.zenodo.org/records/",
            "token": "zenodo-sandbox-token", "env": "ZENODO_SANDBOX_TOKEN", "prefix": "10.5072"},
    True: {"api": "https://zenodo.org/api", "records": "https://zenodo.org/records/",
           "token": "zenodo-token", "env": "ZENODO_TOKEN", "prefix": "10.5281"},
}
SERVICE_NAME = "Zenodo"
MAX_FILES = 100          # Zenodo's limit on files per record
METADATA_FILES = ("datacite.json", "object.json")
PUBLICATION_TYPES = {"Preprint": "preprint", "JournalArticle": "article", "Book": "book",
                     "BookChapter": "section", "Dissertation": "thesis", "Report": "report",
                     "ConferencePaper": "conferencepaper", "Text": "other"}
SCHEMES = {"arXiv": "arxiv", "DOI": "doi", "URL": "url", "Handle": "handle", "ISBN": "isbn",
           "ISSN": "issn", "PMID": "pmid", "SWHID": "swh"}
# Licences Zenodo knows under the SPDX identifier (lower case); anything else
# (All rights reserved, the arXiv licence) is "other-closed": Other (Not Open).
OPEN_LICENCES = {"cc-by-4.0", "cc-by-sa-4.0", "cc-by-nc-4.0", "cc-by-nd-4.0", "cc-by-nc-sa-4.0",
                 "cc-by-nc-nd-4.0", "cc0-1.0", "mit", "apache-2.0", "gpl-3.0-or-later"}


def read_token(s):
    """The token of the service s (an entry of SERVICES), or None."""
    token = os.environ.get(s["env"], "").strip()
    if token:
        return token
    try:
        import keyring
        token = keyring.get_password(s["token"], getpass.getuser())
    except Exception:   # no keyring, no store, or a store that refuses
        token = None
    if token and token.strip():
        return token.strip()
    if sys.platform == "darwin" and shutil.which("security"):
        r = subprocess.run(["security", "find-generic-password", "-s", s["token"], "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


class Zenodo:
    def __init__(self, production):
        self.production = production
        self.s = SERVICES[production]
        self.token = read_token(self.s)
        if not self.token:
            sys.exit(f"no Zenodo token: set {self.s['env']}, or store it under the name "
                     f"{self.s['token']} (see osheaf zenodo --help)")

    def call(self, method, url, data=None, raw=None):
        if not url.startswith("http"):
            url = self.s["api"] + url
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        ctype = "application/octet-stream" if raw is not None else "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": ctype,
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                t = r.read()
                return json.loads(t) if t else None
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Zenodo {method} {url}: {e.code} {e.read().decode()[:1000]}")

    def doi(self, recid):
        return f"{self.s['prefix']}/zenodo.{recid}"


def zenodo_metadata(dc, archive, obj_id):
    """Zenodo deposit metadata from datacite.json (Zenodo generates its own
    DataCite record from it; datacite.json stays authoritative)."""
    creators = []
    for c in dc["creators"]:
        z = {"name": c["name"]}
        affs = [a["name"] if isinstance(a, dict) else a for a in c.get("affiliation", [])]
        if affs:
            z["affiliation"] = "; ".join(affs)
        for ni in c.get("nameIdentifiers", []):
            if ni.get("nameIdentifierScheme") == "ORCID":
                z["orcid"] = ni["nameIdentifier"].rsplit("/", 1)[-1]
        creators.append(z)
    abstract = next((d["description"] for d in dc.get("descriptions", [])
                     if d.get("descriptionType") == "Abstract"), None)
    description = ("".join(f"<p>{html.escape(p.strip())}</p>" for p in abstract.split("\n\n"))
                   if abstract else f"<p>{html.escape(dc['titles'][0]['title'])}</p>")
    dates = {d["dateType"]: d["date"] for d in dc.get("dates", [])}
    rights = dc.get("rightsList", [{}])[0]
    licence = rights.get("rightsIdentifier", "").lower()
    rtype = dc["types"]["resourceTypeGeneral"]
    m = {
        "upload_type": "publication",
        "publication_type": PUBLICATION_TYPES.get(rtype, "other"),
        "title": dc["titles"][0]["title"],
        "creators": creators,
        "description": description,
        "access_right": "open",
        "license": licence if licence in OPEN_LICENCES else "other-closed",
        "version": dc["version"],
        "publication_date": (dates.get("Issued") or dates.get("Available"))[:10],
        "notes": (f"Deposited from the OpenSheaf archive {archive['name']} ({archive['baseUrl']}), "
                  f"line {obj_id}, document version {dc['version']}. "
                  f"Rights: {rights.get('rights', 'see the files')}."),
    }
    if dc.get("language") == "en":
        m["language"] = "eng"
    keywords = [s["subject"] for s in dc.get("subjects", [])]
    if keywords:
        m["keywords"] = keywords
    related = [{"identifier": dc["url"], "relation": "isIdenticalTo", "scheme": "url"}]
    for r in dc.get("relatedIdentifiers", []):
        rel = r["relationType"]
        # Zenodo states the versioning relations of its own records itself
        if rel in ("IsVersionOf", "IsNewVersionOf", "IsPreviousVersionOf") and "zenodo" in r["relatedIdentifier"]:
            continue
        scheme = SCHEMES.get(r["relatedIdentifierType"])
        if scheme:
            related.append({"identifier": r["relatedIdentifier"],
                            "relation": rel[0].lower() + rel[1:], "scheme": scheme})
    m["related_identifiers"] = related
    return m


def zenodo_entries(obj):
    return [e for e in obj.get("external", [])
            if e.get("service") == SERVICE_NAME and e.get("role") == "deposit"]


def reproducible_zip(dest, files):
    """sources.zip as appendix A.1 asks: entries in byte order of their names,
    fixed timestamps, no extra attributes."""
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files, key=lambda n: n.encode()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            z.writestr(info, Path(files[name]).read_bytes())


def upload_plan(P, files, obj, stage):
    """{name on Zenodo: local file}, and the extra files (sources.zip) whose
    digests go into the deposit's entry in object.json. The record holds the content files as
    deposited; sources with sub-folders, or too many files, go into
    sources.zip."""
    if not any("/" in n for n in files) and len(files) <= MAX_FILES:
        return dict(files), []
    keep = set(METADATA_FILES) | {r["path"] for r in obj.get("renditions", [])}
    sources = {n: f for n, f in files.items() if n not in keep}
    if any("/" in n for n in keep):
        sys.exit("renditions in sub-folders cannot be uploaded to Zenodo")
    z = stage / "sources.zip"
    reproducible_zip(z, sources)
    plan = {n: f for n, f in files.items() if n in keep}
    plan["sources.zip"] = z
    extra = [{"name": "sources.zip", "sha512": P.digest(z), "md5": P.digest(z, "md5"),
              "bytes": z.stat().st_size}]
    return plan, extra


def notice_files(obj):
    paths = {n["path"] for n in obj.get("notices", []) if n.get("path")}
    reason = obj.get("withdrawal", {}).get("reason", {})
    if reason.get("path"):
        paths.add(reason["path"])
    return paths


def version_files(P, obj_dir, inv, ver):
    return {lp: obj_dir / P.content_path(inv, ver, lp)
            for paths in inv["versions"][ver]["state"].values() for lp in paths}


def previous_record(P, obj_dir, inv, doc_version, signed):
    """The Zenodo record id and DOI of the latest document version before
    DOC_VERSION in the history (as of SIGNED) that is on Zenodo."""
    hist = P.history_of(obj_dir, inv, signed)
    docs = [P.doc_version_of(obj_dir, inv, v) for v in hist]
    before = docs[:docs.index(doc_version)] if doc_version in docs else docs
    for n in reversed(before):
        # any object version holding document version n may carry its deposit
        for v in sorted(inv["versions"], key=lambda v: int(v[1:]), reverse=True):
            obj = P.read_json(obj_dir, inv, P.OBJ, v)
            if obj["documentVersion"] == n and zenodo_entries(obj):
                e = zenodo_entries(obj)[0]
                return e["record"].rstrip("/").rsplit("/", 1)[-1], e["doi"]
    return None, None


def commit(P, obj_id, stage, state):
    label = P.label_of(obj_id) or obj_id
    d = P.obj_dir(obj_id)
    if state["phase"] == "published":
        inv = P.install_version(obj_id, stage / "version")
        state["phase"] = "added"
        P.write_json(stage / "state.json", state)
    else:
        inv = P.load_inventory(d)
    ver = state.get("version") or inv["head"]
    statuses = P.line_statuses(d, P.load_inventory(d))[1]
    if statuses[int(ver[1:]) - 1] == P.sign.CONTESTED:
        print(f"{label}: {ver} is contested (a key that signed it was exposed): signing it again")
        P.sign_again(P.argparse_namespace(id=obj_id, version=ver, yes=True))
    P.write_discovery()
    remove_stage(P, stage)
    print(f"{label}: {ver} added, DOI {state['doi']}")


def remove_stage(P, stage):
    shutil.rmtree(stage, ignore_errors=True)
    parent = stage.parent
    while parent != P.ROOT and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def check_deposit_record(P, obj, doi):
    """Stop, before anything is uploaded, if OBJ (the object.json built) is malformed."""
    f = P.Findings()
    P.schema_checker(f)("object.json", obj, "object")
    problems = [x["message"] for x in f if x["severity"] == "error"]
    for e in obj.get("external", []):
        if not all(isinstance(e.get(k), str) and e.get(k) for k in ("role", "service", "record")):
            problems.append(f"an external entry lacks role, service or record: {e}")
        elif e["role"] not in ("deposit", "source") or not e["record"].startswith("https://"):
            problems.append(f"an external entry with a bad role or record: {e}")
        if "doi" in e and not re.match(r"^10\.[0-9]+(\.[0-9]+)*/\S+\Z", str(e["doi"])):
            problems.append(f"an external entry with a malformed DOI: {e['doi']}")
    if not [e for e in zenodo_entries(obj) if e.get("doi") == doi]:
        problems.append(f"no external entry of the deposit of {doi}")
    if problems:
        raise RuntimeError("the object version built is malformed: " + "; ".join(problems))


def deposit(P, label, z):
    obj_id = P.resolve(label)
    label = P.label_of(obj_id) or obj_id.split(":")[1]
    obj_dir = P.obj_dir(obj_id)
    inv = P.load_inventory(obj_dir)
    if inv is None:
        sys.exit(f"no line {label}")
    stage = P.ROOT / "zenodo-staging" / P.path_of(obj_id)
    state_path = stage / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["phase"] in ("published", "added"):
            print(f"{label}: completing the object version of record {state['record']}")
            return commit(P, obj_id, stage, state)
        print(f"{label}: discarding the unpublished draft {state['record']}")
        try:
            z.call("DELETE", f"/deposit/depositions/{state['record']}")
        except RuntimeError as e:
            print(f"  (could not discard: {e})")
        remove_stage(P, stage)

    head_obj = P.read_json(obj_dir, inv, P.OBJ)
    if head_obj.get("kind") != "document":
        sys.exit(f"{label} is not a document")
    if head_obj.get("parent"):
        sys.exit(f"{label} is a branch (section 9), which these tools do not deposit on Zenodo yet")
    signed = P.latest_signed(obj_dir, inv)
    if signed is None:
        sys.exit(f"{label} has no signed version that is not contested (section 7.3): nothing is deposited")
    state_obj = P.read_json(obj_dir, inv, P.OBJ, signed)
    if state_obj.get("status") != "active":
        sys.exit(f"{label} is withdrawn")
    # the current version: the last of the history (section 4.2)
    cur = P.current_version(obj_dir, inv, signed)
    obj = P.read_json(obj_dir, inv, P.OBJ, cur)
    dc = P.read_json(obj_dir, inv, "datacite.json", cur)
    doc_version = obj["documentVersion"]
    if zenodo_entries(obj):
        sys.exit(f"{label}: document version {doc_version} is already on Zenodo "
                 f"({zenodo_entries(obj)[0]['doi']})")

    # 1-2. Draft: a new record, or a new version of the document's record;
    # Zenodo reserves the DOI when the draft is created.
    prev_rec, prev_doi = previous_record(P, obj_dir, inv, doc_version, signed)
    if prev_rec:
        nv = z.call("POST", f"/deposit/depositions/{prev_rec}/actions/newversion")
        draft = z.call("GET", nv["links"]["latest_draft"])
        for f in draft.get("files", []):     # a new version inherits the files
            z.call("DELETE", f"/deposit/depositions/{draft['id']}/files/{f['id']}")
    else:
        draft = z.call("POST", "/deposit/depositions", {})
    recid = draft["id"]
    concept = draft.get("conceptrecid")
    doi = z.doi(recid)
    concept_doi = z.doi(concept) if concept else None
    stage.mkdir(parents=True)
    state = {"phase": "draft", "record": recid, "doi": doi, "documentVersion": doc_version}
    P.write_json(state_path, state)

    try:
        # 3. the object version, built in the staging area; its files are those of the
        # object version holding the current version, and the files of the notices
        files = {lp: f for lp, f in version_files(P, obj_dir, inv, cur).items() if lp not in METADATA_FILES}
        skip = notice_files(state_obj)
        for n in state_obj.get("notices", []):
            if n.get("path") and n["path"] not in files:
                files[n["path"]] = obj_dir / P.content_path(inv, signed, n["path"])
        today = datetime.date.today().isoformat()
        dc["doi"] = doi
        dc["url"] = dc.get("url") or P.landing_url(label)
        rel = [r for r in dc.get("relatedIdentifiers", [])
               if not (r["relationType"] in ("IsVersionOf", "IsNewVersionOf")
                       and "zenodo" in r["relatedIdentifier"])]
        if concept_doi:
            rel.append({"relatedIdentifier": concept_doi, "relatedIdentifierType": "DOI",
                        "relationType": "IsVersionOf"})
        if prev_doi:
            rel.append({"relatedIdentifier": prev_doi, "relatedIdentifierType": "DOI",
                        "relationType": "IsNewVersionOf"})
        dc["relatedIdentifiers"] = rel
        if not P.date_of(dc, "Available"):
            # a version not public at the time becomes public now (section 4.4)
            P.set_date(dc, "Available", today)
        P.set_date(dc, "Updated", today)
        upload = {lp: f for lp, f in files.items() if lp not in skip}
        plan, extra = upload_plan(P, upload, obj, stage)
        entry = {"role": "deposit", "service": SERVICE_NAME, "record": f"{z.s['records']}{recid}",
                 "doi": doi}
        if extra:
            entry["files"] = extra
        obj["external"] = obj.get("external", []) + [entry]
        obj.pop("notices", None)
        obj.pop("history", None)
        P.carry_forward(state_obj, obj, inv, P.next_object_version(inv))
        content = dict(files, **{"datacite.json": P.json_bytes(dc)})
        staged = P.add_version(obj_id, content, obj, f"Zenodo: document version {doc_version}, DOI {doi}",
                               stage_in=stage / "version")
        ver = staged["head"]

        def staged_file(logical):
            cp = P.content_path(staged, ver, logical)
            return (stage / "version" / cp) if cp.startswith(f"{ver}/") else obj_dir / cp
        staged_obj = json.loads(staged_file(P.OBJ).read_text(encoding="utf-8"))
        check_deposit_record(P, staged_obj, doi)
        plan["datacite.json"] = staged_file("datacite.json")
        plan[P.OBJ] = staged_file(P.OBJ)
        state.update(phase="staged", version=ver)
        P.write_json(state_path, state)

        # 4. Upload, and compare the checksums Zenodo reports with the fixity of the inventory
        bucket = draft["links"]["bucket"]
        for name, path in sorted(plan.items()):
            data = path.read_bytes()
            if name == "sources.zip":
                expect = extra[0]["md5"]
            else:
                cp = P.content_path(staged, ver, name)
                expect = next((m for m, ps in staged.get("fixity", {}).get("md5", {}).items() if cp in ps), None)
                if expect is None:
                    raise RuntimeError(f"the inventory records no MD5 of {name} (appendix A.1)")
            if hashlib.md5(data).hexdigest() != expect:
                raise RuntimeError(f"{name} does not have the MD5 the inventory records")
            r = z.call("PUT", f"{bucket}/{urllib.parse.quote(name)}", raw=data)
            if r.get("checksum") != f"md5:{expect}":
                raise RuntimeError(f"checksum of {name}: Zenodo {r.get('checksum')}, inventory md5:{expect}")
            print(f"  uploaded {name} (md5 {expect})")
        z.call("PUT", f"/deposit/depositions/{recid}",
               {"metadata": zenodo_metadata(dc, P.ARCHIVE, obj_id)})
        state["phase"] = "uploaded"
        P.write_json(state_path, state)

        # 5. Publish
        pub = z.call("POST", f"/deposit/depositions/{recid}/actions/publish")
    except BaseException:
        print(f"{label}: failed before publication; discarding draft {recid}")
        try:
            z.call("DELETE", f"/deposit/depositions/{recid}")
        except RuntimeError as e:
            print(f"  (could not discard: {e})")
        remove_stage(P, stage)
        raise
    state["phase"] = "published"
    P.write_json(state_path, state)
    if pub.get("doi") != doi:
        sys.exit(f"Zenodo published DOI {pub.get('doi')}, not the reserved {doi}; the staging folder "
                 f"{stage} is kept: the version built there records the reserved DOI")
    print(f"{label}: published {doi} (concept {pub.get('conceptdoi')})")

    # 6. Add the object version and rewrite the discovery document
    commit(P, obj_id, stage, state)


def run(P, args):
    z = Zenodo(args.production)
    if args.production:
        return deposit(P, args.id, z)
    # Sandbox: work on a temporary copy, so that test DOIs never enter the archive
    obj_id = P.resolve(args.id)
    owner = obj_id.split(":")[2]
    tmp = Path(tempfile.mkdtemp(prefix="opensheaf-zenodo-sandbox-"))
    for oid in (obj_id, f"sheaf:{owner}:{owner}"):
        if P.obj_dir(oid).exists():
            shutil.copytree(P.obj_dir(oid), tmp / "ocfl" / P.path_of(oid))
    for f in ("0=ocfl_1.1", "ocfl_layout.json", P.LAYOUT_FILE):
        if (P.OCFL / f).exists():
            shutil.copyfile(P.OCFL / f, tmp / "ocfl" / f)
    real_root, real_ocfl = P.ROOT, P.OCFL
    P.ROOT, P.OCFL = tmp, tmp / "ocfl"
    try:
        print(f"sandbox: working on a copy in {tmp}")
        deposit(P, args.id, z)
        d = P.obj_dir(obj_id)
        inv = P.load_inventory(d)
        print(json.dumps(P.read_json(d, inv, P.OBJ)["external"], indent=2))
        print("statuses: " + ", ".join(P.line_statuses(d, inv)[1]))
    finally:
        P.ROOT, P.OCFL = real_root, real_ocfl
        if args.keep:
            print(f"sandbox copy kept in {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


def add_parser(sub, P):
    z = sub.add_parser("zenodo", help="deposit the current document version on Zenodo (appendix A.1)")
    z.add_argument("id", metavar="LABEL")
    z.add_argument("--production", action="store_true",
                   help="deposit on zenodo.org and add the version (default: sandbox, on a copy)")
    z.add_argument("--keep", action="store_true", help="sandbox: keep the temporary copy")
    z.set_defaults(func=lambda args: run(P, args))
