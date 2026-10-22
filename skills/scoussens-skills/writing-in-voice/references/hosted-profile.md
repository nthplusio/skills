# Hosted personal profiles

This is an optional storage mode. Local-only profiles remain the default.
A hosted personal profile lives in the user's unshared User Skills repository,
not the shared workspace or this reusable skill repository. It uses a separate
`remembering-my-voice/` package with a small `SKILL.md` and a `profile.md`.
The different name avoids masking the shared `writing-in-voice` skill.

## Provider contract

The personal provider identifies the profile owner, bundles the profile, and
records the user's approved storage destination and write policy. It delegates
writing, interviews, and correction classification to `writing-in-voice` rather
than copying those instructions. It must not redirect a declared project voice
or an explicit selection to the personal profile.

Create or publish a provider only with the user's approval. Permission to create
it is not standing permission to push future edits. If the user grants standing
permission, record the date, approving conversation, exact destination, allowed
file, and trigger: an explicit durable preference or approval of a proposed rule.
That grant covers only those profile updates, not sharing, other skills, general
Git operations, unrelated changes, or sending messages. A later revocation wins.

## Read

Verify the provider is from the current user's personal scope, not a shared
skill with the same name. Read its bundled `profile.md` before drafting. The
profile file uses the same schema as local profiles. Do not apply another
participant's personal voice merely because their skill is loaded in the thread.

On Amp, reload skills at the start of a new writing session when possible to
refresh the published revision. Do not recursively reload if the caller already
did so. Read the refreshed provider files; its generated cache is read-only.
In a shell-capable session, fetch the approved personal repository before an
update and read its latest profile as described below.

The published provider is authoritative over the default local working copy.
Do not initialize it from a stale local copy or silently combine the two.
If refresh fails, disclose that the available revision may be stale. If the
profile cannot be read at all, offer session-only drafting rather than inventing
preferences. An environment that can read skills but cannot write repositories
can use the profile, but must report any proposed update as unsaved.

## Save a confirmed preference

1. Apply `writing-in-voice`'s correction classification. Confirm ambiguous rules
   with their scope and before/after examples. Check the current task and the
   provider's recorded authorization before publishing any update.
2. Load `building-skills` before managing the personal repository. Discover the
   authenticated User Skills destination rather than constructing a remote from
   a display name. Check it matches the provider's approved destination.
3. Use the canonical clone outside the project. Inspect its status and fetch.
   Fast-forward a clean clone to the remote branch; preserve unexpected local
   edits or commits rather than resetting them. If unrelated unpublished commits
   would be included in the push, stop and report the blocker. Read the fetched
   profile and record the base revision before preparing the scoped edit.
4. Update only the authorized profile file and its concise history, preserving
   unrelated rules. Read it back and commit only that file. Push normally,
   without force. If the remote advanced, fetch and reapply the intended rule
   to the new profile. Preserve independent changes; ask when a concurrent edit
   conflicts with the same preference or scope. Do not resolve by replacing the
   entire file with the previous local version.
5. Verify the remote contains the committed update, then reload skills and
   read the published profile back. Only then report the rule as saved across
   sessions. If publication or reload fails, distinguish a local edit, a pushed
   commit, and the revision the current session can actually read.

A local working copy is optional. Refresh it from the verified published profile
only if it has no divergent edits; otherwise report the divergence. Keep it at
the user's private data path with owner-only permissions. It is not a second
source of truth. Never automatically share the provider with the workspace.

Amp documents the scopes and publication mechanism in
[Global Plugins & Skills](https://ampcode.com/docs/customize/global-plugins-and-skills).
