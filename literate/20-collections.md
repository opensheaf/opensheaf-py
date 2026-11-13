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
identifier and its object identifier, and gives the address of the
archive when the collection was made.

Collections are of two kinds (section 10.1), and `members.json` says which
in its `type`. An *archive collection* keeps objects whole and is
impartial about their versions: each member pins the head of its object
by the SHA-512 digest of that version's inventory, and may follow the
object as it grows. A *selection* vets particular revisions (a journal its
accepted version, a reading list the version it recommends): each member
pins a *revision set*, the document versions the curator vetted, each by
the object version that held it and the digest of its inventory, and
nothing else of the document is part of the selection:

```json
{
  "format": "opensheaf-collection/0.1",
  "type": "archive",
  "order": "manual",
  "members": [
    {"kind": "document", "archive": "tag:opensheaf.org,2026:mgubi",
     "archiveUrl": "https://mgubi.org/papers/", "id": "fractional-phi43",
     "version": "v4", "inventorySha512": "8f2c…", "follow": "latest",
     "cite": {"title": "…", "creators": ["Gubinelli, Massimiliano"], "year": "2024"}}
  ]
}
```

```json
{
  "format": "opensheaf-collection/0.1",
  "type": "selection",
  "order": "manual",
  "members": [
    {"kind": "document", "archive": "tag:opensheaf.org,2026:mgubi",
     "archiveUrl": "https://mgubi.org/papers/", "id": "fractional-phi43",
     "revisions": [{"documentVersion": 2, "version": "v2", "inventorySha512": "4f1e…"},
                   {"documentVersion": 3, "version": "v4", "inventorySha512": "c07a…"}],
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

`follow: latest`, in an archive collection, is a setting for the
curator's tools, not a floating reference: the member is pinned all the
same, and `osheaf collection update` writes a new collection version when
the followed object has a new head, whatever the head holds. A selection
has no such setting: tools never change its revision sets on their own
(section 10.2), and `update` only reports the members that have versions
the selection has not vetted. `cite` is a cached citation, so that the
collection can be shown and ordered without fetching anything, and stays
readable if a member's archive disappears; it is never authoritative.

The module
----------

The module starts with its documentation, which is the user's
documentation of the input file `collection.yaml` (next section), and
then defines, in this order, the reading of archives, the resolution of a
member, the reading of `collection.yaml`, the writing of a collection
version, the two commands and the checks of members and accepted copies
against other archives.

    # in src/opensheaf/collections.py:
    <<the documentation of collections.py>>

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
    KINDS = ("archive", "selection")


    <<reading another archive>>


    <<resolving a member of a collection>>


    <<reading collection.yaml>>


    <<writing a collection version>>


    <<the command collection sync>>


    <<the command collection update>>


    <<checking the members of other archives>>


    <<checking accepted copies against their sources>>

`UA` is the `User-Agent` header of every request: archives are static
websites, and a server that sees which program reads it can tell its
owner, or block it, without guessing. `KINDS` are the two values of
`type` (section 10.2).

The input: collection.yaml
--------------------------

A curator writes the collection as a short YAML file and runs `osheaf
collection sync --from collection.yaml`. Each member is given by the
address of its archive and its object identifier; the tool does the rest:
it finds the head or the revisions, computes the pins, and caches the
citation. A member of a selection lists its revisions by their document
versions, the numbers readers see (`revisions: [2, 3]`); the tool finds
the object version holding each. A document version may be held by
several object versions (a description added later holds the same files),
and the one taken is the entry of the history, the last object version
holding it, which is what the document's archive presents; a curator who
vetted another one names it by its object version instead (`v2`).

    # in the documentation of collections.py:
    """Curated collections (section 10 of the specification): members from this
    archive or from other archives, each pinned by the SHA-512 digest of the
    inventory of an object version.

        osheaf collection sync [ID] --from collection.yaml
        osheaf collection update [ID]

    collection.yaml (read with every value as text):

        id: collection-main            # optional: the collection object (default: the main collection)
        type: archive                  # archive (the default) or selection (section 10.1)
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

    An archive collection pins the head of each object (section 10.2): `sync`
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

A file without `type` describes an archive collection, as every
collection did before the specification distinguished the two kinds; the
tool says so, so that the curator can write the type and decide. Any
other value than the two kinds is an error.

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
        if "type" not in spec:
            print(f"{path}: no type: an archive collection (write `type: archive`, or `type: selection` "
                  "for a collection vetting revisions, section 10.1)")
            spec["type"] = "archive"
        if spec["type"] not in KINDS:
            sys.exit(f"{path}: type must be archive or selection, not {spec['type']}")
        <<check the keys of the members of each kind>>
        return spec

The keys of the two kinds of members exclude each other (section 10.2): a
member of a selection has revisions and neither a version nor `follow`,
since following is not vetting; a member of an archive collection has no
revisions. A mistake here is better reported before anything is fetched.

    # in check the keys of the members of each kind:
    for e in spec.get("members", []):
        if not isinstance(e, dict) or not e.get("id"):
            sys.exit(f"{path}: every member needs an id")
        if spec["type"] == "selection" and (e.get("version") or e.get("follow")):
            sys.exit(f"{path}: {e['id']}: a member of a selection gives its revisions, not a version or follow")
        if spec["type"] == "archive" and e.get("revisions"):
            sys.exit(f"{path}: {e['id']}: revisions belong to selections (type: selection)")

Reading archives
----------------

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

An archive is read through four operations: the inventory of an object
(at its root, the head, or in a version's folder), a file of a version
through its logical path, as in the chapters on the core, the pin of an
object version, and its archive identifier. Two classes give them: a
`Remote`, read over the network or from a `file://` URL, and `Here`, this
archive, read from the disk. On top of them, a common base class reads
the history and the document versions of an object the same way for both,
so that a member is resolved by the same code wherever it lives.

    # in reading another archive:
    class Archive:
        """What the tools read of an archive: inventories, files, pins, histories."""

        <<the document version and the history of an object of an archive>>


    <<an archive read over the network>>


    <<this archive read from the disk>>

