Resolution: other archives and sheaf: URIs
==========================================

Everything that works across archives starts by reading another archive:
a collection resolves its members there, a mirror copies a line from it, a
branch takes its parent version from it, an owner fetches a fresher copy of
its key log. This chapter is the module `remote.py`, which reads archives
and resolves `sheaf:` URIs (section 12 of the specification); the chapters
that follow, on [collections](21-collections.md), [mirrors](22-mirrors.md)
and [branches](23-branches.md), are built on it.

Three ideas of the specification shape it.

- **Locations are hints.** An archive's base URL, the `at` of a collection
  member or of a `sheaf:` URI, a branch's `parent.url`: none of them is
  signed, and none needs to be, since whatever is fetched from them is
  checked against pins and signatures (section 3). A wrong or stale
  location gives a reader nothing, or an older valid copy, never a forged
  one. So the module never trusts what it fetches: it checks the digest of
  every file it copies, the name of every line against its genesis record,
  and the signatures of every version against the owner's key log.
- **Key logs travel with the objects they sign.** Every copy of a line
  holds beside it the key log of its owner (section 6.5). The module
  fetches it from wherever it fetches the line, meets it with the copies
  it already knows (the archive's own, the copies found elsewhere), and
  judges the line against the longest, or against both sides of a fork.
- **Readers use the latest signed version among the copies that agree.**
  A copy that stops early looks complete, so a resolver looks at every
  copy it can find and takes the latest signed version among those that
  agree (section 7.4); copies that do not agree are a fork of the line,
  reported, and never chosen between.

The module
----------

    # in src/opensheaf/remote.py:
    <<resolution: the docstring and the imports>>


    <<resolution: where an archive is read>>


    <<resolution: an archive read through its discovery document>>


    <<resolution: copying an object from another archive>>


    <<resolution: a copy of a line, judged>>


    <<resolution: the resolver>>


    <<resolution: the command resolve>>

The module reads files over HTTP with the standard library; nothing is
cached between runs. `MAX_BYTES` bounds what one request may return,
`TIMEOUT` how long it may take, and `MAX_FETCH_BYTES` and `MAX_FETCH_FILES`
what one copy of an object may bring in all (section 15.2: tools treat
what they fetch as untrusted, and bound it).

    # in resolution: the docstring and the imports:
    """Other archives and sheaf: URIs (section 12 of OpenSheaf 0.2): archives read through their
    discovery documents, over HTTP or from folders, at the locations configured; objects and key
    logs copied from them and checked; copies of a line judged against the key logs met; sheaf:
    URIs resolved to the latest signed version among the copies that agree (section 12.3).

        osheaf resolve URI [--at URL]... [--json]
    """

    import json
    import os
    import re
    import shutil
    import sys
    import tempfile
    import urllib.error
    import urllib.parse
    import urllib.request
    from dataclasses import dataclass, field
    from pathlib import Path

    from . import core as P, names, owners, sign

    UA = {"User-Agent": "opensheaf-py (https://github.com/opensheaf/opensheaf-py)"}
    TIMEOUT = 30
    MAX_BYTES = 1 << 30
    MAX_FETCH_BYTES = 4 << 30
    MAX_FETCH_FILES = 20000
    LOCATIONS = "OPENSHEAF_LOCATIONS"


    class Unavailable(Exception):
        """An archive, an object or a file that cannot be read where it was looked for."""

Where an archive is read
------------------------

An archive is named by its base URL, which collections and URIs record:
`https://mgubi.org/papers/`. Where it is read may be elsewhere: a copy of
the same archive served at another place, a clone of its repository on
disk, a test fixture. Section 12.3 lets a resolver try "its user's
configuration", and the *locations* are that configuration: a map from
base URLs (or their prefixes) to where they are read instead, a folder or
another URL. It is given in `osheaf.json`, as `locations`, or in the
environment variable `OPENSHEAF_LOCATIONS`, as `URL=TARGET` pairs
separated by `;`. A location changes where files are read, never what they
are checked against: an archive read from a folder is checked exactly as
if it had been fetched from its URL.

    # in resolution: where an archive is read:
    def locations():
        """{base URL or prefix: where it is read} from osheaf.json and OPENSHEAF_LOCATIONS."""
        out = dict(P.ARCHIVE.get("locations") or {}) if P.ARCHIVE else {}
        for part in os.environ.get(LOCATIONS, "").split(";"):
            url, eq, target = part.partition("=")
            if eq and url.strip():
                out[url.strip()] = target.strip()
        return out


    def locate(url):
        """Where the base URL URL is read: its replacement by the longest prefix configured, or itself."""
        found = locations()
        for prefix in sorted(found, key=len, reverse=True):
            if url.startswith(prefix):
                return found[prefix] + url[len(prefix):]
        return url

An archive read
---------------

A `Source` is one archive as read from one place. It is given a base URL
(`https`, `http` or `file`) or a folder, applies the locations, and reads
files below its base: from the folder, never following a path out of it,
or over HTTP, where a missing file (404, 410) is `None` and any other
failure makes the archive unavailable. Static servers cannot list
folders, so a source over HTTP lists nothing; a folder lists its files.

A source also knows the base URL to *record*, `at`: collections and URIs
record `https` URLs only (section 8.2). A source given by an `https` URL
records it; a folder that is an archive of these tools records the
`baseUrl` of its configuration, where it is served; any other source
records nothing, and the commands that need a location to record ask for
one.

    # in resolution: an archive read through its discovery document:
    class Source:
        """An archive as read from one place, through its discovery document (section 3.1)."""

        def __init__(self, where):
            self.given = str(where)
            target = locate(self.given) if "://" in self.given else self.given
            if target.startswith("file://"):
                target = urllib.parse.unquote(urllib.parse.urlparse(target).path)
            self.folder = None if "://" in target else Path(target).resolve()
            self.url = None if self.folder else (target if target.endswith("/") else target + "/")
            self.at = self._hint()
            self._disc = None

        def __str__(self):
            return self.given

        def _hint(self):
            if self.given.startswith("https://"):
                return self.given if self.given.endswith("/") else self.given + "/"
            cfg = self.folder / P.CONFIG_NAME if self.folder else None
            if cfg is not None and cfg.is_file():
                try:
                    base = names.json_value(cfg.read_text(encoding="utf-8")).get("baseUrl", "")
                except ValueError:
                    base = ""
                if base.startswith("https://") and base.endswith("/"):
                    return base
            return None

        <<resolution: reading a file of an archive>>

        <<resolution: the discovery document and the objects of an archive>>

Reading a file. Paths below the base are relative, and a folder never
yields a file outside it, also through a symbolic link (section 15.2). Over
HTTP, the path is percent-encoded segment by segment: the folders of the
hashed layout have names with `%` in them (`sheaf%3a...`, section 3.2),
which are themselves encoded (`%253a`).

    # in resolution: reading a file of an archive:
    def get(self, rel):
        """The bytes of the file REL below the base, or None if there is none."""
        if self.folder is not None:
            p = self.folder / rel
            try:
                p.resolve().relative_to(self.folder)
            except ValueError:
                return None
            return p.read_bytes() if p.is_file() else None
        url = urllib.parse.urljoin(self.url, urllib.parse.quote(rel, safe="/"))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=TIMEOUT) as r:
                data = r.read(MAX_BYTES + 1)
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return None
            raise Unavailable(f"{url}: HTTP {e.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise Unavailable(f"{url}: {e}") from None
        if len(data) > MAX_BYTES:
            raise Unavailable(f"{url}: more than {MAX_BYTES} bytes")
        return data

    def listing(self, rel):
        """The names of the files of the folder REL, or None over HTTP, which lists nothing."""
        if self.folder is None:
            return None
        p = self.folder / rel
        return sorted(x.name for x in p.iterdir() if x.is_file() and not x.is_symlink()) if p.is_dir() else []

The discovery document is read once, and must be of specification 0.2
(section 16.1: these tools read no other). The path of an object follows
the layout the archive's discovery document names, which is authoritative
(section 3.2), below its storage root; an absolute `storageRoot`, which
the specification allows, is read as it is. `object_url` is the URL of an
object version, `<storage root URL><path>/<version>/`, which a branch
records as `parent.url` (section 9.1); it exists only for a source with a
base URL to record. The pages of an archive that pages its objects
(section 3.1) are read with its discovery document, and their entries put
in its `objects`, so that everything after reads one list; a page missing
makes the archive unavailable.

    # in resolution: the discovery document and the objects of an archive:
    def discovery(self):
        """The discovery document of the archive (Unavailable if there is none of 0.2)."""
        if self._disc is None:
            data = self.get("opensheaf.json")
            if data is None:
                raise Unavailable(f"{self}: no discovery document opensheaf.json")
            try:
                disc = names.json_value(data)
            except ValueError as e:
                raise Unavailable(f"{self}: the discovery document is not JSON ({e})") from None
            if not isinstance(disc, dict) or disc.get("specification") != "0.2":
                raise Unavailable(f"{self}: not an archive of specification 0.2")
            if "objectPages" in disc:
                try:
                    disc["objects"] = P.listed_objects(disc, self.get)
                except ValueError as e:
                    raise Unavailable(f"{self}: {e}") from None
            self._disc = disc
        return self._disc

The storage root that a discovery document names is a path below the
archive, relative: a document that names an absolute path, a path with
`..`, an address of another host (`//host/`, `https://...`) is refused,
so that the objects of an archive are read from that archive only.

    # in resolution: the discovery document and the objects of an archive:
    def storage_root(self):
        """The storage root of the archive, a relative path ending with /."""
        root = self.discovery().get("storageRoot", "ocfl/")
        if not isinstance(root, str) or ":" in root or not owners.safe_relative(root.rstrip("/")) \
                or not root.endswith("/"):
            raise Unavailable(f"{self}: the storage root {root!r} is not a relative path below the archive")
        return root

    def object_path(self, obj_id):
        """The path of the object OBJ_ID below the base, in the archive's layout (section 3.2)."""
        return self.storage_root() + P.path_of(obj_id, self.discovery().get("storageLayout"))

    def object_url(self, obj_id, version):
        """The URL of VERSION of OBJ_ID at the base URL recorded (section 9.1), or None."""
        if self.at is None:
            return None
        return urllib.parse.urljoin(self.at, self.object_path(obj_id)) + f"/{version}/"

    def entries(self, nm=None):
        """The entries of objects of the discovery document, of the name NM if given."""
        return [o for o in self.discovery().get("objects", [])
                if isinstance(o, dict) and (nm is None or o.get("name") == nm)]

    def tombstone(self, obj_id):
        """The tombstone of OBJ_ID in the discovery document, or None (section 13.3)."""
        return next((t for t in self.discovery().get("tombstones", [])
                     if isinstance(t, dict) and t.get("id") == obj_id), None)

    def object_folder(self, obj_id):
        """The folder of the object OBJ_ID, read in place, for an archive in a folder; or None."""
        if self.folder is None:
            return None
        d = self.folder / self.object_path(obj_id)
        return d if (d / "inventory.json").is_file() else None

Copying an object
-----------------

An archive in a folder is read in place. An archive over HTTP is copied,
object by object, into a scratch folder, and read there with the
functions that read the archive's own storage root: an object is the same
OCFL folder wherever it is. `fetch_object` copies an object's versions up
to `upto` (by default its head), and is also what [mirrors](22-mirrors.md)
use to copy a line into the storage root, from either kind of source:

1. the inventory of every version, from its version folder (section 4.1).
   Its bytes are what a pin fixes; its checksum file only repeats their
   digest, so a checksum file missing, or not stating that digest, does
   not make the copy fail (section 12.3): it is reported through `warn`,
   and the copy gets a checksum file that states the digest, as every
   archive must hold (section 4.1). A caller that has already judged
   the copy, and copies what it judged, gives `expect`, the digest of the
   inventory of each version it verified: an inventory fetched with other
   bytes (the copy changed between the two readings, or another server
   answered) makes the copy unavailable, never a copy of versions that
   were not the ones verified;
2. every file the inventory of the last version copied records, each
   checked against its digest: a file that does not match makes the copy
   unavailable, never a copy with a wrong file;
3. the witness folder of each version: listed in a folder; over HTTP only
   the witnesses whose names the reader can compute (section 14.1), given
   by `witness_names`: the signature files of the keys the owner's key log
   lists, or, for a key log, of the rotation keys the version before
   commits to;
4. the inventory of the last version copied becomes the root inventory, so
   that a copy stopping before the head is a valid object of its own.

A version's files are read through the inventory of the last version
copied: its `versions` give the state of every earlier version, and its
manifest the content paths. A signature fixes only the bytes of the
inventory of the version it signs, so an unsigned last version could
restate the state of an earlier, signed one, and a reader would take that
version's files from it. The inventory of each version folder is the
inventory as of that version: its `head` is that version, and its
`versions` are those of the head inventory up to it, equal as JSON values
(sections 4.1 and 14.2; OCFL 1.1, section 3.7, whose validation code E066
asks the same of the state). `version_problem` checks one inventory
against the last one, and `fetch_object` refuses a copy in which one
disagrees. `inventories_problem` does the same for a copy read in place,
whose root inventory must also be, as a JSON value, the inventory of its
head version, the one its signature names: its bytes may differ, and a pin
to them is then reported as not matching (section 12.3). With the two in agreement, every earlier version's state is the
one its own inventory, the one signed, records, and each file read through
the manifest has the digest that state names, checked as it is fetched.

A copy read in place is checked as a copy fetched is, before anything
is read from it (`folder_problem`): every path of its manifest is a
content path of the object, a regular file below the object's folder (not
a link leading out of it), with the digest the manifest gives. Without
that, a file changed in the folder, a PDF, a `datacite.json`, an
`object.json`, would be read as the one the signed inventory names, and
the copy would still resolve as verified. Reading every file once costs
what copying it would, without the writing.

