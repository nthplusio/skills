# Slack

Formatting reference version: **1**

Determine whether the tool accepts `mrkdwn`, `plain_text`, or structured blocks.
Slack `mrkdwn` is not standard Markdown and is not HTML:

- Bold is `*text*`, not Markdown's double asterisks.
- Italic is `_text_`; inline code uses backticks.
- Links use `<https://example.com|label>` or a bare URL.
- Paragraphs use line breaks. In `mrkdwn`, lists are text lines beginning with
  bullets or numbers, not HTML list elements. Native rich-text lists require a
  different structured representation and tool support.

Escape literal `&`, `<`, and `>` as `&amp;`, `&lt;`, and `&gt;` in `mrkdwn`
text, while preserving intentional Slack link syntax. Do not HTML-encode the
entire body. Treat mention tokens and automatic mention parsing as notification
behavior, not decoration; do not introduce them during a formatting repair.

Synthetic `mrkdwn` body:

```text
The review has *two steps*.
1. Check `release_id`.
2. Confirm the date.
```

For blocks, use the field's declared text type. Include a meaningful plain-text
fallback for accessibility and notifications when the tool supports it. Keep
fallback wording consistent with the visible content.

For an authorized edit, preserve the channel, message timestamp/identifier, and
thread context. Check how the update tool treats existing blocks and attachments
before replacing text. Read back the same message and inspect its rendering
when available; no repost fallback on an edit failure.

Source: [Slack text formatting](https://docs.slack.dev/messaging/formatting-message-text).
