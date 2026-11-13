Depositing a document
=====================

A deposit adds a document version to the archive: a new document, or a new
version of an existing one. It is the main use of the tools, and the
function that does it, `deposit()`, brings together the previous chapters:
it builds the files of a document version, its two descriptions
(`datacite.json` and `object.json`), and records them as a new object
version of the [storage root](10-archive.md), keeping the
[history and the notices](11-versions.md) of the document. A TeXmacs source
is [typeset](12-texmacs.md) by the archive.

`deposit()` is called by `osheaf deposit`, whose options (see the
[command line](60-command-line.md)) arrive as the attributes of `args`; the
same options may come from a YAML file. The [arXiv import](42-arxiv-import.md)
and the [accepted copies](22-accepted-copies.md) build document versions in
the same way, with the helpers of the previous chapters, but on their own.

From arguments to DataCite
--------------------------

A few helpers turn what a depositor types into DataCite properties.

    # in describe a document from the deposit arguments:
    <<a DataCite creator from a name and an affiliation>>


    <<the name of a creator as readers write it>>


    <<the relations given with a deposit>>


    <<the media types of sources by their extension>>


    <<the licence of a new document version>>


    <<the landing address of a document>>

An author is given as printed in the document, family name first, with an
optional affiliation: `"Noether, Emmy|University of Erlangen"`.
DataCite wants the name as `Family, Given` and the parts separately
(section 8); a name without a comma is kept whole as the family name, which
also covers names that are not split this way.

    # in a DataCite creator from a name and an affiliation:
    # ---------------------------------------------------------------------------
    # Description and deposit

    def creator(spec):
        """'Family, Given|Affiliation' -> DataCite creator."""
        name, _, aff = spec.partition("|")
        family, _, given = name.partition(",")
        family, given = family.strip(), given.strip()
        c = {"name": f"{family}, {given}" if given else family, "nameType": "Personal",
             "familyName": family}
        if given:
            c["givenName"] = given
        if aff.strip():
            c["affiliation"] = [{"name": aff.strip()}]
        return c

Readers see names in the usual order, given name first. This is used by
every presentation and by the cached citations of collections.

    # in the name of a creator as readers write it:
    def display_name(c):
        return (f"{c.get('givenName', '')} {c['familyName']}".strip()
                if "familyName" in c else c["name"])

Relations (section 8.1) link the document to the same work elsewhere. The
common case, a paper also on arXiv, is written `arxiv=ID` and gives
`IsVariantFormOf` (the same work, possibly different in form); any other
relation is written in full, `IsIdenticalTo:doi:10.1234/x`. Relations added
after the deposit, such as the published article, are added by
[a description-only version](14-description.md).

    # in the relations given with a deposit:
    def related_from_args(specs):
        related = []
        for kv in specs or []:
            k, _, v = kv.partition("=")
            if k == "arxiv" and v:
                related.append({"relatedIdentifier": f"arXiv:{v}", "relatedIdentifierType": "arXiv",
                                "relationType": "IsVariantFormOf"})
                continue
            # RELATION:doi:VALUE or RELATION:arxiv:VALUE
            rel, _, rest = kv.partition(":")
            typ, _, val = rest.partition(":")
            if not (rel and typ in ("doi", "arxiv") and val):
                sys.exit(f"--related {kv}: use arxiv=ID or RELATION:doi:DOI or RELATION:arxiv:ID")
            related.append({"relatedIdentifier": f"arXiv:{val}" if typ == "arxiv" else val,
                            "relatedIdentifierType": "arXiv" if typ == "arxiv" else "DOI",
                            "relationType": rel})
        return related

The format of a source that is not TeXmacs is guessed from its extension,
unless given: it is `sourceFormat` in `object.json` and one of the
`formats` in `datacite.json`.

    # in the media types of sources by their extension:
    SOURCE_FORMATS = {".tex": "application/x-tex", ".ltx": "application/x-tex", ".tm": "application/x-texmacs",
                      ".md": "text/markdown", ".txt": "text/plain", ".html": "text/html",
                      ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                      ".odt": "application/vnd.oasis.opendocument.text", ".zip": "application/zip"}

### Licences