Content paths and witness names come from the files fetched, so they are
checked before they are written: every path of the manifest of every
inventory fetched must be a content path of the object (`vN/content/...`,
[key logs](06-owners.md)), and a path leaving the object is refused; and
one copy brings `MAX_FETCH_FILES` files and `MAX_FETCH_BYTES` bytes at most
(section 15.2).

    # in resolution: copying an object from another archive:
    def safe_path(rel):
        return owners.safe_relative(rel)


    def checksum_warning(where, obj_id, n):
        return (f"{where}: {obj_id} v{n}: the checksum file of its inventory is missing, or does not "
                "state its digest (section 12.3)")


    def checksum_problems(where, obj_id, d, inv):
        """The warnings for the checksum files missing or wrong in the copy in D, read in place."""
        out = []
        for n in range(1, int(inv["head"][1:]) + 1):
            data, sc = d / f"v{n}" / "inventory.json", d / f"v{n}" / "inventory.json.sha512"
            if data.is_file() and (not sc.is_file() or
                                   owners.sidecar_digest(sc.read_bytes()) != names.sha512_hex(data.read_bytes())):
                out.append(checksum_warning(where, obj_id, n))
        return out


    def version_problem(inv, n, copy):
        """Why COPY, the inventory held in the folder of vN, is not the inventory INV as of vN
        (sections 4.1 and 14.2), or None."""
        upto = [f"v{k}" for k in range(1, n + 1)]
        if not isinstance(copy, dict) or copy.get("head") != f"v{n}":
            return "its inventory is not one of that version"
        held, stated = copy.get("versions"), inv.get("versions")
        if not isinstance(held, dict) or not isinstance(stated, dict) or sorted(held) != sorted(upto) \
                or any(held[v] != stated.get(v) for v in upto):
            return "its inventory does not record the versions up to it as the head inventory does"
        return None


    def inventories_problem(d, inv):
        """Why the inventories of the version folders of the object in D, read in place, are not
        those of its root inventory INV as of each version (sections 4.1 and 14.2), or None."""
        try:
            head = int(inv["head"][1:])
        except (KeyError, TypeError, ValueError):
            return "its inventory cannot be read"
        for n in range(1, head + 1):
            p = d / f"v{n}" / "inventory.json"
            if not p.is_file():
                return f"v{n} has no inventory (section 4.1)"
            try:
                copy = names.json_value(p.read_bytes())
            except ValueError:
                copy = None
            if n == head:
                if copy != inv:
                    return f"v{n}: the root inventory is not that of the head version (section 14.2)"
                continue
            problem = version_problem(inv, n, copy)
            if problem:
                return f"v{n}: {problem} (section 14.2)"
        return None


    def folder_problem(d, inv):
        """Why the files of the object in D, read in place, are not those its root inventory INV
        names (a content path out of the object, a file missing, out of the folder or with
        another digest), or None."""
        try:
            head = int(inv["head"][1:])
            manifest = list(inv["manifest"].items())
        except (KeyError, TypeError, ValueError, AttributeError):
            return "its inventory cannot be read"
        top = d.resolve()
        for dig, paths in manifest:
            for cp in paths if isinstance(paths, list) else [paths]:
                if not isinstance(cp, str) or not owners.content_path(cp, inv, head):
                    return f"a content path out of the object: {cp!r}"
                p = d / cp
                try:
                    p.resolve().relative_to(top)
                    data = p.read_bytes() if p.is_file() else None
                except (ValueError, OSError):
                    data = None
                if data is None or names.sha512_hex(data) != dig:
                    return f"{cp} is missing, or does not have its digest"
        return None


    def fetch_object(src, obj_id, dest, *, upto=None, witness_names=None, warn=None, expect=None):
        """Copy the object OBJ_ID of the archive SRC, v1 to UPTO (default: its head), into the new
        folder DEST, checking every file; WITNESS_NAMES(n, dest) names the witness files of vN
        to fetch over HTTP; WARN(message) hears of checksum files missing or wrong; EXPECT, if
        given, {n: the digest of the inventory of vN} that each inventory fetched must have.
        Returns the number of the last version copied."""
        base = src.object_path(obj_id)
        root = src.get(f"{base}/inventory.json")
        if root is None:
            raise Unavailable(f"{src}: no object {obj_id}")
        try:
            head = int(names.json_value(root)["head"][1:])
        except (ValueError, KeyError, TypeError):
            raise Unavailable(f"{src}: the inventory of {obj_id} cannot be read") from None
        upto = min(upto or head, head)
        dest.mkdir(parents=True)
        (dest / "0=ocfl_object_1.1").write_text("ocfl_object_1.1\n")
        last, fetched, earlier = None, [0, 0], []

        def get(rel):
            data = src.get(rel)
            if data is not None:
                fetched[0] += 1
                fetched[1] += len(data)
                if fetched[0] > MAX_FETCH_FILES or fetched[1] > MAX_FETCH_BYTES:
                    raise Unavailable(f"{src}: {obj_id} has more than {MAX_FETCH_FILES} files or "
                                      f"{MAX_FETCH_BYTES} bytes: not copied (section 15.2)")
            return data

        for n in range(1, upto + 1):
            data = get(f"{base}/v{n}/inventory.json")
            if data is None:
                raise Unavailable(f"{src}: {obj_id} v{n} has no inventory (section 4.1)")
            if expect is not None and names.sha512_hex(data) != expect.get(n):
                raise Unavailable(f"{src}: {obj_id} v{n}: the inventory fetched is not the one verified "
                                  "(section 12.3): not copied")
            sc = get(f"{base}/v{n}/inventory.json.sha512")
            if sc is None or owners.sidecar_digest(sc) != names.sha512_hex(data):
                if warn:
                    warn(checksum_warning(src, obj_id, n))
                sc = owners.sidecar(data)
            try:
                inv_n = names.json_value(data)
                bad = [cp for ps in inv_n["manifest"].values() for cp in ps if not owners.content_path(cp, inv_n, n)]
            except (ValueError, KeyError, TypeError, AttributeError):
                raise Unavailable(f"{src}: the inventory of {obj_id} v{n} cannot be read") from None
            if bad:
                raise Unavailable(f"{src}: {obj_id} v{n}: a content path out of the object: {bad[0]!r}")
            (dest / f"v{n}").mkdir()
            (dest / f"v{n}" / "inventory.json").write_bytes(data)
            (dest / f"v{n}" / "inventory.json.sha512").write_bytes(sc)
            last = (data, sc)
            earlier.append(inv_n)
        inv = earlier.pop()
        if inv.get("id") != obj_id or inv.get("head") != f"v{upto}":
            raise Unavailable(f"{src}: the inventory of {obj_id} v{upto} is not one of that version")
        for n, inv_n in enumerate(earlier, 1):
            problem = version_problem(inv, n, inv_n)
            if problem:
                raise Unavailable(f"{src}: {obj_id} v{n}: {problem} (section 14.2): not copied")
        for dig, paths in inv.get("manifest", {}).items():
            for cp in paths:
                if not owners.content_path(cp, inv, upto):
                    raise Unavailable(f"{src}: {obj_id}: a content path out of the object: {cp!r}")
                data = get(f"{base}/{cp}")
                if data is None or names.sha512_hex(data) != dig:
                    raise Unavailable(f"{src}: {obj_id}: {cp} is missing, or does not have its digest")
                (dest / cp).parent.mkdir(parents=True, exist_ok=True)
                (dest / cp).write_bytes(data)
        (dest / "inventory.json").write_bytes(last[0])
        (dest / "inventory.json.sha512").write_bytes(last[1])
        for n in range(1, upto + 1):
            folder = f"{base}/{sign.WITNESSES}/v{n}"
            found = src.listing(folder)
            if found is None:
                found = witness_names(n, dest) if witness_names else ()
            for name in found:
                if not safe_path(name) or "/" in name:
                    continue
                data = get(f"{folder}/{name}")
                if data is not None:
                    (dest / sign.WITNESSES / f"v{n}").mkdir(parents=True, exist_ok=True)
                    (dest / sign.WITNESSES / f"v{n}" / name).write_bytes(data)
        return upto

