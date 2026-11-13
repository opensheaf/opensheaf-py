# Generated from literate/20-collections.md by tools/tangle.py: edit the document, not this file.
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
import urllib.parse
import urllib.request
from pathlib import Path

from . import core as P

UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}


def norm_url(url):
    if url.startswith(("http://", "https://", "file://")):
        return url if url.endswith("/") else url + "/"
    return Path(url).resolve().as_uri() + "/"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        return r.read()


def get_json(url):
    return json.loads(get(url))


class Remote:
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

    def current(self, obj_id):
        """The object version holding the current document version."""
        inv = self.inventory(obj_id)
        head = json.loads(self.file(obj_id, inv, inv["head"], P.OBJ))
        if head.get("history"):
            return head["history"][-1], inv
        last = {}
        for ver in inv["versions"]:
            last[json.loads(self.file(obj_id, inv, ver, P.OBJ))["documentVersion"]] = ver
        return last[max(last)], inv

    def pin(self, obj_id, ver):
        data = get(self.root + f"{obj_id}/{ver}/inventory.json")
        dig = hashlib.sha512(data).hexdigest()
        side = get(self.root + f"{obj_id}/{ver}/inventory.json.sha512").decode().split()[0]
        if side != dig:
            raise ValueError(f"{obj_id} {ver}: the inventory does not match its checksum file")
        return dig


def resolve(entry):
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


def sync(args):
    P.init_storage_root()
    spec = load_spec(args.from_file)
    coll_id = args.collection or spec.get("id") or P.ARCHIVE["mainCollection"]
    order = spec.get("order", "manual")
    members = []
    for e in spec.get("members", []):
        m = resolve(e)
        print(f"  {m['id']} ({m['archive']}): {m['version']}  {m['inventorySha512'][:16]}...")
        members.append(m)
    if order != "manual":
        P.ORDER = order
        members = P.member_order(members)
    write(coll_id, members, spec.get("title", P.ARCHIVE["name"]),
          spec.get("description", "A collection of documents."), order, args.message)


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
                # the pin is kept, and the curator is told (section 10.2 now follows the head)
                print(f"  {m['id']}: withdrawn in its archive; the pin {m['version']} is kept")
                members.append(m)
                continue
            entry = {"archive": "." if local else m["archiveUrl"], "id": m["id"]}
            new = resolve(entry)
            if new["version"] != m["version"]:
                print(f"  {m['id']}: {m['version']} -> {new['version']}")
            m = new
        members.append(m)
    desc = next((x["description"] for x in dc.get("descriptions", [])), "")
    write(coll_id, members, dc["titles"][0]["title"], desc, doc.get("order", "manual"), args.message)


def head_status(m, local):
    """The status of a member's object, read from its head."""
    if local:
        d = P.OCFL / m["id"]
        return P.read_json(d, P.load_inventory(d), P.OBJ).get("status")
    r = Remote(m["archiveUrl"])
    inv = r.inventory(m["id"])
    return json.loads(r.file(m["id"], inv, inv["head"], P.OBJ)).get("status")


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
