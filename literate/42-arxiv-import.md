Importing from arXiv: the object versions
=========================================

This chapter describes `osheaf arxiv import`, which turns the downloads of
[the first arXiv chapter](40-arxiv.md) into documents of the archive, using
the metadata of [the second](41-arxiv-metadata.md). Each arXiv version
becomes one object version, deposited as the chapter on deposits
describes; this chapter is about what goes into it.

The rules
---------

The specification fixes the main choices.

- **Byte for byte.** The PDF and the sources are those served by arXiv,
  unchanged; nothing is typeset. The files received from arXiv, before
  unpacking, are named in `object.json` under `external`, with role
  `source`, with their digests (section 9), so that anyone can check the
  import against arXiv.
- **Numbering.** Document versions are numbered by the archive, without
  gaps (section 7.3): if arXiv cannot provide version 2 of a paper, its
  versions 1, 3 and 4 become document versions 1, 2 and 3, and arXiv's
  label `v3` is recorded in `external`.
- **Missing sources.** A version for which arXiv has only a PDF is a
  document version without sources, with `sourcesMissing` in `object.json`
  saying why, and the PDF as its only rendition (section 9). Its sources
  may be added later, by completion (section 7.3).
- **Identity.** The object identifier is chosen by the depositor
  (section 6.3); the tool only proposes one.
- **Relations.** Each version `IsIdenticalTo` its arXiv version and
  `IsVersionOf` the DOI that arXiv registers for the paper, `10.48550/arXiv.ID`
  (section 8.1).

Papers already in the archive
-----------------------------

A paper is in the archive when some version of some document is related to
it, by its arXiv identifier or by its arXiv DOI, with or without a version
number. This finds the papers imported before, and also those deposited by
hand with a link to arXiv, so that a paper is never imported twice under
two identifiers. The answer maps arXiv identifiers to objects.

    # in arXiv: papers already in the archive:
    def already_archived():
        """arXiv identifier -> object, from the arXiv identifiers and arXiv DOIs
        (10.48550/arXiv.ID) related to any version of a document."""
        out = {}
        for obj_id, d, inv in P.objects():
            for ver in inv["versions"]:
                dc = P.read_logical(d, inv, "datacite.json", ver)
                if not dc:
                    continue
                for r in json.loads(dc.read_text()).get("relatedIdentifiers", []):
                    v = r["relatedIdentifier"]
                    if r["relatedIdentifierType"] == "arXiv":
                        out[re.sub(r"v\d+$", "", v.split(":", 1)[1])] = obj_id
                    elif r["relatedIdentifierType"] == "DOI" and v.lower().startswith("10.48550/arxiv."):
                        out[re.sub(r"v\d+$", "", v[len("10.48550/arXiv."):])] = obj_id
        return out

When a paper is in the archive, `--update` adds its new arXiv versions. The
versions already present are those named, with their arXiv label, by the
`external` entries of role `source` in any version of the object.

    # in arXiv: versions already in an object:
    def archived_versions(obj_id):
        """The arXiv versions (e.g. 2303.18112v4) already in object OBJ_ID."""
        d = P.OCFL / obj_id
        inv = P.load_inventory(d)
        out = set()
        for ver, info in inv["versions"].items():
            obj = P.read_json(d, inv, P.OBJ, ver)
            for e in obj.get("external", []):
                if e.get("service") == "arXiv":
                    out.add(e["record"].rsplit("/abs/", 1)[1])
        return out

For a new paper without an identifier in `identifiers.json`, the import
stops and proposes one, made of the first words of the title, at most 56
characters, in lower case ASCII, with a number added if it is taken. The
specification advises against identifiers derived mechanically from titles,
and the depositor will usually choose something shorter; the proposal is
there to save typing.

    # in arXiv: proposing an identifier from the title:
    def slug(title, taken):
        t = unicodedata.normalize("NFKD", detex(title))  # It\\^o -> Ito
        t = re.sub(r"\\[a-zA-Z]+", lambda m: m.group(0)[1:], t)  # \Phi -> Phi
        t = re.sub(r"[^a-z0-9]+", "-", t.encode("ascii", "ignore").decode().lower()).strip("-")
        out = ""
        for w in t.split("-"):
            if len(out) + len(w) + 1 > 56:
                break
            out = f"{out}-{w}" if out else w
        base, n = out, 2
        while out in taken:
            out = f"{base}-{n}"
            n += 1
        return out

