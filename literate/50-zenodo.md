Zenodo: DOIs for document versions
==================================

An OpenSheaf archive is a set of static files; it cannot register DOIs.
Zenodo, run by CERN, registers DataCite DOIs for what is deposited with it
and keeps the files permanently. Appendix A of the specification binds the
two: each document of the archive is one Zenodo record, each document
version a version of that record, with its own DOI, and the archive records
the DOI in a new object version. This chapter describes `osheaf zenodo`,
which makes such a deposit. It builds on the chapters on the core, in
particular on description-only versions and on the history of document
versions, and is independent of the [arXiv chapters](40-arxiv.md), except
that papers imported from arXiv are typical candidates for a DOI.

The command
-----------

```
osheaf zenodo ID                  try it on the Zenodo sandbox, on a copy
osheaf zenodo ID --production     deposit on zenodo.org and commit
```

deposits the current document version of object ID. Its docstring
summarises what happens.

    # in Zenodo: what the binding does:
    """Zenodo binding of OpenSheaf 0.1 (appendix A of the specification).

        osheaf zenodo ID [--production] [--keep]

    Deposits the current document version of object ID (the last of its
    history, section 7.3) on Zenodo and commits a description-only object version
    holding it, whose datacite.json carries the version DOI and whose object.json
    records the Zenodo record under `external` (role `deposit`).

    The first deposit of a document creates a Zenodo record (its concept DOI
    stands for the document); later document versions are new versions of that
    record, linked IsNewVersionOf the DOI of the version before them in the
    history. Zenodo orders record versions by publication, so a document version
    that is not the current one (an earlier version found later) is not deposited
    as a new version of the record (appendix A). Files of notices are not
    uploaded: the files of a published record version are fixed. A version that
    was not public at the time gets its Available date when Zenodo publishes it.
    Order of operations (appendix A): create the draft (Zenodo reserves
    its DOI), write datacite.json and object.json with that DOI in a staging
    folder, upload the files and compare their MD5 checksums with the inventory's
    fixity, publish, then commit the object version and rewrite opensheaf.json.

    Without --production the Zenodo sandbox is used, and everything is done on a
    temporary copy of the object, so that test DOIs never enter the archive; the
    copy is printed and removed unless --keep is given.

    Tokens: the environment variable ZENODO_TOKEN (production) or
    ZENODO_SANDBOX_TOKEN (sandbox); otherwise the system's credential store,
    under the service name zenodo-token or zenodo-sandbox-token and the login
    name, read through the Python package keyring (pip install
    'opensheaf[zenodo]': macOS keychain, Windows Credential Manager, Secret
    Service on Linux); on macOS also the keychain directly. To store a token:
        keyring set zenodo-token "$USER"                              (any system)
        security add-generic-password -a "$USER" -s zenodo-token -w   (macOS)

    If publication succeeds and the commit fails, the staging folder
    zenodo-staging/ID/ is kept, and the next run completes the object version
    from it before anything else (appendix A).
    """

The module does not import the core: the command line passes it the core
module, as `P`, when it registers the command. This is what makes the
sandbox safe, as we shall see.

    # in src/opensheaf/zenodo.py:
    <<Zenodo: what the binding does>>

    import datetime
    import getpass
    import html
    import json
    import os
    import shutil
    import subprocess
    import sys
    import tempfile
    import urllib.error
    import urllib.parse
    import urllib.request
    import zipfile
    from pathlib import Path

    <<Zenodo: the production and sandbox services>>
    <<Zenodo: vocabularies of the deposit metadata>>


    <<Zenodo: the token>>


    <<Zenodo: talking to the API>>


    <<Zenodo: deposit metadata from datacite.json>>


    <<Zenodo: deposits recorded in object.json>>


    <<Zenodo: a reproducible sources.zip>>


    <<Zenodo: what is uploaded>>


    <<Zenodo: files of notices>>


    <<Zenodo: the files of an object version>>


    <<Zenodo: the record of the version before>>


    <<Zenodo: committing the deposit>>


    <<Zenodo: depositing a document version>>


    <<Zenodo: sandbox or production>>


    <<Zenodo: the zenodo command>>

