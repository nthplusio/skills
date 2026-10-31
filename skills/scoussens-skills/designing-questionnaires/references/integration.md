# Select integrations from discovery

Use relevant saved `harness-discovery` facts when available, or inspect
read-only inventories, schemas, authoritative documentation and probes
authorized for this questionnaire. Preserve unrelated discoveries. Manual and
static review require no discovery companion or wake adapter. The table is a
mode-specific checklist, not a requirement to initialize a registry. Keep narrow
observations in the private run note; use the existing discovery report when a
durable harness survey is needed.

| Need | Existing discovery home | Evidence required |
| --- | --- | --- |
| Publishing | `artifacts` | Stable URL, update operation, audience/authentication, same-origin API routing; test served updates |
| Feedback/event delivery | `artifacts[].interaction`, `monitoring.notifications` | Distinguish native review controls from custom forms; prove a saved form triggers the selected route |
| Agent wake-up (automatic only) | `monitoring.wake`, `owners.message` | A message in the actual reviewer's conversation/queue, not an HTTP acknowledgment; idle/resume behavior and expiration limits |
| Persistence | `evidence.retain_before_close`, artifact limits | Disk/database lifetime, service restart behavior, backup/export and retention before closure; distinguish durable file from always-on worker |
| Browser verification | `sources`, `limitations` | Installed browser or harness tool and supported viewport, DOM and recording operations; name untested browsers |
| Issue tracker | `repository.ticket_sources`, `ticket_template`, `notes` | Actual configured tool/repository and read permissions; lack of configuration is a result, not a reason to invent tickets |
| Category research | `owners`, `helpers`, `sources`, `limitations` | Code/source access, bounded assignments, actual concurrency, continuation and result collection; shared versus isolated checkouts and how local changes reach a researcher |

The current schema has no dedicated browser or database capability key; record
those observations in its existing descriptive fields. Do not fork the schema
or infer support from a model name. Deployment choices (database path, reviewer
handle, URL, authorization, secrets) stay in private run configuration, never
the shared registry.

## Fallbacks

- **Native feedback with real wake-up:** usable if submissions can be preserved,
  attributed to stable question IDs, and reconciled with page receipts. Adapt
  native events into the same workflow. Native page review does not wire a
  custom form automatically.
- **Durable host plus tested adapter:** use the bundled page/API/outbox. Confirm
  the gateway serves relative assets and `/api/*` on the same origin.
- **Persistent feedback but no wake:** show manual-review mode. Name the
  reviewer and an agreed handoff channel. Ask the person to send the page link
  and submission ID; the reviewer reads pending rows. Do not invent polling,
  schedules, or background permissions.
- **Static-only publishing:** publish read-only requirements and questions,
  with an explicit existing reply channel. Disable/remove form submission;
  never claim comments are saved or reviewed. The bundled dynamic host cannot
  be uploaded unchanged to a static-only host. Preserve received originals with
  stable IDs in approved durable storage, then add review receipts and update
  the page and JSONL together; the reply channel replaces the form, not the ledger.
- **No durable storage:** keep the questionnaire and feedback in the existing
  conversation or a user-approved durable document. Disclose that no live form
  loop exists. If neither retains originals and receipts, hold the review loop
  and deliver only a labeled draft. Browser storage is for drafts, not team
  feedback persistence.

Never select a tracker write as the wake mechanism merely because a tracker
tool is available. Tracker edits, infrastructure changes, expanded sharing,
and sending private content to another service need their own authorization.
