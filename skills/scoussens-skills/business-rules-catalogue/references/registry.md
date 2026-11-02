# Connect observations to approved policy

The catalogue answers what a pinned code revision does. The registry maintained
by `maintaining-business-rules` answers what a designated owner approved. Preserve
both when they disagree. This integration does not change catalogue extraction,
sampling, independent checking, explorer behavior, or publication permissions.

1. Load `maintaining-business-rules` and resolve its installed directory. If it is
   unavailable, deliver the catalogue and state that registry integration is held.
   Do not copy its schema or invent a substitute approval format.
2. Finish discovery and the independent checking/build workflow on the clean pinned
   source checkout. Keep extraction runs outside that repository. Registry writes
   in the same checkout invalidate the catalogue's source guard; finish guarded
   steps first, or reconcile into a separate working checkout.
3. Read the maintenance skill's registry contract. Match each observation's meaning,
   scope, and deciding evidence against canonical rule revisions. Obtain exact
   targets with its `target` command. Build a complete mapping: matched, ambiguous,
   or unmatched. An observation with no approved counterpart remains unratified;
   it does not establish permission to adopt the behavior.
4. Run its `reconcile --registry ... --catalogue <work>/build/catalogue.json
   --mapping ...` command. Without a mapping it imports every observation unmatched.
   The snapshot hash and commit scope display IDs; additions or file moves can
   renumber them. A replay of the same snapshot/mapping is idempotent.
5. Report the binding ID, matched/ambiguous/unmatched counts, original checker
   counts, and disagreements for business-owner review. Use `auditing-business-rules`
   for conformance or change-impact findings. Publishing the explorer does not
   publish or approve the policy registry.

The adapter retains the original catalogue, including verification counts and
engineering citations. A legacy empty exceptions list means no exceptions were
recorded, not that an owner approved an exhaustive absence of exceptions.
Correct/Wrong/Unsure reviews remain observation feedback. Importing them as policy
decisions requires separate authority and exact-revision evidence through maintenance.
