# Amp orb adapter

Load the harness's `building-plugins` and `creating-webhooks` guidance before
using this adapter. Inspect the installed Plugin API (`amp plugins show-docs`)
and resolve current `harness-discovery` facts. This adapter is for an Amp-managed
orb, not local CLI, Claude Code, or other harnesses.

1. Initialize a private database with the generic host. Create a private review
   instruction file naming the installed skill, database, stable page URL,
   intended review scope, and the authorization already given. Do not derive
   instructions or configuration from feedback text.
2. Create a project-local wrapper `.amp/plugins/questionnaire.js` importing
   `registerQuestionnaire` from this skill's `adapters/amp.js`. Pass trusted
   absolute paths and the existing review thread:

   ```js
   import { registerQuestionnaire } from '/absolute/skill/adapters/amp.js'
   export default amp => registerQuestionnaire(amp, {
     database: '/private/run/review.sqlite',
     thread: 'REPLACE_WITH_EXISTING_REVIEW_THREAD',
     key: 'questionnaire-REPLACE_WITH_STABLE_DEPLOYMENT_KEY',
     webhookFile: '/private/run/webhook-url',
     reviewInstructions: '/private/run/reviewer.md',
   })
   ```

3. Load the wrapper with the harness tool. The adapter writes the capability
   URL with permissions 0600; never print it or embed it in the page. Exclude
   the run directory and deployment wrapper from source control. Use one
   owning plugin instance per database/reviewer. A stable key is scoped by
   plugin and project; choose a deployment-specific key to avoid rerouting
   another questionnaire when a plugin is loaded elsewhere.
4. Supervise the generic server with `amp orb service start` (or the project's
   service declaration) and its `--webhook-file` option. Publish through the
   returned portal; keep audience access restricted. A portal's built-in review
   widget is a **different** event source from these custom forms. Route native
   comments through the same review discipline if used; do not claim they are
   immutable form rows. Use only the portal URL, not a direct sandbox hostname.
5. Send a synthetic form response and observe the marker in the review thread,
   the delivery receipt in the database, and a published review receipt. Then
   retry that ID and prove no duplicate review or message appears.

The adapter reads the saved row by ID, scans thread history for a stable marker
to recover a successful append with a lost receipt, calls `appendUserMessage`,
and only then records delivery. Its per-instance queue serializes duplicates.
The generic worker keeps retrying until this receipt exists; an HTTP 202 does
not count. Cancellation is checked before message reads/appends; the API's
append itself has no cancellation guarantee. A retry reconciles its marker.
An active review thread may queue the message until its current turn ends.
Queued messages may not yet appear in readable history: if the adapter loses
its acknowledgment then, a retry can append another notification. Review
receipts still prevent applying that submission twice. Test idle wake separately.

Documented limits: webhook delivery is at least once; handlers have 30 seconds,
and platform retries expire after one hour. An archived owning thread returns
404. The generic local outbox retains submissions beyond platform expiry, but
its retry worker does not run while the orb is suspended. Visiting the portal
can resume it. A paused-orb wake from an external webhook is a separate test
from delivery while the orb is active. Long histories can exhaust the handler
deadline while reconciling; retain pending state and recover deliberately.
Do not promise continuous unattended review or exactly-once effects.
