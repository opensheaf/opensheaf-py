Importing from arXiv: the metadata
==================================

The description of an OpenSheaf document version is a `datacite.json`
(section 4.4 of the specification). For a paper imported from arXiv it is
made from arXiv's OAI record and from the abstract page of each version,
both downloaded as described in [the previous chapter](40-arxiv.md). This
chapter reads the record and converts its fields: the names of the authors,
the title and the abstract, written by the authors in TeX, and the
licences. [The next chapter](42-arxiv-import.md) puts the pieces together
into the files of each version.

Reading the record
------------------

The record is XML in two namespaces: that of OAI-PMH, for the envelope, and
that of the `arXivRaw` format, for the metadata.

    # in arXiv: the namespaces of the OAI record:
    NS = {"o": "http://www.openarchives.org/OAI/2.0/", "r": "http://arxiv.org/OAI/arXivRaw/"}

`record` returns the fields we use as a dictionary. Text fields are
returned with their white space normalised, since arXiv folds long lines.
The abstract is the exception: it keeps its line breaks, which separate
paragraphs, but loses the spaces around them. The dates of the versions are
written as in e-mail (`Mon, 3 Apr 2023 17:59:58 GMT`) and become ISO 8601
in UTC. The authors are one string, `A. Author, B. Author and C. Author`,
split by `author_names` (below). The field `doi` holds the DOIs
of the published article, if the authors gave any, separated by spaces;
`journal-ref` is the reference of that article as text.

    # in arXiv: reading the arXivRaw record:
    def record(folder):
        root = ET.parse(folder / "record.xml").getroot()
        r = root.find(".//r:arXivRaw", NS)
        if r is None:
            sys.exit(f"{folder}: no arXivRaw record")

        def text(tag):
            e = r.find(f"r:{tag}", NS)
            return " ".join(e.text.split()) if e is not None and e.text else None

        versions = []
        for v in r.findall("r:version", NS):
            date = email.utils.parsedate_to_datetime(v.find("r:date", NS).text)
            versions.append({"v": v.get("version"), "date": date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "source_type": (v.findtext("r:source_type", default="", namespaces=NS) or "").strip()})
        authors = author_names(text("authors"))
        abstract = r.find("r:abstract", NS).text.strip()
        return {"id": text("id"), "title": text("title"), "authors": [detex(a) for a in authors if a.strip()],
                "abstract": re.sub(r"[ \t]*\n[ \t]*", "\n", abstract), "license": text("license"),
                "doi": text("doi"), "journal": text("journal-ref"), "categories": (text("categories") or "").split(),
                "comments": text("comments"), "versions": versions}

The list of authors is split at the commas and at the word "and", also
when the two come together, as in `A, B, and C`: the comma alone would
leave a name `and C`, recorded with the given name `and C`. Some authors
add their affiliations in parentheses, `A (Paris), B (INRIA / IECN,
IECL)`, whose commas are not separators; affiliations are removed first,
innermost parentheses first, since arXiv's own field for them is the name
and nothing else is reliable. Both mistakes were in the archive that
first used these tools (`and Tadahiro Oh`, `IECL)`).

    # in arXiv: the names in the list of authors:
    def author_names(s):
        """'A, B (Univ. X, Y), and C' -> ['A', 'B', 'C']."""
        while True:
            t = re.sub(r"\s*\([^()]*\)", "", s)
            if t == s:
                break
            s = t
        return [a for a in re.split(r",\s*(?:and\s+)?|\s+and\s+", s) if a.strip()]

Names
-----

arXiv keeps the names of authors as the authors typed them, often in TeX:
`G\"unter`, `Ga\'{e}tan`, `\v{S}imon`. DataCite wants Unicode. An accent
command becomes the corresponding combining character after the letter,
and Unicode normalisation (NFC) merges the two into one character where one
exists.

    # in arXiv: TeX accents:
    ACCENTS = {"'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303",
               "c": "\u0327", "v": "\u030c", "u": "\u0306", "H": "\u030b", "=": "\u0304"}

The accents written with a symbol (`\'e`, `\"{u}`) may omit the braces;
those written with a letter (`\c{c}`, `\v{s}`) need them, or `\v s` would be
confused with a command. Letters that are commands of their own, such as
`\o`, `\l` or `\ss`, are converted by `tex_text` of the core, which does
the same for titles of documents deposited from TeX. What is left of TeX
grouping disappears, and a tie `~` is a space.

    # in arXiv: plain names from TeX:
    def detex(s):
        """Plain text of a name written with TeX accents (G\\"unter -> Günter)."""
        s = re.sub(r"\\([\'`\"^~=])\s*\{?([A-Za-z])\}?", lambda m: unicodedata.normalize(
            "NFC", m.group(2) + ACCENTS[m.group(1)]), s)
        s = re.sub(r"\\([cvuH])\s*\{([A-Za-z])\}", lambda m: unicodedata.normalize(
            "NFC", m.group(2) + ACCENTS[m.group(1)]), s)
        s = P.tex_text(s)  # letters such as \\l, \\o, {\\ss}
        s = s.replace("{", "").replace("}", "").replace("~", " ")
        return " ".join(s.split())