The witness names a reader over HTTP can compute. A version of a key log
after the first is signed by rotation keys of the version before, whose
digests its `next` lists; the first 16 characters of a key's digest name
its signature file (section 7.2), so the digests are enough. A version of
a line is signed by current keys of some version of its owner's key log:
every key that any version lists, on either side of a fork, may have
signed it.

    # in resolution: copying an object from another archive:
    def key_log_witness_names(n, dest):
        """The names of the signature files that may sign vN of the key log copied into DEST."""
        if n == 1:
            return []
        inv = names.json_value((dest / f"v{n - 1}" / "inventory.json").read_bytes())
        k = P.read_json(dest, inv, owners.KEYS, f"v{n - 1}") or {}
        return [f"signature-{d[:16]}.json" for d in k.get("next", []) if isinstance(d, str)]


    def line_witness_names(log):
        """A function naming the signature files that may sign a version of a line of LOG's owner."""
        dids = set()
        for v in log.versions if log else []:
            dids.update((v.keys or {}).get("keys", []))
            for c in (v.carried if v.fork_record else []):
                dids.update((c.keys or {}).get("keys", []))
        found = sorted(sign.file_name(did) for did in dids if isinstance(did, str))
        return lambda n, dest: found

A copy of a line
----------------

A `Copy` is one copy of a line, found at one place, in a folder: the
archive's own storage root, an archive on disk, or the scratch folder an
object over HTTP was copied into. Its versions are judged against the key
log the resolver has met for its owner (section 7.3), and the copy answers
what the resolver asks: the digest of a version's inventory, as its own
version folder holds it; the status of a version; the latest signed one.

