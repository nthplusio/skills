# Destinations: where the catalogue goes and who sees it

Discover the destinations that work in this session yourself; the user
chooses the destination and the **audience**. A destination used in an earlier
run, a default, or an option a tool offers is not this run's answer.

A run has three things to place:

- the **explorer**: `<work>/site/`, a multi-file static app, and
  `<work>/bundle.html`, the same app as one file;
- the **research note**: Markdown that cites every rule;
- the **saved scope**: `scope.json` and `partition.json`, which let the next
  run skip discovery.

## Usable destinations

List only the destinations you can deliver to from this session. Read each
publishing tool's description for who can see what it publishes, whether it
executes JavaScript, upload limits, and whether its preview and final URL have
different access controls. Verify these facts before offering a host. A wiki
that stores the HTML as text is not an explorer host. DocStash is one option,
not a dependency or a default.

- **Local**, always available. Open `site/index.html` (or `bundle.html`)
  with `open` or `xdg-open` when there is a desktop. In a remote sandbox,
  serve `site/` through the harness's preview or portal mechanism and give
  that link; a sandbox-local URL is not a delivery link. Audience: the user.
- **Hosted static app**: a tool that hosts a multi-file static bundle and
  returns a link, such as DocStash `create_app`. Follow the host's section
  below.
- **Hosted single page**: a tool that publishes one HTML page, such as an
  Artifact tool or a page-creation MCP tool. Deliver `bundle.html` after
  checking the tool's size limit; the bundle runs about 1.5 KB per rule.
- **A static host the user names**, such as GitHub Pages, object storage or
  an intranet site. Copy `site/` there with a command or tool you can run.

## Audiences

- **private**: only the user.
- **shared**: named people or the user's organisation.
- **public**: anyone with the link.

The explorer exposes rule text, internal table, column and file names, and
flagged defects: a map of where the code is weak. Say so when you ask.
Citation links open only for people who can read the repository, so a public
catalogue of a private repository has links that fail for outsiders. Say that
too.

## Ask once, at the step 3 checkpoint

Put up to three questions in the same message as the scope confirmation:

1. The explorer: local preview/file or published delivery; the local output
   location or available publishing provider; private, named/shared, or public
   access. For shared access, resolve the actual recipients or organisation.
   Offer local first as a proposal, not an answer on the user's behalf.
2. The research note: a repository path following the convention survey found
   (`noteDirs`), or the work directory only.
3. The saved scope: `.business-rules/` in the repository, another path, or
   not saved.

Then:

- When the user already named an answer, confirm it instead of asking again.
- Restore confirmed choices when resuming the same run. Saved scope or another
  run's hosting preference is evidence for a proposal, not publication approval.
- "Publish it" settles hosted delivery, but leaves an unnamed provider or
  audience unanswered. Ask only for those remaining choices. "For the product
  team" names reviewers, not permission to make the page public.
- When local is the only destination and the user asked for nothing more, use
  local without asking that question.
- When the destination question goes unanswered, build locally and **hold**
  delivery: record nothing, keep the other steps moving, and say in the
  report that the explorer is waiting on a destination.

Record each answer as it arrives:

```bash
$BR record --work <work> --destination docstash --audience private --note docs/research/business-rules.md --save-scope .business-rules
```

`--destination` accepts any host name. Keep the concrete local path, provider
identifier and shared recipients with the user's confirmation in
`<work>/delivery.md`; `run.json` holds the destination, audience and final URL.
An unresolved choice stays absent. Neither file grants permission by itself.

## Separate permissions

Choosing a destination authorizes delivering the explorer there at the chosen
audience. Each of these needs its own explicit request:

- widening the audience, from private to shared or from shared to public;
- committing, pushing or opening a pull request for the note or the saved
  scope (writing them into the working tree is part of the run);
- announcing the link by chat or email;
- uploading anything besides the explorer.

## Other hosts and local delivery

Copy the chosen output to the confirmed location. For a single-page host, use
`bundle.html`; for a static-file host, retain `site/` paths and upload every
file. Verify the host runs scripts and preserves the rule data, citations,
review controls and download/import behavior. A hash-checked upload alone does
not prove the hosted app works, because a host can strip scripts or sandbox
downloads and browser storage.

Apply only the confirmed audience and record the URL the provider returns.
For public access, load the final URL in a fresh signed-out browser session.
For private/shared access, check the host's access settings and test an
authorised viewer plus an unauthorised session when available. Report any
access check you cannot perform; keep delivery held if the requested access
control cannot be established. An unguessable link alone is not private access.
For local remote-sandbox delivery, use its supported portal and describe the
portal's actual audience and lifetime, rather than calling it private by default.

Reviews stay in browser storage for that origin, not on the host or in a
shared database. Different browsers and private sessions do not share them;
moving the explorer to another origin needs a JSON export/import. Reviewers
and the product architect export their own corrections and send them to
engineering. Import keeps the newer review per rule and can replace a different
reviewer's verdict; retain the original exports for attribution. CSV and
Markdown are handoff formats; only JSON imports. A legacy JSON export without
a project field still requires the matching commit and valid rule IDs.

## DocStash

1. Run `$BR publish-prep --work <work>`. It refuses until a hosted
   destination is recorded, splits the site into upload groups, and proves
   with `node` that every file rebuilds from what helpers will paste.
2. One helper creates the shell from `<work>/publish/UPLOAD.md`, section
   *Create the shell*, named `<title> (<short sha>)`. Record the slug it
   returns.
3. Upload groups sequentially, each using section *Upload a group*, the slug
   and its group number. Calls edit one shared app, so a single writer avoids
   lost updates. Helpers may prepare payloads in parallel, but the coordinator
   owns every `edit_app` call.
4. Paste `<work>/publish/verify.js` into `code_exec` with the slug filled in.
   Done when it prints `allOk: true`.
5. Apply the recorded audience:
   - private: `stash({ slug })` saves it, visible to the owner only.
   - shared: `stash`, then
     `manage_sharing({ slug, action: "add", email, level: "read" })` for each
     person. Each recipient needs a DocStash account.
   - public: `stash`, then
     `manage_sharing({ slug, action: "set-public", isPublic: true })`. The
     link is `https://docstash.ai/<slug>`. Open it in a fresh browser session
     to confirm it loads without signing in.
6. Run `$BR record --work <work> --share-url <link>` so the note cites it.
7. Run the same browser and access checks as other hosts on the final link.
   Inspect the current tool schemas before invoking create, save or sharing
   operations; the snippets describe the intended workflow, not guaranteed
   provider API compatibility.

The draft link (`app.docstash.ai/<slug>`) needs a sign-in. Give each commit
its own document: rule IDs hold for one commit, so a new run never becomes a
new version of a document people are reviewing. The explorer keys stored
reviews by commit and refuses to import reviews from another commit.

## Announcing

Announce only when the user asks, through the messaging tool they name. The
message gives the link and its audience, what the catalogue covers (rule and
flag counts, the top contradictions), and how to review: mark each rule, write
the correction, export, and send the file back to engineering.
