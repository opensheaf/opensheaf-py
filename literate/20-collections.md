Collections
========================================

## `src/opensheaf/collections.py`

    # in src/opensheaf/collections.py:
    <<collections.py: UA>>


    <<collections.py: norm_url>>


    <<collections.py: get>>


    <<collections.py: get_json>>


    <<collections.py: Remote>>


    <<collections.py: resolve>>


    <<collections.py: load_spec>>


    <<collections.py: write>>


    <<collections.py: sync>>


    <<collections.py: update>>


    <<collections.py: head_status>>


    <<collections.py: check_remote>>

Prose for collections.py: UA.

    # in collections.py: UA:
    """Curated collections (section 10 of the specification): members from this
    archive or from other archives, each pinned by the SHA-512 digest of the
    inventory of an object version.

        osheaf collection sync [ID] --from collection.yaml
        osheaf collection update [ID]

    collection.yaml (read with every value as text):

        id: collection-main            # optional: the collection object (default: the main collection)
        title: Stochastic quantisation
        description: Papers on the stochastic quantisation of field theories.
        order: manual                  # manual (default: the order below) or issued-desc / issued-asc
        members:
          - archive: https://mgubi.org/papers/        # an archive's base URL (or "." for this archive)
            id: fractional-phi43                      # the object
            # version: v3                             # a fixed object version (default: the current one)
            # follow: no                              # default: latest (`update` follows the current version)
          - {archive: https://mgubi.org/papers/, id: paracontrolled-distributions}

    `sync` resolves every member: it reads the member archive's discovery
    document, the object's inventory and the head's object.json, takes the
    current version (the last of the history), checks the pin against the
    checksum file the archive publishes, and caches a citation. A new collection
    version is written when the list or a pin changes. `update` moves members
    with follow: latest to their archives' current versions. Archive addresses may
    be https:// or file:// URLs, or local folders.
    """

    import hashlib
    import json
    import sys
    import tempfile
    import shutil
    import urllib.request
    from pathlib import Path

    from . import core as P

    UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}

Prose for collections.py: norm_url.

    # in collections.py: norm_url:
    def norm_url(url):
        if url.startswith(("http://", "https://", "file://")):
            return url if url.endswith("/") else url + "/"
        return Path(url).resolve().as_uri() + "/"

Prose for collections.py: get.

    # in collections.py: get:
    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            return r.read()

Prose for collections.py: get_json.

    # in collections.py: get_json:
    def get_json(url):
        return json.loads(get(url))

Prose for collections.py: Remote.

    # in collections.py: Remote:
    class Remote:
        """An OpenSheaf archive read over HTTP(S) or from a file:// URL."""

        def __init__(self, url):
            self.url = norm_url(url)
            self.disc = get_json(self.url + "opensheaf.json")
            self.root = self.url + self.disc.get("storageRoot", "ocfl/")
            self.archive_id = self.disc["archiveId"]

        def inventory(self, obj_id, ver=None):
            return get_json(self.root + obj_id + "/" + (f"{ver}/" if ver else "") + "inventory.json")

        def file(self, obj_id, inv, ver, logical):
            cp = P.content_path(inv, ver, logical)
            if cp is None:
                raise KeyError(f"{obj_id} {ver}: no {logical}")
            return get(self.root + obj_id + "/" + cp)

        def current(self, obj_id):
            """The object version holding the current document version."""
            inv = self.inventory(obj_id)
            head = json.loads(self.file(obj_id, inv, inv["head"], P.OBJ))
            return (head["history"][-1] if head.get("history") else inv["head"]), inv

        def pin(self, obj_id, ver):
            data = get(self.root + f"{obj_id}/{ver}/inventory.json")
            dig = hashlib.sha512(data).hexdigest()
            side = get(self.root + f"{obj_id}/{ver}/inventory.json.sha512").decode().split()[0]
            if side != dig:
                raise ValueError(f"{obj_id} {ver}: the inventory does not match its checksum file")
            return dig

