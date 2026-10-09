# Discovery: find where the business logic lives

`br.py survey` prints the repository's shape and writes `scope.draft.json`.
This reference turns that draft into `scope.json`: which **areas** readers
cover, how deep, and the lifecycle **stages** the explorer's map shows.

## Read before classifying

- The guidance files survey lists (`AGENTS.md`, `CLAUDE.md`,
  `ARCHITECTURE.md`) and the root `README`. They usually say which package
  owns what.
- The glossary, if survey found one. Readers write rules in its words.
- The entry-point candidates. They show how work enters the system, which is
  the backbone of the stages.

Then read two or three files from each candidate area: its largest file and
the one with the most decisions. Survey's `dec/kloc` column counts branch and
query keywords per thousand lines. It hints where conditions concentrate; the
files you read decide the tier.

## Classify every candidate area

- **business**: the code decides outcomes the business owns. Domain models
  with invariants, services, pricing, eligibility and matching, workflows and
  state machines, validation schemas, query builders and stored procedures
  whose predicates encode policy, rule-engine files, and seed data that
  defines defaults. Readers cover it at full depth.
- **platform**: infrastructure that still carries decisions an owner may care
  about, such as provisioning, tenancy and isolation, secrets, storage layout
  and encoding. One reader covers all platform areas as a summary, 3 to 12
  rules per area.
- **skip**: code that decides nothing a business owner reviews, such as
  rendering-only UI, generated clients, test utilities, build tooling and
  vendored code. Keep it in `scope.json` with `tier: "skip"` and a one-line
  `summary` of why, so the note and the next run both see the choice.

Business logic also hides outside the obvious services:

- In query text: migrations with defaults and constraints, SQL files, ORM
  scopes, stored procedures.
- In the UI: front-end validation and calculations often repeat a backend
  rule. Make such a UI area business, so readers can catch the two drifting
  apart and flag it `inconsistent`.
- In handlers: an API handler sometimes decides more than the service behind
  it.
- In configuration: rate tables, feature flags and rule files. Add their
  extensions to `extensions` when they encode decisions.

Split a candidate whose halves have different owners or vocabulary. Merge a
tiny candidate into its caller's area.

## Draft the stages

A **stage** is where a business user meets a decision. Trace one unit of
work: how it enters (request, upload, schedule, message), what it passes
through, where it is stored, and how it is read back. Name 4 to 10 stages in
that order, in the glossary's words, with `lane: "main"`. Then:

- A concern that runs beside several stages, such as reference data,
  permissions or hierarchies, becomes `lane: "side"`. Give it `laneFrom`, the
  first main stage it spans.
- Cross-cutting rules, such as identifiers, encoding and tenancy, go in one
  `lane: "band"` stage.
- A stage where work can wait and resume gets
  `loop: {"label": "...", "title": "..."}`.
- `entries` lists the job, route or command names that run the stage. The
  map shows them under the stage's box.

For a library or a system with no flow, use capability stages (pricing,
eligibility, scheduling) in the order a user meets them.

## Surfaces, glossary and documents

- `surfaceKinds`: one entry per entry-point family survey found, each with
  `label`, `icon` (one or two plain characters) and `where` (the directories
  where readers find that family). Keep `internal`.
- `glossary`: `{"path": ..., "format": ...}` with format `bold-colon`
  (`**Term**:` followed by a paragraph), `headings` (`## Term` followed by a
  paragraph) or `other`. For `other`, readers still read the document. To get
  definitions into the explorer, write `{term: definition}` to
  `<work>/glossary.json` yourself.
- `docs`: the glossary and decision-record folders that readers check the
  code against.
- `exclude`: whole-path globs for generated or vendored files survey did not
  recognise. `*` also crosses `/`, so `*/generated/*` matches at any depth.
- `links`: only when `origin` is not GitHub, GitLab or Bitbucket and the user
  wants clickable citations. Give `file`, `line` and `commit` URL templates
  using `{commit}`, `{path}`, `{start}` and `{end}`.

## Large repositories

When there are more candidate areas than you can classify by reading a few
files each, give each top-level unit to a helper with this reference, then
merge their proposed area entries yourself.

## The scope contract

```json
{
  "schema_version": 1,
  "project": {"name": "Shop", "slug": "shop"},
  "title": "Shop business rules",
  "glossary": {"path": "docs/GLOSSARY.md", "format": "bold-colon"},
  "docs": ["docs/GLOSSARY.md", "docs/adr"],
  "extensions": [".go", ".sql", ".ts"],
  "exclude": ["*.gen.ts"],
  "areas": [
    {"id": "orders", "code": "OR", "title": "Orders", "tier": "business",
     "paths": ["services/orders"], "summary": "Prices, places and cancels orders.",
     "focus": "The glossary says a cancelled order keeps its number; check that."}
  ],
  "surfaceKinds": [{"id": "api", "label": "API", "icon": "{ }", "where": ["services/orders/src"]},
                   {"id": "internal", "label": "Internal", "icon": "•"}],
  "stages": [{"id": "checkout", "label": "Checkout", "lane": "main", "entries": ["POST /v1/orders"],
              "description": "Pricing, fees and validation when an order is placed."}],
  "flagTypes": "keep the draft's six types; edit a description only to name this project's documents",
  "noteDirs": ["docs/research"]
}
```

`id` is a lowercase slug. `code` is 2 to 4 capitals, unique across areas, and
prefixes every rule ID in the area (`BR-OR-012`). `paths` are
repository-relative directories or files. A file under two areas belongs to
the one with the longer path. `summary` says in one or two sentences what the
area decides, or why it is skipped. `focus` is optional: claims from the
glossary or decision records that readers should check against this area's
code.
