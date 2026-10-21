---
name: picking-skills
description: "Opens a reusable searchable skill picker and copies an exact-source loading instruction. Use for submitted /skills messages, a <skill> placeholder anywhere in a message, or requests to browse and choose skills."
compatibility: Amp Linux orbs with portals, Amp CLI, Node.js 22 or later, and flock.
---

# Picking skills

Open the picker and wait for the user to choose. The page copies a loading
instruction, optionally with the user's completed message. Load the selected
source after the user pastes and sends it.

## Submitted-message triggers

- `/skills`: show all skills. `/skills code review`: prefill `code review`.
- A literal `<skill>` anywhere in the user's message: show all skills and
  preserve the full message using the message-file option below. Defer the
  task until the user sends the completed message; let the user choose the
  skill rather than selecting one for them.
- Requests to show the picker or browse skills also open it.

These triggers run after submission, not while the user types in Amp's textbox.
When the user asks to modify the picker itself, do that work rather than
launching the quoted examples.

## Show the picker

If the skill-picker plugin already provided a portal link for this message,
use its URL in step 2 and end the turn. Reuse its saved request instead of
launching another picker.

1. Resolve this skill's directory to an absolute filesystem path. If Amp shows
   a `file://` URI, decode it first. From the current **project** directory,
   run the bundled launcher, substituting that path for `<skill-directory>`:

   ```bash
   node "<skill-directory>/scripts/launch.mjs"
   ```

   For an explicit search topic, pass it as a quoted argument. Keep the full
   inventory so the user can change their search:

   ```bash
   node "<skill-directory>/scripts/launch.mjs" "code review"
   ```

   For `<skill>`, write the full original user message unchanged to a temporary
   UTF-8 file using a file-writing tool, inside a fresh directory from
   `mktemp -d`. Pass its path, not the message, to the shell. Leave the search
   empty unless the user explicitly requests a filter:

   ```bash
   node "<skill-directory>/scripts/launch.mjs" --message-file "<unique-temporary-directory>/message.txt"
   ```

   Delete the temporary message file and directory after launch. Selection replaces every
   literal `<skill>` with the same chosen skill name and prepends one
   exact-source loading instruction. All other message text stays unchanged.

2. Show the live picker inline in Amp web chat. Use the launcher's exact HTTPS
   URL, including its fragment, and preserve the `amp-portal` title:

   ```markdown
   ![Skill picker](<exact-URL-from-launcher> "amp-portal")
   ```

   Emit the image Markdown outside a code fence so Amp embeds the portal.
   Selection belongs inside the conversation; no opening dialog is needed.
   For a client without inline portals, use the launcher's normal link instead.
   The bundled page and server are reusable: no HTML, inventory, generated view,
   or skill bodies belong in your response. A healthy service is reused;
   changes to the package restart only this project's picker. Report a launcher
   error instead of rebuilding it.
3. End the turn and let the user choose. Selecting or copying inside the page
   does not notify the agent. The user pastes into Amp's message box and sends
   the completed message, or adds a task to a standalone loading request.

Opening the page or clicking **Refresh** reads `amp skills list --json` in the
project where it launched. Filtering runs locally in the browser; typing does
not invoke Amp or the agent. The page contains names, descriptions, and exact
source directories, never skill bodies or bundled resources. Amp's effective
inventory determines which skills appear, including project skills. Discovery
failures disable copying; warnings mark a possibly incomplete inventory.

Saved messages have separate private orb-local files and opaque links. They
expire after 24 hours, are pruned hourly while running, and are limited to 128
requests per project. Portal access follows the thread's permissions; keep it
private. Outside an Amp Linux orb, report the compatibility requirement.

## Cross-orb installation

Publish the **whole directory** as top-level `picking-skills/` in an Amp User
or Workspace Skills repository. Discover writable destinations with
`amp skills repositories`; confirm the scope and get approval before pushing.
New threads discover a published skill automatically; use `reload_skills` for
an existing thread. `amp skill add --global` installs only on one machine and
does not distribute across orbs. Each orb starts its own picker on first use;
inventories, portal URLs, and exact source paths remain local to that orb.

## Interaction contract

- Search filters on every keystroke, ignoring case and matching every entered
  word across names, descriptions, sources, and directories. It is literal
  search, not semantic ranking.
- Enter in the search selects its first result. Arrow Down moves into the
  results; arrows navigate them; Escape returns to search. Clear restores all
  results.
- Selection prepares the exact-source request or completed message. **Details**
  reveals the full description, source directory, and prepared text. **Copy**
  uses the clipboard when permitted, revealing selected text if copying fails.
- Nothing sends automatically or edits Amp's main textbox. A copied request is
  an instruction to load a skill, not proof that the skill was loaded.