Two copies *agree* when the inventory of the earlier head is the same file
in both (section 7.4). A host can add to its copy versions that are not
signed, which are not versions of the line (section 7.3) and change
nothing for a reader; so the resolver compares copies up to their latest
signed versions, and a copy whose signed versions differ from another's is
a fork of the line. The versions a copy holds after its latest signed one
are not ignored for all that: they are reported with their status
(section 7.4), since a reader should know that a host holds versions that
are not the line's, or that are unchecked until their key log is found.

    # in resolution: a copy of a line, judged:
    SIGNED_LIKE = (sign.SIGNED, sign.VOUCHED)
    MEMBER_STATUS = {sign.SIGNED: "verified", sign.VOUCHED: "verified", sign.CONTESTED: "contested",
                     sign.UNCHECKED: "unchecked", sign.UNSIGNED: "not a version", sign.INVALID: "not a version"}


    @dataclass
    class Copy:
        """A copy of a line, found at WHERE, held in the folder DIR, judged against LOG."""
        where: str
        dir: Path
        inv: dict
        log: object
        statuses: list
        src: object = None

        @property
        def id(self):
            return self.inv["id"]

        @property
        def head(self):
            return int(self.inv["head"][1:])

        def digest(self, n):
            p = self.dir / f"v{n}" / "inventory.json"
            return names.sha512_hex(p.read_bytes()) if 0 < n and p.is_file() else None

        def status(self, n):
            return self.statuses[n - 1] if 0 < n <= len(self.statuses) else None

        @property
        def latest_signed(self):
            return sign.latest_signed(self.statuses) or 0

        def find(self, digest):
            """The number of the version whose inventory has DIGEST, or None."""
            return next((n for n in range(1, self.head + 1) if self.digest(n) == digest), None)

        def read(self, logical, n):
            return P.read_json(self.dir, self.inv, logical, f"v{n}")

        def after_signed(self):
            """The versions held after the latest signed one, as (number, status) pairs (section 7.4)."""
            return [(n, self.status(n)) for n in range(self.latest_signed + 1, self.head + 1)]

        def agrees(self, other):
            """Whether this copy and OTHER agree up to the earlier of their latest signed versions."""
            k = min(self.latest_signed, other.latest_signed)
            return k == 0 or self.digest(k) == other.digest(k)

