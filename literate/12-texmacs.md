TeXmacs: typesetting and reading markup
=======================================

An archive following the TeXmacs profile (appendix B of the specification)
deposits TeXmacs documents, and typesets them itself: the PDF and the HTML
version of a document are made by the archive's tools from the deposited
source, so that the source reproduces them. This chapter is the part of
`core.py` that drives TeXmacs, and the small reader of TeXmacs markup that
extracts titles and abstracts for `datacite.json`. It is used by the
[deposit](13-deposit.md) of TeXmacs documents and by the
[TeXmacs index](16-index.md).

    # in run TeXmacs and read its markup:
    <<run Scheme code in a headless TeXmacs>>


    <<the Scheme code exporting a TeXmacs document>>


    <<add a style package to a TeXmacs document>>


    <<typeset a TeXmacs source into a PDF and an HTML version>>


    <<find the end of the arguments of a TeXmacs tag>>


    <<the paragraphs of the abstract of a TeXmacs document>>


    <<parse TeXmacs inline markup into a tree>>


    <<the TeXmacs symbols written as characters>>


    <<render parsed TeXmacs markup as text with LaTeX mathematics>>


    <<convert TeXmacs markup to plain text>>

Running TeXmacs
---------------

TeXmacs has no command-line typesetter: it is an editor, which can run
without a window (`-headless`) and execute Scheme code given with `-x`. The
tools build that code and run TeXmacs once per deposit, with every export
of the deposit in one call, since starting TeXmacs takes seconds.

