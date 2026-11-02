# Set up once per questionnaire

When `explain-to` is available, run only its settings step and read its
`references/settings-sheet.md` and `references/audiences.md`. If unavailable,
use the intake below directly; neither it nor `harness-discovery` needs to be
installed for manual/static review. Fix the outputs as one review page and
the final JSONL handoff for ticket planning. Fix page interaction as filtering,
answering, and reviewing at the supported destination. A static fallback must
say which interactions it cannot provide. Keep both outputs within the same
approved audience.

Reuse known settings from the request, caller, or saved setup. Present only
unresolved consequential settings, with recommendations and reasons, in one
sheet; if none remain, proceed without an interview. Add these rows to
the same sheet rather than conducting another interview:

| Setting | Settle before publishing |
| --- | --- |
| Outcome and scope | Which decision should the answers unlock? What is outside this review? |
| Roles | Which roles the questions are for, what each role knows and cares about, and who holds each role now. One person may hold several roles. Who decides, kept in the review policy. |
| Response budget | Quick choices, a short explanation, or evidence-backed answers. Ask for the cheapest response that settles the question. |
| Delivery | Page audience, preferred reply channel, verified recipient identity, and the user's permission to notify them. |
| Review policy | Reviewing agent, human fallback, conflict decision maker, and the condition for escalation. |
| Team channel | Whether to post asks to a team chat channel and watch it for answers. If yes: the tool (Microsoft Teams, Slack or another), the channel, the harness route that reaches it, the owner's approval of each post, and the watch schedule. See [channel posting and monitoring](channel.md). |

Accept corrections in one reply and keep the other recommendations. Incidental
format choices follow the saved response budget. Return the selected settings,
destination, actual audience, and permission source or hold. One public
destination is not publication consent; hold uploads until the content and
audience are approved, even if the user grants drafting autonomy. Unknown
identity or authority stays unknown; it never becomes permission to send.
Use a draft notification as the fallback. Keep the page and JSONL contract;
a static mode discloses its missing interactions rather than claiming a live form.

Save the public choices in the model's `setup` object before publication.
Save the roles in the model's `roles` list, and keep `setup.readers` to one
line that maps people to roles, such as "Taylor holds all three roles;
Morgan decides conflicts."
Save private delivery choices in `RUN/routing.md`, outside served assets:

```markdown
# Delivery for <questionnaire ID>
- Page URL and allowed audience:
- Respondent, verified account ID, and verification source:
- Preferred channel and reply path:
- Authorized send scope and source of permission, or draft only:
- Reviewing agent and human fallback:
- Capability evidence: relevant saved discovery or inspected tool/documentation
  sources and limits; manual/static wake-up is not required.
- Sent batches: publication revision, recipient, question IDs, transport
  receipt, and outcome. Record uncertain sends for reconciliation.

## Team channel (only if chosen; otherwise "No channel")
- Tool, channel name, stable channel ID, and link:
- Route (MCP server, connector, CLI or bot) and its read, reply and post operations:
- Access evidence: read check and post check, with dates:
- Voice and approval: per post, or standing approval with scope and source:
- Watch: schedule, time zone and working hours, wake capability, or on demand only:
- Cursor: last message read and recorded:
- Posts: status (sending, posted, uncertain), revision, question IDs,
  approved text, message ID and link.
- Unmatched messages: link, author, time, and why no question matched.
```

The routing note records this questionnaire's choices, not harness
capabilities. Secrets remain in the adapter's credential store. Check the
saved setup on later reviews; ask only about a changed or unresolved choice.
A saved setup without a channel choice means no channel; settle the channel
row only when the owner asks for channel posting or watching.
An older page without setup can continue reviewing existing submissions.
Derive its setup from available evidence without blocking that review on a
fresh interview.

**Done when** the saved settings identify the decision, readers, response
budget, review policy, authorized delivery scope, and the team channel choice.
A chosen channel has passed its read and post checks or is labeled draft only.
Each unknown has a visible fallback rather than a guessed person, deadline, or
permission.