DataCite wants each creator's family and given names apart. arXiv gives
only the whole name, in the usual order, so we take the last word as the
family name, together with the particles before it (`de`, `van`, `von`,
`di` and so on), and the rest as the given names. `Massimiliano Gubinelli`
and `Johannes van der Waals` come out right; a double family name without
particle, as in `Maria Gómez García`, does not. A wrong split shows only in
how the name is sorted and cited, and can be corrected by a description-
only version.

    # in arXiv: a creator from an author's name:
    def creator(name):
        words = name.split()
        # a family name with a particle (de, van, von, di, ...) keeps it
        i = len(words) - 1
        while i > 0 and words[i - 1].lower() in ("de", "van", "von", "der", "di", "da", "del", "la", "le"):
            i -= 1
        family, given = " ".join(words[i:]), " ".join(words[:i])
        c = {"name": f"{family}, {given}" if given else family, "nameType": "Personal", "familyName": family}
        if given:
            c["givenName"] = given
        return c

Titles and abstracts
--------------------

Titles and abstracts on arXiv are TeX with a lot of freedom: mathematics
between `$...$`, `$$...$$`, `\(...\)` or `\[...\]`; accents and quotes
written in TeX; and, in the mathematics, the authors' own macros, such as
`\R` for the real numbers or `\eps` for epsilon, which arXiv displays
unexpanded. Section 8 of the specification asks for plain text with
mathematics in LaTeX between single dollar signs, using only the standard
commands, so that a renderer such as MathJax displays it without the
document's preamble. It also asks importers to replace the authors' macros
by their definitions when these are known, from the preamble of the
imported sources, and never to invent definitions.

So `clean_text` first brings all mathematics between single dollars, then
treats text and mathematics separately. In the text, accents become
Unicode, TeX quotes become typographic quotes, `\&` becomes `&`, changes of
font become their plain argument (`plain_markup`, below), and braces
around plain words are dropped; then the TeX ways of writing
spaces and dashes become characters (`typographic_text`, below). In the
mathematics, each command that is a
macro of the authors, defined in the preamble and not a standard command,
is replaced by its definition, in braces so that `\R^2` stays
`{\mathbb{R}}^2`. Definitions may use other macros, so the replacement is
repeated, at most four times, which also stops a macro defined in terms of
itself.

    # in arXiv: titles and abstracts as plain text:
    def clean_text(s, macros=None):
        """Plain text with mathematics in $...$ (section 4.4): TeX accents and quotes
        outside mathematics become Unicode; inside mathematics, the authors'
        macros without arguments are replaced by their definitions when known."""
        # mathematics is written between single dollar signs only (section 4.4)
        s = re.sub(r"\$\$(.+?)\$\$", r"$\1$", s, flags=re.S)
        s = re.sub(r"\\\[(.+?)\\\]", lambda m: "$" + m.group(1).strip() + "$", s, flags=re.S)
        s = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1).strip() + "$", s, flags=re.S)
        out = []
        for is_math, part in split_math(s):
            if not is_math:
                part = P.tex_text(part).replace("``", "\u201c").replace("''", "\u201d").replace("\\&", "&")
                part = plain_markup(part)
                part = re.sub(r"(\\[A-Za-z]+\s*)?\{([^{}\\$]*)\}",
                              lambda m: m.group(0) if m.group(1) else m.group(2), part)
                part = typographic_text(part)
            elif macros:
                for _ in range(4):
                    new = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])",
                                 lambda m: ("{" + macros[m.group(1)] + "}") if m.group(1) in macros
                                 and m.group(1) not in STANDARD else m.group(0), part)
                    if new == part:
                        break
                    part = new
            out.append(("$" + part + "$") if is_math else part)
        return "".join(out)

A description is plain text (section 4.4): emphasis and other changes of
font cannot be kept, so they give their argument. Both forms of LaTeX are
recognised, the commands with an argument (`\emph{x}`, `\textit{x}`,
`\textbf{x}`, ..., and those of TeXmacs' LaTeX export, `\tmtextit{x}`,
`\tmem{x}`, ...) and the old declarations inside a group (`{\it x}`,
`{\em x}`, `{\bf x}`). The arguments may contain other groups or
commands, so the replacement is repeated from the innermost outwards
until nothing changes.

