# Repeatable verification

Run from any directory using the installed skill's absolute path:

```bash
python3 -B -m unittest discover -s "<skill>/evals" -p 'test_*.py' -v
```

The standard-library suite exercises a disposable multi-language Git repository
through the CLI. It checks discovery, nested skip ownership, partitioning,
source drift, checker completeness and stale results, correction application,
chunk loading, citations in the note and hash-checked upload preparation.
Browser tests skip unless explicitly enabled. With `agent-browser` and its
installed Chromium, run:

```bash
BR_BROWSER_TEST=1 python3 -B -m unittest discover -s "<skill>/evals" -p 'test_*.py' -v
```

The browser contracts generate the same fixture, then open both `site/index.html`
and `bundle.html` directly. They check immediate JSON/CSV/Markdown export,
note ownership after immediate navigation, reload persistence, import merging
and rejection, keyboard tree navigation and export/import focus, a real CSV
download, data completeness, horizontal overflow and unobscured correction
fields at 1440 and 390 pixels.
The fixture uses prepared reader/checker results, not an agent extraction.
These checks do not establish extraction accuracy or provider access controls.

After template changes, also perform step 7's visual inspection on a generated
explorer and retain the inspected screenshots. After publishing, repeat review
and access checks at the actual final URL. Local file behavior does not prove a
host allows storage, scripts or downloads. `evals/evals.json` contains separate
workflow evaluation prompts; report them as unrun unless an agent actually
executes them with retained evidence.