The command registers itself with the command line of `osheaf`.

    # in Zenodo: the zenodo command:
    def add_parser(sub, P):
        z = sub.add_parser("zenodo", help="deposit the current document version on Zenodo (appendix A)")
        z.add_argument("id")
        z.add_argument("--production", action="store_true",
                       help="deposit on zenodo.org and commit (default: sandbox, on a copy)")
        z.add_argument("--keep", action="store_true", help="sandbox: keep the temporary copy")
        z.set_defaults(func=lambda args: run(P, args))

Sandbox and production
----------------------

Zenodo has a sandbox, `sandbox.zenodo.org`, a separate copy of the service
for trying things out. Its DOIs are test DOIs, with the prefix `10.5072`,
which do not resolve; production DOIs have Zenodo's prefix `10.5281`. The
two have separate accounts and tokens, each with a name under which it is
stored and an environment variable that can carry it (see the next
section). `SERVICE_NAME` is the name of the service in the `external`
entries of `object.json`; the other constants are explained where they are
used.

    # in Zenodo: the production and sandbox services:
    SERVICES = {
        False: {"api": "https://sandbox.zenodo.org/api", "records": "https://sandbox.zenodo.org/records/",
                "token": "zenodo-sandbox-token", "env": "ZENODO_SANDBOX_TOKEN", "prefix": "10.5072"},
        True: {"api": "https://zenodo.org/api", "records": "https://zenodo.org/records/",
               "token": "zenodo-token", "env": "ZENODO_TOKEN", "prefix": "10.5281"},
    }
    SERVICE_NAME = "Zenodo"
    MAX_FILES = 100          # Zenodo's limit on files per record
    METADATA_FILES = ("datacite.json", "object.json")

Where tokens are kept
--------------------

A token is never kept in a file of the archive or given on the command
line, where it could end up in a repository or in the shell history. It is
looked for in three places, in order:

1. **The environment**, `ZENODO_TOKEN` or `ZENODO_SANDBOX_TOKEN`. This works
   on every system, and it is how continuous integration passes secrets:
   a workflow of GitHub Actions sets it from a secret of the repository.