Prose for collections.py: resolve.

    # in collections.py: resolve:
    def resolve(entry, here):
        """The member for an entry of collection.yaml (mirror: yes copies the
        object into this archive first, and lists the copy as a mirror)."""
        url = entry.get("archive", ".")
        obj_id = entry["id"]
        mirrored = str(entry.get("mirror", "")).lower() in ("yes", "true", "1")
        if mirrored:
            from . import mirror
            mirror.mirror(url, obj_id, str(entry.get("licence-checked", "")).lower() in ("yes", "true", "1"))
        local = url in (".", "", P.ARCHIVE["baseUrl"]) or norm_url(url) == norm_url(str(P.ROOT))
        if local:
            d = P.OCFL / obj_id
            inv = P.load_inventory(d)
            if inv is None:
                sys.exit(f"this archive has no object {obj_id}")
            ver = entry.get("version") or P.current_version(d, inv)
            pin = P.digest(d / ver / "inventory.json")
            dc = P.read_json(d, inv, "datacite.json", ver)
            obj = P.read_json(d, inv, P.OBJ, ver)
            archive_id, archive_url = P.ARCHIVE["archiveId"], P.ARCHIVE["baseUrl"]
        else:
            r = Remote(url)
            inv = r.inventory(obj_id)
            ver = entry.get("version") or r.current(obj_id)[0]
            pin = r.pin(obj_id, ver)
            dc = json.loads(r.file(obj_id, inv, ver, "datacite.json"))
            obj = json.loads(r.file(obj_id, inv, ver, P.OBJ))
            archive_id = r.archive_id
            archive_url = url if url.startswith(("http://", "https://")) else r.url
        cite = {"title": dc["titles"][0]["title"],
                "creators": [P.display_name(c) for c in dc["creators"]],
                "year": dc.get("publicationYear")}
        if P.date_of(dc, "Issued"):
            cite["issued"] = P.date_of(dc, "Issued")
        m = {"kind": obj["kind"], "archive": archive_id, "archiveUrl": norm_url(archive_url),
             "id": obj_id, "version": ver, "inventorySha512": pin}
        if dc.get("doi"):
            m["doi"] = dc["doi"]
        if str(entry.get("follow", "latest")).lower() not in ("no", "false", "none", "fixed") \
                and not entry.get("version"):
            m["follow"] = "latest"
        if mirrored or (not local and (P.OCFL / obj_id).exists()
                        and P.read_json(P.OCFL / obj_id, P.load_inventory(P.OCFL / obj_id), P.OBJ)
                        .get("archiveId") == archive_id):
            m["mirrors"] = [P.ARCHIVE["baseUrl"]]
        m["cite"] = cite
        return m

Prose for collections.py: load_spec.

    # in collections.py: load_spec:
    def load_spec(path):
        import yaml
        text = Path(path).read_text(encoding="utf-8")
        try:
            spec = json.loads(text) if str(path).endswith(".json") else yaml.load(text, Loader=yaml.BaseLoader)
        except (yaml.YAMLError, ValueError) as e:
            sys.exit(f"{path}: not valid: {e}")
        if not isinstance(spec, dict) or not isinstance(spec.get("members", []), list):
            sys.exit(f"{path}: expected a mapping with members: [...]")
        return spec

