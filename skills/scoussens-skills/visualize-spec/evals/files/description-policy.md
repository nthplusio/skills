# Enforce a description-quality policy in the skill validator

## Problem Statement

As a maintainer of this skills pack, I can merge a skill whose `description` is too weak to ever fire. The description is the only text an agent reads before deciding whether to load a skill, so a vague one ("Helps with PRs.") means the skill silently never triggers. Nothing errors: the validator checks that the field exists and is a non-empty string, and then calls a description-quality hook that returns an empty list. Two of the pack's skills shipped with descriptions that named no trigger at all before a reviewer caught them by eye.

## Solution

`npm run validate` applies a description-quality policy to every skill. Hard rules fail the run; soft rules print a warning and let it pass. The policy distinguishes model-invoked skills, whose description must carry triggers, from user-invoked skills (`disable-model-invocation: true`), whose description is a one-line human summary and is held to a lighter bar.

## User Stories

1. As a pack maintainer, I want the validator to fail when a description is longer than 1024 characters, so that a skill the builder would truncate never ships.
2. As a pack maintainer, I want a warning when a model-invoked skill's description has no trigger clause ("Use when…", "Load this when…"), so that I notice before the skill silently never fires.
3. As a pack maintainer, I want a warning when a description is shorter than 40 characters, so that one-word descriptions get a second look.
4. As a pack maintainer, I want user-invoked skills exempt from the trigger-clause warning, so that a correct one-line summary is not nagged on every run.
5. As a contributor, I want each warning to say which rule fired and how to fix it, so that I do not need to read the validator's source.
6. As a contributor, I want the policy to run on every push and pull request, so that CI catches what my local run missed.

## Implementation Decisions

- Extract the policy into its own module in the scripts library, exporting one function that takes the parsed frontmatter and returns a list of `{ level, msg }` findings. The validator's existing `checkDescriptionQuality` hook calls it.
- The function receives the whole frontmatter, not just the description, because the rules depend on `disable-model-invocation`.
- Hard rule (error): description over 1024 characters.
- Soft rules (warn): under 40 characters; model-invoked with no trigger clause. A trigger clause is any of "Use when", "Use this when", "Load this when", "Load this only when", matched case-insensitively.
- No change to the CI workflow is needed: the `validate` job already runs `npm run validate`.

## Testing Decisions

- A good test calls the policy function with a frontmatter object and asserts on the returned findings. It does not run the whole validator or touch the filesystem.
- Tests use Node's built-in test runner (`node --test`), so the pack gains no dev dependency. A `test` script is added to `package.json`, and the CI `validate` job runs it before validating.
- Cases: a 1025-character description errors; a 30-character description warns; a model-invoked description with no trigger warns; the same description with `disable-model-invocation: true` does not warn; a description with "Load this only when" passes.
- There is no prior art for unit tests in this repository; this is the first test file.

## Out of Scope

- Checking description quality with a language model.
- Rewriting existing skills' descriptions; this change only reports.
- Enforcing the `": "` rule, which the YAML parse already catches.

## Further Notes

The 1024-character limit comes from the skills.sh builder documentation.
