# Instructions for agents (and people)

This project is a literate program. The Markdown chapters in `literate/`
are the source; these files are **tangled** out of them and must never be
edited directly:

- `src/opensheaf/**/*.py` (every module of the package)
- `src/opensheaf/templates/*` (`index.html`, `paper.html`, `style.css`)
- `tests/test_core.py`, `tests/test_identity.py`, `tests/test_across.py`,
  `tests/test_wallets.py` and `tests/test_paths.py`

Every tangled file that can hold a comment starts with a notice
"Generated from literate/… by opensheaf-literate"; `literate tangle --list`
lists all of them (the templates carry no notice, as they are copied into
archives).

To change them, edit the chapter of `literate/` that defines the code
(`literate tangle --where FILE:LINE` tells which chapter and line a line of
a tangled file comes from), explaining the change in the prose, then run

    pip install -r requirements-literate.txt   # once: the pinned literate tools
    literate tangle                            # write the files
    literate tangle --check                    # they are what the documents say
    pytest -q                                  # the tests

Plain files, edited directly: `pyproject.toml`, `README.md`,
`literate.json`, `requirements-literate.txt`, `src/opensheaf/schemas/*.json`
(the specification's schemas), `.github/workflows/*`, `AGENTS.md`.
