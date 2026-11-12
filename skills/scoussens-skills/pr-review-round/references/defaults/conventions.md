# Conventions review defaults

Apply to changed code and documentation. Read applicable repository conventions and accepted architectural decisions first; this checklist does not prescribe a language, framework or directory layout.

- Trace ownership and callers. Does the change respect documented module boundaries, or expose internals that callers now depend on?
- Check whether names, types and error behavior express the actual contract. Look for an input where a plausible interpretation gives a different result.
- Check whether new abstractions or dependencies solve a present requirement. Prefer an existing coherent API over a one-use wrapper; do not demand extraction just because two lines resemble each other.
- Check changed public interfaces and documentation against consumers and compatibility commitments. Distinguish intentional contract changes from accidental breaks.
- Treat duplication, long navigation chains, primitive domain values and large modules as investigation leads, not automatic demands for new types, inheritance or layers.

Cite the repository rule or an observed consequence with the affected path. Style preferences and architectural smells without such support are nonblocking advice. Tool-enforced formatting needs the tool's result, not duplicate review comments.