The sources
-----------

### Unpacking an e-print

An e-print is a PDF, a gzipped tar archive or a single gzipped file
([downloading](40-arxiv.md) explains why). A PDF gives no sources. A single
file is named after the paper, with `.tex` if it looks like TeX. The files
of a tar archive are put under `source/`, in the folders they had.

An archive from elsewhere is untrusted (section 15 of the specification).
Only regular files are extracted: links and devices are skipped and noted.
A path containing `..` is refused, and a leading `/` is dropped; a path
that differs only in case from one already extracted is skipped too, since
the archive may be kept on a file system that does not distinguish them.

An archive may also be made to expand to an excessive size, a few
kilobytes of gzip giving gigabytes of zeros, or to hold a very large
number of tiny files. The decompressed data are therefore read only up to
a limit, `MAX_UNPACKED` (1 GiB, far more than any paper needs), and the
tar archive may have at most `MAX_MEMBERS` members (10000) whose sizes
add up to at most the same limit; the sizes are those the headers
declare, which also bounds sparse files, whose data expand when
extracted. An archive over either limit is refused as a whole, before
anything is written. The tar archive is opened as uncompressed (`r:`),
so that a compressed archive inside the gzip, which `tarfile` would
otherwise decompress without limit, is kept as a single file.

    # in arXiv: unpacking an e-print:
    MAX_UNPACKED = 1 << 30      # bytes, after decompression
    MAX_MEMBERS = 10000         # members of a tar archive


    def unpack(src, dest, base_id):
        """Unpack an arXiv e-print into DEST; return (kind, [(logical, path)], notes)."""
        data = src.read_bytes()
        notes, files = [], []
        if data[:4] == b"%PDF":
            return "pdf", [], notes
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as g:
            raw = g.read(MAX_UNPACKED + 1)
        if len(raw) > MAX_UNPACKED:
            sys.exit(f"{src}: expands to more than {MAX_UNPACKED >> 20} MiB; refused (section 15)")
        try:
            tf = tarfile.open(fileobj=io.BytesIO(raw), mode="r:")
            members = []
            for m in tf:
                members.append(m)
                if len(members) > MAX_MEMBERS:
                    sys.exit(f"{src}: more than {MAX_MEMBERS} files; refused (section 15)")
        except tarfile.TarError:
            name = base_id.replace("/", "-") + (".tex" if b"\\documentclass" in raw or b"\\begin" in raw else "")
            p = dest / name
            p.write_bytes(raw)
            return "single", [(f"source/{name}", p)], notes
        if sum(m.size for m in members if m.isfile()) > MAX_UNPACKED:
            sys.exit(f"{src}: its files add up to more than {MAX_UNPACKED >> 20} MiB; refused (section 15)")
        seen = set()
        for m in members:
            if m.isdir():
                continue
            logical = safe_logical(m.name)
            if not m.isfile():
                notes.append(f"skipped {'link' if m.issym() or m.islnk() else 'special file'} {m.name}")
                continue
            if logical is None:
                notes.append(f"skipped unsafe path {m.name}")
                continue
            if logical.lower() in seen:
                notes.append(f"skipped {m.name}: differs only in case from another file")
                continue
            seen.add(logical.lower())
            p = dest / "f" / logical
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(tf.extractfile(m).read())
            files.append((f"source/{logical}", p))
        return "tar", files, notes

A logical path is made of the components of the name other than empty
ones and `.`, with backslashes taken as separators; a name that could leave
the folder, or is empty, has none.

    # in arXiv: safe logical paths:
    def safe_logical(name):
        parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
        if not parts or ".." in parts:
            return None
        return "/".join(parts)

### The main TeX file