A `Remote` is an archive opened at an address: its discovery document is
read once, and gives the storage root (by default `ocfl/`; a relative
address is relative to the base URL, an absolute one is taken as it is)
and the archive identifier, which is what names the archive in
collections.

    # in an archive read over the network:
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

        <<the pin of a remote object version>>

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

This archive is read from its storage root on the disk, with the same
operations. Its pins need no comparison with the sidecar, which the
verification of the archive checks anyway. A missing object or version
raises an exception, as a missing file of a remote archive does.

    # in this archive read from the disk:
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

The document version of an object version is in its `object.json`. The
history is that of section 7.3, as in the chapter on
[document versions](11-versions.md): the `history` of `object.json`, read
from the head or from an earlier object version `at`, and otherwise the
last object version holding each document version, among those up to
`at`, which needs the `object.json` of every one of them. The current
version is the last entry. A selection uses the history to find the
object version holding each vetted document version, and to keep its
revisions in the order of the document's history (section 10.2); an
archive collection, to cache the citation of the current version.

    # in the document version and the history of an object of an archive:
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

Resolving a member
------------------

Resolving turns an entry of `collection.yaml` into a member of
`members.json`, in a collection of the given kind. It reads the object,
here or in its archive, pins it (an archive collection) or its revisions
(a selection), and builds the member record from the `object.json` and
`datacite.json` of the version presented: the current version of an
archive collection's member, the last revision of a selection's. `old` is
the member as the previous version of the collection has it, if any, so
that revisions already vetted keep their pins; it is ignored if it names
another archive's object of the same identifier.

    # in resolving a member of a collection:
    def resolve(entry, kind="archive", old=None):
        """The member for an entry of collection.yaml in a collection of KIND
        (mirror: yes copies the object into this archive first, and lists the
        copy as a mirror); OLD is the member in the previous collection version."""
        url = entry.get("archive", ".")
        obj_id = entry["id"]
        <<mirror a member first, if its entry asks>>
        local = url in (".", "", P.ARCHIVE["baseUrl"]) or norm_url(url) == norm_url(str(P.ROOT))
        src = Here() if local else Remote(url)
        try:
            inv = src.inventory(obj_id)
        except Exception as e:  # noqa: BLE001 - reported
            sys.exit(f"{obj_id}: not found in {src.archive_id}: {e}")
        if old and old.get("archive") != src.archive_id:
            old = None
        if kind == "selection":
            <<the revisions of a member of a selection>>
        else:
            <<the pinned version of a member of an archive collection>>
        dc = json.loads(src.file(obj_id, inv, shown, "datacite.json"))
        obj = json.loads(src.file(obj_id, inv, shown, P.OBJ))
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
member is read from the disk; any other through a `Remote`, whose archive
identifier is the one its discovery document states, whatever address was
written in the entry.

