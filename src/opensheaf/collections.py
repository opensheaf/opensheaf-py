# Generated from literate/20-collections.md by opensheaf-literate: edit the document, not this file.
"""Curated collections (section 10 of the specification): members from this
archive or from other archives, each pinned by the SHA-512 digest of the
inventory of an object version.

    osheaf collection sync [ID] --from collection.yaml
    osheaf collection update [ID]

collection.yaml (read with every value as text):

    id: collection-main            # optional: the collection object (default: the main collection)
    type: catalogue                  # catalogue (the default) or selection (section 10.1)
    title: Stochastic quantisation
    description: Papers on the stochastic quantisation of field theories.
    order: manual                  # manual (default: the order below) or issued-desc / issued-asc
    members:
      - archive: https://mgubi.org/papers/        # an archive's base URL (or "." for this archive)
        id: fractional-phi43                      # the object
        # version: v3                             # a fixed object version (default: the head)
        # follow: no                              # default: latest (`update` follows the head)
      - {archive: https://mgubi.org/papers/, id: paracontrolled-distributions}

In a selection each member gives the revisions vetted instead:

    type: selection
    members:
      - archive: https://authors.example.org/
        id: network-discrimination
        revisions: [2, 3]          # document versions (or object versions: [v2, v4])
      - {archive: ., id: accepted-paper, revisions: [1]}

A catalogue pins the head of each object (section 10.2): `sync`
reads the member archive's discovery document and the object's inventory,
checks the pin against the checksum file the archive publishes, and caches a
citation of the current version. `update` moves members with follow: latest to
the new head of their object, whatever it holds (a withdrawal too), and brings
up to date the mirrors of these members held here. A selection pins each
revision by the object version holding that document version (the entry of
its history); a member without `revisions` keeps the revisions of the
previous version of the selection, or vets the current version. Revisions
already pinned keep their pins. `update` never changes a selection: it
reports the members with document versions not vetted. A new collection
version is written when the list or a pin changes. Archive addresses may be
https:// or file:// URLs, or local folders.
"""

import hashlib
import json
import sys
import tempfile
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from . import core as P

UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}
KINDS = ("catalogue", "selection")


def norm_url(url):
    if url.startswith(("http://", "https://", "file://")):
        return url if url.endswith("/") else url + "/"
    return Path(url).resolve().as_uri() + "/"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def get_json(url):
    return json.loads(get(url))


class Archive:
    """What the tools read of an archive: inventories, files, pins, histories."""

    def doc_version(self, obj_id, inv, ver):
        return json.loads(self.file(obj_id, inv, ver, P.OBJ))["documentVersion"]

    def history(self, obj_id, at=None):
        """(the history as of object version AT (default: the head), the root inventory)."""
        inv = self.inventory(obj_id)
        at = at or inv["head"]
        obj = json.loads(self.file(obj_id, inv, at, P.OBJ))
        if obj.get("history"):
            return obj["history"], inv
        last = {}
        for ver in inv["versions"]:
            if int(ver[1:]) <= int(at[1:]):
                last[self.doc_version(obj_id, inv, ver)] = ver
        return [last[n] for n in sorted(last)], inv

    def current(self, obj_id, at=None):
        """The object version holding the current document version as of AT."""
        return self.history(obj_id, at)[0][-1]


class Remote(Archive):
    """An OpenSheaf archive read over HTTP(S) or from a file:// URL."""

    def __init__(self, url):
        self.url = norm_url(url)
        self.disc = get_json(self.url + "opensheaf.json")
        self.root = urllib.parse.urljoin(self.url, self.disc.get("storageRoot", "ocfl/"))
        self.archive_id = self.disc["archiveId"]

    def inventory(self, obj_id, ver=None):
        return get_json(self.root + obj_id + "/" + (f"{ver}/" if ver else "") + "inventory.json")

    def file(self, obj_id, inv, ver, logical):
        cp = P.content_path(inv, ver, logical)
        if cp is None:
            raise KeyError(f"{obj_id} {ver}: no {logical}")
        return get(self.root + obj_id + "/" + cp)

    def pin(self, obj_id, ver):
        data = get(self.root + f"{obj_id}/{ver}/inventory.json")
        dig = hashlib.sha512(data).hexdigest()
        side = get(self.root + f"{obj_id}/{ver}/inventory.json.sha512").decode().split()[0]
        if side != dig:
            raise ValueError(f"{obj_id} {ver}: the inventory does not match its checksum file")
        return dig


