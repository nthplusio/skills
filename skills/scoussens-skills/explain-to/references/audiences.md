# Audience profiles

One profile per reader. Each gives what the reader already knows, what they
decide with the explanation, the question they ask first, the altitude to
start at, the words that are native to them and the ones that are jargon,
whether an anchor analogy helps, the default output, and a reading budget.
Pick one profile in step 1 and hold to it.

The budget is a ceiling on prose outside pictures, tables, and code blocks;
the reader line and the assumption lines sit outside it. A reader who wants
more asks; a reader who got too much stops.

The *always include* items in a profile describe a change. For a concept
rather than a change, give instead the definition, one example from the
reader's own domain, and where the reader meets the concept in their work.

## End user

A person who uses the product to do their job and does not read code.

- **Knows:** the screens, the buttons, the records they work with, their own
  workflow and its deadlines.
- **Decides:** whether to change how they work, and whether to tell their team.
- **First question:** What changes for me, and what do I have to do?
- **Altitude:** Outcome only.
- **Native words:** the product's screen and feature names, their business
  objects such as orders, invoices, accounts, reports, exports.
- **Jargon:** everything on the engineering side, including *API*, *schema*,
  *migration*, *deploy*, *backend*, *cache*, *endpoint*, *environment*.
- **Anchor:** yes. Draw from everyday objects or from their own workflow.
- **Output:** chat reply, or a short Markdown note they can forward.
- **Budget:** about 250 words, two minutes. At most one picture, of the screen
  flow. Commands the reader types and names they see on screen are native;
  code, file names, and identifiers they never type are not. Say when the
  change takes effect and whom to contact if it looks wrong; when the source
  names nobody, say so and name who can fill it in.

## Business stakeholder

A product manager, executive, or client who owns a goal, a budget, or a
customer relationship.

- **Knows:** customers, revenue, dates, scope, risk, dependencies, and who
  owns what.
- **Decides:** approve, fund, prioritise, delay, or tell customers.
- **First question:** What is the impact, what does it cost, and what do you
  need from me?
- **Altitude:** Outcome, with one System picture when parts and ownership
  explain the cost or the risk.
- **Native words:** customer, user, risk, timeline, scope, dependency, effort,
  cost, rollout.
- **Jargon:** every technical term, including *database*, *service*, *query*,
  and *test coverage*. Translate each into a consequence.
- **Anchor:** yes. Draw from business processes, contracts, logistics, or
  buildings.
- **Output:** chat reply for one decision. HTML page when others must review
  and comment, or when it is referenced over days.
- **Budget:** about 400 words, three minutes. Lead with the ask and the
  recommendation. Put each number in a table with a column for the baseline
  or the thing it is compared with, so that no number stands alone. One
  picture, and the prose that explains it may share its altitude.

## Developer new to the code

An engineer who knows how to program and does not yet know this system.

- **Knows:** general software: requests, services, queues, tests, modules,
  branches, builds.
- **Decides:** where to look first, and what not to break.
- **First question:** Where does this live, and how does it connect to what I
  already know?
- **Altitude:** System, then Part. Code only in a short excerpt that shows a
  convention.
- **Native words:** generic software vocabulary.
- **Jargon:** every project-local name, including module names, internal
  acronyms, and domain terms. Define each at first use, in generic words.
- **Anchor:** yes. Draw from patterns they know from other systems: a queue, a
  cache, middleware, a lookup table.
- **Output:** Markdown document in the repository when it should outlive the
  thread. Chat reply otherwise.
- **Budget:** about 700 words, five minutes. Include a shallow file map with
  one line per folder. For a change, one before-and-after picture.

## Developer who owns the code

An engineer who maintains this system and will review, extend, or debug the
thing being explained.

- **Knows:** the system, its names, its history, its conventions.
- **Decides:** whether the change is right, and whether it is safe.
- **First question:** What changed, why, and what could break?
- **Altitude:** Part and Code.
- **Native words:** everything, including project-local names.
- **Jargon:** none. Their time is the constraint.
- **Anchor:** no. A one-line definition at most.
- **Output:** chat reply with a diff or a before-and-after drawing. Follow the
  harness's code-explaining skill when it has one.
- **Budget:** about 300 words, two minutes. Lead with the behaviour difference,
  then risks and edge cases. Omit background they already hold.

## Data engineer

An engineer who owns tables, pipelines, and the contracts between producers and
consumers of data.

- **Knows:** tables, columns, views, schemas, grain, partitions, lineage,
  migrations, backfills, warehouses, orchestration, SQL, dbt-style models.
- **Decides:** whether a change breaks downstream data, what to backfill, when
  to run it, and whom to warn.
- **First question:** Which tables and columns change, who reads them, and what
  happens to the rows already stored?
- **Altitude:** System as data flow, then Part as schema.
- **Native words:** upstream, downstream, grain, backfill, idempotent,
  incremental, partition, contract, lineage.
- **Jargon:** application-side terms such as *component*, *hook*, *handler*,
  *dependency injection*, *middleware*. Anchor each to a data concept.
- **Anchor:** yes, for application concepts. Draw from data flow and contracts.
- **Output:** Markdown document for a schema change, because it is read during
  the migration and after. HTML page when several engineers review the
  change or when the schema picture carries the argument. Chat reply for a
  question.
- **Budget:** about 600 words, five minutes. Always include a before-and-after
  of the schema, of the lineage, or of both when the change touches both; the
  answer for existing rows; and the list of consumers by name.

## Operator

An engineer on call who deploys, watches, and rolls back, often without
knowing the code.

- **Knows:** deploys, dashboards, alerts, logs, feature flags, rollbacks,
  runbooks, capacity.
- **Decides:** whether to deploy, what to watch, and how to undo it.
- **First question:** What do I watch, and how do I undo it?
- **Altitude:** System.
- **Native words:** service, alert, latency, error rate, rollout, flag,
  rollback, saturation.
- **Jargon:** business domain terms and code internals. Translate each to a
  signal they can see.
- **Anchor:** yes, sparingly. Draw from physical plant and operations.
- **Output:** Markdown runbook section, or a chat reply with the same shape.
- **Budget:** about 300 words, three minutes. Signals with thresholds, the
  rollback step, and the person to call come first.

## Two readers

When the request names two readers, write for the one that is less technical
and add one block at the end, headed for the other reader, that holds only
what they need beyond the main text. Two full texts in one output serve
neither reader.
