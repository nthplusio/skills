# Writing a description that triggers

The `description` field is the only part of a skill an agent sees before it
decides whether to load the rest. It is a retrieval key, not a summary.

## The shape that works

> `<what it does>. Use when <concrete trigger>, <concrete trigger>, or <concrete trigger>.`

Include the vocabulary a user would actually type. Agents match on surface
terms far more than on intent, so a description that omits the words "deploy"
and "rollback" will not fire when someone says "roll back the deploy".

## Good

```yaml
description: Generate and validate OpenAPI specs from an Express or Fastify app.
  Use when the user asks to document an API, mentions swagger or openapi.json,
  reports drifted API docs, or wants request/response schemas generated from routes.
```

Names the technologies, names the artifacts, and lists phrasings that should
trigger it.

## Bad

```yaml
description: Helps with API documentation.
```

No trigger vocabulary, no technology names, no situations. It will lose to any
more specific skill and will not fire on an indirect request.

## Checklist

- [ ] States what the skill *does* in the first sentence.
- [ ] Contains a "Use when …" clause with at least three distinct triggers.
- [ ] Names concrete tools, file types, commands, or error strings.
- [ ] Includes the words a user would type, not just the words you would.
- [ ] States when *not* to use it, if it overlaps with a sibling skill.
- [ ] Reads as one self-contained string — it is shown without the body.