class Here(Archive):
    """This archive, read from the disk with the operations of a Remote."""

    def __init__(self):
        self.url = P.ARCHIVE["baseUrl"]
        self.disc = {"name": P.ARCHIVE["name"], "archiveId": P.ARCHIVE["archiveId"]}
        self.archive_id = P.ARCHIVE["archiveId"]

    def inventory(self, obj_id, ver=None):
        p = P.OCFL / obj_id / (ver or "") / "inventory.json"
        if not p.exists():
            raise FileNotFoundError(f"this archive has no {obj_id} {ver or ''}".strip())
        return json.loads(p.read_text(encoding="utf-8"))

    def file(self, obj_id, inv, ver, logical):
        cp = P.content_path(inv, ver, logical)
        if cp is None:
            raise KeyError(f"{obj_id} {ver}: no {logical}")
        return (P.OCFL / obj_id / cp).read_bytes()

    def pin(self, obj_id, ver):
        return P.digest(P.OCFL / obj_id / ver / "inventory.json")


def resolve(entry, kind="catalogue", old=None):
    """The member for an entry of collection.yaml in a collection of KIND
    (mirror: yes copies the object into this archive first, and lists the
    copy as a mirror); OLD is the member in the previous collection version."""
    url = entry.get("archive", ".")
    obj_id = entry["id"]
    mirrored = str(entry.get("mirror", "")).lower() in ("yes", "true", "1")
    if mirrored:
        from . import mirror
        mirror.mirror(url, obj_id, str(entry.get("licence-checked", "")).lower() in ("yes", "true", "1"))
    local = url in (".", "", P.ARCHIVE["baseUrl"]) or norm_url(url) == norm_url(str(P.ROOT))
    src = Here() if local else Remote(url)
    try:
        inv = src.inventory(obj_id)
    except Exception as e:  # noqa: BLE001 - reported
        sys.exit(f"{obj_id}: not found in {src.archive_id}: {e}")
    if old and old.get("archive") != src.archive_id:
        old = None
    if kind == "selection":
        hist, _ = src.history(obj_id)
        docs = {h: src.doc_version(obj_id, inv, h) for h in hist}
        before = {r["documentVersion"]: r for r in (old or {}).get("revisions", [])}
        given = entry.get("revisions")
        if isinstance(given, str):
            given = [given]
        if not given and before:
            given = [str(n) for n in before]
        elif not given:
            given = [str(docs[hist[-1]])]
            print(f"  {obj_id}: no revisions given: vetting its current version {given[0]}")
        revisions = []
        for g in given:
            g = str(g).strip()
            if g.startswith("v"):
                if g not in inv["versions"]:
                    sys.exit(f"{obj_id} has no object version {g}")
                ver, n = g, src.doc_version(obj_id, inv, g)
            else:
                n = int(g)
                ver = before[n]["version"] if n in before else next((h for h in hist if docs[h] == n), None)
                if ver is None:
                    sys.exit(f"{obj_id} has no document version {n}")
            if n in before and before[n]["version"] == ver:
                revisions.append(before[n])
            else:
                revisions.append({"documentVersion": n, "version": ver, "inventorySha512": src.pin(obj_id, ver)})
        order = [docs[h] for h in hist]
        revisions.sort(key=lambda r: order.index(r["documentVersion"]) if r["documentVersion"] in order else -1)
        if len({r["documentVersion"] for r in revisions}) != len(revisions):
            sys.exit(f"{obj_id}: a document version is vetted twice")
        shown = revisions[-1]["version"]
    else:
        ver = entry.get("version") or inv["head"]
        if ver not in inv["versions"]:
            sys.exit(f"{obj_id} has no object version {ver} (versions: {', '.join(inv['versions'])})")
        if ver != inv["head"]:
            print(f"  {obj_id}: pinned at {ver}, not at its head {inv['head']}: the object as it was at "
                  f"{ver} (to vet one version, make a selection, section 10.1)")
        pin = src.pin(obj_id, ver)
        shown = src.current(obj_id, ver)
    dc = json.loads(src.file(obj_id, inv, shown, "datacite.json"))
    obj = json.loads(src.file(obj_id, inv, shown, P.OBJ))
    archive_url = url if not local and url.startswith(("http://", "https://")) else src.url
    cite = {"title": dc["titles"][0]["title"],
            "creators": [P.display_name(c) for c in dc["creators"]],
            "year": dc.get("publicationYear")}
    if P.date_of(dc, "Issued"):
        cite["issued"] = P.date_of(dc, "Issued")
    m = {"kind": obj["kind"], "archive": src.archive_id, "archiveUrl": norm_url(archive_url), "id": obj_id}
    if kind == "selection":
        m["revisions"] = revisions
    else:
        m["version"], m["inventorySha512"] = ver, pin
    if dc.get("doi"):
        m["doi"] = dc["doi"]
    if kind == "catalogue" and str(entry.get("follow", "latest")).lower() not in ("no", "false", "none", "fixed") \
            and not entry.get("version"):
        m["follow"] = "latest"
    d = P.OCFL / obj_id
    have = P.load_inventory(d) if not local else None
    if have and P.mirror_of(d, have) == src.archive_id \
            and all(v in have["versions"] for v, _, _ in P.member_pins(m)):
        m["mirrors"] = [P.ARCHIVE["baseUrl"]]
    m["cite"] = cite
    return m