Prose for collections.py: write.

    # in collections.py: write:
    def write(coll_id, members, title, description, order, message):
        """A new version of collection COLL_ID, if its member list changed."""
        coll_dir = P.OCFL / coll_id
        inv = P.load_inventory(coll_dir)
        version, issued = 1, P.TODAY
        doc = {"format": "opensheaf-collection/0.1", "order": order, "members": members}
        if inv:
            old = P.read_json(coll_dir, inv, "members.json")
            old_dc = P.read_json(coll_dir, inv, "datacite.json")
            if old == doc and old_dc["titles"][0]["title"] == title:
                print(f"{coll_id}: unchanged ({inv['head']})")
                return inv
            version = P.read_json(coll_dir, inv, P.OBJ)["documentVersion"] + 1
            issued = P.date_of(old_dc, "Issued") or P.TODAY
        cur = P.ARCHIVE["curator"]
        tmp = Path(tempfile.mkdtemp())
        P.write_json(tmp / "members.json", doc)
        P.write_json(tmp / "datacite.json", {
            "titles": [{"title": title}],
            "creators": [{"name": cur["name"], "nameType": "Personal", "givenName": cur.get("givenName", ""),
                          "familyName": cur.get("familyName", cur["name"]),
                          "affiliation": [{"name": cur["affiliation"]}] if cur.get("affiliation") else []}],
            "publisher": {"name": P.ARCHIVE["name"]},
            "publicationYear": int(issued[:4]),
            "types": {"resourceTypeGeneral": "Collection"},
            "version": str(version),
            "url": P.ARCHIVE["baseUrl"],
            "dates": [{"date": issued, "dateType": "Issued"}, {"date": P.TODAY, "dateType": "Available"}],
            "descriptions": [{"description": description, "descriptionType": "Abstract"}],
            "rightsList": [dict(P.RIGHTS["cc0-1.0"])],
        })
        P.write_json(tmp / P.OBJ, {
            "format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "collection",
            "archiveId": P.ARCHIVE["archiveId"], "objectId": coll_id, "documentVersion": version,
            "status": "active"})
        inv = P.add_version(coll_id, {n: tmp / n for n in ("members.json", "datacite.json", P.OBJ)},
                            message or f"Collection version {version}: {len(members)} members")
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"{coll_id}: {inv['head']} ({len(members)} members)")
        return inv

Prose for collections.py: sync.

    # in collections.py: sync:
    def sync(args):
        P.init_storage_root()
        spec = load_spec(args.from_file)
        coll_id = args.collection or spec.get("id") or P.ARCHIVE["mainCollection"]
        order = spec.get("order", "manual")
        members = []
        for e in spec.get("members", []):
            m = resolve(e, P.ROOT)
            print(f"  {m['id']} ({m['archive']}): {m['version']}  {m['inventorySha512'][:16]}...")
            members.append(m)
        if order != "manual":
            P.ORDER = order
            members = P.member_order(members)
        write(coll_id, members, spec.get("title", P.ARCHIVE["name"]),
              spec.get("description", "A collection of documents."), order, args.message)

Prose for collections.py: update.

    # in collections.py: update:
    def update(args):
        """Members with follow: latest move to their archives' current versions."""
        coll_id = args.collection or P.ARCHIVE["mainCollection"]
        d = P.OCFL / coll_id
        inv = P.load_inventory(d)
        if inv is None:
            sys.exit(f"no collection {coll_id}")
        doc = P.read_json(d, inv, "members.json")
        dc = P.read_json(d, inv, "datacite.json")
        members = []
        for m in doc["members"]:
            if m.get("follow") == "latest":
                local = m["archive"] == P.ARCHIVE["archiveId"]
                if head_status(m, local) == "withdrawn":
                    # section 10.3: the pin is kept, and the curator is told
                    print(f"  {m['id']}: withdrawn in its archive; the pin {m['version']} is kept")
                    members.append(m)
                    continue
                entry = {"archive": "." if local else m["archiveUrl"], "id": m["id"]}
                new = resolve(entry, P.ROOT)
                if new["version"] != m["version"]:
                    print(f"  {m['id']}: {m['version']} -> {new['version']}")
                m = new
            members.append(m)
        desc = next((x["description"] for x in dc.get("descriptions", [])), "")
        write(coll_id, members, dc["titles"][0]["title"], desc, doc.get("order", "manual"), args.message)

Prose for collections.py: head_status.

    # in collections.py: head_status:
    def head_status(m, local):
        """The status of a member's object, read from its head."""
        if local:
            d = P.OCFL / m["id"]
            return P.read_json(d, P.load_inventory(d), P.OBJ).get("status")
        r = Remote(m["archiveUrl"])
        inv = r.inventory(m["id"])
        return json.loads(r.file(m["id"], inv, inv["head"], P.OBJ)).get("status")

