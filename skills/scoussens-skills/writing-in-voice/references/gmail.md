# Gmail

Formatting reference version: **1**

Read the actual composing tool's schema. A connector may accept body text and
an HTML switch; the Gmail API itself accepts a complete MIME message in `raw`,
encoded with **base64url**. Do not encode twice when the connector handles MIME.

For plain text, use `text/plain`. For rich email, use `text/html` with simple
paragraphs, semantic lists, emphasis, and links. When constructing MIME, prefer
`multipart/alternative` with equivalent plain-text and HTML parts, using a MIME
library for headers, character sets, boundaries, and encoding. Markdown in a
plain-text part remains literal text.

For replies, preserve the thread and reply metadata through the tool's reply
operation. Treat the quoted conversation and attachments as separate from the
new authored text. Check the selected sending identity and signature behavior;
do not assume the Gmail web editor's signature appears in an API-created body.
Use only a signature authorized by the profile or current request, once.

For formatting corrections, update an existing draft when supported. A sent
email cannot be reformatted in the recipient's inbox by editing a draft.
Verify the decoded MIME parts and inspect a draft preview when available.

Source: [Gmail API message creation and sending](https://developers.google.com/workspace/gmail/api/guides/sending).
