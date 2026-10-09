# Checker brief: second read of derived business rules

Parallel readers derived business rules from the code in `{REPO}`. Their brief
is `{WORK}/BRIEF.md`; read it for what a rule is, the style and the flag
types. Business owners will review these rules and engineers will change code
because of the flags, so a wrong claim costs real work. You are an independent
**checker**: re-read the code each rule cites and reach your own verdict. Leave
the repository unchanged.

Your input is a JSON list. Each item has `worker`, `area`, `module`, `key` and
the full `rule`, and one of two cases applies:

- `check_flags` lists indices into `rule.flags`. Verify each listed flag
  against its evidence lines and against the other side it names (the
  glossary, a decision record, a docstring or another code path). Check the
  rule's statement too.
- `sample: true` marks a random unflagged rule. Check its `statement`,
  `applies_when`, `exceptions`, `example` and `on_violation` against the code
  in `engineering`.

Settle each claim from what the code does: conditions, query text, defaults,
raised errors and constants. Follow calls as far as the claim needs. Confirm
that `engineering` line ranges point at the deciding code, and correct any
range that is off by more than a few lines.

Verdicts:

- Rule: `correct`; `needs-revision`, with the corrected fields in
  `rule_revision` written in the reader brief's style; or `wrong`, when the
  code does not enforce it at all. A `wrong` rule takes a `rule_revision` when
  there is a true rule to state instead.
- Flag: `confirmed`; `revised`, when the concern is real but the detail or
  evidence is off, with `revised_detail` and, if needed, `revised_evidence`;
  or `refuted`, when the concern does not hold, with the reason in `note`.

Write the output file your prompt names as a JSON list, one entry per input
item:

```json
[
  {
    "worker": "W3",
    "area": "orders",
    "key": "the-rule-key",
    "rule_verdict": "correct",
    "rule_revision": null,
    "flags": [
      {"index": 0, "verdict": "confirmed", "revised_detail": null, "revised_evidence": null, "note": "what you checked"}
    ],
    "note": "what you read and why you reached the verdict"
  }
]
```

`rule_revision` holds only the fields to change, for example
`{"statement": "...", "engineering": [...]}`. `flags` lists only the flags in
`check_flags`, so it is empty for samples.

Prove the file parses before you finish:
`python3 -c "import json;json.load(open('<your output>'))"`. Then reply with
rules correct, needs-revision and wrong; flags confirmed, revised and refuted;
and one line for each refuted flag and each wrong rule.