Prose for collections.py: check_remote.

    # in collections.py: check_remote:
    def check_remote(members):
        """Errors for members of other archives whose pin cannot be confirmed."""
        errors = []
        for m in members:
            if m.get("archive") == P.ARCHIVE["archiveId"]:
                continue
            problems = []
            for src in [m["archiveUrl"]] + list(m.get("mirrors", [])):
                try:
                    if src == P.ARCHIVE["baseUrl"]:        # our own mirror: read it from disk
                        dig = P.digest(P.OCFL / m["id"] / m["version"] / "inventory.json")
                    else:
                        r = Remote(src)
                        if src == m["archiveUrl"] and r.archive_id != m["archive"]:
                            problems.append(f"{src} is now the archive {r.archive_id}")
                            continue
                        dig = r.pin(m["id"], m["version"])
                    if dig != m["inventorySha512"]:
                        problems.append(f"{src}: the pin does not match")
                        continue
                    if src != m["archiveUrl"]:
                        print(f"  {m['id']}: its archive failed; checked on the mirror {src}")
                    break
                except Exception as e:  # noqa: BLE001 - reported
                    problems.append(f"{src}: unavailable: {str(e)[:120]}")
            else:
                errors.append(f"member {m['id']} {m['version']}: " + "; ".join(problems))
        return errors

## `src/opensheaf/mirror.py`

    # in src/opensheaf/mirror.py:
    <<mirror.py: OPEN>>


    <<mirror.py: is_open>>


    <<mirror.py: mirror>>


    <<mirror.py: is_mirror>>


    <<mirror.py: main>>

Prose for mirror.py: OPEN.

    # in mirror.py: OPEN:
    """Mirrors (section 10.2 of the specification): a copy, in this archive's
    storage root, of another archive's object, byte for byte and with all its
    versions, kept under its own identifier.

        osheaf mirror ARCHIVE-URL ID [--licence-checked]

    A mirror is allowed only if the licence of the copied content allows
    redistribution: the tool checks the rightsList of every version and refuses
    unless each is an open licence (CC BY, CC BY-SA, CC0, GPL), or the curator
    states with --licence-checked that redistribution is allowed (for instance by
    the authors' permission). A reference (a member pinned in a collection,
    without a copy) needs no permission. Every copied file is checked against the
    digest of the source's inventory; a mirror that exists already gets the new
    versions only.
    """

    import hashlib
    import json
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    from . import core as P
    from .collections import Remote, get

    OPEN = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later", "cc-by-3.0"}
    OPEN_URIS = ("creativecommons.org/licenses/by/", "creativecommons.org/licenses/by-sa/",
                 "creativecommons.org/publicdomain/zero/", "gnu.org/licenses/gpl")

Prose for mirror.py: is_open.

    # in mirror.py: is_open:
    def is_open(rights):
        for r in rights or []:
            if (r.get("rightsIdentifier") or "").lower() in OPEN:
                return True
            uri = (r.get("rightsUri") or "").lower()
            if any(u in uri for u in OPEN_URIS) and "-nc" not in uri and "-nd" not in uri:
                return True
        return False

Prose for mirror.py: mirror.

    # in mirror.py: mirror:
    def mirror(url, obj_id, licence_checked=False):
        """Copy (or bring up to date) object OBJ_ID of the archive at URL."""
        r = Remote(url)
        if r.archive_id == P.ARCHIVE["archiveId"]:
            sys.exit(f"{obj_id} is an object of this archive")
        inv = r.inventory(obj_id)
        closed = []
        for ver in inv["versions"]:
            dc = json.loads(r.file(obj_id, inv, ver, "datacite.json"))
            if not is_open(dc.get("rightsList")):
                closed.append(f"{ver} ({(dc.get('rightsList') or [{}])[0].get('rights', 'no licence')})")
        if closed and not licence_checked:
            sys.exit(f"{obj_id}: not mirrored: these versions are not under an open licence: "
                     f"{', '.join(closed)}. Pin it in a collection instead (a reference needs no "
                     "permission), or mirror with --licence-checked if redistribution is allowed.")
        d = P.OCFL / obj_id
        have = P.load_inventory(d)
        if have:
            here = P.read_json(d, have, P.OBJ)
            if here.get("archiveId") != r.archive_id:
                sys.exit(f"this archive has an object {obj_id} already (section 10.2: a mirror keeps its "
                         "identifier only if no object of this archive has it)")
        tmp = Path(tempfile.mkdtemp(dir=P.OCFL))
        try:
            stage = tmp / obj_id
            if have:
                shutil.copytree(d, stage)
            else:
                stage.mkdir()
            new = [v for v in inv["versions"] if not (stage / v).exists()]
            base = r.root + obj_id + "/"
            for ver in new:
                for name in ("inventory.json", "inventory.json.sha512"):
                    (stage / ver).mkdir(parents=True, exist_ok=True)
                    (stage / ver / name).write_bytes(get(base + f"{ver}/{name}"))
                for dig, paths in inv["manifest"].items():
                    for cp in paths:
                        if cp.startswith(ver + "/"):
                            data = get(base + cp)
                            if hashlib.sha512(data).hexdigest() != dig:
                                sys.exit(f"{obj_id}: {cp} does not match its digest; nothing mirrored")
                            f = stage / cp
                            f.parent.mkdir(parents=True, exist_ok=True)
                            f.write_bytes(data)
            for name in ("0=ocfl_object_1.1", "inventory.json", "inventory.json.sha512"):
                (stage / name).write_bytes(get(base + name))
            if hashlib.sha512((stage / "inventory.json").read_bytes()).hexdigest() != \
                    (stage / "inventory.json.sha512").read_text().split()[0]:
                sys.exit(f"{obj_id}: the inventory does not match its checksum file; nothing mirrored")
            if d.exists():
                shutil.rmtree(d)
            shutil.move(str(stage), str(d))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        print(f"{obj_id}: mirrored from {r.archive_id} ({len(new)} new version(s), head {inv['head']})")
        return r

