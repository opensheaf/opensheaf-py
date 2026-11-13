Collections across archives
===========================

An OpenSheaf archive lists its own documents in its *main collection*,
which the chapters on the core build automatically from the documents
deposited (`osheaf collect`). This chapter is about collections that a
curator composes by hand: a reading list, the papers of a group, the
issue of a journal. Their members may live in this archive or in any
other, and each is fixed by a digest, so that a collection states exactly
what it contains even when the members belong to archives the curator
does not control. The module is `src/opensheaf/collections.py`.

Two kinds of copies complete the picture, each in a chapter of its own:
[mirrors](21-mirrors.md), whole copies of another archive's object, and
[accepted copies](22-accepted-copies.md), a copy of the one version of a
document that a journal or a series has vetted. The
[website](30-website.md) shows the members of the main collection,
whatever archive they come from.

What a collection is
--------------------

A collection is an OCFL object like a document, with three files in each
version: `datacite.json` (its description: title, curator, licence),
`object.json` (its identity, with `kind` `collection`), and
`members.json`, the list of members (section 10.2 of the
specification). A member names an object by the pair of its archive
identifier and its object identifier, gives the address of the archive
when the collection was made, and *pins* one object version by the
SHA-512 digest of its inventory:

```json
{
  "format": "opensheaf-collection/0.1",
  "order": "manual",
  "members": [
    {"kind": "document", "archive": "tag:opensheaf.org,2026:mgubi",
     "archiveUrl": "https://mgubi.org/papers/", "id": "fractional-phi43",
     "version": "v3", "inventorySha512": "8f2c…", "follow": "latest",
     "cite": {"title": "…", "creators": ["Gubinelli, Massimiliano"], "year": "2024"}}
  ]
}
```

The pin is what makes the collection trustworthy across archives. The
inventory of an object version lists the digest of every file of that
version and of all the versions before it; its digest therefore fixes the
whole object up to that version. A collection version, which is itself an
object version with an inventory, fixes all its members in turn: a
collection is a hash tree, and whoever reads it can check every byte
without trusting the archives it was fetched from (section 6.4: "integrity
comes from the pin, not from the place").

`follow: latest` is a setting for the curator's tools, not a floating
reference: the member is pinned all the same, and `osheaf collection
update` writes a new collection version when the followed object has a
new current version. `cite` is a cached citation, so that the collection
can be shown and ordered without fetching anything, and stays readable if
a member's archive disappears; it is never authoritative.

The specification now distinguishes two kinds of collections (section
10.1): *archive collections*, impartial about their members' versions,
whose members are pinned as above, and *selections*, which vet particular
revisions and pin them in a list `revisions`, with `type` in
`members.json` saying which kind a collection is. These tools do not yet
make that distinction: they write no `type`, and every collection they
make has members in the form above, that of an archive collection. The
section numbers in the comments of the code also predate the amended
specification: what they call section 10.2 (mirrors) and 10.3 (members
of other archives) are now sections 10.4 and 10.3.

The module
----------

The module starts with its documentation, which is the user's
documentation of the input file `collection.yaml` (next section), and
then defines, in this order, the reading of other archives, the
resolution of a member, the reading of `collection.yaml`, the writing of
a collection version, the two commands and the check of the members of
other archives.

    # in src/opensheaf/collections.py:
    <<the documentation of collections.py>>

    import hashlib
    import json
    import sys
    import tempfile
    import shutil
    import urllib.request
    from pathlib import Path

    from . import core as P

    UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}


    <<reading another archive>>


    <<resolving a member of a collection>>


    <<reading collection.yaml>>


    <<writing a collection version>>


    <<the command collection sync>>


    <<the command collection update>>


    <<checking the members of other archives>>

`UA` is the `User-Agent` header of every request: archives are static
websites, and a server that sees which program reads it can tell its
owner, or block it, without guessing.

The input: collection.yaml
--------------------------

A curator writes the collection as a short YAML file and runs `osheaf
collection sync --from collection.yaml`. Each member is given by the
address of its archive and its object identifier; the tool does the rest:
it finds the current version, computes the pin, and caches the citation.

    # in the documentation of collections.py:
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

Two keys of an entry are not in this summary: `mirror: yes` asks for a
copy of the member in this archive ([mirrors](21-mirrors.md)), and
`licence-checked: yes` goes with it when the member's licence is not an
open one.

The file is read with YAML's `BaseLoader`, which takes every value as a
string. The ordinary loader would turn `follow: no` into `False`, a
version `1.0` into a number and a date into a `datetime.date`; with every
value a string, the code decides itself what `no`, `yes` or `fixed`
mean, and a value is never silently changed. A file ending in `.json` is
read as JSON instead. The module `yaml` is imported only here, so that
the rest of the package works without it.

    # in reading collection.yaml:
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