### A member of an archive collection

A member of an archive collection pins the head of its object
(section 10.2), and presents its current version, read from the history
of the head. An entry may fix another version: the member then does not
follow (below), and keeps that pin. The specification calls the pinned
version the head of the object when the collection version was made,
which describes the pin of a member that follows; a fixed earlier version
pins the object as it was then, every version up to it. The curator is
told, since vetting one version of a document is what a selection does.

    # in the pinned version of a member of an archive collection:
    ver = entry.get("version") or inv["head"]
    if ver not in inv["versions"]:
        sys.exit(f"{obj_id} has no object version {ver} (versions: {', '.join(inv['versions'])})")
    if ver != inv["head"]:
        print(f"  {obj_id}: pinned at {ver}, not at its head {inv['head']}: the object as it was at "
              f"{ver} (to vet one version, make a selection, section 10.1)")
    pin = src.pin(obj_id, ver)
    shown = src.current(obj_id, ver)

### The revisions of a member of a selection

A member of a selection lists the revisions vetted, as document versions
or as object versions. A document version is resolved to the entry of the
document's history, the last object version holding it; an object version
is taken as given, with the document version it holds. A revision of the
previous version of the selection for the same document version is kept
as it is, pin included, unless the entry names another object version:
running `sync` again with the same file changes nothing, even if the
document's archive has described the version again since, which the
selection has not vetted (section 10.2).

Without `revisions`, the member keeps the revisions of the previous
version of the selection or, if it is new, vets the current version of
the document, and the curator is told which. Adding or removing a
revision is a change of the file, an act of the curator, as the
specification requires; the tool never decides it.

    # in the revisions of a member of a selection:
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
        <<one revision of a member of a selection>>
    <<the revisions in the order of the history>>
    shown = revisions[-1]["version"]

A revision given as an object version (`v4`) must exist, and holds the
document version its `object.json` states; one given as a number must be
a document version of the document, and is the revision pinned before or
else the entry of the history.

    # in one revision of a member of a selection:
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

The revisions are listed in the order of the document's history
(section 10.2), whatever the order of the file, and the last is the one
presented. Two revisions of the same document version would make the
set ambiguous, and section 14 asks for distinct document versions.

    # in the revisions in the order of the history:
    order = [docs[h] for h in hist]
    revisions.sort(key=lambda r: order.index(r["documentVersion"]) if r["documentVersion"] in order else -1)
    if len({r["documentVersion"] for r in revisions}) != len(revisions):
        sys.exit(f"{obj_id}: a document version is vetted twice")

### The member record

The member record has the fields of section 10.2. The address recorded is
the one written, if it is an HTTP address, so that a collection published
on the web records the address its readers know; for a local folder, the
`file://` URL is all there is, and for this archive its base URL. The
cached citation, from the version presented, holds the title, the
creators as display names, the year and, when known, the `Issued` date,
by which collections in date order are sorted. A member of an archive
collection has its pin, a member of a selection its revisions.

    # in the member record of a resolved entry:
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
    <<whether a resolved member follows its object>>
    <<whether this archive mirrors a resolved member>>
    m["cite"] = cite
    return m

The citation is added last, so that it stands at the end of the member
in `members.json`, after the fields that matter.