Prose for mirror.py: is_mirror.

    # in mirror.py: is_mirror:
    def is_mirror(obj_dir, inv):
        return P.read_json(obj_dir, inv, P.OBJ).get("archiveId") != P.ARCHIVE["archiveId"]

Prose for mirror.py: main.

    # in mirror.py: main:
    def main(args):
        P.init_storage_root()
        mirror(args.url, args.id, args.licence_checked)

## `src/opensheaf/accept.py`

    # in src/opensheaf/accept.py:
    <<accept.py: header>>


    <<accept.py: accept>>

Prose for accept.py: header.

    # in accept.py: header:
    """Accepting a vetted version (a journal, a series, a curated archive):

        osheaf accept ARCHIVE-URL ID --version vN [--as NEW-ID] [--stage VoR]
                      [--available DATE] [--agreement METHOD] [--licence-checked]

    copies the files of exactly one version of another archive's object (the
    version that was vetted) into a document of this archive: its first document
    version, or, for a document accepted before, a new document version (a
    correction, which is an editorial act of this archive: the authors' later
    versions change nothing here). The files are copied byte for byte, each
    checked against the digest of the source's inventory; object.json records the
    source under `external` (role source: the archive's address, the object and
    its version as the label, and the SHA-512 of that version's inventory, its
    pin), and datacite.json takes the source's description, with this archive as
    publisher and a relation to the source version.

    Copying needs the right to redistribute: the version's licence must be an open
    one (CC BY, CC BY-SA, CC0, GPL), or --licence-checked states that it is
    allowed (for instance by the authors' agreement, which --agreement records).
    """

    import hashlib
    import json
    import shutil
    import sys
    import tempfile
    from pathlib import Path

    from . import core as P
    from .collections import Remote, get
    from .mirror import is_open