`object.json` names the main source. arXiv works it out when it compiles a
paper, but does not say which it is, so we guess as arXiv does: a TeX file
(or a file without extension, as old submissions have) with a
`\documentclass` or `\documentstyle` that is not commented out. Among
several, files nearer the top are preferred, then those that contain
`\begin{document}` (a file that has the class but not the document is
usually an included one or a leftover), then the first in alphabetical
order.

    # in arXiv: finding the main TeX file:
    def main_tex(files):
        """The logical path of the main TeX file."""
        cands = []
        for logical, p in files:
            if logical.lower().endswith((".tex", ".ltx")) or "." not in logical.rsplit("/", 1)[-1]:
                head = p.read_bytes()
                if re.search(rb"^[^%\n]*\\documentclass", head, re.M) or re.search(rb"^[^%\n]*\\documentstyle", head, re.M):
                    cands.append((logical.count("/"), not re.search(rb"\\begin\s*\{document\}", head), logical))
        return sorted(cands)[0][2] if cands else None

### TeXmacs sources found elsewhere

Some papers were written with TeXmacs. arXiv does not accept TeXmacs
files, so their authors submitted either the PDF alone or the LaTeX that
TeXmacs exports. When the TeXmacs originals are found elsewhere, in the
authors' own files, they can be given to the import with `--texmacs`, a
JSON file mapping an arXiv version (`2303.18112v2`) to a description: `tm`,
the TeXmacs file; `bib`, its bibliography database, if any; `name`, the
name to give the file in the archive; `mode`, `alongside` when arXiv has
the LaTeX export; `texmacsVersion`; and notes, `adjusted` (how the file
was adjusted to match the submission) and `bibNote`, which go into the
report and the deposit message.

A TeXmacs file names its bibliography database in its `bibliography` tag,
not necessarily by the name the database has on disk; the database is
deposited under the name the document uses, so that the sources typeset as
they are.

    # in arXiv: the files of a TeXmacs source:
    def texmacs_files(spec, dest, folder="source"):
        """[(logical, path)] for a TeXmacs source (spec from texmacs-sources.json):
        the .tm under its own name, and its .bib under the name the document
        refers to."""
        tm = Path(spec["tm"])
        files = [(f"{folder}/{spec.get('name', tm.name)}", tm)]
        if spec.get("bib"):
            text = tm.read_text(encoding="latin-1")
            m = re.search(r"<\\?bibliography\*?\|bib\|[^|]*\|([^|>]+)", text)
            name = m.group(1) if m else Path(spec["bib"]).stem
            if not name.endswith(".bib"):
                name += ".bib"
            files.append((f"{folder}/{name}", Path(spec["bib"])))
        return files

The TeXmacs version, for the `toolchain` of `object.json` (appendix B), is
the one given, or else the one the file records in its first line,
`<TeXmacs|2.1.4>`.

    # in arXiv: the TeXmacs version of a source:
    def tm_version(spec):
        if spec.get("texmacsVersion"):
            return spec["texmacsVersion"]
        m = re.match(r"<TeXmacs\|([^>]+)>", Path(spec["tm"]).read_text(encoding="latin-1"))
        return m.group(1) if m else "unknown"

### Digests

The files received from arXiv are recorded with their SHA-512 (the
digest of OCFL, required by section 9) and their MD5 (the digest services
such as Zenodo report).

    # in arXiv: digests of the received files:
    def sha(path, algo):
        return P.digest(path, algo)

Importing a paper
-----------------

`import_paper` imports the versions of one paper. It finds the object,
then goes through arXiv's versions in order, and for each one gathers the
files, writes `datacite.json` and `object.json`, and adds the object
version. What it did is appended to a report, one entry per version, and
summarised in one printed line per paper.

    # in arXiv: importing a paper:
    def import_paper(folder, taken, report, dry, texmacs=None, licences=None, existing=None, only=None, ids=None):
        """Import the arXiv versions of a paper; with EXISTING (an object id), only
        the versions not yet in that object are added, as new object versions."""
        texmacs = texmacs or {}
        licences = licences or {}
        rec = record(folder)
        aid = rec["id"]
        <<arXiv: the object of the paper, new or existing>>
        # the record gives only the current licence; each version's own licence
        # comes from its abstract page (version-licences.json, written by osheaf arxiv fetch)
        info = {"arxiv": aid, "id": obj_id, "versions": [], "license": rights_of(rec["license"])["rights"]}
        first_date = rec["versions"][0]["date"][:10]
        <<arXiv: the last document version deposited>>
        for n, v in enumerate(rec["versions"], 1):
            <<arXiv: skip a version, or note its licence>>
            <<arXiv: the sources of a version>>
            <<arXiv: the main source and its format>>
            <<arXiv: the content and the files received>>
            <<arXiv: the relations of a version>>
            <<arXiv: the title and abstract of a version>>
            <<arXiv: the datacite.json of a version>>
            <<arXiv: the object.json of a version>>
            <<arXiv: commit an imported version>>
            shutil.rmtree(tmp, ignore_errors=True)
        report.append(info)
        kinds = ",".join(x.get("kind", "?") for x in info["versions"])
        print(f"{aid:>18}  {obj_id}  [{kinds}]", flush=True)