def load_spec(path):
    import yaml
    text = Path(path).read_text(encoding="utf-8")
    try:
        spec = json.loads(text) if str(path).endswith(".json") else yaml.load(text, Loader=yaml.BaseLoader)
    except (yaml.YAMLError, ValueError) as e:
        sys.exit(f"{path}: not valid: {e}")
    if not isinstance(spec, dict) or not isinstance(spec.get("members", []), list):
        sys.exit(f"{path}: expected a mapping with members: [...]")
    if "type" not in spec:
        print(f"{path}: no type: a catalogue (write `type: catalogue`, or `type: selection` "
              "for a collection vetting revisions, section 10.1)")
        spec["type"] = "catalogue"
    if spec["type"] not in KINDS:
        sys.exit(f"{path}: type must be catalogue or selection, not {spec['type']}")
    for e in spec.get("members", []):
        if not isinstance(e, dict) or not e.get("id"):
            sys.exit(f"{path}: every member needs an id")
        if spec["type"] == "selection" and (e.get("version") or e.get("follow")):
            sys.exit(f"{path}: {e['id']}: a member of a selection gives its revisions, not a version or follow")
        if spec["type"] == "catalogue" and e.get("revisions"):
            sys.exit(f"{path}: {e['id']}: revisions belong to selections (type: selection)")
    return spec


def write(coll_id, members, title, description, order, message, kind="catalogue"):
    """A new version of collection COLL_ID, if its member list changed."""
    coll_dir = P.OCFL / coll_id
    inv = P.load_inventory(coll_dir)
    version, issued = 1, P.TODAY
    doc = {"format": "opensheaf-collection/0.1", "type": kind, "order": order, "members": members}
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