A member of an archive collection follows its object unless the entry
says otherwise (`follow: no`, `false`, `none` or `fixed`) or fixes a
version: a fixed version that followed its object would not stay fixed.
A member of a selection never follows (section 10.2).

    # in whether a resolved member follows its object:
    if kind == "archive" and str(entry.get("follow", "latest")).lower() not in ("no", "false", "none", "fixed") \
            and not entry.get("version"):
        m["follow"] = "latest"

The member's `mirrors` lists this archive when it holds a copy of every
version the member pins: a mirror made just now or earlier, recognised
as an object of the same identifier whose head names the member's
archive. A mirror that has not been brought up to date to the pinned
version is not listed, since a reader resolving the pin there would not
find it.

    # in whether this archive mirrors a resolved member:
    d = P.OCFL / obj_id
    have = P.load_inventory(d) if not local else None
    if have and P.mirror_of(d, have) == src.archive_id \
            and all(v in have["versions"] for v, _, _ in P.member_pins(m)):
        m["mirrors"] = [P.ARCHIVE["baseUrl"]]

Writing a collection version
----------------------------

A collection version is written only if something changed: the kind, the
member list (members, pins, order) or the title. A change of the
description alone does not make a new version. The *document version* of
a collection counts the changes of its member list (section 7.4), and its
`Issued` date is that of its first version.

    # in writing a collection version:
    def write(coll_id, members, title, description, order, message, kind="archive"):
        """A new version of collection COLL_ID, if its member list changed."""
        coll_dir = P.OCFL / coll_id
        inv = P.load_inventory(coll_dir)
        version, issued = 1, P.TODAY
        doc = {"format": "opensheaf-collection/0.1", "type": kind, "order": order, "members": members}
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
collection shows that title. A collection written before `members.json`
had a `type` gets a new version, which states it.

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
creates an empty main collection with order `manual`, an archive
collection until the curator's first `sync` says otherwise, which `osheaf
collect` then leaves alone, so that the curator's list is never replaced
by the archive's own documents.

The commands
------------

### collection sync

`sync` resolves every entry of the file, in order, printing the pins as
it goes, and writes the collection (by default the main collection of the
archive). The members of the previous version of the collection that
have revisions are given to `resolve` by identifier, so that their
revisions keep their pins. The order `manual` keeps the order of the
file; the orders by date use the sorting of the main collection, from
the chapters on the core (section 10.2: by `Issued`, then `Available`,
ties broken by the object identifier). That function reads its direction
from the module variable `ORDER` of the core, which is therefore set
first. Curated members have no `Available` date in their citation, so
they are sorted by `Issued` alone, those without a date last.

    # in the command collection sync:
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

### collection update

`update` needs no input file: it reads the last version of the collection
and acts according to its kind. A collection written before the
specification had kinds has no `type`: it is taken as an archive
collection, and its next version says so.

    # in the command collection update:
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
            print(f"{coll_id}: no type: an archive collection (section 10.1)")
            kind = "archive"
        if kind == "selection":
            report_unvetted(coll_id, doc["members"])
            return
        members = []
        for m in doc["members"]:
            if m.get("follow") == "latest":
                <<move a followed member to the head of its object>>
            members.append(m)
        desc = next((x["description"] for x in dc.get("descriptions", [])), "")
        write(coll_id, members, dc["titles"][0]["title"], desc, doc.get("order", "manual"), args.message)

A followed member is resolved again from its archive's address as
recorded in the collection (or `.` for a member of this archive), which
pins the head of its object, whatever the head holds (section 10.2): a
new document version, a description, a notice, or a withdrawal, which the
curator is told about and presentations show. A mirror of the member held
here is brought up to date first, so that the copy holds the new head and
stays listed in the member's `mirrors`. A member whose archive cannot be
read keeps its pin, and the curator is told.

    # in move a followed member to the head of its object:
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

A mirror is recognised as in the rest of the tools: an object of this
storage root, of the member's identifier, whose head names the member's
archive. It is brought up to date by the [mirror](21-mirrors.md) module,
which copies the new versions only, checking their licences and files. A
refusal (a new version without an open licence) or a failure leaves the
mirror as it was, a valid copy of the earlier versions, and is reported;
the member is then no longer listed with this archive among its
`mirrors`, since the copy does not hold the new pin.

    # in the command collection update:
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

The status of an object belongs to the object (section 11.1) and is read
from its head, here or in its archive.

    # in the command collection update:
    def head_status(m, local):
        """The status of a member's object, read from its head."""
        src = Here() if local else Remote(m["archiveUrl"])
        inv = src.inventory(m["id"])
        return json.loads(src.file(m["id"], inv, inv["head"], P.OBJ)).get("status")

A selection is never changed by `update`: tools must not change revision
sets on their own (section 10.2). What a curator needs to know is which
members have document versions that the selection has not vetted, later
in the document's history than its last revision, and which were
withdrawn; the curator decides, and records the decision with `sync`.

    # in the command collection update:
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

Checking the members of other archives
--------------------------------------

`osheaf verify --remote` (in the chapters on the core) checks the pins of
the members of every collection. Members of this archive are checked
with the rest of the archive; this function checks the others. Each pin
is checked: the pin of a member of an archive collection, and the pin of
every revision of a member of a selection, whose object version must
also hold the document version the revision states (section 14).

    # in checking the members of other archives:
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

A pin is resolved as section 6.4 says: first at the archive's recorded
address, then at the mirrors listed in the member, then at those listed
in the discovery document of the member's archive, when that document
can be read (the archive's storage may have failed while its discovery
document did not, or an object was lost). The first source whose
inventory matches the pin settles the question; the pin is in error only
if every source fails, and the error lists what went wrong at each.
External copies (a DOI record, a software archive snapshot), which a
client may also use, are not tried.

    # in checking the members of other archives:
    def confirm(m, ver, pin, n):
        """None if the pin VER/PIN of member M (holding document version N, if
        given) is confirmed at a source; else what went wrong at each."""
        problems = []
        sources = [m["archiveUrl"]] + [u for u in m.get("mirrors", []) if u != m["archiveUrl"]]
        for src in sources:      # the list grows with the archive's own mirrors
            try:
                <<confirm a pin at one source>>
            except Exception as e:  # noqa: BLE001 - reported
                problems.append(f"{src}: unavailable: {str(e)[:120]}")
        return "; ".join(problems)

Four cases need care:

- a mirror in this archive is read from the disk rather than over the
  network, so that the check works offline and does not depend on this
  archive's website being up to date;
- the address of the member's archive may now serve another archive (a
  domain changed hands, a folder was reused): the archive identifier of
  the discovery document must be the member's;
- an object taken down in its archive is listed among its tombstones
  (section 11.3), and is reported as removed, not as unavailable;
- when the original fails and a mirror confirms the pin, the curator is
  told, since the member's archive may be gone for good.

Any exception (a network failure, a missing file, an inventory whose
sidecar disagrees) makes the source unavailable, not the member wrong:
only bytes that are found and differ from the pin are a mismatch.

    # in confirm a pin at one source:
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

Checking accepted copies
------------------------

Section 14 also asks a verifier to check each
[accepted copy](22-accepted-copies.md) against its source, when the
source is available: its first document version must hold exactly the
files of the source version named in `external`. An accepted copy is a
document of this archive whose first object version records a source with
`service` `OpenSheaf`; the record is the address of the source object
version, and the digest under `files` its pin. The source's inventory of
that version is fetched and checked against the pin, and then the two
states are compared: the digests of every logical path but the two
descriptions. Since inventories record SHA-512 digests, no file needs to
be fetched. A source that cannot be read is reported, and not counted as
an error: the copy exists precisely so as not to depend on it.

    # in checking accepted copies against their sources:
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
            <<compare an accepted copy with its source>>
        return errors

The state of a version maps digests to logical paths; turned around, it
gives the digest of each path, which is what is compared.

    # in compare an accepted copy with its source:
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
    files = lambda state: {p: dg for dg, ps in state.items() for p in ps if p not in ("datacite.json", P.OBJ)}
    if files(json.loads(data)["versions"][ver]["state"]) != files(inv["versions"][first]["state"]):
        errors.append(f"{obj_id}: accepted copy: its first version does not hold exactly the files of "
                      f"{src.get('label')}")
