# Microsoft Teams

Formatting reference version: **1**

For Graph-style message bodies, select `contentType: "html"` explicitly when
using HTML. Some connectors default to text and expose this as `content_type`;
inspect the schema rather than guessing the field name.

Use `<p>` for paragraphs, `<ol><li>` or `<ul><li>` for actual lists, `<strong>`
for selective emphasis, `<code>` for inline identifiers, and `<a href="…">`
for links. Verify the rendering in the available client. Teams supports a
restricted HTML surface: browser HTML, `<div>` layouts, and inline styles are
not reliable substitutes. A native multi-line code block is a separate feature;
consult the tool's support rather than assuming Markdown fences work in HTML.

Synthetic body, not a saved voice sample:

```html
<p>The review has <strong>two steps</strong>.</p>
<ol><li>Check <code>release_id</code>.</li><li>Confirm the date.</li></ol>
```

Mentions require identity metadata, not just a displayed name. Preserve existing
mention and attachment references when updating; do not create new notifications
as a side effect of formatting.

For an authorized correction, read the original message, update using the same
conversation and message IDs, and read it back to confirm HTML and unchanged
words. Update availability depends on the tool, permissions, and message author.
A failed or unavailable update is not permission to post another message.

Sources: [Teams messaging body model](https://learn.microsoft.com/en-us/graph/teams-messaging-overview),
[Graph message formatting restrictions and examples](https://learn.microsoft.com/en-us/graph/api/chatmessage-post?view=graph-rest-1.0).