def sync(args):
    P.init_storage_root()
    spec = load_spec(args.from_file)
    coll_id = args.collection or spec.get("id") or P.ARCHIVE["mainCollection"]
    kind, order = spec["type"], spec.get("order", "manual")
    before = {}
    cinv = P.load_inventory(P.OCFL / coll_id)
    if cinv:
        before = {m["id"]: m for m in P.read_json(P.OCFL / coll_id, cinv, "members.json")["members"]
                  if "revisions" in m}
    members = []
    for e in spec.get("members", []):
        m = resolve(e, kind, before.get(e["id"]))
        pins = ", ".join(f"{v} {d[:16]}..." for v, d, _ in P.member_pins(m))
        print(f"  {m['id']} ({m['archive']}): {pins}")
        members.append(m)
    if order != "manual":
        P.ORDER = order
        members = P.member_order(members)
    write(coll_id, members, spec.get("title", P.ARCHIVE["name"]),
          spec.get("description", "A collection of documents."), order, args.message, kind)


def update(args):
    """Members with follow: latest move to the head of their object; a selection
    is never changed, its members' versions not vetted are reported."""
    coll_id = args.collection or P.ARCHIVE["mainCollection"]
    d = P.OCFL / coll_id
    inv = P.load_inventory(d)
    if inv is None:
        sys.exit(f"no collection {coll_id}")
    doc = P.read_json(d, inv, "members.json")
    dc = P.read_json(d, inv, "datacite.json")
    kind = doc.get("type")
    if kind is None:
        print(f"{coll_id}: no type: a catalogue (section 10.1)")
        kind = "catalogue"
    if kind == "selection":
        report_unvetted(coll_id, doc["members"])
        return
    members = []
    for m in doc["members"]:
        if m.get("follow") == "latest":
            local = m["archive"] == P.ARCHIVE["archiveId"]
            if not local:
                refresh_mirror(m)
            try:
                new = resolve({"archive": "." if local else m["archiveUrl"], "id": m["id"]})
            except Exception as e:  # noqa: BLE001 - reported, the pin is kept
                print(f"  {m['id']}: its archive cannot be read ({str(e)[:120]}); the pin {m['version']} is kept")
                members.append(m)
                continue
            if new["version"] != m["version"]:
                print(f"  {m['id']}: {m['version']} -> {new['version']}")
                if head_status(new, local) == "withdrawn":
                    print(f"  {m['id']}: withdrawn in its archive; followed all the same (section 10.2)")
            m = new
        members.append(m)
    desc = next((x["description"] for x in dc.get("descriptions", [])), "")
    write(coll_id, members, dc["titles"][0]["title"], desc, doc.get("order", "manual"), args.message)


def refresh_mirror(m):
    """Bring a mirror of member M held here up to date (section 10.4)."""
    d = P.OCFL / m["id"]
    inv = P.load_inventory(d)
    if not inv or P.mirror_of(d, inv) != m["archive"]:
        return
    from . import mirror
    try:
        mirror.mirror(m["archiveUrl"], m["id"])
    except (SystemExit, Exception) as e:  # noqa: BLE001 - reported, the mirror is kept
        print(f"  {m['id']}: the mirror here was not brought up to date: {str(e)[:200]}")


def head_status(m, local):
    """The status of a member's object, read from its head."""
    src = Here() if local else Remote(m["archiveUrl"])
    inv = src.inventory(m["id"])
    return json.loads(src.file(m["id"], inv, inv["head"], P.OBJ)).get("status")


def report_unvetted(coll_id, members):
    """Report the document versions of a selection's members that it has not vetted."""
    print(f"{coll_id}: a selection: its revisions change only by the curator's sync (section 10.2)")
    for m in members:
        local = m["archive"] == P.ARCHIVE["archiveId"]
        try:
            src = Here() if local else Remote(m["archiveUrl"])
            hist, inv = src.history(m["id"])
            docs = [src.doc_version(m["id"], inv, h) for h in hist]
            status = json.loads(src.file(m["id"], inv, inv["head"], P.OBJ)).get("status")
        except Exception as e:  # noqa: BLE001 - reported
            print(f"  {m['id']}: its archive cannot be read ({str(e)[:120]})")
            continue
        vetted = [r["documentVersion"] for r in m["revisions"]]
        last = max((docs.index(n) for n in vetted if n in docs), default=-1)
        newer = docs[last + 1:]
        if newer:
            print(f"  {m['id']}: document version(s) {', '.join(map(str, newer))} not vetted "
                  f"(the selection has {', '.join(map(str, vetted))})")
        if status == "withdrawn":
            print(f"  {m['id']}: withdrawn in its archive")