Licences with an SPDX identifier are recorded as section 8 asks: the
identifier in lower case, with the URL of the licence. The tools know a few
by name, those an author of scholarly documents is likely to choose; any
other licence is given as a statement, which is recorded as it stands.

    # in the licences known by their SPDX identifiers:
    RIGHTS = {
        "cc-by-4.0": {"rights": "Creative Commons Attribution 4.0 International",
                      "rightsUri": "https://creativecommons.org/licenses/by/4.0/",
                      "rightsIdentifier": "cc-by-4.0", "rightsIdentifierScheme": "SPDX"},
        "cc0-1.0": {"rights": "Creative Commons Zero v1.0 Universal",
                    "rightsUri": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "rightsIdentifier": "cc0-1.0", "rightsIdentifierScheme": "SPDX"},
        "cc-by-sa-4.0": {"rights": "Creative Commons Attribution Share Alike 4.0 International",
                         "rightsUri": "https://creativecommons.org/licenses/by-sa/4.0/",
                         "rightsIdentifier": "cc-by-sa-4.0", "rightsIdentifierScheme": "SPDX"},
        "gpl-3.0-only": {"rights": "GNU General Public License v3.0 only",
                         "rightsUri": "https://www.gnu.org/licenses/gpl-3.0.html",
                         "rightsIdentifier": "gpl-3.0-only", "rightsIdentifierScheme": "SPDX"},
        "gpl-3.0-or-later": {"rights": "GNU General Public License v3.0 or later",
                             "rightsUri": "https://www.gnu.org/licenses/gpl-3.0.html",
                             "rightsIdentifier": "gpl-3.0-or-later", "rightsIdentifierScheme": "SPDX"},
    }

A new version keeps the licence of the previous one unless another is
given: a licence is a decision of the authors, not something to forget at
the next version. A first version without a licence is "All rights
reserved", which the specification allows (section 16): deposit grants
access, not reuse.

    # in the licence of a new document version:
    def rights_list(rights, prev_dc=None):
        """The licence given (an SPDX key of RIGHTS or a statement), or else that
        of the previous version, or else 'All rights reserved'."""
        if rights:
            return [dict(RIGHTS[rights]) if rights in RIGHTS else {"rights": rights}]
        if prev_dc and prev_dc.get("rightsList"):
            return prev_dc["rightsList"]
        return [{"rights": "All rights reserved"}]

### The landing address

The `url` of `datacite.json` is where readers are sent: the landing page,
if the archive has a [website](30-website.md), or else the HTML version of
the TeXmacs document. The [accepted copies](22-accepted-copies.md) use it too.

    # in the landing address of a document:
    def landing_url(obj_id):
        """The address readers are sent to: the landing page of the HTML website,
        or else the HTML version of a TeXmacs document."""
        if INDEX.get("html"):
            return f"{ARCHIVE['baseUrl']}paper/{obj_id}/"
        return f"{ARCHIVE['baseUrl']}site/{obj_id}/{obj_id}.html"

The deposit
-----------

A deposit takes one of three forms: a TeXmacs source, which the archive
typesets; any other source with its PDF (`--pdf`), since the archive
cannot reproduce a LaTeX build faithfully; or a PDF alone, with the reason
why the sources are missing (`--no-source REASON`, section 9), which a
later [completion](14-description.md) may remedy. The function reads as a
sequence of steps.

    # in deposit a document version:
    def deposit(args):
        """Deposit a document, or a new document version of it: a TeXmacs source
        (typeset by the archive), or any source with its PDF (--pdf), or a PDF
        alone (--no-source REASON)."""
        <<check the identifier and the files of a deposit>>
        <<find the earlier versions of a deposited document and the new number>>
        <<the dates of a deposited version>>

        <<collect the files of a deposited version>>
        <<typeset the TeXmacs source of a deposit, or check its PDF>>

        <<the abstract of a deposited version>>
        <<the datacite.json of a deposited version>>
        <<the object.json of a deposited version>>
        <<record the deposited version as a new object version>>

### Checks

The identifier is permanent and appears in every URL of the object; the
specification limits it to 64 characters of a restricted form, and
recommends at most 32 (section 6.3; the warning still cites section 5,
where the rule used to be). All files are checked before anything is
written, so that a mistyped name stops the deposit early.

    # in check the identifier and the files of a deposit:
    obj_id = args.id
    if not ID_RE.match(obj_id) or len(obj_id) > 64:
        sys.exit("ID must match ^[a-z0-9]+(-[a-z0-9]+)*$ and have at most 64 characters")
    if len(obj_id) > 32:
        print(f"warning: {obj_id} is longer than 32 characters (section 5: SHOULD be short)")
    init_storage_root()
    source = Path(args.source) if args.source else None
    for f in [source, args.pdf and Path(args.pdf)] + [Path(x.partition("=")[0]) for x in args.extra_source or []]:
        if f and not f.is_file():
            sys.exit(f"no file {f}")

### The number of the new version