Prose for accept.py: accept.

    # in accept.py: accept:
    def accept(args):
        P.init_storage_root()
        r = Remote(args.url)
        if r.archive_id == P.ARCHIVE["archiveId"]:
            sys.exit(f"{args.id} is an object of this archive")
        inv = r.inventory(args.id)
        ver = args.version
        if ver not in inv["versions"]:
            sys.exit(f"{args.id} has no object version {ver} (versions: {', '.join(inv['versions'])})")
        src_obj = json.loads(r.file(args.id, inv, ver, P.OBJ))
        src_dc = json.loads(r.file(args.id, inv, ver, "datacite.json"))
        if not is_open(src_dc.get("rightsList")) and not args.licence_checked:
            sys.exit(f"{args.id} {ver} is not under an open licence "
                     f"({(src_dc.get('rightsList') or [{}])[0].get('rights', 'none')}): copying it needs "
                     "the right to redistribute (--licence-checked, with --agreement to record it)")
        obj_id = args.as_id or args.id
        d = P.OCFL / obj_id
        have = P.load_inventory(d)
        doc_version = 1
        prev_obj = prev_dc = None
        if have:
            prev_obj, prev_dc = P.read_json(d, have, P.OBJ), P.read_json(d, have, "datacite.json")
            if prev_obj.get("archiveId") != P.ARCHIVE["archiveId"] or prev_obj["kind"] != "document":
                sys.exit(f"{obj_id} is not a document of this archive")
            if prev_obj.get("status") == "withdrawn":
                sys.exit(f"{obj_id} is withdrawn")
            doc_version = max(P.doc_version_of(d, have, v) for v in have["versions"]) + 1
        pin = r.pin(args.id, ver)
        tmp = Path(tempfile.mkdtemp())
        files = {}
        base = r.root + args.id + "/"
        state = {p: dg for dg, ps in inv["versions"][ver]["state"].items() for p in ps}
        received = []
        for logical, dg in sorted(state.items()):
            if logical in ("datacite.json", P.OBJ):
                continue
            data = get(base + inv["manifest"][dg][0])
            if hashlib.sha512(data).hexdigest() != dg:
                sys.exit(f"{args.id} {ver}: {logical} does not match its digest; nothing accepted")
            f = tmp / "files" / logical
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            files[logical] = f
        for n in src_obj.get("notices", []):      # notices of the source are its archive's, not ours
            if n.get("path"):
                files.pop(n["path"], None)
        available = args.available or P.TODAY
        dc = {k: v for k, v in src_dc.items() if k not in ("doi", "url", "dates", "relatedIdentifiers", "version")}
        dc["publisher"] = {"name": P.ARCHIVE["name"]}
        dc["version"] = str(doc_version)
        dc["url"] = P.landing_url(obj_id)
        if args.type:
            dc["types"] = {"resourceTypeGeneral": args.type}
        issued = P.date_of(src_dc, "Issued") or (P.date_of(prev_dc, "Issued") if prev_dc else None)
        dc["dates"] = []
        if issued:
            P.set_date(dc, "Issued", issued)
        P.set_date(dc, "Available", available)
        # the files are those of the source version: its relations stay true
        rel = list(src_dc.get("relatedIdentifiers", []))
        rel.append({"relatedIdentifier": f"{r.url}ocfl/{args.id}/{ver}/", "relatedIdentifierType": "URL",
                    "relationType": "IsIdenticalTo"})
        dc["relatedIdentifiers"] = rel
        obj = {"format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
               "archiveId": P.ARCHIVE["archiveId"], "objectId": obj_id, "documentVersion": doc_version}
        for k in ("mainSource", "sourceFormat", "sourcesMissing", "renditions", "toolchain"):
            if k in src_obj:
                obj[k] = src_obj[k]
        obj["changes"] = {"text": args.changes or (
            f"Accepted: version {src_obj['documentVersion']} of {args.id} in {r.disc.get('name', r.archive_id)}"
            if doc_version == 1 else f"Correction: version {src_obj['documentVersion']} of {args.id} accepted "
            "by this archive in place of the earlier one")}
        if args.stage:
            obj["stage"] = {"scheme": "NISO-JAV", "value": args.stage}
        if args.agreement:
            obj["agreement"] = {"by": [c["name"] for c in src_dc["creators"]], "date": available,
                                "method": args.agreement}
        obj["external"] = [{"role": "source", "service": "OpenSheaf", "record": f"{r.url}ocfl/{args.id}/{ver}/",
                            "label": f"{args.id} {ver}",
                            "files": [{"name": "inventory.json", "sha512": pin}]}]
        obj["status"] = "active"
        P.carry_forward(prev_obj, obj, have, P.next_object_version(have))
        for lp, f in P.carried_files(obj_id, have).items():
            files.setdefault(lp, f)
        P.write_json(tmp / "datacite.json", dc)
        P.write_json(tmp / P.OBJ, obj)
        files["datacite.json"], files[P.OBJ] = tmp / "datacite.json", tmp / P.OBJ
        msg = args.message or (f"Accepted from {r.archive_id}: {args.id} {ver} (pin {pin[:16]}...)")
        new = P.add_version(obj_id, files, msg)
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"{obj_id}: {new['head']} (document version {doc_version}, from {args.id} {ver})")
