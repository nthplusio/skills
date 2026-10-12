# Reader brief: derive the business rules {PROJECT}'s code enforces

You are one of several parallel readers. Together you are writing a catalogue
of the business rules the code in `{REPO}` enforces. Business owners will walk
the catalogue as a tree, mark each rule Correct, Wrong or Unsure, and send
corrections to engineering, who change the code. A wrong rule sends someone to
"fix" correct code, so accuracy beats volume.

{GLOSSARY}

## What a rule is

A **rule** is one decision the code enforces. Read it from what the code does:
function bodies, query text (`WHERE`, `ON`, `CASE`, `COALESCE`, `ORDER BY`),
guards, raised errors, defaults and constants. Each rule cites the line that
enforces it; a decision you cannot point at stays out. Docstrings, comments and
documentation tell you what someone intended, which is how you find flags, not
rules. Tests confirm your reading, and their literal values make good examples.

Record two families:

- **Data outcomes**: validations and what a violation does, defaults,
  derivations (names, keys, IDs, dates), matching and precedence, state
  transitions, thresholds and limits, ordering, naming, authorization.
- **Guarantees a user feels**: what a re-run or a repeated delivery does,
  what a partial failure leaves behind, ordering and concurrency, what is
  retried and what is not.

Plumbing with no business effect (pooling, logging, back-off timing, type
plumbing) stays out, with one exception: plumbing that silently changes an
outcome, such as a swallowed error that drops rows, is a rule flagged `silent`.

One rule is one decision: merge near-duplicates, and keep one decision in one
rule. A typical module yields 0 to 15 rules. A module that decides nothing
gets a summary and an empty rule list, because "this decides nothing" is
reviewable too.

## Where a rule lives

The catalogue is a tree of area, module (file) and rule. A rule's **home** is
the module holding the condition that decides the outcome. When that condition
is query or template text in one file and the code that runs it is in another,
the home is the text's file, and the runner appears in `engineering` with role
`executes`. Each rule has exactly one home; link dependent rules with
`related`.

## Writing style

- `statement`: one or two sentences, present tense, active voice, in business
  language. Say what the system does. Put physical names in backticks: tables
  and columns (`orders.status`), fields, status values (`PAID`), route paths.
  Function and variable names belong in `engineering`.
- `applies_when`: the trigger or context, in one sentence.
- `exceptions`: each real exception the code makes, one sentence each; an
  empty list when there are none.
- `example`: concrete input and outcome, for example "An order of `99.99`
  ships free; `99.98` pays the `4.95` fee."
- `on_violation`: for validations, what a violation does: rejected with which
  message, skipped silently, retried, or marked failed. `null` otherwise.
- Module `title`: a short business name ("Shipping fee", not `shipping.ts`).
  Module `summary`: one to three sentences on what the module decides.

## Where you see this (`surfaces`)

Trace each rule to where it reaches the product: start from the public function
that enforces it and follow its callers to an entry point. Trace once per
entry point and reuse the result for every rule that function enforces.
`rg -n "<function_name>\("` is fast. Surface kinds for this repository:

{SURFACES}

Give an API surface its method and full path (`POST /v1/orders`), a job its
scheduler name, a screen the route and the name a user would call it, and cite
`file:line` in `ref`. When nothing outside your area reaches a rule, use one
`internal` surface that names the caller.

## Flags

A **flag** is a verified reason a business owner must decide something about
a rule. Add one only with evidence:

{FLAGS}

Every flag cites `evidence` as `path:line`. `contradicts-docs` and
`inconsistent` cite both sides. Documentation to check the code against:
{DOCS}.

## Output

Write the one file your prompt names. Every path is repository-relative:
`module`, `engineering[].file`, `surfaces[].ref` and `evidence`.

```json
{
  "worker": "W1",
  "areas": [
    {
      "area": "orders",
      "summary": "Only when you own the whole area, otherwise null. Two to four sentences in business language.",
      "modules": [
        {
          "module": "services/orders/src/shipping.ts",
          "title": "Shipping fee",
          "stage": "checkout",
          "summary": "What this module decides, in business terms.",
          "rules": [
            {
              "key": "free-shipping-threshold",
              "title": "Orders of 99.99 or more ship free",
              "stage": "checkout",
              "kind": "threshold",
              "statement": "...",
              "applies_when": "...",
              "exceptions": [],
              "example": "...",
              "on_violation": null,
              "terms": ["Order"],
              "surfaces": [
                {"kind": "api", "name": "POST /v1/orders", "ref": "services/orders/src/routes.ts:42"}
              ],
              "engineering": [
                {"role": "decides", "file": "services/orders/src/shipping.ts", "symbol": "shippingFee", "lines": "12-30"}
              ],
              "flags": [
                {"type": "magic-value", "detail": "...", "evidence": ["services/orders/src/shipping.ts:14"]}
              ],
              "related": ["orders:fee-rounding"],
              "confidence": "high"
            }
          ]
        }
      ]
    }
  ],
  "notes": "What the merger should know: overlaps with neighbours, modules you skimmed, callers you could not trace."
}
```

The values only show the shape. Field values:

- `area`: an area ID from your prompt.
- `module`: a file, a directory for a grouped summary module, or
  `dir/a.ts, b.ts` for a few files read as one.
- `key`: a kebab-case slug, unique within the area.
- `stage`: the stage where a business user meets the decision:
{STAGES}
- `kind`: `validation`, `default`, `derivation`, `matching`, `precedence`,
  `state-transition`, `threshold`, `ordering`, `guarantee`, `naming` or
  `authorization`.
- `terms`: glossary terms the rule uses, spelled as the glossary spells them.
- `engineering[].role`: `decides` (holds the deciding condition), `executes`
  (runs text or code decided elsewhere) or `calls` (reaches it on the way).
- `related`: `key` or `area:key` of rules this one depends on.
- `confidence`: `high` when you read the enforcing line, `medium` when the
  rule needed inference across calls you did not fully trace. A rule weaker
  than that goes in `notes` instead.

Prove the file parses before you finish:
`python3 -c "import json;json.load(open('<your output>'))"`. Then reply with
rules per module, flags per type, and your `notes`.
