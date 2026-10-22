# Outlook

Formatting reference version: **1**

For Microsoft Graph's JSON message representation, set `body.contentType` to
`HTML` or `Text` to match `body.content`. HTML in a Text body is not rich email.
Use the connected tool's equivalent fields rather than assuming it exposes the
Graph payload directly.

Graph also supports MIME submission, encoded with **base64**. This differs from
Gmail's base64url `raw` wrapper; do not transplant a Gmail payload. Prefer the
tool's native body interface when it handles serialization.

Use simple HTML paragraphs, semantic lists, emphasis, and links. Avoid depending
on browser-style layouts or complex styling across Outlook clients. Check the
actual client's preview for important formatting. Preserve reply metadata,
quoted content, and attachments through the tool's draft/reply operations.

Confirm whether the composing tool inserts a signature. A signature configured
in an Outlook client is not evidence that an API call supplies it. Follow the
profile or current request without inventing or duplicating a signature.

Edit a draft in place when supported; do not promise to reformat sent email.
Graph `sendMail` returning `202 Accepted` confirms acceptance, not completed
processing or recipient delivery. Describe only what the response proves.

Sources: [Graph sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0),
[Outlook MIME submission](https://learn.microsoft.com/en-us/graph/outlook-send-mime-message).