The calls are wrapped so that TeXmacs always quits, also after an error,
and prints a marker that the tools look for: a headless TeXmacs that fails
in Scheme exits normally, and its exit status says nothing. An `init` file
of the configuration is loaded first (it may define the macros of the
archive's documents), and the cache of style environments is cleared,
since it lives in the profile and would keep the result of an earlier
version of a style package. TeXmacs runs in a scratch folder, since its
helpers may leave files in the current folder, which is often the
archive.

    # in run Scheme code in a headless TeXmacs:
    def run_texmacs(calls):
        """Run Scheme CALLS in a headless TeXmacs with the private profile."""
        <<prepare the private TeXmacs profile of the archive>>
        # style-clear-cache: TeXmacs caches style environments in the profile.
        init = f"(load \"{ROOT / TEXMACS['init']}\") " if TEXMACS.get("init") else ""
        cmd = (f"(begin {init}(catch #t (lambda () (style-clear-cache) {calls}) (lambda args"
               f" (display \"SCHEME-ERROR \") (write args) (newline))) (quit-TeXmacs))")
        # in a scratch folder: TeXmacs' helpers (Ghostscript) may leave files in
        # the current folder, which must not end up in the archive
        work = tempfile.mkdtemp(prefix="osheaf-texmacs-")
        try:
            out = subprocess.run([tm, "-headless", "-x", cmd], env=env, capture_output=True,
                                 text=True, errors="replace", timeout=1200, cwd=work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if "SCHEME-ERROR" in out.stdout + out.stderr:
            sys.exit(out.stdout + out.stderr)

The run must not depend on the user's own TeXmacs: the archive's documents
would otherwise come out differently on another machine, or after a change
of preferences. TeXmacs therefore runs with a private profile,
`texmacs_home/` in the archive folder, whose plugins are those of the user
(linked, since the archive may need plugins such as `max-html`); the
plugins the configuration requires are checked first. The very first start
of a profile creates it and would overwrite the preferences, so it is done
once, alone. The preferences make the HTML export use MathJax, and no
images for formulas. TeXmacs itself is the macOS application, unless
`TEXMACS_BIN` names another binary.

    # in prepare the private TeXmacs profile of the archive:
    tm = os.environ.get("TEXMACS_BIN", "/Applications/TeXmacs.app/Contents/MacOS/TeXmacs")
    TM_HOME.mkdir(exist_ok=True)
    if not (TM_HOME / "plugins").exists():
        (TM_HOME / "plugins").symlink_to(USER_PLUGINS)
    for p in TEXMACS.get("plugins", []):
        if not (TM_HOME / "plugins" / p).exists():
            sys.exit(f"TeXmacs plugin {p} not found in {USER_PLUGINS}")
    env = dict(os.environ, LC_ALL="C.UTF-8", QT_QPA_PLATFORM="offscreen",
               TEXMACS_HOME_PATH=str(TM_HOME))
    if not (TM_HOME / "system" / "settings.scm").exists():
        # the first start sets the profile up and would discard preferences
        subprocess.run([tm, "-headless", "-x", "(quit-TeXmacs)"], env=env,
                       capture_output=True, timeout=600, cwd=tempfile.gettempdir())
    (TM_HOME / "system" / "preferences.scm").write_text(
        '("texmacs->html:images" "off")\n'
        '("texmacs->html:mathjax" "on")\n'
        '("texmacs->html:mathml" "off")\n')

The Scheme code exporting a document loads it into a buffer and exports
the buffer to PDF, to HTML, or both, in this order: the PDF export
typesets the document first, and the HTML export then finds it typeset,
with its numbers and references.

Before exporting, the buffer is typeset as for the screen, with
`(update-forced)`. The PDF export takes the hyperlinks from tables that this
typesetting fills, and a buffer just loaded, never displayed, has none: up to
TeXmacs 2.1.5, a PDF exported headless lost every external link (its `hlink`s
and `slink`s), while the links inside the document survived. The fork of
TeXmacs fixes this in the printer itself (mgubi/texmacs#341); the call costs
one typesetting and makes the tools independent of the version.

    # in the Scheme code exporting a TeXmacs document:
    def export_calls(doc, pdf=None, html=None):
        """Scheme code exporting DOC; a PDF export typesets it first."""
        c = (f'(let ((u (string->url "{doc}"))) (load-buffer u) (switch-to-buffer u)'
             ' (update-forced)')
        if pdf:
            c += f' (export-buffer-main u (string->url "{pdf}") "pdf" (list :overwrite))'
        if html:
            c += f' (export-buffer-main u (string->url "{html}") "html" (list :overwrite))'
        return c + ")"

### The PDF and the HTML version

The PDF must come from the deposited source as it is: it is the rendition
that the source reproduces. The HTML version is presentation (section
7.2): it is not deposited, and the archive is free to improve it. An
archive may give a style package for its HTML versions
(`texmacs.htmlPackage`), which TeXmacs applies to the export. The source
is never modified (appendix B): the package is added to a *copy*, in
another folder with the package next to it.

Adding a package means extending the style line of the document, which is
either a single style (`<style|article>`) or a tuple of styles and packages
(`<style|<tuple|article|notes>>`).

    # in add a style package to a TeXmacs document:
    def with_package(text, package):
        """Add PACKAGE to the style of a TeXmacs document."""
        m = re.search(r"<style\|<tuple\|([^>]*)>>", text)
        if m:
            return text[:m.start()] + f"<style|<tuple|{m.group(1)}|{package}>>" + text[m.end():]
        m = re.search(r"<style\|([^<>|]*)>", text)
        if not m:
            sys.exit("no style line in the source")
        return text[:m.start()] + f"<style|<tuple|{m.group(1)}|{package}>>" + text[m.end():]

Typesetting puts the plain copy and the styled copy in separate folders of
a scratch area, and exports both in one run of TeXmacs: the PDF from the
plain copy, the HTML (and a PDF that is thrown away, needed to typeset it)
from the styled copy. The HTML version replaces the previous one in
`site/<id>/`, with the resources of the plugins it needs (a style sheet).
Without `html_dir` only the PDF is made: an archive whose website is made
by [the website](30-website.md) needs no HTML version unless it has an
HTML package.

TeXmacs files are read and written as Latin-1: TeXmacs uses its own 8-bit
encoding, and Latin-1 maps every byte to one character and back, so that
the copy is the same bytes as the source but for the style line.

    # in typeset a TeXmacs source into a PDF and an HTML version:
    def typeset(source, obj_id, pdf, html_dir):
        """PDF from a plain copy of SOURCE; with an HTML package configured
        (texmacs.htmlPackage), the HTML version from another copy using it."""
        tmp = Path(tempfile.mkdtemp())
        plain, styled, out = tmp / "plain", tmp / "styled", tmp / "out"
        for d in (plain, styled, out):
            d.mkdir()
        shutil.copyfile(source, plain / f"{obj_id}.tm")
        calls = export_calls(plain / f"{obj_id}.tm", pdf=pdf)
        pkg = TEXMACS.get("htmlPackage")
        if html_dir is not None:
            text = source.read_text(encoding="latin-1")
            if pkg:
                shutil.copyfile(ROOT / pkg, styled / Path(pkg).name)
                text = with_package(text, Path(pkg).stem)
            with open(styled / f"{obj_id}.tm", "w", encoding="latin-1", newline="") as f:
                f.write(text)
            calls += " " + export_calls(styled / f"{obj_id}.tm", pdf=tmp / "styled.pdf",
                                        html=out / f"{obj_id}.html")
        run_texmacs(calls)
        if html_dir is not None:
            html_dir.mkdir(parents=True, exist_ok=True)
            for old in html_dir.iterdir():
                old.unlink()
            for f in out.iterdir():
                shutil.copyfile(f, html_dir / f.name)
            for r in TEXMACS.get("htmlResources", []):
                shutil.copyfile(TM_HOME / "plugins" / r, html_dir / Path(r).name)
        shutil.rmtree(tmp, ignore_errors=True)

Reading TeXmacs markup
----------------------

The abstract in `datacite.json` is plain text, with mathematics in LaTeX
between dollars (section 8, appendix B), converted from the TeXmacs
document; the title is given by the depositor, who may want it different
from the one in the document. TeXmacs files are a markup of their own:
`<tag|arg1|arg2>` for inline tags, `<\tag>...</tag>` for tags whose last
argument is long, `\<alpha\>` for symbols, `\|`, `\\` and so on for escaped
characters. A complete parser is not needed: abstracts use a small part
of the markup.

The arguments of a tag end at the `>` that balances its `<`, skipping
escaped characters.

    # in find the end of the arguments of a TeXmacs tag:
    def tm_balanced(s, i):
        """Index of the '>' closing the tag argument list starting at i."""
        depth, j = 0, i
        while j < len(s):
            if s[j] == "\\":
                j += 2
                continue
            if s[j] == "<":
                depth += 1
            elif s[j] == ">":
                if depth == 0:
                    return j
                depth -= 1
            j += 1
        return j

An abstract may be written either way, as `<\abstract>` with paragraphs on
separate lines, or as `<abstract|...>`. Paragraphs are separated by blank
lines; inside each, the line breaks of the file are only layout.

    # in the paragraphs of the abstract of a TeXmacs document:
    def tm_abstract(source):
        """The paragraphs of the abstract of a TeXmacs document, as markup."""
        s = source.read_text(encoding="latin-1")
        i = s.find("<\\abstract>")
        if i >= 0:
            body = s[i + len("<\\abstract>"):s.find("</abstract>", i)]
        else:
            i = s.find("<abstract|")
            if i < 0:
                return None
            i += len("<abstract|")
            body = s[i:tm_balanced(s, i)]
        paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body)]
        return [p for p in paragraphs if p]

### From markup to text with LaTeX

The markup of an abstract is parsed into a list of nodes: strings, symbols
`("sym", name)` and tags `("tag", name, arguments)`, each argument a list
of nodes. The parser is recursive: an argument ends at the `|` or `>` that
the enclosing tag is waiting for. Escapes become their characters (`\U` is
TeXmacs' en dash).

    # in parse TeXmacs inline markup into a tree:
    # TeXmacs inline markup to plain text with LaTeX mathematics (the subset used
    # in abstracts: symbols, scripts, brackets, blackboard bold).

    def _parse(s, i=0, stop=""):
        nodes, buf = [], []

        def flush():
            if buf:
                nodes.append("".join(buf))
                buf.clear()
        while i < len(s):
            c = s[i]
            if c in stop:
                break
            if s.startswith("\\<", i):
                j = s.index("\\>", i)
                flush()
                nodes.append(("sym", s[i + 2:j]))
                i = j + 2
            elif c == "\\" and i + 1 < len(s):
                buf.append({"U": "–", "|": "|", "\\": "\\"}.get(s[i + 1], s[i + 1]))
                i += 2
            elif c == "<":
                j = i + 1
                while j < len(s) and s[j] not in "|>":
                    j += 1
                name, args = s[i + 1:j], []
                while j < len(s) and s[j] == "|":
                    arg, j = _parse(s, j + 1, "|>")
                    args.append(arg)
                flush()
                nodes.append(("tag", name, args))
                i = j + 1
            else:
                buf.append(c)
                i += 1
        flush()
        return nodes, i

Most symbols are LaTeX commands of the same name (`\<alpha\>` is
`\alpha`). The few that are not are mapped, differently in text and in
mathematics.

    # in the TeXmacs symbols written as characters:
    SYMBOLS_TEXT = {"less": "<", "gtr": ">", "nbsp": " ", "ldots": "..."}
    SYMBOLS_MATH = {"less": "<", "gtr": ">", "ldots": "\\ldots"}

Rendering walks the tree. A `math` tag starts mathematics, written between
dollars; scripts become `^{}` and `_{}`; `around` (big brackets) gives its
three parts; `with` gives its body, in `\mathbb` when the font is
blackboard bold; any other tag gives its last argument, which in TeXmacs is
usually the text it applies to. A symbol becomes a command followed by a
space, which is dropped at the end where it is not needed (`\alpha_{1}`, not
`\alpha _{1}`), so that the result is the LaTeX a person would write.

    # in render parsed TeXmacs markup as text with LaTeX mathematics:
    def _render(nodes, math):
        out = []
        for n in nodes:
            if isinstance(n, str):
                out.append(n)
            elif n[0] == "sym":
                table = SYMBOLS_MATH if math else SYMBOLS_TEXT
                out.append(table.get(n[1], "\\" + n[1] + " "))
            else:
                name, args = n[1], n[2]
                def r(a):
                    return _render(a, math)
                if name == "math":
                    out.append("$" + re.sub(r"\s+", " ", _render(args[0], True)).strip() + "$")
                elif name == "rsup":
                    out.append("^{" + r(args[0]) + "}")
                elif name == "rsub":
                    out.append("_{" + r(args[0]) + "}")
                elif name in ("around", "around*") and len(args) == 3:
                    out.append(r(args[0]) + r(args[1]) + r(args[2]))
                elif name == "with" and args:
                    inner = r(args[-1])
                    if any(r(a) == "Bbb" for a in args[:-1]):
                        inner = "\\mathbb{" + inner + "}"
                    out.append(inner)
                elif args:
                    out.append(r(args[-1]))
        s = "".join(out)
        return re.sub(r"(\\[A-Za-z]+) (?=[^A-Za-z])", r"\1", s) if math else s

The text of an abstract paragraph, with its spaces normalised.

    # in convert TeXmacs markup to plain text:
    def tm_to_text(markup):
        return re.sub(r"[ \t]+", " ", _render(_parse(markup)[0], False)).strip()