A new document gets document version 1. An existing object must be a
document, and not withdrawn (section 11.1: a withdrawal is final; a
retracted paper is not corrected by a new version). The new number is one
more than the highest so far, whatever the order of the history. A deposit
always gets a new number: it is meant for files not deposited before, which
is when section 7.3 assigns one; changing only the description of an
existing version is the work of the
[description-only versions](14-description.md).

    # in find the earlier versions of a deposited document and the new number:
    obj_dir = OCFL / obj_id
    inv = load_inventory(obj_dir)
    prev_obj = prev_dc = None
    doc_version = 1
    if inv:
        prev_obj, prev_dc = read_json(obj_dir, inv, OBJ), read_json(obj_dir, inv, "datacite.json")
        if prev_obj["kind"] != "document":
            sys.exit(f"{obj_id} is not a document")
        if prev_obj.get("status") == "withdrawn":
            sys.exit(f"{obj_id} is withdrawn (section 11.1): a withdrawn document gets no new versions")
        doc_version = max(doc_version_of(obj_dir, inv, v) for v in inv["versions"]) + 1

### Dates

A version is either public (`Available`, by default the day of the
deposit, which is what section 8 asks for a version first made public by
the archive) or was not public at the time (`Created`: a manuscript
deposited years later); never both. The `Issued` date, the first public
appearance of the work, is the same in every version: given, or kept from
the previous version, or else the date of this one.

    # in the dates of a deposited version:
    if args.created and args.available:
        sys.exit("give --created (a version not public at the time) or --available, not both")
    available = None if args.created else (args.available or TODAY)
    issued = args.issued or (date_of(prev_dc, "Issued") if prev_dc else None) or available

### The files

The files of the version are collected as a map from logical paths to
files on disk, as `add_version()` wants them. A TeXmacs source is stored as
`<id>.tm`, whatever its name on disk, so that its HTML version and its
links have predictable names; other sources keep their names, since other
files may refer to them. Further sources (images, a bibliography, a style
file) are stored at the path the main source uses for them, which is
checked against the rules of section 7.1 (no absolute paths, no `.` or `..`).
The scratch folder made first will hold the generated files: the PDF of a
TeXmacs source and the two descriptions.

    # in collect the files of a deposited version:
    tmp = Path(tempfile.mkdtemp())
    texmacs = source is not None and source.suffix == ".tm" and not args.pdf
    if not texmacs and not args.pdf:
        sys.exit("give the PDF of this version with --pdf (only TeXmacs sources are typeset by the archive)")
    if source is None and not args.no_source:
        sys.exit("a deposit without sources needs --no-source REASON (section 9: sourcesMissing)")
    files, formats = {}, []
    if texmacs:
        main = f"{obj_id}.tm"
        fmt = "application/x-texmacs"
    elif source is not None:
        main = source.name
        fmt = args.source_format or SOURCE_FORMATS.get(source.suffix.lower(), "application/octet-stream")
    if source is not None:
        files[main] = source
        formats.append(fmt)
    formats.append("application/pdf")
    for spec in args.extra_source or []:
        # FILE or FILE=LOGICAL/PATH (the path the main source refers to)
        src, _, logical = spec.partition("=")
        logical = logical or Path(src).name
        parts = logical.split("/")
        if logical.startswith("/") or ".." in parts or "." in parts:
            sys.exit(f"bad logical path {logical}")
        files[logical] = Path(src)
        if logical.endswith(".bib") and "application/x-bibtex" not in formats:
            formats.append("application/x-bibtex")

The rendition is always `paper.pdf`. A TeXmacs source is typeset now: the
PDF into the scratch folder, the HTML version (if the archive makes one)
into `site/`. A PDF given by the depositor is checked to be one.

    # in typeset the TeXmacs source of a deposit, or check its PDF:
    if texmacs:
        pdf = tmp / "paper.pdf"
        typeset(source, obj_id, pdf, SITE / obj_id if TEXMACS.get("htmlPackage") or not INDEX.get("html") else None)
    else:
        pdf = Path(args.pdf)
        if pdf.read_bytes()[:4] != b"%PDF":
            sys.exit(f"{pdf} is not a PDF")
    files["paper.pdf"] = pdf

### The description

The abstract comes from the depositor, or from the TeXmacs source, or else
from the previous version: a correction rarely changes the abstract, and
forgetting it would empty the description. Keywords are kept the same way.

    # in the abstract of a deposited version:
    if args.abstract_file:
        abstract_text = Path(args.abstract_file).read_text(encoding="utf-8").strip()
    elif args.abstract:
        abstract_text = args.abstract.strip()
    elif texmacs:
        paras = tm_abstract(source)
        abstract_text = "\n\n".join(tm_to_text(p) for p in paras) if paras else None
    else:
        abstract_text = None
    if abstract_text is None and prev_dc:
        # a new version keeps the abstract and keywords unless they are given
        abstract_text = next((x["description"] for x in prev_dc.get("descriptions", [])
                              if x["descriptionType"] == "Abstract"), None)

