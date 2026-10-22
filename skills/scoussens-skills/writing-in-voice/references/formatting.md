# Formatting and delivery

Formatting reference version: **1**

Voice determines wording. Audience and purpose select the applicable voice
rules. The destination and the actual tool determine the representation. A
profile preference can select among supported formats; it cannot make an
unsupported format work.

## Before delivery

Inspect the connected tool's schema or the destination editor's capabilities.
Distinguish a plain-text field, HTML body, Markdown, Slack `mrkdwn`, and a native
rich-text document. Do not paste markup into an editor expecting rendered text.
If no delivery tool is available, return a draft, not a claim that it was sent.

Use semantic paragraphs and lists where supported, selective emphasis, and
code styling for actual technical identifiers. Keep formatting proportional to
the message. Escape text for the chosen representation instead of interpreting
user-supplied angle brackets or identifiers as markup or mentions. Keep link
targets intact and avoid introducing notifications while formatting.

## Formatting-only corrections

1. Read the existing draft or message and retain its identifier, wording, link
   targets, and any mentions or attachments that must survive the update.
2. Change representation only. Compare the decoded visible text with the
   original; ignore only presentation whitespace and generated list markers,
   not punctuation, numbers within the prose, or technical tokens.
3. When authorized and supported, update that same object. Do not send a new
   message as a fallback if editing fails or is unavailable. Explain the limit
   and offer a corrected draft instead. Sent email is not an editable draft.
4. Read back the updated object. Confirm its identifier, content type, words,
   and retained links/attachments. Inspect the client rendering when accessible;
   a successful API call alone does not prove appearance or delivery.

After an uncertain tool response, read the original object's state before any
retry. If readback is unavailable, report the verification limit rather than
claiming success or sending a duplicate.

## Improving these references

Keep platform syntax, capability limits, and synthetic examples here. Keep
individual preferences in profiles. Verify platform changes against official
documentation and the tool in use; update the affected reference and its version
when behavior changes. Do not copy real messages or personal correction logs
into the shared package. Saved evaluation scenarios live in
[evals.json](../evals/evals.json); they specify behavior, not proof of a live run.
