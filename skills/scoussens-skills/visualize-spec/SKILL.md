---
name: visualize-spec
description: Turn a spec into a throwaway HTML page — problem, outcome, workflow, pieces and seams, data layer, file layout, tests, and validation plan — themed to the repository and opened locally or published wherever the agent can, so a developer can check it delivers what they want.
disable-model-invocation: true
---

# Visualize spec

Build one HTML page that shows a spec to the developer who asked for it, so they can decide in a few minutes whether the spec delivers what they want.

The page is a **mirror**. It shows what the spec says, in plain words and pictures, and only that. Where the spec is silent, the page shows a **gap**: a marked box that names what is missing. A gap is often the most useful thing on the page, because it is a decision the developer has to make before anyone builds. A plausible guess in its place hides that decision.

The page is a throwaway. It is built in the temp folder and rebuilt whenever the spec changes. Publishing it gives it a link, not a longer life.

## Step 1 — Get the whole spec

Take the spec from wherever the user points:

- **A file path.** Read it.
- **An issue URL or ID.** Fetch it with the tracker's own tool (`gh issue view <n> --comments`, or the Linear MCP's `get_issue`). Include comments and sub-issues that amend it.
- **Pasted text, or "the spec we just wrote".** Use the text in the conversation.

If you cannot tell which spec is meant, ask.

**Done when** you hold the full text of one spec and can name where it came from.

## Step 2 — Choose where the page goes

List the destinations you can deliver to in this session:

- **Local file.** Always available. You can open it in a browser only when there is a desktop: macOS, or Linux with `$DISPLAY` or `$WAYLAND_DISPLAY` set. Over SSH or in a container, the user gets the path instead.
- **Hosted page.** Each tool in your tool list that publishes an HTML page and returns a link, such as an `Artifact` tool or an MCP server's page-creation tool. Read each tool's description for who can see what it publishes. A tool that stores documents as text, such as a docs or wiki connector, does not count, because it drops the styles and the diagrams.

Then settle one destination:

- The user already said where, for example "just open it" or "publish it": use that.
- Only the local file is available: use it, without asking.
- Otherwise, ask once, and offer only the destinations you found. Put the local file first as the default. Give each option one line that says who will be able to see the page. Publishing shows the repository's paths and gaps to everyone who can see the page, so the user decides this, not you. If step 1 also needs a question, ask both together.

**Done when** you hold one destination, chosen by the user or left as the only one available.

## Step 3 — Find the code the spec touches

Specs often name modules but not files. A spec written by `to-spec` leaves paths out on purpose. So the current file layout comes from the repository, never from the spec. For each module, command, and test the spec names, find its real path and read enough to know what it does today. Also find where this area's tests live and the command that runs them (the scripts in `package.json`, `pyproject.toml`, `Makefile`, or the CI workflow). Then find where its data is defined: a schema file (such as `schema.prisma` or SQL migrations), the ORM models, or the types and in-memory stores that hold the records. The data layer is wherever the records live, whether a database, a file, or a dictionary in memory.

Settle each fact about the repository by running something, such as a parser, the test command, or a count, rather than by reading grep output by eye. A wrong fact on the page does more damage than a missing one, because the developer trusts the page.

If there is no repository to read, continue. The file-layout section then shows a gap.

**Done when** every module and every kind of stored record the spec names is one of these:

- mapped to a real path
- marked **new**, because the spec says to create it
- marked **not found**, because the spec assumes it exists and the repository does not have it. That is a gap.

## Step 4 — Find the theme

Look for a theme or style guide in the repository you are working in. Stop at the first source that gives real colour values:

1. The repository's agent instructions (`AGENTS.md`, `CLAUDE.md`, or a `docs/` standards folder), which often name the package that owns styling or link a style guide.
2. A tokens file or a CSS theme. Prefer a shared package (`packages/ui/`, `libs/design-system/`, `src/theme/`) over one app's stylesheet.

   ```bash
   rg -l -g '!node_modules' -g '!dist' -g '*.{css,scss,sass,less}' '@theme|--color-|:root\s*\{'
   rg -l -g '!node_modules' 'tailwind\.config|createTheme|extendTheme' .
   ```

3. A written style guide or brand sheet under `docs/`, such as a file named `style-guide`, `brand`, or `design-system`. A table of hex values counts.

When you find one, read [`references/theming.md`](references/theming.md). It says which tokens the theme may replace and how to map them. When you find none, the page uses the template's default theme unchanged. Colours you would have to guess from screenshots or a website do not count as a theme.

**Done when** you can name the theme's source file, or you know that the page uses the default theme.

## Step 5 — Sort the spec into eight sections

Draft each section as notes before writing any HTML. For every item, know its source: the spec, the code, or your own inference. Items you inferred are tagged **inferred** on the page, and that includes diagram boxes and steps, which take the `inferred` class. Items with no source are gaps.

When the spec gives a section nothing, the section opens with a gap. Anything you add there, such as a test plan or validation steps the spec never gave, goes inside that gap as a labelled suggestion. That way a reader who skims only that section still knows it is your idea, not the spec's.