Reading another archive
-----------------------

An archive is read through its base URL, as section 6.4 prescribes: the
discovery document `opensheaf.json` at that address names the storage
root, and an object version is then found at
`<storageRoot><id>/<version>/inventory.json`, with its files at the
content paths the inventory gives. Everything is a plain GET of a static
file, so the same code reads an archive served over HTTPS and one in a
folder of the local disk, through a `file://` URL. The tests use the
latter, and a curator may use it for archives kept side by side.

An address is normalised to a URL ending with a slash, so that relative
paths can be appended; a local folder becomes a `file://` URL.

    # in reading another archive:
    def norm_url(url):
        if url.startswith(("http://", "https://", "file://")):
            return url if url.endswith("/") else url + "/"
        return Path(url).resolve().as_uri() + "/"

`urllib` reads all three kinds of URLs. The timeout is generous: a PDF of
a long paper over a slow connection takes time.

    # in reading another archive:
    def get(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
            return r.read()

Most files read are JSON.

    # in reading another archive:
    def get_json(url):
        return json.loads(get(url))

A `Remote` is an archive opened at an address: its discovery document is
read once, and gives the storage root (by default `ocfl/`, relative to the
base URL) and the archive identifier, which is what names the archive in
collections. An inventory is read from the object's root (the head) or
from a version's folder; a file of a version is found through its logical
path, as in the chapters on the core.

    # in reading another archive:
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

        <<the current version of a remote object>>

        <<the pin of a remote object version>>

The *current* version of a document is not always the head. A version
found later (an old preprint deposited after a newer one) is placed in
the history before the current version, and a description-only version
changes the head without changing which document version is current
(section 7.3). The current version is the last entry of `history` in the
head's `object.json`, or the head when there is no history.

    # in the current version of a remote object:
    def current(self, obj_id):
        """The object version holding the current document version."""
        inv = self.inventory(obj_id)
        head = json.loads(self.file(obj_id, inv, inv["head"], P.OBJ))
        return (head["history"][-1] if head.get("history") else inv["head"]), inv

A pin is the SHA-512 of the bytes of an inventory. OCFL keeps next to
each inventory a *sidecar*, `inventory.json.sha512`, with its digest.
Before pinning, the two are compared: a collection that pinned a damaged
or half-uploaded inventory would fix the damage for ever, and a mismatch
is cheap to report now and expensive to discover later.

    # in the pin of a remote object version:
    def pin(self, obj_id, ver):
        data = get(self.root + f"{obj_id}/{ver}/inventory.json")
        dig = hashlib.sha512(data).hexdigest()
        side = get(self.root + f"{obj_id}/{ver}/inventory.json.sha512").decode().split()[0]
        if side != dig:
            raise ValueError(f"{obj_id} {ver}: the inventory does not match its checksum file")
        return dig

Resolving a member
------------------

Resolving turns an entry of `collection.yaml` into a member of
`members.json`. It reads the pinned version of the object, here or in its
archive, and builds the member record from its `object.json` and
`datacite.json`. The second argument, the root of this archive, is not
used: the archive is known from the configuration.

    # in resolving a member of a collection:
    def resolve(entry, here):
        """The member for an entry of collection.yaml (mirror: yes copies the
        object into this archive first, and lists the copy as a mirror)."""
        url = entry.get("archive", ".")
        obj_id = entry["id"]
        <<mirror a member first, if its entry asks>>
        local = url in (".", "", P.ARCHIVE["baseUrl"]) or norm_url(url) == norm_url(str(P.ROOT))
        if local:
            <<read the pinned version of a member of this archive>>
        else:
            <<read the pinned version of a member of another archive>>
        <<the member record of a resolved entry>>

With `mirror: yes` the object is first copied into this archive, or
brought up to date if it was copied before; the copy is then listed in
the member's `mirrors`. The values are strings (`BaseLoader`), hence the
comparison with the usual spellings of yes.

    # in mirror a member first, if its entry asks:
    mirrored = str(entry.get("mirror", "")).lower() in ("yes", "true", "1")
    if mirrored:
        from . import mirror
        mirror.mirror(url, obj_id, str(entry.get("licence-checked", "")).lower() in ("yes", "true", "1"))

A member is of this archive when its address is `.` (or empty), the base
URL of this archive, or a path or URL leading to its root folder. Such a
member is read from the disk. Unless the entry fixes a version, the
current one is taken; its pin is the digest of its inventory file, and
needs no comparison with the sidecar, which the verification of the
archive checks anyway.

    # in read the pinned version of a member of this archive:
    d = P.OCFL / obj_id
    inv = P.load_inventory(d)
    if inv is None:
        sys.exit(f"this archive has no object {obj_id}")
    ver = entry.get("version") or P.current_version(d, inv)
    pin = P.digest(d / ver / "inventory.json")
    dc = P.read_json(d, inv, "datacite.json", ver)
    obj = P.read_json(d, inv, P.OBJ, ver)
    archive_id, archive_url = P.ARCHIVE["archiveId"], P.ARCHIVE["baseUrl"]

A member of another archive is read through a `Remote`. Its archive
identifier is the one its discovery document states, whatever address
was written in the entry. The address recorded is the one written, if it
is an HTTP address, so that a collection published on the web records
the address its readers know; for a local folder, the `file://` URL is
all there is.

    # in read the pinned version of a member of another archive:
    r = Remote(url)
    inv = r.inventory(obj_id)
    ver = entry.get("version") or r.current(obj_id)[0]
    pin = r.pin(obj_id, ver)
    dc = json.loads(r.file(obj_id, inv, ver, "datacite.json"))
    obj = json.loads(r.file(obj_id, inv, ver, P.OBJ))
    archive_id = r.archive_id
    archive_url = url if url.startswith(("http://", "https://")) else r.url

The member record has the fields of section 10.2. The cached citation
holds the title, the creators as display names, the year and, when known,
the `Issued` date, by which collections in date order are sorted.

    # in the member record of a resolved entry:
    cite = {"title": dc["titles"][0]["title"],
            "creators": [P.display_name(c) for c in dc["creators"]],
            "year": dc.get("publicationYear")}
    if P.date_of(dc, "Issued"):
        cite["issued"] = P.date_of(dc, "Issued")
    m = {"kind": obj["kind"], "archive": archive_id, "archiveUrl": norm_url(archive_url),
         "id": obj_id, "version": ver, "inventorySha512": pin}
    if dc.get("doi"):
        m["doi"] = dc["doi"]
    <<whether a resolved member follows its object>>
    <<whether this archive mirrors a resolved member>>
    m["cite"] = cite
    return m

The citation is added last, so that it stands at the end of the member
in `members.json`, after the fields that matter.

A member follows its object unless the entry says otherwise (`follow:
no`, `false`, `none` or `fixed`) or fixes a version: a fixed version
that followed its object would not stay fixed.

    # in whether a resolved member follows its object:
    if str(entry.get("follow", "latest")).lower() not in ("no", "false", "none", "fixed") \
            and not entry.get("version"):
        m["follow"] = "latest"

The member's `mirrors` lists this archive when it holds a copy: one made
just now, or one made earlier, recognised as an object of the same
identifier whose head names the member's archive.

    # in whether this archive mirrors a resolved member:
    if mirrored or (not local and (P.OCFL / obj_id).exists()
                    and P.read_json(P.OCFL / obj_id, P.load_inventory(P.OCFL / obj_id), P.OBJ)
                    .get("archiveId") == archive_id):
        m["mirrors"] = [P.ARCHIVE["baseUrl"]]

Writing a collection version
----------------------------

A collection version is written only if something changed: the member
list (members, pins, order) or the title. A change of the description
alone does not make a new version. The *document version* of a
collection counts the changes of its member list (section 7.4), and its
`Issued` date is that of its first version.

    # in writing a collection version:
    def write(coll_id, members, title, description, order, message):
        """A new version of collection COLL_ID, if its member list changed."""
        coll_dir = P.OCFL / coll_id
        inv = P.load_inventory(coll_dir)
        version, issued = 1, P.TODAY
        doc = {"format": "opensheaf-collection/0.1", "order": order, "members": members}
        <<stop if the collection is unchanged, or number its next version>>
        cur = P.ARCHIVE["curator"]
        tmp = Path(tempfile.mkdtemp())
        P.write_json(tmp / "members.json", doc)
        <<the description of a collection version>>
        <<the object record of a collection version>>
        inv = P.add_version(coll_id, {n: tmp / n for n in ("members.json", "datacite.json", P.OBJ)},
                            message or f"Collection version {version}: {len(members)} members")
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"{coll_id}: {inv['head']} ({len(members)} members)")
        return inv