2. **The system's credential store**, through the Python package
   [keyring](https://pypi.org/project/keyring/): the keychain on macOS,
   the Credential Manager on Windows, the Secret Service (GNOME Keyring,
   KWallet) on Linux. The token is stored under the name of the service,
   `zenodo-token` or `zenodo-sandbox-token`, and the login name of the
   user. keyring is optional (`pip install 'opensheaf[zenodo]'`); without
   it, or without a working store, this step is skipped.
3. **On macOS, the keychain directly**, with the `security` command, which
   needs no package. This finds the tokens stored with
   `security add-generic-password`, under any account name.

The first token found is used. When there is none, the message names the
variable and the stored name, so that the user knows where to put it.

    # in Zenodo: the token:
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

The API is Zenodo's REST API for deposits. Requests and answers are JSON,
except uploads, which send the bytes of a file. An HTTP error becomes an
exception with Zenodo's explanation, which is usually precise. The DOI of a
record is made from its number, as Zenodo makes it.

    # in Zenodo: talking to the API:
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

An object version cannot be removed once committed. A deposit on the
sandbox would leave a test DOI in the archive for ever. So, without
`--production`, the deposit is made on a temporary copy of the object, in a
temporary storage root, and the result is printed and thrown away (kept
with `--keep`, for inspection). The core module keeps the location of the
storage root in the variables `ROOT` and `OCFL`, which all its functions
read when they are called; setting them redirects every function of the
core to the copy, and the deposit code, which reaches the core only through
`P`, runs unchanged. The variables are restored whatever happens.

    # in Zenodo: sandbox or production:
    def run(P, args):
        z = Zenodo(args.production)
        if args.production:
            return deposit(P, args.id, z)
        # Sandbox: work on a temporary copy, so that test DOIs never enter the archive
        tmp = Path(tempfile.mkdtemp(prefix="opensheaf-zenodo-sandbox-"))
        shutil.copytree(P.OCFL / args.id, tmp / "ocfl" / args.id)
        for f in ("0=ocfl_1.1", "ocfl_layout.json"):
            shutil.copyfile(P.OCFL / f, tmp / "ocfl" / f)
        real_root, real_ocfl = P.ROOT, P.OCFL
        P.ROOT, P.OCFL = tmp, tmp / "ocfl"
        try:
            print(f"sandbox: working on a copy in {tmp}")
            deposit(P, args.id, z)
            inv = P.load_inventory(P.OCFL / args.id)
            print(json.dumps(P.read_json(P.OCFL / args.id, inv, P.OBJ)["external"], indent=2))
        finally:
            P.ROOT, P.OCFL = real_root, real_ocfl
            if args.keep:
                print(f"sandbox copy kept in {tmp}")
            else:
                shutil.rmtree(tmp, ignore_errors=True)

The deposit
-----------

### Which version

The version deposited is always the current version of the document: the
last of its history (section 7.3), which is not necessarily the one in the
head object version. Zenodo orders the versions of a record by their
publication, and resolves the concept DOI to the latest; a document version
deposited out of order, an earlier version found later, would become the
latest on Zenodo. Appendix A therefore does not deposit it as a new version
of the record, and this tool deposits only the current version. A version
already deposited is not deposited again.

### The order of operations

A deposit changes two things that must agree: a record on Zenodo and an
object version in the archive. Neither can be undone once made: a published
Zenodo record stays, and so does an object version. Appendix A fixes the
order of operations so that a failure at any point leaves something that
can be completed or discarded:

1. create a draft record, or a new version of the document's record;
2. take the DOI that Zenodo reserves for the draft;
3. write `datacite.json` and `object.json`, with that DOI, in a staging
   folder;
4. upload the files, and compare their checksums with ours;
5. publish;
6. commit the object version, and rewrite the discovery document.

Before step 5 nothing is public, and a failure discards the draft. After
step 5 the DOI exists, and the object version must be committed; the
staging folder holds everything needed for it. The state of the deposit is
kept in `state.json` in that folder, `zenodo-staging/ID/`, and its phase is
written after each step.

    # in Zenodo: depositing a document version:
    def deposit(P, obj_id, z):
        obj_dir = P.OCFL / obj_id
        inv = P.load_inventory(obj_dir)
        if inv is None:
            sys.exit(f"no object {obj_id}")
        stage = P.ROOT / "zenodo-staging" / obj_id
        state_path = stage / "state.json"
        <<Zenodo: complete or discard an interrupted deposit>>

        <<Zenodo: the document version to deposit>>

        <<Zenodo: a draft and its DOI>>

        try:
            <<Zenodo: stage the files of the version>>
            <<Zenodo: the DOI and the relations in datacite.json>>
            <<Zenodo: the deposit in object.json>>

            <<Zenodo: upload and compare the checksums>>

            # 5. Publish
            pub = z.call("POST", f"/deposit/depositions/{recid}/actions/publish")
        except BaseException:
            print(f"{obj_id}: failed before publication; discarding draft {recid}")
            try:
                z.call("DELETE", f"/deposit/depositions/{recid}")
            except RuntimeError as e:
                print(f"  (could not discard: {e})")
            shutil.rmtree(stage, ignore_errors=True)
            raise
        state["phase"] = "published"
        P.write_json(state_path, state)
        if pub.get("doi") != doi:
            sys.exit(f"Zenodo published DOI {pub.get('doi')}, not the reserved {doi}; "
                     f"the staging folder {stage} is kept: fix datacite.json there and rerun")
        print(f"{obj_id}: published {doi} (concept {pub.get('conceptdoi')})")

        # 6. Commit the object version and rewrite the discovery document
        commit(P, obj_id, stage, state)

Any exception before publication, an interruption from the keyboard
included, discards the draft and the staging folder: Zenodo allows only
one unpublished version per record, and a draft left behind would block
the next attempt. After publication, the DOI that Zenodo published is
compared with the one reserved and written into `datacite.json`. They
should agree; if they do not, the staging folder is kept, so that
`datacite.json` can be corrected there, and running the command again
completes the commit.

### Starting again

A deposit finds the staging folder of an earlier one when that one was
interrupted. If it was published, the object version is committed, and
nothing else is done: appendix A requires this before any other deposit of
the document. Otherwise its draft is discarded, as far as Zenodo allows,
and the deposit starts again.

    # in Zenodo: complete or discard an interrupted deposit:
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state["phase"] == "published":
            print(f"{obj_id}: completing the object version of record {state['record']}")
            return commit(P, obj_id, stage, state)
        print(f"{obj_id}: discarding the unpublished draft {state['record']}")
        try:
            z.call("DELETE", f"/deposit/depositions/{state['record']}")
        except RuntimeError as e:
            print(f"  (could not discard: {e})")
        shutil.rmtree(stage)

### Steps 1 and 2: the draft and its DOI

Only documents are deposited (appendix A allows a collection to be
deposited when it is released, which this tool does not do), and only
active ones: a withdrawn document gets no new DOI. The current version and
its description are read from the object version that holds it.

    # in Zenodo: the document version to deposit:
    head_obj = P.read_json(obj_dir, inv, P.OBJ)
    if head_obj["kind"] != "document":
        sys.exit(f"{obj_id} is not a document")
    if head_obj["status"] != "active":
        sys.exit(f"{obj_id} is withdrawn")
    # the current version: the last of the history (section 7.3)
    cur = P.current_version(obj_dir, inv)
    obj = P.read_json(obj_dir, inv, P.OBJ, cur)
    dc = P.read_json(obj_dir, inv, "datacite.json", cur)
    doc_version = obj["documentVersion"]
    if zenodo_entries(obj):
        sys.exit(f"{obj_id}: document version {doc_version} is already on Zenodo "
                 f"({zenodo_entries(obj)[0]['doi']})")

If an earlier document version is on Zenodo, the new one becomes a new
version of its record. Zenodo copies the files of the previous version
into the new one; we delete them, since the new version has its own. If
none is, a new record is created. Zenodo reserves the DOI of the draft when
it is created, and the record number gives it; the concept record, the one
standing for all versions, gives the concept DOI.

    # in Zenodo: a draft and its DOI:
    # 1-2. Draft: a new record, or a new version of the document's record;
    # Zenodo reserves the DOI when the draft is created.
    prev_rec, prev_doi = previous_record(P, obj_dir, inv, doc_version)
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

The earlier version is the one before the current version in the history,
or the latest before it that was deposited. Its deposit may be recorded in
any object version holding it, not only in the last, so we look through
all of them, the newest first.

    # in Zenodo: the record of the version before:
    def previous_record(P, obj_dir, inv, doc_version):
        """The Zenodo record id and DOI of the latest document version before
        DOC_VERSION in the history that is on Zenodo."""
        hist = P.history_of(obj_dir, inv)
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

A deposit is an entry of `external` with role `deposit` and service
Zenodo.

    # in Zenodo: deposits recorded in object.json:
    def zenodo_entries(obj):
        return [e for e in obj.get("external", [])
                if e.get("service") == SERVICE_NAME and e.get("role") == "deposit"]

### Step 3: the new object version

The new object version is a description-only version (section 7.3): it
holds the current document version, with its files unchanged, and a new
description. Its files are copied into the staging folder, all but the two
metadata files, which are written anew.

    # in Zenodo: the files of an object version:
    def version_files(P, obj_dir, inv, ver):
        return {lp: obj_dir / P.content_path(inv, ver, lp)
                for paths in inv["versions"][ver]["state"].values() for lp in paths}

The notices about the document must be kept in every later object version
(section 7.3), so their files are taken from the head and staged too.
They are not uploaded: the files of a published Zenodo version are fixed,
and a notice usually comes later than the version it is about. The same
holds for the file of a withdrawal reason.

    # in Zenodo: stage the files of the version:
    # 3. datacite.json and object.json with the DOI, in the staging area;
    # the files are those of the object version holding the current version
    files_dir = stage / "files"
    files = {}
    skip = notice_files(head_obj)
    for lp, src in version_files(P, obj_dir, inv, cur).items():
        if lp not in METADATA_FILES:
            dest = files_dir / lp
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            files[lp] = dest
    # notices are kept in the archive (and in later object versions) but
    # not uploaded: the files of a published record version are fixed
    for lp in head_obj.get("notices", []):
        if lp.get("path") and lp["path"] not in files:
            src = obj_dir / P.content_path(inv, inv["head"], lp["path"])
            dest = files_dir / lp["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            files[lp["path"]] = dest

The files left out of the upload are those named by the notices of the
head and by its withdrawal reason, if any. The file of the licence terms
(`licence`, section 9) is not among them, although `osheaf verify` does
not count it among the files of the document version either (licence
terms describe the object, sections 7.3 and 9): this list serves only to
choose what is uploaded, and the licence terms are the terms under which
the uploaded files are distributed. They are deposited with the content,
not written later about it as a notice is; and Zenodo knows licences only
by their SPDX identifiers, recording any other as "Other (Not Open)" with
its name in the notes (see below), so the full terms of such a licence
reach the readers of the record only as a file next to the content.

    # in Zenodo: files of notices:
    def notice_files(obj):
        paths = {n["path"] for n in obj.get("notices", []) if n.get("path")}
        reason = obj.get("withdrawal", {}).get("reason", {})
        if reason.get("path"):
            paths.add(reason["path"])
        return paths

`datacite.json` gets the DOI, and a `url`: the page of the document on the
archive's website if it has one, otherwise the one it had (for a paper from
arXiv, arXiv's page), or the archive's address. The relations to Zenodo
versions are rewritten: the version is a version of the concept DOI and a
new version of the version before (section 8.1); relations of this kind
copied from the description of an earlier version are dropped. A version
that had not been public before becomes public now, and its `Available`
date is today (section 8); `Updated` is today, the date of this
description-only version.

    # in Zenodo: the DOI and the relations in datacite.json:
    today = datetime.date.today().isoformat()
    dc["doi"] = doi
    if (P.SITE / obj_id / f"{obj_id}.html").exists():
        dc["url"] = f"{P.ARCHIVE['baseUrl']}site/{obj_id}/{obj_id}.html"
    else:
        dc.setdefault("url", P.ARCHIVE["baseUrl"])
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
        # a version not public at the time becomes public now (section 8)
        P.set_date(dc, "Available", today)
    P.set_date(dc, "Updated", today)

`object.json` gets the deposit in `external`, next to an arXiv source if
there is one, with the record and the DOI, and the digests of
`sources.zip` if one is uploaded. The notices and the history are those of
the head (section 7.3), which may be more recent than those of the version
deposited, and are carried forward from it. The list of staged files is
kept in the state, for step 6.

    # in Zenodo: the deposit in object.json:
    upload = {lp: f for lp, f in files.items() if lp not in skip}
    plan, extra = upload_plan(P, upload, obj, stage)
    entry = {"role": "deposit", "service": SERVICE_NAME, "record": f"{z.s['records']}{recid}",
             "doi": doi}
    if extra:
        entry["files"] = extra
    obj["external"] = obj.get("external", []) + [entry]
    # notices and history as read from the head (section 7.3)
    obj.pop("notices", None)
    obj.pop("history", None)
    P.carry_forward(head_obj, obj, inv, P.next_object_version(inv))
    P.write_json(files_dir / "datacite.json", dc)
    P.write_json(files_dir / P.OBJ, obj)
    files["datacite.json"] = files_dir / "datacite.json"
    files[P.OBJ] = files_dir / P.OBJ
    plan["datacite.json"] = files["datacite.json"]
    plan[P.OBJ] = files[P.OBJ]
    state["files"] = sorted(files)

### Step 4: the upload

Each file is uploaded into the draft's bucket, and Zenodo answers with the
MD5 checksum of what it received. This is why archives following the
binding record MD5 digests in their inventories (section 13.1): what Zenodo
holds can be compared with the archive without downloading it. A
difference stops the deposit before publication. The metadata of the
record are sent last.

    # in Zenodo: upload and compare the checksums:
    # 4. Upload, and compare the checksums Zenodo reports
    bucket = draft["links"]["bucket"]
    for name, path in sorted(plan.items()):
        r = z.call("PUT", f"{bucket}/{urllib.parse.quote(name)}", raw=path.read_bytes())
        local = P.digest(path, "md5")
        if r.get("checksum") != f"md5:{local}":
            raise RuntimeError(f"checksum of {name}: Zenodo {r.get('checksum')}, local md5:{local}")
        print(f"  uploaded {name} (md5 {local})")
    z.call("PUT", f"/deposit/depositions/{recid}",
           {"metadata": zenodo_metadata(dc, P.ARCHIVE, obj_id)})
    state["phase"] = "uploaded"
    P.write_json(state_path, state)

### Step 6: the commit

The object version is added with the staged files, and the discovery
document `opensheaf.json`, which lists the head version and inventory
digest of every object, is written again. Then the staging folder goes.

    # in Zenodo: committing the deposit:
    def commit(P, obj_id, stage, state):
        files = {lp: stage / "files" / lp for lp in state["files"]}
        inv = P.add_version(obj_id, files, f"Zenodo: document version {state['documentVersion']}, "
                                           f"DOI {state['doi']}")
        P.write_json(P.ROOT / "opensheaf.json", P.discovery())
        shutil.rmtree(stage)
        print(f"{obj_id}: {inv['head']} committed, DOI {state['doi']}")

The files on Zenodo
-------------------

A Zenodo record version holds the content files of the object version
(appendix A). Zenodo records have no folders, and at most 100 files. A
version whose files are flat and few enough is uploaded as it is. Otherwise
the renditions and the metadata files are uploaded as they are, and the
sources go into one archive, `sources.zip`, whose digests are recorded in
the deposit's entry in `object.json`. A rendition in a sub-folder could not
be uploaded either way, and stops the deposit.

    # in Zenodo: what is uploaded:
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

`sources.zip` is built reproducibly: from the same files, anyone gets the
same bytes, and so can check the archive on Zenodo against the files of
the archive, and the other way round. The entries are in the byte order of
their names; every entry has the same date, 1 January 1980, the earliest a
zip file can record, and the same Unix permissions; no extra fields
(timestamps, owners) are written.

    # in Zenodo: a reproducible sources.zip:
    def reproducible_zip(dest, files):
        """sources.zip as appendix A asks: entries in byte order of their names,
        fixed timestamps, no extra attributes."""
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for name in sorted(files, key=lambda n: n.encode()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                info.create_system = 3
                z.writestr(info, Path(files[name]).read_bytes())

The metadata on Zenodo
----------------------

Zenodo does not take a DataCite record: it takes its own metadata and
generates the DataCite record of the DOI from them. `datacite.json` remains
the authoritative description (appendix A), and the translation only has
to be faithful, not complete. Zenodo's vocabularies differ from DataCite's:
types of publications, schemes of identifiers, and licences, which Zenodo
knows by their SPDX identifiers. A licence it does not know, such as
"All rights reserved" or arXiv's licence to distribute, becomes "Other (Not
Open)", and its text goes into the notes of the record.

    # in Zenodo: vocabularies of the deposit metadata:
    PUBLICATION_TYPES = {"Preprint": "preprint", "JournalArticle": "article", "Book": "book",
                         "BookChapter": "section", "Dissertation": "thesis", "Report": "report",
                         "ConferencePaper": "conferencepaper", "Text": "other"}
    SCHEMES = {"arXiv": "arxiv", "DOI": "doi", "URL": "url", "Handle": "handle", "ISBN": "isbn",
               "ISSN": "issn", "PMID": "pmid", "SWHID": "swh"}
    # Licences Zenodo knows under the SPDX identifier (lower case); anything else
    # (All rights reserved, the arXiv licence) is "other-closed": Other (Not Open).
    OPEN_LICENCES = {"cc-by-4.0", "cc-by-sa-4.0", "cc-by-nc-4.0", "cc-by-nd-4.0", "cc-by-nc-sa-4.0",
                     "cc-by-nc-nd-4.0", "cc0-1.0", "mit", "apache-2.0", "gpl-3.0-or-later"}

The creators keep their names, affiliations and ORCID iDs. The abstract
becomes the HTML description of the record, a paragraph for each block of
text separated by a blank line; without an abstract, the title stands in.
The publication date is the first public appearance of the work. The notes
say where the record comes from: the archive, the object and the document
version. The related identifiers are those of `datacite.json` that Zenodo
can express, with the archive's page of the document as identical to the
record; the versioning relations between Zenodo records are left out,
since Zenodo states them itself.

    # in Zenodo: deposit metadata from datacite.json:
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
            "notes": (f"Deposited from the OpenSheaf archive {archive['archiveId']} "
                      f"({archive['name']}), object {obj_id}, document version {dc['version']}. "
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