The resolver
------------

A `Resolver` keeps, for one run, the archives it has read, the objects it
has copied (in a scratch folder removed at the end), the key logs it has
met, and its *notes*: what it found that a reader should know (an archive
unavailable, a fork, an ended owner), each with its severity, as the
findings of a verifier (section 14.1). It reads the places it is given,
and the archive's own storage root when there is one.

    # in resolution: the resolver:
    class Resolver:
        """Finds and checks copies of lines and key logs at the places it is given (section 12.3)."""

        def __init__(self, places=(), here=True):
            self.places = list(places)
            self.here = here and P.OCFL is not None
            self.cache = Path(tempfile.mkdtemp(prefix="osheaf-resolve-"))
            self.sources, self.fetched, self.logs, self.notes, self.bases = {}, {}, {}, [], {}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            shutil.rmtree(self.cache, ignore_errors=True)

        def note(self, severity, message):
            if (severity, message) not in self.notes:
                self.notes.append((severity, message))

        <<resolution: the archives and the objects the resolver reads>>

        <<resolution: the key logs the resolver meets>>

        <<resolution: the copies of a line>>

        <<resolution: resolving a pin, a version or a line>>

        <<resolution: resolving a sheaf: URI>>

### Archives and objects

An archive that cannot be read is noted once and skipped; the places are
tried in the order given, those of the call first (the `at` of a URI,
then the `at` of a member), then those of the resolver, without
repetition. `folder` gives the folder holding an object at a place: the
archive's own storage root ("here"), the folder of an archive on disk, or
a copy fetched over HTTP, once per run.

    # in resolution: the archives and the objects the resolver reads:
    def source(self, where):
        """The archive at WHERE, or None if it cannot be read (noted)."""
        if where not in self.sources:
            src = Source(where)
            try:
                src.discovery()
            except Unavailable as e:
                self.note("warning", f"unavailable: {e}")
                src = None
            self.sources[where] = src
        return self.sources[where]

    def where(self, extra=()):
        out = []
        for w in list(extra) + self.places:
            if w and w not in out:
                out.append(w)
        return out

    def folder(self, where, obj_id, witness_names=None, upto=None):
        """The folder holding the object OBJ_ID at WHERE ('here': this archive), or None; over
        HTTP, a copy of v1 to UPTO (default: the head), kept apart from the whole copy."""
        if where == "here":
            d = P.obj_dir(obj_id) if self.here else None
            return d if d is not None and (d / "inventory.json").is_file() else None
        src = self.source(where)
        if src is None:
            return None
        if src.folder is not None:
            key = (where, obj_id)
            if key not in self.fetched:
                try:
                    d = src.object_folder(obj_id)
                except (ValueError, Unavailable):
                    d = None
                problem = folder_problem(d, P.load_inventory(d) or {}) if d is not None else None
                if problem:
                    self.note("warning", f"{where}: {obj_id}: {problem}: not read (section 12.3)")
                    d = None
                self.fetched[key] = d
            return self.fetched[key]
        key = (where, obj_id) if upto is None else (where, obj_id, upto)
        if key not in self.fetched:
            dest = self.cache / str(len(self.fetched))
            try:
                fetch_object(src, obj_id, dest, upto=upto, witness_names=witness_names,
                             warn=lambda m: self.note("warning", m))
                self.fetched[key] = dest
            except Unavailable as e:
                if "no object" not in str(e):
                    self.note("warning", str(e))
                self.fetched[key] = None
        return self.fetched[key]

A branch records where its parent version is, `parent.url`, the URL of
the object version (section 9.1), not the base URL of the archive holding
it, which the resolver needs to read that archive's discovery document.
The base is the prefix of the URL below which the archive's storage root,
`storageRoot` of its discovery document, holds the object; the storage root
may have any name, or be elsewhere (section 3.1). `archive_of` therefore
tries the prefixes of the URL that end with `/`, the conventional
`.../ocfl/` cut first, so that the common case reads one discovery document,
then from the longest to the shortest, and takes the first whose discovery
document has a storage root that the URL is below. A prefix that is not an
archive is not noted: it was only a guess. The answer is kept, and so is
the archive found, which the resolution that follows reads.

    # in resolution: the archives and the objects the resolver reads:
    def archive_of(self, url):
        """The base URL of the archive holding the object version at URL (a parent.url,
        section 9.1), as a list of one, found through its discovery document; [] if none is."""
        if url not in self.bases:
            self.bases[url] = []
            u = urllib.parse.urlsplit(url)
            if u.scheme in ("https", "http") and u.netloc:
                origin = f"{u.scheme}://{u.netloc}"
                cuts = [k + 1 for k in range(len(u.path) - 2, -1, -1) if u.path[k] == "/"]
                guess = u.path.find("/ocfl/")
                if guess >= 0:
                    cuts.insert(0, guess + 1)
                for k in dict.fromkeys(cuts):
                    base = origin + u.path[:k]
                    src = self.sources.get(base) or Source(base)
                    try:
                        root = urllib.parse.urljoin(base, src.storage_root())
                    except Unavailable:
                        continue
                    if not root.endswith("/"):
                        root += "/"
                    if (origin + u.path).startswith(root) and len(origin + u.path) > len(root):
                        self.sources[base] = src
                        self.bases[url] = [base]
                        break
        return self.bases[url]