Comparing the whole of `members.json` also compares the cached
citations: a member whose title was corrected in its archive gives a new
collection version at the next `sync`, which is what one wants, since the
collection shows that title.

    # in stop if the collection is unchanged, or number its next version:
    if inv:
        old = P.read_json(coll_dir, inv, "members.json")
        old_dc = P.read_json(coll_dir, inv, "datacite.json")
        if old == doc and old_dc["titles"][0]["title"] == title:
            print(f"{coll_id}: unchanged ({inv['head']})")
            return inv
        version = P.read_json(coll_dir, inv, P.OBJ)["documentVersion"] + 1
        issued = P.date_of(old_dc, "Issued") or P.TODAY

The curator of the archive (from `osheaf.json`) is the creator of the
collection, and the archive its publisher. The member list is placed
under CC0 (section 10.6): a list of references is metadata, and its
licence never extends to the members, which keep their own.

    # in the description of a collection version:
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

The `object.json` of a collection has only the fields common to all
objects: none of those of documents (sources, renditions, history,
notices) applies.

    # in the object record of a collection version:
    P.write_json(tmp / P.OBJ, {
        "format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "collection",
        "archiveId": P.ARCHIVE["archiveId"], "objectId": coll_id, "documentVersion": version,
        "status": "active"})

The chapters on the core also use `write`: `osheaf init --curated`
creates an empty main collection with order `manual`, which `osheaf
collect` then leaves alone, so that the curator's list is never replaced
by the archive's own documents.

