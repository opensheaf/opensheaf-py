Document versions, history and dates
====================================

OCFL, as used in the [previous chapter](10-archive.md), knows only object
versions: `v1`, `v2`, ..., one for every change of an object. A reader of a
scholarly archive wants something else: the versions of the *work*, the
preprint, its correction, the version accepted by a journal. OpenSheaf calls
them *document versions* (section 7.3) and keeps the two numberings apart.
This chapter defines the functions that read and maintain document versions
inside the object versions; [depositing](13-deposit.md) and the
[description-only versions](14-description.md) use them, and
[verification](17-verify.md) checks their rules.

Object versions and document versions
-------------------------------------

Every object version holds two descriptions, `datacite.json` (the
description for readers and services, section 8) and `object.json`
(OpenSheaf's record of the object: its kind, its document version, its
sources, its state, section 9). `TODAY` is the date of the run, used as the
default date of everything a command records.

    # in the names of object.json and of its format:
    OBJ = "object.json"
    OBJ_FORMAT = "opensheaf-object/0.1"
    TODAY = datetime.date.today().isoformat()

The document version an object version holds is written in its
`object.json`.

    # in the document version an object version holds:
    def doc_version_of(obj_dir, inv, version):
        return read_json(obj_dir, inv, OBJ, version)["documentVersion"]

The two numberings diverge for three reasons. A *description-only version*
changes the description of an object (a DOI, a link to the published
article, a licence, a notice, a withdrawal) but not the files of the work,
so it is a new object version holding an existing document version. A
*completion* adds the sources of a version first deposited without them,
and keeps its number. And a version may be *found later*: a manuscript
submitted to a journal and deposited after the corrected version, which
gets the next number although it comes earlier in the history of the work.
Numbers are assigned by the archive, from 1, without gaps; they never say
what came first.

The name of the next object version, from the inventory (or `v1` for a new
object), is needed before the version is written, to record it in the
history.

    # in the name of the next object version:
    def next_object_version(inv):
        return f"v{int(inv['head'][1:]) + 1}" if inv else "v1"

The history and the current version
------------------------------------

The *history* is the order of the document versions in the history of the
work (section 7.3). Usually it is the order of their numbers, and
`object.json` says nothing about it. When a version is found later,
`object.json` gets a `history`: the list, in the order of the work, of the
last object version holding each document version. The last one is used
because it carries the most complete description of that document version
(a DOI added later, a notice). Once an object version has `history`, every
later one keeps it.

Without `history`, the default is computed from the inventory: for each
document version, the last object version holding it, in the order of the
numbers.

    # in the history of a document without a history in object.json:
    def default_history(obj_dir, inv):
        """Without `history`: the last object version holding each document
        version, in the order of the numbers (section 7.3)."""
        last = {}
        for ver in inv["versions"]:
            last[doc_version_of(obj_dir, inv, ver)] = ver
        return [last[n] for n in sorted(last)]

The history is read from the head version, the latest knowledge of the
archive; earlier object versions keep the history as it was known when
they were made.

    # in the history of a document as its head states it:
    def history_of(obj_dir, inv):
        """The history as read from the head version."""
        head = read_json(obj_dir, inv, OBJ)
        return head.get("history") or default_history(obj_dir, inv)

The *current version* is the one readers are sent to: the last entry of the
history. Landing pages, the index and the main collection use it rather
than the head, since the head may hold an earlier document version (one
found later, or one just described).

    # in the object version holding the current version of a document:
    def current_version(obj_dir, inv):
        """The object version holding the current document version: the last
        entry of the history of the head (section 7.3)."""
        head = read_json(obj_dir, inv, OBJ)
        return head["history"][-1] if head.get("history") else inv["head"]

Without `history`, this takes the head, which is the object version of the
highest document version as long as the head holds the current version:
true after a deposit and after the description-only versions of
[chapter 14](14-description.md), which describe the head. A completion of an
*earlier* version without sources is the exception: its object version
becomes the head without writing a history, and this function then returns
it, where the specification (the highest document version) and
`default_history` would give the later version. The case is rare (it needs
a version imported without sources, then a later version, then the
sources of the first) but these tools do not handle it yet.

### Carrying the history and the notices forward

Two parts of `object.json` outlive the document version they were written
with. *Notices* about a document version (a theorem found wrong, say) are
written after it, by description-only versions, and every later object
version keeps them, unchanged (section 7.3), so that a reader of any
later version sees them. The *history* is kept, updated, by every object
version once it exists.

Every function that builds a new `object.json` from scratch, or from an
earlier version, calls this one with the head's `object.json` (`prev`). It
copies the notices, then decides the history:

- without a history in the head, and without `--after`, nothing is written:
  the order of the numbers is the history;
- a new object version for a document version already in the history (a
  description-only version, or a completion) takes the place of that
  document version's entry, since it is now the last object version holding
  it;
- a new document version goes at the end, and becomes the current version;
- a new document version deposited `--after` an earlier one is inserted
  just after it, and the history is written from then on.

The specification says that a version whose place is unknown goes just
before the current version; with these tools the depositor says so, with
`--after` and the number before the current one.

    # in carry the notices and the history to a new object version:
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

The files of the notices (a notice may be a PDF with mathematics, section
9) are files of the content, so they must also be carried: these are the
files, in the head, of the notices with a `path`. Deposits add them to the
files of the new version.

    # in the notice files that every later object version keeps:
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

Dates
-----

DataCite records dates as a list of `{date, dateType}`, at most one per
type for our purposes. The types used by OpenSheaf (section 8) each have one
meaning: `Issued` the first public appearance of the work, the same in every
version; `Available` when this document version became public; `Created`
when a version not public at the time was written; `Updated` the latest
description-only version; `Withdrawn` the date of a withdrawal. Dates are
information for readers: they never order versions.

Reading a date tries several types in turn, the first found wins (the
collection orders by `Available`, else `Created`).

    # in read a date of a DataCite description:
    def date_of(dc, *types):
        for t in types:
            for d in dc.get("dates", []):
                if d["dateType"] == t:
                    return d["date"]
        return None

Setting a date replaces the date of that type, if any, and puts it last,
with an explanation for approximate dates (`dateInformation`, such as
"from file timestamps").

    # in set a date of a DataCite description:
    def set_date(dc, date_type, date, info=None):
        dates = [d for d in dc.get("dates", []) if d["dateType"] != date_type]
        entry = {"date": date, "dateType": date_type}
        if info:
            entry["dateInformation"] = info
        dc["dates"] = dates + [entry]
