# Acceptance procedure

Run the local tests, then exercise the **actual selected adapter**. A fake
receiver tests the delivery contract, not a harness's ability to wake an agent.
Use disposable generic data, not copied customer feedback.

1. Publish the example and open the served page in the installed browser. Expect
   three open, zero completed. Filter High + Alex: only “Which export format?”
   remains. High + Anyone gives an explicit empty state. Reset and follow a
   question link; it opens the targeted question. Open that link in a fresh tab.
   Expand the saved setup and verify the outcome, reader roles, response budget,
   and review policy. Open a question and check its recommendation, consequence,
   and response format without needing the agent conversation.
2. Submit “CSV is sufficient for the monthly comparison. Which encoding will
   preserve accented names?” to the format question. Observe exact text in
   storage and visible pending delivery/review. Inspect the actual reviewer
   message and its matching delivery receipt. A log from the server is not
   enough. Replay the same UUID and body; expect one stored response and one
   review effect. Replay different text under that UUID; expect rejection.
3. While notification is unavailable, submit another disposable response.
   Confirm it remains saved and pending. Restore the route and retry the same
   ID. Verify recovery after restarting the local host, and distinguish this
   from a cold/suspended harness resume test. Do not interrupt shared services.
4. Leave an unsent draft under a different question. The reviewing agent reads
   the format response, changes the requirement to CSV, publishes its answer
   with a source-feedback link, and adds a named encoding follow-up. The same
   publication includes the response's review receipt. The page offers an
   update without replacing the draft. Load it; the draft and deep links remain.
   Expect three open, one completed. Confirm original feedback unchanged.
   Remove attention from the answered question and give the follow-up a
   clarification state and a named next action. Verify saved setup unchanged,
   the last review time visible, and pending-review counts cleared by the
   receipt rather than delivery. Follow the latest interpretation to its source.
5. Filter Completed; inspect the answer and follow its source link. Filter the
   suggested respondent and priority together. Inspect the new follow-up.
   Submit to the new question without restarting the server. Repeating review
   must not create another follow-up or overwrite the original receipt.
   Submit a challenge to the answered question. It stays Completed while its
   response appears awaiting review. In a disposable revision, publish an open
   conflict with both claims' evidence links and a named decision maker. Confirm
   filters also scope the attention counts and next actions. Verify polling
   preserves focus on an unchanged navigation link and any open disclosure.
6. Inspect at desktop and 390 CSS pixels wide. Check no horizontal overflow,
   readable labels, keyboard focus, toggles, open form, empty result, pending
   feedback and completed answer. Capture and inspect representative states;
   record pointer/keyboard interactions if supported. Name the tested engine.
7. If tab storage is blocked, verify the update control refuses a destructive
   reload and asks the reader to copy drafts. A denied save must leave text
   editable. Treat browser/offline limitations as such, not as saved feedback.

Record the actual commands/results and screenshots in the consuming project.
Report lifecycle tests not run (suspension, archival, gateway authentication,
multiple writers, other browsers/harnesses). Stop short of claiming an automatic
loop if no reviewer received and interpreted the saved feedback.
