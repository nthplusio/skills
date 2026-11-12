# Amp integration

Read this only when using Amp. Apply the host-independent feedback workflow; these are mappings to Amp facilities, not different ruling rules.

## Record and overview

- Use `artifact` to find the existing document, read its current revision and comments, and update it with `base_revision`. Keep the document's URL. The owner may have edited it since the last read.
- Publish the generated overview as a `visual` artifact in `visuals`; update the same artifact on later renders. Embed its URL under `Last updated` in the record with `![Overview](<artifact URL>)`. The embed displays the latest published revision.
- A host date chip such as `{{date:2026-11-05}}` is supported for `Last updated`. Keep chips out of tables.
- For additional decision visuals, use the available view-creation skill and embed the result in Context.

## Feedback and messages

- A visual artifact runs in a sandbox without network submission or persistent storage. Its controls may navigate or demonstrate a flow, but cannot save owner feedback. Label demonstrations as simulations. Use `button` elements for internal navigation; fragment links can navigate an embedded frame away from the view.
- For a record using document comments, put the exact manual route in **Where things stand**, for example “Comment on this decision, then ask the editor in its linked thread to review the comment.” Read comments with `artifact`; after review, reply to the source comment and update the record. Do not resolve the comment unless asked.
- An owner can also respond directly in the editor's thread. Use the authenticated sender information, not a name typed into a prototype. If feedback is relayed by another agent, verify the original owner message before treating it as authorization.
- Use `send_thread_message` for worker/research reports and lane notifications when available. Include the actual editor thread ID in a brief and request a reply when the result is needed. For a subagent whose final result returns to the editor, that result is the report; do not require a thread messaging tool it does not have.
- A document comment alone does not establish automatic editor wake-up. Use manual review unless an available event or connected-page integration passes the generic save/read-back/delivery/receipt check. A portal's feedback widget is a separate input route; verify its behavior and respondent identity before treating it as owner approval. Do not assume the widget exists on artifacts.

Keep Amp IDs, artifact URLs, comment IDs and delivery details in the project's setup and receipts. The record format, feedback meanings and ruling lifecycle stay the same on other hosts. A request to use this skill does not itself authorize deploying a connected page or installing a webhook.