### Key logs

The key log of an owner is the copies the resolver finds of it, met one
with another as an archive meets them (section 6.3), in memory: the
archive's own first, then the copy beside each copy of a line it reads.
Whichever extends the other is used; when two differ, the copy met first
gets a fork record carrying the other side, so that signatures naming
either side are judged, and the versions they sign contested from the fork
point on (section 7.3). Every copy found is kept in `found`, so that a
[mirror](22-mirrors.md) can record what it met in the archive's own
storage root.

    # in resolution: the key logs the resolver meets:
    def key_log(self, owner, where=()):
        """The key log of OWNER: this archive's copy met with those at WHERE, or None."""
        entry = self.logs.setdefault(owner, {"log": None, "met": set(), "found": []})
        oid = names.object_id(owner, owner)
        for w in (["here"] if self.here else []) + list(where):
            if w in entry["met"]:
                continue
            entry["met"].add(w)
            d = self.folder(w, oid, key_log_witness_names)
            if d is None:
                continue
            try:
                log = owners.load_key_log(d)
            except owners.OwnerError as e:
                self.note("warning", f"{w}: the key log of {owner}: {e}")
                continue
            if log.owner != owner:
                continue
            entry["found"].append((w, log))
            before = entry["log"]
            entry["log"] = log if before is None else before.met(log)
            if before is not None and before.fork_point is None and entry["log"].fork_point is not None:
                self.note("result", f"a fork of the key log of {owner} at v{entry['log'].fork_point}, "
                          f"met at {w} (section 6.3)")
        return entry["log"]

    def found_logs(self, owner):
        """[(place, KeyLog)] of every copy of the key log of OWNER found."""
        return list(self.logs.get(owner, {}).get("found", []))

    def owner_notes(self, owner):
        """What a reader is told about OWNER: an end, a fork, exposed keys, a successor (section 12.3)."""
        log = (self.logs.get(owner) or {}).get("log")
        if log is None:
            return []
        out = []
        if log.fork_point:
            out.append(f"owner {owner} ended by a fork of its key log at v{log.fork_point}")
        elif log.ended:
            out.append(f"owner {owner} ended")
        if log.successor:
            out.append(f"owner {owner}: successor {log.successor} named by its ending version")
        out += [f"owner {owner}: exposed key {did}" for did in sorted(log.exposed_keys())]
        return out

### The copies of a line

The copies of a line are looked for at the places given and at the
resolver's own; for each archive that holds one, the key log beside it is
met first, so that over HTTP the signature files of every key it lists can
be named and fetched. Each copy is then checked as section 12.3 says: the
name is a name of its genesis record, and every version's `object.json`
records the line; and, since its versions are read through its root
inventory, the inventory of each version folder is that inventory as of
the version (`inventories_problem`, above), so that an unsigned head cannot
restate the files of a signed version before it. A copy that fails is
noted and left out. A checksum file
missing or wrong in a copy read in place is noted, as one in a copy
fetched is (section 12.3); this archive's own are its verification's. Its versions
are judged against the key log met so far, which, once every copy is
read, is met again with all of them: a later copy may bring a longer key
log, or a fork. A tombstone met in an archive read stops nothing: a
tombstone is not signed, and the resolver keeps looking, and reports both
the copies it finds and the tombstone (section 12.3).

    # in resolution: the copies of a line:
    def copies(self, nm, owner, where=()):
        """The copies of the line (NM, OWNER) at WHERE and the resolver's places, checked."""
        obj_id = names.object_id(nm, owner)
        places = list(dict.fromkeys((["here"] if self.here else []) + self.where(where)))
        found = []
        for w in places:
            if w != "here":
                src = self.source(w)
                if src is None or (src.folder is None and not any(o.get("id") == obj_id for o in src.entries(nm))):
                    continue
            log = self.key_log(owner, [] if w == "here" else [w])
            d = self.folder(w, obj_id, line_witness_names(log))
            if d is None:
                continue
            inv = P.load_inventory(d)
            problem = self.identity_problem(obj_id, d, inv)
            if problem:
                self.note("warning", f"{w}: {obj_id}: not a copy of the line: {problem}")
                continue
            if w != "here" and self.sources[w].folder is not None:
                for message in checksum_problems(w, obj_id, d, inv):
                    self.note("warning", message)
            found.append((w, d, inv))
        log = self.key_log(owner)
        out = []
        for w, d, inv in found:
            _, statuses = P.line_statuses(d, inv, log)
            out.append(Copy(w, d, inv, log, statuses, None if w == "here" else self.sources.get(w)))
        if out and self.tombstoned(obj_id, where):
            self.note("result", f"{obj_id}: taken down in an archive read, and found elsewhere (section 12.3)")
        return out

    def identity_problem(self, obj_id, d, inv):
        """Why the object in D is not a copy of the line OBJ_ID (section 12.3), or None."""
        if inv is None or inv.get("id") != obj_id:
            return "its inventory names another object"
        problem = inventories_problem(d, inv)
        if problem:
            return problem
        _, nm, owner = obj_id.split(":")
        g = P.read_logical(d, inv, P.GENESIS, "v1")
        if g is None or not names.is_name_of(nm, g.read_bytes()):
            return "the name is not a name of its genesis record (section 5.2)"
        for ver in inv["versions"]:
            obj = P.read_json(d, inv, P.OBJ, ver) or {}
            if (obj.get("name"), obj.get("owner")) != (nm, owner):
                return f"{ver}: object.json does not record the line"
        return None

### Resolving

`pin` answers the question of collections and branches: is the object
version `version`, whose inventory has `digest`, of the line (`nm`,
`owner`), available and signed? It looks at every copy found, and gives
the status of section 8.5:

- **verified** or **contested**, when a copy holds a version whose
  inventory has the digest, and that version is signed, or contested
  (section 7.3);
- **unchecked** or **not a version**, when the version found is unchecked,
  or unsigned or invalid;