1. **The problem.** Who is hurting today, and how. Use two or three sentences with one concrete example: a command someone runs, and what goes wrong.
2. **The outcome.** What is true once the work ships, as three to six statements a person could check, for example "Running `npm run validate` on a skill with no trigger phrase prints a warning". Condense the user stories into these statements. Add a short "Not in this change" list if the spec has an out-of-scope section.
3. **The workflow.** The path through the system after the change: who starts it, each step, and where it ends. Draw it as a `.flow`: one node per step, a `.fork` where it branches, and a `.via` label on an arrow when what passes along it matters. Colour new and changed steps, and mark an undecided step `open`.
4. **The pieces and their seams.** Draw a `.stack`: one node per module the change touches, callers in the row above the pieces they call, and a seam line between the rows. Label each seam with its name and what crosses it: a function call, a file, or an HTTP request. A **seam** is a place where two pieces meet, and where a test can swap one side for a fake. Mark each seam new, changed, or unchanged. Under the diagram, give each seam one line: what crosses it, and why it is there.
5. **The data layer.** What the change stores, before and after. An **entity** is a kind of stored record, such as an order. Two panes of `.erd` cards side by side: **Today** comes from the definitions found in step 3, and **After this change** applies the spec to them. Show the entities the change touches, plus any entity one relationship away. Give each entity its properties, each with a type in plain words (text, whole number, date and time, yes or no) and whether it is required. Under each pane, write each relationship as a plain sentence: "one Order has many Deliveries". In the After pane, mark each entity, property, and relationship new, changed, or removed, and tag the ones you chose as inferred. Say "links to Customer" rather than "foreign key", and "optional" rather than "nullable". Then, for each new required property, changed type, or removed entity, say in one line what happens to the records already stored. Where the spec does not say, that is a gap. When the change stores nothing new and changes nothing stored, replace the panes with one `<p class="no-data">` line that says so.
6. **File layout.** Two trees side by side. **Today** shows the real paths from step 3. **After this change** shows the proposed layout. Show only the affected folders, plus one level of context around them. Mark each entry new, changed, or removed. Tag as inferred any path the spec does not name and you chose.
7. **Tests and where they plug in.** Show where the tests live as a tree, today and after. Add a `.stack` for each seam a test enters through: the test beside the real caller above the seam, and any fake it swaps in beside the real piece below it. Give each test file one line: what it proves. This section comes from the spec's testing decisions.
8. **How to check it worked.** Ordered steps the developer follows to confirm the outcome. Each step is a command to run and what they should see, and it names the outcomes it checks. End with the project's standard check, the command CI runs, when there is one. This section comes from the spec's acceptance criteria or validation plan.

Sections 7 and 8 each mark their list `data-source="spec"` or `data-source="suggested"`. Decide this against the spec's text, not against how natural your steps look. A spec with outcomes but no stated checks gives section 8 nothing, so its steps are suggested and sit inside a gap that says so.

Then **play the spec forward**. Take the concrete case in its problem statement, such as the incident, the failing command, or the example, and trace it through the proposed change. If the change would not fix that case, that is the most important gap on the page. Do the same for any number the spec states, like a time window or a limit: recompute it from the spec's own inputs, and show the working in one line.

Last, collect every gap into the **Decide before building** list at the top of the page, ranked. Up to three **major** gaps come first: the ones that decide whether the spec meets its goal, such as a contradiction, an unmet promise, or a case the spec fails to fix. Every other gap goes under **smaller points**. Give each a single line, linked to its section.

**Done when** all eight sections have content or a gap, and every outcome in section 2 is checked by at least one step in section 8. An outcome that no step can check gets a gap that says so.

## Step 6 — Write the page

**Voice.** If `speak-clearly` is in your available skills, load it now and apply it to every sentence on the page. If it is not, write as you would explain the spec to a junior developer in their first week: short sentences, one idea each, and name who or what acts.

Either way, use plain words. That applies to everything on the page a person reads, including diagram labels, tree notes, and table cells. The repository's own vocabulary counts too: a word that is everyday inside the project, such as "frontmatter" or "model-invoked", is still jargon to the reader. Keep a technical term only when the developer needs it to match the page back to the spec. Define it in a few plain words before its first diagram, or in the same sentence where it first appears. For example: "jitter, a small random wait so retries do not all fire at once." Spell out every abbreviation: "p99" becomes "the slowest 1 in 100 requests". Replace every other term with the plain words it stands for.

**Length.** The developer should be able to read the whole page in five minutes. Each list item is one line. Keep diagrams to about twelve boxes. Keep the words outside diagrams, trees, entity cards, and headings under 900, the "Decide before building" list included. The checker counts them, and every gap stays; cut words, never gaps.

**Build.** Copy `assets/page-template.html` from this skill's folder to `${TMPDIR:-/tmp}/visualize-spec/<spec-slug>.html`, then replace every `{{…}}` marker. The template's header comment lists the class names, the traceability attributes (`data-outcome`, `data-checks`, `data-gap-for`), and the diagram kit: `.flow`, `.stack`, and `.erd`, built from plain HTML so the browser lays them out, with no library and no network. Use them, so every page reads the same way and the checker can trace outcomes to steps. Then apply the theme from step 4 to the template's `THEME` block.

When the destination is a hosted page, follow that tool's own authoring rules, and load any skill its description names before writing (the `Artifact` tool names `artifact-design`). Keep the template's sections, classes, and diagram kit, because the checker still runs on the page.

## Step 7 — Check it, then deliver it

```bash
python3 <this skill's folder>/scripts/check_page.py <page>
```

Fix each `FAIL` line and rerun until the checker exits 0. Then deliver the checked file to the destination from step 2:

- **Local file:** open it with `open` on macOS or `xdg-open` on Linux. Without a desktop, give the path only.
- **Hosted page:** publish the file with the tool. When the spec changes, republish to the same link rather than creating a new one.

Your reply gives the page's path, and the link with who can see it when you published it. Next is one line naming the theme's source file, or saying the page uses the default theme. Last come the gaps, one line each. The gaps are what the developer has to act on, and the page carries everything else.
