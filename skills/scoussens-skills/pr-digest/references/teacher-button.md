# Making the teacher button copy reliably

Reached from Step 7 while writing the button's click handler. The measured
facts here cost a shipped bug once, so they are worth reading before writing
the copy path rather than after.

**Copying reliably.** Artifacts render in an iframe that does **not** delegate
`clipboard-write`, and this is the one part of the button that has actually
been measured. In that frame `window.isSecureContext` is `true` and
`navigator.clipboard` is present, so a capability check passes — and then
`writeText()` rejects with `NotAllowedError` ("blocked because of a
permissions policy applied to the current document"). Meanwhile
`document.execCommand('copy')` in the same frame, in the same click, returns
`true`.

So **chain the fallback on rejection, never on feature detection.** This is
the failure that shipped once already:

```js
// WRONG — the guard passes in the artifact frame, writeText then rejects,
// and the execCommand path is unreachable dead code.
if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(t);
return execCommandCopy(t);

// RIGHT — outcome decides, not capability.
function copyText(t) {
  return Promise.resolve()
    .then(function () {
      if (!navigator.clipboard) throw new Error('no clipboard api');
      return navigator.clipboard.writeText(t);
    })
    .catch(function () { return execCommandCopy(t); });  // runs on NotAllowedError too
}
```

Because `execCommand` is itself removed-on-paper and can be disabled, treat
even that as fallible and give the reader a real third resort: **render the
prompt into a selectable element** — a collapsed `<details>` per card, or one
shared `<dialog>`/`<pre>` the handler fills in and reveals. Do not tell anyone
to "select the text manually" unless the text is on the page; a prompt that
only exists inside `buildPrompt()` at click time cannot be selected, so that
message is unfollowable advice. Revealing the text *is* the graceful
degradation — the message is just how you point at it.

Say what actually happened in each of the three cases, and never report
"Copied" on a write you didn't confirm.
