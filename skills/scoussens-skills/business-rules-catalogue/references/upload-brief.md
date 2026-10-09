# Upload brief: copy the site into DocStash exactly

You are copying prepared files into a DocStash app. They must arrive
byte-for-byte, so you paste prepared text into code and copy it unchanged. A
hash check proves each copy before anything is written.

DocStash is reached through `code_exec` with `import { ... } from "docstash"`.
The `code_exec` runtime has no filesystem, network, `setTimeout` or `crypto`,
so you read each prepared file with your shell tool and paste its contents into
the code you send. Every prepared file is JSON, and JSON is valid JavaScript:
copy every character exactly, including escapes and Unicode. Whitespace between
tokens does not matter, because the code rebuilds the compact form and checks
the hash on that. Read each file in full (use `sed -n` ranges for long output)
and confirm with `wc -l` that you read every line.

The function you need in both sections:

```js
function fnv(s) { let h = 0x811c9dc5; for (const ch of s) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); }
```

If your code throws `hash mismatch`, you mis-copied something. Compare
against the file, find the difference and send the call again. Never change an
expected hash.

## Create the shell

Do this section only when your prompt says to create the shell.

`{WORK}/publish/shell.json` lists `index.html`, `styles.css` and `app.js`.
Each has the path of a `.lines.json` file (a JSON array of the file's lines)
and its expected `fnv`. It also has `placeholders`, which maps every data file
path to a placeholder string such as `/*PENDING d05.js*/`.

Send one `code_exec` call that:

1. builds each file as `lines.join("\n")` from the pasted arrays, and throws
   `hash mismatch` if any `fnv` differs from `shell.json`;
2. calls `create_app` with `name` from your prompt, `entry: "index.html"`,
   `language: "static"` (no `framework`), `description` from your prompt, and
   `files` as a path-to-content map (not a list) holding the three files plus
   every placeholder path with its placeholder string as content;
3. reads the three files back with `read_document({ slug, file })` and checks
   their `fnv`;
4. prints the slug (`unsavedVersion.slug`), `shareUrl` and the three
   read-back results with `text(...)`.

Leave saving and sharing to the coordinator: call no `stash`,
`manage_sharing` or publish tool. Reply with the printed values.

## Upload a group

`{WORK}/publish/plan.json` lists upload groups. Each item in your group has
`file`, `payload` (a path), `prefix`, `suffix`, `placeholder` and `fnv`. Other
workers upload other groups into the same app at the same time, and
concurrent `edit_app` calls on one app can drop each other's edits. The
template re-reads your files after writing and re-applies an edit that was
dropped.

Fill in the template from your group and send it as one `code_exec` call:

```js
import { edit_app, read_document } from "docstash"
function fnv(s) { let h = 0x811c9dc5; for (const ch of s) { h ^= ch.codePointAt(0); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); }
const slug = "SLUG_HERE";
const files = [
  // one object per item in your group:
  { file: "data/dNN.js", placeholder: "/*PENDING dNN.js*/", prefix: "PASTE prefix", suffix: "PASTE suffix", fnv: "PASTE fnv",
    items: /* PASTE the payload JSON here, verbatim */ null },
];
const prepared = files.map((f) => ({ ...f, content: f.prefix + JSON.stringify(f.items) + f.suffix }));
for (const f of prepared) {
  const h = fnv(f.content);
  if (h !== f.fnv) throw new Error(`hash mismatch before upload for ${f.file}: got ${h}, want ${f.fnv}`);
}
const readHash = async (f) => { try { const d = await read_document({ slug, file: f.file }); return { h: fnv(d.content || ""), isPlaceholder: (d.content || "").trim() === f.placeholder }; } catch (e) { return { h: "", err: String(e) }; } };
const log = [];
let attempts = 0;
for (let round = 0; round < 8; round++) {
  const todo = [];
  for (const f of prepared) {
    const r = await readHash(f);
    if (r.h === f.fnv) continue;
    if (r.isPlaceholder) todo.push(f); else log.push(`${f.file}: unexpected content (hash ${r.h}${r.err ? ", " + r.err : ""})`);
  }
  if (!todo.length) {
    // Re-check a few times: a concurrent edit that started before ours can still land after it.
    let stable = true;
    for (let i = 0; i < 6 && stable; i++) for (const f of prepared) if ((await readHash(f)).h !== f.fnv) stable = false;
    if (stable) break; else continue;
  }
  attempts++;
  try { await edit_app({ slug, edits: todo.map((f) => ({ file: f.file, old_string: f.placeholder, new_string: f.content })), description: `Upload ${todo.map((f) => f.file).join(", ")}` }); }
  catch (e) { log.push(`edit error: ${String(e).slice(0, 300)}`); }
  for (let i = 0; i < round + 1; i++) await readHash(prepared[0]); // short back-off
}
const final = [];
for (const f of prepared) final.push({ file: f.file, ok: (await readHash(f)).h === f.fnv });
text({ final, attempts, log });
```

Reply with `final`, `attempts` and `log` for your files. If a file shows
`ok: false` and the log says "unexpected content", stop and report it: that
file holds something other than your placeholder or your content, and only
the coordinator decides what to do with it.