### The object

A paper already archived (`existing`) continues its object, skipping the
arXiv versions it holds. A new paper needs an identifier from the
depositor, not already taken; `taken` collects the identifiers of the
archive and of the papers imported in the same run.

    # in arXiv: the object of the paper, new or existing:
    if existing:
        obj_id, present = existing, archived_versions(existing)
    else:
        if aid not in (ids or {}):
            sys.exit(f"{aid}: no identifier in identifiers.json (proposal: \"{aid}\": \"{slug(rec['title'], taken)}\");"
                     " identifiers are chosen by the depositor (section 6.3)")
        obj_id, present = ids[aid], set()
        if obj_id in taken:
            sys.exit(f"{aid}: identifier {obj_id} is taken")
        taken.add(obj_id)

Document versions are numbered in the order in which they are deposited.
For a new object they start at 1; for an existing one, after the highest
document version it has, which may come from versions deposited by hand
between arXiv's.

    # in arXiv: the last document version deposited:
    # document versions are consecutive in the order of deposit; they need not
    # match arXiv's numbers (missing arXiv versions, versions deposited by hand)
    docn = 0
    if existing:
        d = P.OCFL / existing
        dinv = P.load_inventory(d)
        docn = max(P.doc_version_of(d, dinv, v) for v in dinv["versions"])

### Each version

A version is skipped when it is already in the object or not among those
asked for with `--versions`. Its licence must be known: the import stops
otherwise, rather than record a wrong one. A version whose PDF could not be
downloaded (arXiv removed it, or the download failed) is reported, and
takes no document version number.

    # in arXiv: skip a version, or note its licence:
    vid = v["v"]
    pdf = folder / f"{vid}.pdf"
    srcs = sorted(folder.glob(f"{vid}-source.*"))
    if f"{aid}{vid}" in present or (only and vid not in only):
        continue
    vinfo = {"v": vid, "date": v["date"][:10]}
    if f"{aid}{vid}" not in licences:
        sys.exit(f"{aid}{vid}: licence of this version unknown (run osheaf arxiv fetch)")
    rights = rights_of(licences[f"{aid}{vid}"]["licence"])
    vinfo["licence"] = rights["rightsUri"]
    info["versions"].append(vinfo)
    if not pdf.exists():
        vinfo["error"] = "not available from arXiv"
        continue
    docn += 1

The sources are unpacked into a temporary folder. A version without an
e-print is taken to be one whose source arXiv withholds. A TeXmacs original
found elsewhere either takes the place of the missing sources, when arXiv
has only a PDF, or, in mode `alongside`, joins arXiv's LaTeX export: the
export stays in `source/`, as arXiv has it, and the original goes into
`texmacs/`. Given a TeXmacs original for a version whose LaTeX sources
arXiv has, without `alongside`, the import stops: one of the two would be
lost.

    # in arXiv: the sources of a version:
    tmp = Path(tempfile.mkdtemp())
    if srcs:
        kind, files, notes = unpack(srcs[0], tmp, aid)
    else:
        kind, files, notes = "pdf", [], ["source withheld on arXiv"]
    tm_spec = texmacs.get(f"{aid}{vid}")
    alongside = False
    if tm_spec:
        notes = notes + [x for x in (tm_spec.get("adjusted"), tm_spec.get("bibNote")) if x]
        if kind == "pdf":
            kind, files = "texmacs", texmacs_files(tm_spec, tmp)
        elif tm_spec.get("mode") == "alongside":
            # arXiv has the LaTeX export: keep it in source/, the TeXmacs
            # original goes to texmacs/ and becomes the main source
            alongside = True
            latex_files = files
            tm_files = texmacs_files(tm_spec, tmp, "texmacs")
            files = latex_files + tm_files
        else:
            sys.exit(f"{aid}{vid}: a TeXmacs source is given but arXiv has a {kind} source")