def check_remote(members):
    """Errors for members of other archives whose pins cannot be confirmed."""
    errors = []
    for m in members:
        if m.get("archive") == P.ARCHIVE["archiveId"]:
            continue
        for ver, pin, n in P.member_pins(m):
            problem = confirm(m, ver, pin, n)
            if problem:
                errors.append(f"member {m['id']} {ver}: {problem}")
    return errors


def confirm(m, ver, pin, n):
    """None if the pin VER/PIN of member M (holding document version N, if
    given) is confirmed at a source; else what went wrong at each."""
    problems = []
    sources = [m["archiveUrl"]] + [u for u in m.get("mirrors", []) if u != m["archiveUrl"]]
    for src in sources:      # the list grows with the archive's own mirrors
        try:
            r = Here() if src == P.ARCHIVE["baseUrl"] else Remote(src)
            if src == m["archiveUrl"]:
                if r.archive_id != m["archive"]:
                    problems.append(f"{src} is now the archive {r.archive_id}")
                    continue
                sources += [u for u in r.disc.get("mirrors", []) if u not in sources]
                if any(t.get("id") == m["id"] for t in r.disc.get("tombstones", [])):
                    return "removed (a tombstone in its archive)"
            if r.pin(m["id"], ver) != pin:
                problems.append(f"{src}: the pin does not match")
                continue
            if n is not None and r.doc_version(m["id"], r.inventory(m["id"], ver), ver) != n:
                problems.append(f"{src}: {ver} does not hold document version {n}")
                continue
            if src != m["archiveUrl"]:
                print(f"  {m['id']} {ver}: its archive failed; checked on the mirror {src}")
            return None
        except Exception as e:  # noqa: BLE001 - reported
            problems.append(f"{src}: unavailable: {str(e)[:120]}")
    return "; ".join(problems)


def check_accepted_copies():
    """Errors for accepted copies whose first document version does not hold
    exactly the files of their source version (section 14)."""
    errors = []
    for obj_id, d, inv in P.objects():
        first = next(iter(inv["versions"]))
        obj = P.read_json(d, inv, P.OBJ, first)
        src = next((e for e in obj.get("external", []) if e.get("role") == "source"
                    and e.get("service") == "OpenSheaf"), None)
        if obj.get("kind") != "document" or P.mirror_of(d, inv) or not src:
            continue
        pin = next((f.get("sha512") for f in src.get("files", []) if f.get("name") == "inventory.json"), None)
        ver = src["record"].rstrip("/").rsplit("/", 1)[1]
        try:
            data = get(src["record"].rstrip("/") + "/inventory.json")
        except Exception as e:  # noqa: BLE001 - the source is unavailable: not checked
            print(f"  {obj_id}: the source of the accepted copy is unavailable ({str(e)[:120]}); not checked")
            continue
        if hashlib.sha512(data).hexdigest() != pin:
            errors.append(f"{obj_id}: accepted copy: the source {src.get('label')} does not match its pin")
            continue
        versions = json.loads(data).get("versions") or {}
        if ver not in versions:
            errors.append(f"{obj_id}: accepted copy: the source {src.get('label')} has no version {ver}")
            continue
        files = lambda state: {p: dg for dg, ps in state.items() for p in ps if p not in ("datacite.json", P.OBJ)}
        if files(versions[ver]["state"]) != files(inv["versions"][first]["state"]):
            errors.append(f"{obj_id}: accepted copy: its first version does not hold exactly the files of "
                          f"{src.get('label')}")
    return errors