Braces right after a command are not removed by the step that drops the
braces around plain words: a command we do not know keeps its argument,
`\url{...}` stays `\url{...}`. Removing the braces alone, as the import
once did, glued the two together: `\emph{distribution}` (arXiv
1810.01700) became `\emphdistribution`.

    # in arXiv: changes of font as plain text:
    FONT_COMMANDS = ("emph|textit|textbf|textsl|textsc|textrm|textsf|texttt|textup|textmd|textnormal|"
                     "tmtextit|tmtextbf|tmtextsl|tmtextsc|tmtextrm|tmtextsf|tmtexttt|tmtextup|tmtextmd|"
                     "tmem|tmstrong|tmname|tmsamp")
    FONT_DECLARATIONS = "it|em|bf|sl|sc|rm|sf|tt|itshape|bfseries|slshape|scshape|upshape|mdseries|normalfont"


    def plain_markup(s):
        """Text with \\emph{x}, \\textbf{x}, \\tmtextit{x}, {\\it x}, ... as its plain text."""
        while True:
            t = re.sub(r"\\(?:" + FONT_COMMANDS + r")\s*\{([^{}]*)\}", r"\1", s)
            t = re.sub(r"\{\\(?:" + FONT_DECLARATIONS + r")(?![A-Za-z])\s*([^{}]*)\}", r"\1", t)
            if t == s:
                return s
            s = t

TeX writes some characters with others: a tie `~` is a space that does not
break (`Korteweg-de~Vries`, arXiv 2505.24270), `--` an en dash
(`Osterwalder--Schrader`, arXiv 1810.01700) and `---` an em dash. In plain
text they become a space and the dashes themselves. The tie becomes an
ordinary space, as in the names of authors: how the text is broken into
lines is up to whoever displays it. A tilde after a slash or a backslash is not a tie but
part of an address (`https://example.org/~user`) or an accent, and is
left alone; accents are converted before, by `tex_text`, anyway.

    # in arXiv: spaces and dashes written the TeX way:
    def typographic_text(s):
        """Ties as spaces, --- and -- as em and en dashes."""
        s = re.sub(r"(?<![/\\])~", " ", s)
        return s.replace("---", "\u2014").replace("--", "\u2013")

Text and mathematics alternate at the dollar signs not preceded by a
backslash: in the list of parts, the odd ones are mathematics.

    # in arXiv: separating text and mathematics:
    def split_math(s):
        """Text and mathematics of a title or abstract: [(is_math, part)]."""
        parts = re.split(r"(?<!\\)\$", s)
        return [(i % 2 == 1, p) for i, p in enumerate(parts)]

The definitions come from the preamble of the main TeX file of the same
arXiv version (the next chapter finds it). We read only definitions
without arguments, the common case in titles and abstracts: those of
`\newcommand` and `\renewcommand`, starred or not, with or without braces
around the name, and those of `\def`. A `\newcommand` with a number of
arguments is skipped; if a name is defined both ways, the `\newcommand`
wins.

    # in arXiv: the authors' macros from the preamble:
    def preamble_macros(tex):
        """Definitions without arguments, \\newcommand{\\R}{\\mathbb{R}} or
        \\def\\R{...}, from the preamble of a LaTeX source."""
        pre = tex.split("\\begin{document}", 1)[0]
        out = {}
        for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z]+)\}?\s*(\[\d\])?\s*\{", pre):
            if m.group(2):
                continue
            body = balanced(pre, m.end() - 1)
            if body is not None:
                out[m.group(1)] = body
        for m in re.finditer(r"\\def\s*\\([A-Za-z]+)\s*\{", pre):
            body = balanced(pre, m.end() - 1)
            if body is not None:
                out.setdefault(m.group(1), body)
        return out

A definition is the text between a brace and the brace that closes it,
counting the braces not escaped by a backslash. A definition longer than
2000 characters is not something to put in an abstract, and we give up.

    # in arXiv: the contents of balanced braces:
    def balanced(s, i):
        """The contents of the braces opening at s[i]."""
        depth = 0
        for j in range(i, min(len(s), i + 2000)):
            if s[j] == "{" and (j == 0 or s[j - 1] != "\\"):
                depth += 1
            elif s[j] == "}" and s[j - 1] != "\\":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j]
        return None