The main source and its media type follow from the kind of source. With
TeXmacs alongside, the TeXmacs file is the main source, and the main file
of the LaTeX export is noted in the report, and used below for the macros.
When no main TeX file is found, the first file stands in for it, and the
report says so.

    # in arXiv: the main source and its format:
    vinfo.update(kind=kind, files=len(files), notes=notes)
    main = main_tex(files) if kind == "tar" else (files[0][0] if files else None)
    if alongside:
        vinfo["latexMain"] = main_tex(latex_files) if kind == "tar" else latex_files[0][0]
        main, fmt = tm_files[0][0], "application/x-texmacs"
    elif kind == "texmacs":
        fmt = "application/x-texmacs"
    elif kind == "pdf":
        main, fmt = None, None
    else:
        fmt = "application/x-tex"
        if main is None:
            vinfo["notes"].append("no main TeX file found")
            main = files[0][0]
    vinfo["main"] = main

The content of the version is its sources and arXiv's PDF as `paper.pdf`.
The files received are the PDF and the e-print as downloaded, before
unpacking. `formats`, in `datacite.json`, lists the media types of the
renditions and the sources.

    # in arXiv: the content and the files received:
    content = {lg: p for lg, p in files}
    content["paper.pdf"] = pdf
    received = [pdf] + srcs
    formats = ["application/pdf"] + {"pdf": [], "texmacs": ["application/x-texmacs", "application/x-bibtex"]
                                     if len(files) > 1 else ["application/x-texmacs"]}.get(kind, ["application/x-tex"])
    if alongside:
        formats += ["application/x-texmacs"] + (["application/x-bibtex"] if len(tm_files) > 1 else [])

The relations say that the version is identical to arXiv's and a version of
the paper's arXiv DOI. If the authors gave the DOI of the published
article, each version is a preprint of it (`IsPreprintOf`), except the last,
when its comments say it is the published version: then it is identical to
the article. The comments are those of this version, from its abstract
page.

    # in arXiv: the relations of a version:
    related = [{"relatedIdentifier": f"arXiv:{aid}{vid}", "relatedIdentifierType": "arXiv",
                "relationType": "IsIdenticalTo"},
               {"relatedIdentifier": f"10.48550/arXiv.{aid}", "relatedIdentifierType": "DOI",
                "relationType": "IsVersionOf"}]
    comments = licences[f"{aid}{vid}"].get("comments")
    if rec["doi"]:
        # the last arXiv version may be the published version itself
        published = (n == len(rec["versions"]) and comments
                     and re.search(r"published version", comments, re.I))
        for doi in rec["doi"].split():
            related.append({"relatedIdentifier": doi, "relatedIdentifierType": "DOI",
                            "relationType": "IsIdenticalTo" if published else "IsPreprintOf"})

The title and the abstract are converted as the previous chapter explains,
with the macros of the preamble of this version's LaTeX main file, if it
has one. The macros that remain unknown go into the report.

    # in arXiv: the title and abstract of a version:
    # titles and abstracts: plain text with mathematics in $...$; the
    # authors' macros are replaced from the preamble of this version's source
    tex_main = main if fmt == "application/x-tex" else vinfo.get("latexMain")
    macros = {}
    if tex_main:
        macros = preamble_macros(dict(files)[tex_main].read_text(encoding="latin-1"))
    title, abstract = clean_text(rec["title"], macros), clean_text(rec["abstract"], macros)
    left = unknown_macros(abstract)
    if left:
        vinfo["notes"].append("macros in the abstract not defined in the source: " + ", ".join(left))