- **mismatch**, when copies are found but none holds the digest at that
  version;
- **removed**, when no copy is found and an archive read has a tombstone of
  the line (section 13.3);
- **unavailable** otherwise.

A copy that holds the version with another digest is noted with its
location, whether another copy matches or not: the status comes from the
copies that match, and a copy that does not is damage or tampering where
it is (section 12.3).

A version of a key log is looked up in the key log met, where it is held
or carried by a fork record (section 6.3); it counts as signed when it is
a version of the key log: a version held with that number and digest
that fails the checks of the key log (section 14.3) is not a version.

The answer is a `Found`: the status, the copy and version where it was
found, and the notes. A pin comes from a member of a collection, which may
be another archive's: one whose line is not two names, whose version is not
`v` and a positive integer, or whose digest is not 128 hexadecimal digits,
pins nothing, and is not a version (section 8.5), noted, never a crash of
the verification that asked.

    # in resolution: resolving a pin, a version or a line:
    def pin(self, nm, owner, version, digest, where=()):
        """The status of the pin (VERSION, DIGEST) of the line (NM, OWNER) (section 8.5), as a Found."""
        if not (all(isinstance(x, str) and names.NAME.match(x) for x in (nm, owner))
                and isinstance(version, str) and re.fullmatch(r"v[1-9][0-9]*", version)
                and isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{128}", digest)):
            self.note("warning", f"sheaf:{nm}:{owner}: the pin {version!r} sha512={digest!r} is not a line, "
                      "an object version and a digest (section 8.5)")
            return Found("not a version", version=version if isinstance(version, str) else None)
        if nm == owner:
            log = self.key_log(owner, self.where(where))
            v = log.lookup(int(version[1:]), digest) if log else None
            if v is not None and log.verified(int(version[1:]), digest) is not None:
                return Found("verified", version=version, digest=digest, log=log)
            status = "unavailable" if log is None else "mismatch" if v is None else "not a version"
            return Found(status, version=version, digest=digest, log=log)
        copies = self.copies(nm, owner, where)
        n = int(version[1:])
        for c in copies:
            if c.digest(n) not in (None, digest):
                self.note("warning", f"{c.where}: {names.object_id(nm, owner)} {version} does not match "
                          "the pin (section 12.3)")
        for c in copies:
            if c.digest(n) == digest:
                return Found(MEMBER_STATUS.get(c.status(n), "not a version"), c, version, digest, copies)
        if copies:
            return Found("mismatch", None, version, digest, copies)
        return Found("removed" if self.tombstoned(names.object_id(nm, owner), where) else "unavailable",
                     None, version, digest, copies)

    def tombstoned(self, obj_id, where=()):
        """Whether an archive read holds a tombstone of OBJ_ID (section 13.3)."""
        if self.here and any(t.get("id") == obj_id for t in P.TOMBSTONES):
            return True
        return any(self.sources.get(w) is not None and self.sources[w].tombstone(obj_id)
                   for w in self.where(where))

`latest` answers the question of catalogues and resolvers: what is the
latest signed version of the line? Among the copies found, the one with
the latest signed version is taken, and every copy that does not agree
with it is a fork of the line, noted with where it was found and the
status of each side (section 7.4). When two copies with signed versions
disagree, the resolver does not choose (section 12.3): it notes the fork
and answers nothing, unless a pin decides. A copy that agrees but stops
earlier is older, and noted as such only by being older.

    # in resolution: resolving a pin, a version or a line:
    def latest(self, nm, owner, where=()):
        """The copy with the latest signed version of the line among the copies that agree, as a
        Found (status unavailable, removed or fork when there is none)."""
        copies = self.copies(nm, owner, where)
        signed = sorted((c for c in copies if c.latest_signed), key=lambda c: -c.latest_signed)
        if not signed:
            status = ("removed" if self.tombstoned(names.object_id(nm, owner), where) else "unavailable") \
                if not copies else "not a version"
            return Found(status, None, None, None, copies)
        top = signed[0]
        forks = [c for c in signed if not top.agrees(c)]
        for c in forks:
            self.note("result", f"a fork of the line {top.id}: the copy at {c.where} (latest signed "
                      f"v{c.latest_signed}) does not agree with the copy at {top.where} (latest signed "
                      f"v{top.latest_signed}) (section 7.4)")
        if forks:
            return Found("fork", None, None, None, copies)
        v = f"v{top.latest_signed}"
        return Found("verified", top, v, top.digest(top.latest_signed), copies)

    def document_version(self, nm, owner, n, where=()):
        """The object version holding document version N that the history of the latest signed
        version lists (section 12.1), as a Found."""
        found = self.latest(nm, owner, where)
        if found.copy is None:
            return found
        c = found.copy
        for h in P.history_of(c.dir, c.inv, found.version):
            if P.doc_version_of(c.dir, c.inv, h) == n:
                k = int(h[1:])
                return Found(MEMBER_STATUS.get(c.status(k), "not a version"), c, h, c.digest(k), found.copies)
        self.note("warning", f"{c.id}: no document version {n} in the history of {found.version}")
        return Found("unavailable", None, None, None, found.copies)

The answer of a resolution.

    # in resolution: a copy of a line, judged:
    @dataclass
    class Found:
        """What a resolver found: a status (section 8.5), the copy and version, the copies seen."""
        status: str
        copy: object = None
        version: str = None
        digest: str = None
        copies: list = field(default_factory=list)
        log: object = None

        @property
        def ok(self):
            return self.status in ("verified", "contested")

### Resolving a sheaf: URI

A URI names a line, a document version of it, an object version by its
pin, or a key log and its versions (section 12.1). The resolver tries the
URI's `at` first, then the places it was given. Without an owner part, the
URI names the originator's line: the owner is found among the lines of
that name the archives list, as the `originator` of their genesis record,
or the name itself when an archive lists it as an owner, whose key log the
URI then names. Short forms are expanded among the lines the archives
read list (section 12.2), and refused when more than one matches. A work,
`sheaf:<name>:*`, is not resolved by these tools yet (section 12.4).

    # in resolution: resolving a sheaf: URI:
    def resolve(self, text, where=()):
        """Resolve the sheaf: URI TEXT (section 12.3): (the line's identifier or None, Found)."""
        u = names.parse_sheaf(text, short=True, fold=True)
        where = self.where(([u.at] if u.at else []) + list(where))
        if u.owner == "*":
            raise ValueError("a work, sheaf:<name>:*, is searched for (section 12.4), which these tools "
                             "do not do yet")
        nm, owner = self.expand(u, where)
        if nm == owner:
            log = self.key_log(owner, where)
            if log is None:
                return None, Found("unavailable")
            if u.version is None:
                v = log.side()[-1]
                return names.object_id(owner, owner), Found("verified", version=f"v{v.number}",
                                                            digest=v.digest, log=log)
            if u.sha512 is None:
                side = log.side()
                if u.version > len(side):
                    return names.object_id(owner, owner), Found("unavailable", log=log)
                return names.object_id(owner, owner), Found(
                    "verified", version=f"v{u.version}", digest=side[u.version - 1].digest, log=log)
            return names.object_id(owner, owner), self.pin(owner, owner, f"v{u.version}", u.sha512, where)
        obj_id = names.object_id(nm, owner)
        if u.version is None:
            return obj_id, self.latest(nm, owner, where)
        if u.sha512 is None:
            return obj_id, self.document_version(nm, owner, u.version, where)
        for c in self.copies(nm, owner, where):
            k = c.find(u.sha512)
            if k is not None:
                held = (c.read(P.OBJ, k) or {}).get("documentVersion")
                if held != u.version:
                    self.note("warning", f"{obj_id}: the version pinned holds document version {held}, "
                              f"not {u.version}")
                    return obj_id, Found("mismatch", c, f"v{k}", u.sha512)
                return obj_id, Found(MEMBER_STATUS.get(c.status(k), "not a version"), c, f"v{k}", u.sha512)
        copies = self.copies(nm, owner, where)
        status = "mismatch" if copies else ("removed" if self.tombstoned(obj_id, where) else "unavailable")
        return obj_id, Found(status, None, None, u.sha512, copies)

Finding the line of a URI among the lines the archives list. With complete
parts and an owner part, the line is the URI's. Otherwise every archive
read lists candidates: lines whose name starts with the name given and
whose owner starts with the owner part, or, without one, whose owner is
the originator of their genesis record, which is read from the copy.
Over HTTP only the first version is copied for this, without witnesses,
and kept apart from the copy of the whole line that the resolution then
makes with its witnesses: a short form resolves as the full URI does.

    # in resolution: resolving a sheaf: URI:
    def expand(self, u, where):
        """The (name, owner) of the line the URI U names, among the lines the archives list."""
        if u.is_complete() and u.owner is not None:
            return u.name, u.owner
        found = set()
        for w in (["here"] if self.here else []) + where:
            entries = P.discovery()["objects"] if w == "here" else (
                self.source(w).entries() if self.source(w) else [])
            for o in entries:
                nm, owner = o.get("name") or "", o.get("owner") or ""
                if not u.matches(nm, owner):
                    continue
                if u.owner is None:
                    if o.get("kind") != "owner" and self.originator(w, o.get("id")) != owner:
                        continue
                    if o.get("kind") == "owner" and nm != owner:
                        continue
                found.add((nm, owner))
        if len(found) != 1:
            listed = "\n".join(f"  sheaf:{n}:{o}" for n, o in sorted(found))
            raise ValueError(f"{u}: " + ("ambiguous, the candidates are:\n" + listed if found
                                         else "no line of that name in the archives read"))
        return found.pop()

    def originator(self, where, obj_id):
        """The originator of the genesis record of the object OBJ_ID at WHERE, or None."""
        d = self.folder(where, obj_id, upto=1)
        inv = P.load_inventory(d) if d else None
        g = P.read_logical(d, inv, P.GENESIS, "v1") if inv else None
        try:
            return names.read_genesis(g.read_bytes()).get("originator") if g else None
        except ValueError:
            return None

The command
-----------

`osheaf resolve URI` prints what a resolver found: the line, the copies
seen (where, head, latest signed version, and the versions after it with
their status), the version the URI
resolves to with its pin and status, and the notes, among them the state
of the owner (section 12.3: a resolver reports an ended owner, exposed
keys and successors). It shows the full form of what it resolved, and
exits with an error when nothing was resolved to. It works in an archive,
whose storage root and locations it then uses, or anywhere else.

    # in resolution: the command resolve:
    def main(args):
        """osheaf resolve URI [--at URL]... [--json]."""
        with Resolver(places=args.at or []) as r:
            try:
                line, found = r.resolve(args.uri)
            except ValueError as e:
                sys.exit(str(e))
            owner = line.split(":")[2] if line else None
            out = {"uri": args.uri, "line": line, "status": found.status, "version": found.version,
                   "inventorySha512": found.digest,
                   "foundAt": found.copy.where if found.copy else None,
                   "copies": [{"at": c.where, "head": f"v{c.head}",
                               "latestSigned": f"v{c.latest_signed}" if c.latest_signed else None,
                               "after": [{"version": f"v{n}", "status": s} for n, s in c.after_signed()]}
                              for c in found.copies],
                   "notes": [f"{s}: {m}" for s, m in r.notes] + (r.owner_notes(owner) if owner else [])}
            if found.ok and found.copy is not None:
                dv = (found.copy.read(P.OBJ, int(found.version[1:])) or {}).get("documentVersion")
                if dv is not None:
                    out["pin"] = f"sheaf:{line.split(':')[1]}:{owner}/v{dv}?sha512={found.digest}"
        if getattr(args, "json", False):
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print(f"{out['uri']}\n  line {line}")
            for c in out["copies"]:
                after = ", ".join(f"{a['version']} {a['status']}" for a in c["after"])
                print(f"  copy at {c['at']}: head {c['head']}, latest signed {c['latestSigned']}"
                      + (f"; after it: {after} (section 7.4)" if after else ""))
            print(f"  {found.status}" + (f": {found.version} sha512={found.digest}" if found.version else "")
                  + (f" at {out['foundAt']}" if out["foundAt"] else ""))
            if out.get("pin"):
                print(f"  pin {out['pin']}")
            for n in out["notes"]:
                print(f"  {n}")
        sys.exit(0 if found.ok else 1)
