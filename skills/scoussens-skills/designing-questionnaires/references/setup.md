# Set up once per questionnaire

Load `explain-to` from this library and run only its settings step. Read
`references/settings-sheet.md` and `references/audiences.md` relative to that
loaded skill's directory. If unavailable, install `explain-to` from the same
library before the first-run intake. Fix the outputs as one review page and
the final JSONL handoff for ticket planning. Fix page interaction as filtering,
answering, and reviewing at the supported destination. A static fallback must
say which interactions it cannot provide. Keep both outputs within the same
approved audience.

Infer known settings from the request and evidence. Present only unresolved
settings, with recommendations and reasons, in one sheet. Add these rows to
the same sheet rather than conducting another interview:

| Setting | Settle before publishing |
| --- | --- |
| Outcome and scope | Which decision should the answers unlock? What is outside this review? |
| Readers | Who supplies facts, who decides, what each already knows, and what vocabulary they use. |
| Response budget | Quick choices, a short explanation, or evidence-backed answers. Ask for the cheapest response that settles the question. |
| Delivery | Page audience, preferred reply channel, verified recipient identity, and the user's permission to notify them. |
| Review policy | Reviewing agent, human fallback, conflict decision maker, and the condition for escalation. |

Accept corrections in one reply and keep the other recommendations. Follow
the settings sheet's skip rules when the request already settles the choices
or grants autonomy. Unknown identity or authority stays unknown; it never
becomes permission to send. Use a draft notification as the fallback.

Save the public choices in the model's `setup` object before publication.
Save private delivery choices in `RUN/routing.md`, outside served assets:

```markdown
# Delivery for <questionnaire ID>
- Page URL and allowed audience:
- Respondent, verified account ID, and verification source:
- Preferred channel and reply path:
- Authorized send scope and source of permission, or draft only:
- Reviewing agent and human fallback:
- Capability evidence: pointer to the existing harness-discovery entry.
- Sent batches: publication revision, recipient, question IDs, transport
  receipt, and outcome. Record uncertain sends for reconciliation.
```

The routing note records this questionnaire's choices, not harness
capabilities. Secrets remain in the adapter's credential store. Check the
saved setup on later reviews; ask only about a changed or unresolved choice.
An older page without setup can continue reviewing existing submissions.
Derive its setup from available evidence without blocking that review on a
fresh interview.

**Done when** the saved settings identify the decision, readers, response
budget, review policy, and authorized delivery scope. Each unknown has a
visible fallback rather than a guessed person, deadline, or permission.