`datacite.json` follows section 8. The resource type is `Preprint`: an
author's version of a work, wherever it was published. The dates are those
of arXiv: `Issued`, the first public appearance of the paper, is the date
of its first arXiv version, and `Available`, when this version became
public, is the date of this arXiv version. The subjects are arXiv's
categories, under the scheme `arXiv`; the journal reference, a free text,
becomes a description of type `SeriesInformation`. The `url` is arXiv's
page of the version; the archive has no DOI for it yet (the chapter on
Zenodo gives it one).

    # in arXiv: the datacite.json of a version:
    datacite = {
        "titles": [{"title": title}],
        "creators": [creator(a) for a in rec["authors"]],
        "publisher": {"name": P.ARCHIVE["name"]},
        "publicationYear": int(first_date[:4]),
        "types": {"resourceTypeGeneral": "Preprint"},
        "version": str(docn),
        "url": f"https://arxiv.org/abs/{aid}{vid}",
        "dates": [{"date": first_date, "dateType": "Issued"},
                  {"date": v["date"][:10], "dateType": "Available"}],
        "language": "en",
        "formats": formats,
        "subjects": [{"subject": c, "subjectScheme": "arXiv"} for c in rec["categories"]],
        "rightsList": [rights],
        "descriptions": [{"description": abstract, "descriptionType": "Abstract"}],
        "relatedIdentifiers": related,
    }
    if rec["journal"]:
        datacite["descriptions"].append({"description": f"Journal reference: {rec['journal']}",
                                         "descriptionType": "SeriesInformation"})

`object.json` names the main source, or explains why there is none: arXiv
either served a PDF as the e-print, or served no e-print at all. arXiv's
comments on the version become its change note (section 9 compares the two
explicitly). The `external` entry records where the version comes from,
with arXiv's label and the files received.

    # in arXiv: the object.json of a version:
    obj = {
        "format": P.OBJ_FORMAT, "specification": P.SPEC, "kind": "document",
        "archiveId": P.ARCHIVE["archiveId"], "objectId": obj_id, "documentVersion": docn,
    }
    if main:
        obj.update(mainSource=main, sourceFormat=fmt)
    else:
        obj["sourcesMissing"] = {"text": "arXiv keeps only the PDF of this version"
                                 if srcs else "the source of this version is withheld on arXiv"}
    obj["renditions"] = [{"path": "paper.pdf", "mediaType": "application/pdf"}]
    if tm_spec:
        obj["toolchain"] = [{"name": "TeXmacs", "version": tm_version(tm_spec)}]
    if comments:
        obj["changes"] = {"text": clean_text(comments)}
    obj["external"] = [{"role": "source", "service": "arXiv", "record": f"https://arxiv.org/abs/{aid}{vid}",
                        "doi": f"10.48550/arXiv.{aid}", "label": vid,
                        "files": [{"name": f.name, "sha512": sha(f, "sha512"), "md5": sha(f, "md5"),
                                   "bytes": f.stat().st_size} for f in received]}]
    obj["status"] = "active"

Unless the run is a dry run, the version is committed. The new
`object.json` first carries forward what later object versions must keep
(the history and the notices, as the chapter on deposits explains),
together with their files. The deposit message says where the version comes
from, and how a TeXmacs original was used. After the last version, the
website gets the HTML version of the document if its head has a TeXmacs
source, as for the archive's own TeXmacs deposits, and loses any HTML
version left from before otherwise: an HTML version is made only from a
TeXmacs source.

    # in arXiv: commit an imported version:
    if not dry:
        d = P.OCFL / obj_id
        inv0 = P.load_inventory(d)
        P.carry_forward(P.read_json(d, inv0, P.OBJ) if inv0 else None, obj, inv0, P.next_object_version(inv0))
        for lp, f in P.carried_files(obj_id, inv0).items():
            content.setdefault(lp, f)
        P.write_json(tmp / "datacite.json", datacite)
        P.write_json(tmp / P.OBJ, obj)
        content["datacite.json"] = tmp / "datacite.json"
        content[P.OBJ] = tmp / P.OBJ
        msg = f"Imported from arXiv: {aid}{vid} of {v['date'][:10]}"
        if tm_spec and alongside:
            msg += ("; with the TeXmacs original, from the authors' files, in texmacs/ (arXiv's"
                    " source in source/ is its LaTeX export)")
        elif tm_spec:
            msg += ("; the TeXmacs source, from the authors' files, replaces the PDF that arXiv"
                    " has as source (the PDF is arXiv's)")
        if tm_spec and tm_spec.get("adjusted"):
            msg += "; the TeXmacs file was adjusted to match the submission: " + tm_spec["adjusted"]
        inv = P.add_version(obj_id, content, msg)
        vinfo["object_version"] = inv["head"]
        if tm_spec and n == len(rec["versions"]):
            # the HTML version of the head, as for the archive's TeXmacs deposits
            P.typeset(Path(tm_spec["tm"]), obj_id, tmp / "check.pdf", P.SITE / obj_id)
            vinfo["html"] = True
        elif n == len(rec["versions"]) and (P.SITE / obj_id).exists():
            # the head has no TeXmacs source: no HTML version of it
            shutil.rmtree(P.SITE / obj_id)

