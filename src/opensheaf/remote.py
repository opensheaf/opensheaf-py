# Generated from literate/20-resolution.md by opensheaf-literate: edit the document, not this file.
"""Other archives and sheaf: URIs (section 12 of OpenSheaf 0.2): archives read through their
discovery documents, over HTTP or from folders, at the locations configured; objects and key
logs copied from them and checked; copies of a line judged against the key logs met; sheaf:
URIs resolved to the latest signed version among the copies that agree (section 12.3).

    osheaf resolve URI [--at URL]... [--json]
"""

import json
import os
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

    def pin(self, nm, owner, version, digest, where=()):
        """The status of the pin (VERSION, DIGEST) of the line (NM, OWNER) (section 8.5), as a Found."""
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
