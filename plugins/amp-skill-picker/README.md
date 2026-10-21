# Amp skill picker plugin

Adds **Skills: Open picker** to Amp's command palette and detects submitted
`/skills [topic]` and literal `<skill>` placeholders. It uses the installed
`picking-skills` skill's launcher, server, and page; it contains no second UI
or skill inventory. The skill remains usable without the plugin.

## Use

1. Send `/skills` in Amp web chat. The agent's reply embeds the live picker
   inside the conversation, without an opening dialog.
2. Search by name or description, choose a skill, and click **Copy**.
3. Paste into Amp, add your task, and send.

**Details** shows the full description, exact source, and prepared request.

Send `/skills code review` to prefill a search. Send a message
such as `Use <skill> to review this change.` to preserve the whole task. The
page replaces every placeholder with the selected name and prepends the
exact-source loading instruction. It copies no skill bodies and sends nothing.

The submitted-message hook runs after Send. It prepares the request and adds
instructions for the agent to embed its portal and wait, reusing the same
request. This route still takes an agent turn; waiting for your completed
message relies on the agent following those instructions. The plugin does not
provide a native searchable chat widget or typing-time slash autocomplete.
Neither route edits Amp's unsent textbox.

The optional palette command **Skills: Open picker** runs without an agent
turn but opens a native dialog with a link instead of embedding the page in
chat. In the CLI, `Ctrl+O` opens that link. Close the dialog with **Done** after
copying. An orb does not open your computer's browser automatically. If no
interactive UI is available, the command notifies the portal link. Cancelling
the dialog sends nothing and leaves its private request to expire under the
picker's normal 24-hour retention policy.

## Install across orbs

Install the whole `picking-skills` package from this library into your Amp
User or Workspace Skills repository first. It requires an Amp Linux orb,
Node.js 22+, and `flock`. The plugin resolves the effective installed skill
from `amp skills list --json` in each project on each invocation, so it follows
project overrides and skill updates instead of retaining another orb's path.

Publish `index.ts` as `skill-picker.ts` in your Amp User or Workspace Plugins
repository. `amp plugins repositories` lists writable destinations. Publishing
requires approval; adding a plugin to this GitHub library does not install it
globally. New threads load the published plugin; reload plugins in existing
threads. Keep the source here and the published copy identical.

Do not install this as a Claude Code marketplace plugin. It uses Amp's
`@ampcode/plugin` API, not Claude Code's plugin hooks.

## Verify

Run `npm run test:amp-plugins`. Tests exercise the registered command and event
handlers with the real launcher and server, an isolated skill inventory, and a
simulated Amp UI transport. Submitted requests must produce an inline portal
embed without a native dialog or notification. In Amp web chat, submit
`/skills` and check that you can search, select, and copy inside the embedded
picker. Opening the standalone page does not verify the chat embedding.

Also open the command palette, search for `picker`, and choose **Skills: Open
picker**. Check that its optional native dialog shows **Open skill picker**,
that the link loads the page, and that **Done** closes the dialog without
sending a message.