The command
-----------

`osheaf arxiv import DOWNLOADS [ARXIV-ID ...]` imports the papers of the
downloads folder, or only those named. The papers already in the archive
are skipped, or, with `--update`, get their new versions. Papers are
imported in the order of their first submission to arXiv, so that the
deposits of the archive follow the history of the papers.

`--rebuild` first deletes the objects of the named papers, and their HTML:
useful while trying out an import, and only then. Once an archive is
published, its objects are permanent, and a correction is a new version.

The report, `import-report.json` (with `-dry` and `-partial` in its name
for dry runs and runs on some papers), is written into the downloads
folder: for each version, its kind of source, number of files, main
source, notes and object version.

    # in arXiv: the import command:
    def main(argv=None):
        ap = argparse.ArgumentParser(prog="osheaf import-arxiv", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
        ap.add_argument("downloads")
        ap.add_argument("ids", nargs="*")
        ap.add_argument("--dry-run", action="store_true")
        ap.add_argument("--texmacs", action="append", help="JSON: arXiv id+version -> {tm, bib, ...}, TeXmacs sources of"
                        " versions for which arXiv has only a PDF")
        ap.add_argument("--versions", help="only these arXiv versions, e.g. v1,v3 (versions are"
                        " always appended in arXiv's order; deposit other versions in between by hand)")
        ap.add_argument("--update", action="store_true",
                        help="for papers already archived, add their new arXiv versions")
        ap.add_argument("--identifiers", help="JSON: arXiv id -> object identifier, chosen by the depositor"
                        " (default: DOWNLOADS/identifiers.json)")
        ap.add_argument("--rebuild", action="store_true",
                        help="delete the objects of the given papers first (only before publication)")
        a = ap.parse_args(argv)
        dl = Path(a.downloads)
        P.init_storage_root()
        licences = json.loads((dl / "version-licences.json").read_text())
        ids = json.loads(Path(a.identifiers or dl / "identifiers.json").read_text())
        texmacs = {}
        for f in a.texmacs or []:
            texmacs.update(json.loads(Path(f).read_text()))
        done = already_archived()
        if a.rebuild:
            if not a.ids:
                sys.exit("--rebuild needs the arXiv identifiers")
            for i in a.ids:
                obj = done.pop(i, None)
                if obj:
                    shutil.rmtree(P.OCFL / obj)
                    shutil.rmtree(P.SITE / obj, ignore_errors=True)
                    print(f"{i:>18}  removed {obj}")
        taken = {o[0] for o in P.objects()}
        folders = sorted((dl / "papers").iterdir()) if not a.ids else [dl / "papers" / i.replace("/", "_") for i in a.ids]
        recs = []
        for f in folders:
            if (f / "record.xml").exists():
                r = record(f)
                if r["id"] in done:
                    if a.update:
                        recs.append((r["versions"][0]["date"], f, done[r["id"]]))
                    else:
                        print(f"{r['id']:>18}  skipped: already archived as {done[r['id']]} (--update adds new versions)")
                    continue
                recs.append((r["versions"][0]["date"], f, None))
        report = []
        # deposit in chronological order of first submission, so that the deposit
        # history follows the papers' history
        for _, f, existing in sorted(recs, key=lambda x: (x[0], str(x[1]))):
            import_paper(f, taken, report, a.dry_run, texmacs, licences, existing,
                         set(a.versions.split(",")) if a.versions else None, ids)
        name = "import-report" + ("-dry" if a.dry_run else "") + ("-partial" if a.ids else "") + ".json"
        P.write_json(dl / name, report)