The commands
------------

### collection sync

`sync` resolves every entry of the file, in order, printing each pin as
it goes, and writes the collection (by default the main collection of
the archive). The order `manual` keeps the order of the file; the orders
by date use the sorting of the main collection, from the chapters on the
core (section 10.2: by `Issued`, then `Available`, ties broken by the
object identifier). That function reads its direction from the module
variable `ORDER` of the core, which is therefore set first. Curated
members have no `Available` date in their citation, so they are sorted
by `Issued` alone, those without a date last.

    # in the command collection sync:
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

### collection update

`update` needs no input file: it reads the last version of the collection
and resolves again, at their archives' current versions, the members that
follow their object. The others, and their order, are kept as they are.
The title, description and order of the collection are taken from its
last version.

    # in the command collection update:
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
                <<move a followed member to its current version>>
            members.append(m)
        desc = next((x["description"] for x in dc.get("descriptions", [])), "")
        write(coll_id, members, dc["titles"][0]["title"], desc, doc.get("order", "manual"), args.message)

A followed member is resolved again from its archive's address as
recorded in the collection (or `.` for a member of this archive). If the
object has been withdrawn in its archive, the member keeps its pin and
the curator is told: a withdrawal should not silently replace what the
curator chose. The amended specification (section 10.2) asks the
opposite of archive collections, which follow their members whatever the
new head holds, a withdrawal included, and show the withdrawal; these
tools keep the earlier behaviour.

    # in move a followed member to its current version:
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

The entry built here has no `mirror` key: `update` lists an existing
mirror in the member's `mirrors`, but does not copy the new versions into
it. To keep a mirror current, run `osheaf mirror` again before `update`.

The status of an object belongs to the object (section 11.1) and is read
from its head, here or in its archive.

    # in the command collection update:
    def head_status(m, local):
        """The status of a member's object, read from its head."""
        if local:
            d = P.OCFL / m["id"]
            return P.read_json(d, P.load_inventory(d), P.OBJ).get("status")
        r = Remote(m["archiveUrl"])
        inv = r.inventory(m["id"])
        return json.loads(r.file(m["id"], inv, inv["head"], P.OBJ)).get("status")

Checking the members of other archives
--------------------------------------

`osheaf verify --remote` (in the chapters on the core) checks the pins of
the members of every collection. Members of this archive are checked
with the rest of the archive; this function checks the others, by
resolving each as section 6.4 says: first at the archive's recorded
address, then at the mirrors listed in the member. The first source
whose inventory matches the pin settles the question; the member is in
error only if every source fails, and the error lists what went wrong at
each.

Three cases need care:

- a mirror in this archive is read from the disk rather than over the
  network, so that the check works offline and does not depend on this
  archive's website being up to date;
- the address of the member's archive may now serve another archive (a
  domain changed hands, a folder was reused): the archive identifier of
  the discovery document must be the member's;
- when the original fails and a mirror confirms the pin, the curator is
  told, since the member's archive may be gone for good.

The specification also lets a reader try the mirrors listed in the
archive's own discovery document, and external copies such as a DOI
record; these are not tried here.

    # in checking the members of other archives:
    def check_remote(members):
        """Errors for members of other archives whose pin cannot be confirmed."""
        errors = []
        for m in members:
            if m.get("archive") == P.ARCHIVE["archiveId"]:
                continue
            problems = []
            for src in [m["archiveUrl"]] + list(m.get("mirrors", [])):
                try:
                    <<confirm the pin of a member at one source>>
                except Exception as e:  # noqa: BLE001 - reported
                    problems.append(f"{src}: unavailable: {str(e)[:120]}")
            else:
                errors.append(f"member {m['id']} {m['version']}: " + "; ".join(problems))
        return errors

The `for ... else` does the bookkeeping: `break` on success skips the
`else`, which records the error only when no source confirmed the pin.
Any exception (a network failure, a missing file, an inventory whose
sidecar disagrees) makes the source unavailable, not the member wrong:
only bytes that are found and differ from the pin are a mismatch.

    # in confirm the pin of a member at one source:
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