Some authors define macros with the names of standard commands, for
instance `\renewcommand{\phi}{\varphi}`. Expanding those would change what
every reader of the abstract sees; we leave them alone, and keep a list of
the commands that MathJax and KaTeX know anyway. The list is not complete:
it only has to contain the commands that authors are likely to redefine,
and those that should not be reported as unknown.

    # in arXiv: the standard mathematical commands:
    STANDARD = set("""alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi
    pi varpi rho varrho sigma varsigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma
    Upsilon Phi Psi Omega mathbb mathcal mathfrak mathrm mathbf mathit mathsf mathtt operatorname text textrm
    frac dfrac tfrac sqrt sum prod int oint iint lim limsup liminf sup inf max min exp log ln sin cos tan sinh cosh
    partial nabla infty cdot cdots ldots dots times otimes oplus leq geq le ge neq approx sim simeq equiv to mapsto
    in notin subset subseteq supset cup cap setminus emptyset forall exists left right big Big bigg Bigg langle rangle
    lfloor rfloor lceil rceil hat tilde bar vec dot ddot overline underline widehat widetilde quad qquad prime ast
    star circ bullet pm mp div mid parallel perp lesssim gtrsim ll gg ell hbar Re Im wedge vee neg det dim ker deg
    varnothing alpha_ operatorname* boldsymbol displaystyle textstyle mathscr llbracket rrbracket
    rightarrow leftarrow Rightarrow Leftarrow longrightarrow leftrightarrow hookrightarrow uparrow downarrow
    geqslant leqslant bot top vartriangle triangle square diamond angle backslash colon vert Vert lvert rvert
    lVert rVert binom choose mathring check breve acute grave over not neq ne propto cong asymp nearrow searrow""".split())

The commands left in the mathematics that are not standard are macros
whose definition was not found: in a PDF-only version, in a file included
by the main one, or defined with arguments. They are kept, as the
specification asks, and reported, so that the depositor can correct the
abstract by hand if needed.

    # in arXiv: macros left unknown:
    def unknown_macros(s):
        return sorted({m for is_math, part in split_math(s) if is_math
                       for m in re.findall(r"\\([A-Za-z]+)", part) if m not in STANDARD})

Licences
--------

Every arXiv version carries a licence, chosen by the authors when they
submit it, and named by a URI: one of arXiv's own licences or a Creative
Commons licence. Section 4.4 of the specification records a licence with an
SPDX identifier by that identifier, in lower case, and the URL; a licence
without one, such as arXiv's, by its name and the URI arXiv uses for it,
so that all archives record the same licence the same way. The table below
holds the licences arXiv offers today, and the one it assumes for old
submissions; the URIs are written as arXiv writes them, with `http`.

    # in arXiv: licences known by name:
    LICENCES = {
        "http://arxiv.org/licenses/assumed-1991-2003/":
            {"rights": "arXiv.org non-exclusive license to distribute, assumed for submissions of 1991-2003; "
                       "all other rights reserved to the authors"},
        "http://arxiv.org/licenses/nonexclusive-distrib/1.0/":
            {"rights": "arXiv.org perpetual, non-exclusive license to distribute; "
                       "all other rights reserved to the authors"},
        "http://creativecommons.org/licenses/by/4.0/":
            {"rights": "Creative Commons Attribution 4.0 International", "rightsIdentifier": "cc-by-4.0"},
        "http://creativecommons.org/licenses/by-sa/4.0/":
            {"rights": "Creative Commons Attribution Share Alike 4.0 International",
             "rightsIdentifier": "cc-by-sa-4.0"},
        "http://creativecommons.org/licenses/by-nc-sa/4.0/":
            {"rights": "Creative Commons Attribution Non Commercial Share Alike 4.0 International",
             "rightsIdentifier": "cc-by-nc-sa-4.0"},
        "http://creativecommons.org/licenses/by-nc-nd/4.0/":
            {"rights": "Creative Commons Attribution Non Commercial No Derivatives 4.0 International",
             "rightsIdentifier": "cc-by-nc-nd-4.0"},
        "http://creativecommons.org/publicdomain/zero/1.0/":
            {"rights": "Creative Commons Zero v1.0 Universal", "rightsIdentifier": "cc0-1.0"},
    }

A version without a licence gets arXiv's default, the non-exclusive licence
to distribute. A licence not in the table is recorded under its URI, which
then serves as its name too.

    # in arXiv: the rights of a licence:
    def rights_of(uri):
        """The DataCite rights entry of a licence URI."""
        uri = uri or "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"
        r = dict(LICENCES.get(uri, {"rights": uri}), rightsUri=uri)
        if "rightsIdentifier" in r:
            r["rightsIdentifierScheme"] = "SPDX"
        return r