`datacite.json` holds the properties section 8 requires, and those it
recommends that the tools know. The publisher is the archive (until a DOI
service registers the version, [appendix A](50-zenodo.md)); the version is
the document version, as a string; the publication year is that of the
`Issued` date. Keywords become `subjects`, without a `subjectScheme`
(section 8 recommends one; the tools do not ask for it yet).

    # in the datacite.json of a deposited version:
    datacite = {
        "titles": [{"title": args.title}],
        "creators": [creator(a) for a in args.author],
        "publisher": {"name": ARCHIVE["name"]},
        "publicationYear": int((issued or args.created)[:4]),
        "types": {"resourceTypeGeneral": args.type},
        "version": str(doc_version),
        "url": landing_url(obj_id),
        "dates": [],
        "language": args.language or "en",
        "formats": formats,
        "rightsList": rights_list(args.rights, prev_dc),
    }
    if args.keyword:
        datacite["subjects"] = [{"subject": k} for k in args.keyword]
    elif prev_dc and prev_dc.get("subjects"):
        datacite["subjects"] = prev_dc["subjects"]
    if issued:
        set_date(datacite, "Issued", issued)
    if available:
        set_date(datacite, "Available", available, args.date_info)
    else:
        set_date(datacite, "Created", args.created, args.date_info)
    if abstract_text:
        datacite["descriptions"] = [{"description": abstract_text, "descriptionType": "Abstract"}]
    related = related_from_args(args.related)
    if related:
        datacite["relatedIdentifiers"] = related

`object.json` (section 9) names the main source and its format, or says
why there is none; lists the rendition; records the toolchain (for TeXmacs,
the version that typesets it; for other sources, what the depositor
declares); and the state, `active`. The optional parts follow the
options: the change note, the stage of the version in the NISO scheme
(an author's original, an accepted manuscript, ...), and the record of the
authors' agreement, which a journal accepting a paper needs (section 9:
names, a date and how, no personal data).

    # in the object.json of a deposited version:
    obj = {
        "format": OBJ_FORMAT,
        "specification": SPEC,
        "kind": "document",
        "archiveId": ARCHIVE["archiveId"],
        "objectId": obj_id,
        "documentVersion": doc_version,
    }
    if source is not None:
        obj.update(mainSource=main, sourceFormat=fmt)
    else:
        obj["sourcesMissing"] = {"text": args.no_source}
    obj["renditions"] = [{"path": "paper.pdf", "mediaType": "application/pdf"}]
    if texmacs:
        obj["toolchain"] = [{"name": "TeXmacs", "version": TEXMACS_VERSION}]
    elif args.toolchain:
        obj["toolchain"] = [{"name": n, "version": v} for n, _, v in (t.partition("=") for t in args.toolchain)]
    obj["status"] = "active"
    if args.changes:
        obj["changes"] = {"text": args.changes}
    if getattr(args, "agreement", None):
        obj["agreement"] = {"by": [c["name"] for c in datacite["creators"]],
                            "date": available or args.created or TODAY, "method": args.agreement}
    if args.stage:
        obj["stage"] = {"scheme": "NISO-JAV", "value": args.stage}

### Recording the version

Last, the notices and the history of the head are carried forward (placing
the version `--after` another if asked), the notice files are added to the
files, and the two descriptions are written to the scratch folder and added
as files like the others. The object version is then added in one step:
until that moment no object has changed, so an error
anywhere above leaves the archive as it was (only `site/` may have a new
HTML version).

    # in record the deposited version as a new object version:
    carry_forward(prev_obj, obj, inv, next_object_version(inv), args.after)
    for lp, f in carried_files(obj_id, inv).items():
        files.setdefault(lp, f)
    write_json(tmp / "datacite.json", datacite)
    write_json(tmp / OBJ, obj)
    files["datacite.json"] = tmp / "datacite.json"
    files[OBJ] = tmp / OBJ
    inv = add_version(obj_id, files, args.message or f"Deposit: document version {doc_version}")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{obj_id}: {inv['head']} (document version {doc_version})")

The new version is in the storage root, but readers do not see it yet: the
[main collection](15-main-collection.md), the
[discovery document and the index](16-index.md) are updated by their own
commands, `osheaf collect` and `osheaf index`, so that several deposits can
be made before the pages are written again.
