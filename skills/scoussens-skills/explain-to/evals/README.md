# Shared-settings evaluation

These files separate three evidence layers:

- `evals.json` and `settings-scenarios.json` define agent scenarios. Definitions
  are not observed behavior or target-product support.
- `test_settings_contract.py` checks fixture structure and static instruction
  guardrails. A matching string does not prove an agent follows it.
- An actual agent run needs a transcript, tool trace, output inspection, and
  the environment record below. No model runner is bundled or implied.

## Run deterministic checks

From the repository root:

```bash
python3 -B -m unittest discover -s skills/scoussens-skills/explain-to/evals -v
python3 -B -m unittest discover -s skills/scoussens-skills/designing-questionnaires/evals -v
npm run validate
```

The questionnaire suite separately exercises the real local HTTP/store/export
path, including manual review without a delivery receipt. Its adapter doubles
do not certify a live harness wake route.

## Run a scenario with a supported agent harness

1. Choose one scenario by `id`. For example, print the tool-free case:

   ```bash
   jq '.scenarios[] | select(.id == "known-chat-no-runtime")' \
     skills/scoussens-skills/explain-to/evals/settings-scenarios.json
   ```

2. Start an isolated evaluation through the harness's supported interface.
   Supply only the listed canonical skills and their owned references; stage
   synthetic fixtures in a disposable directory. Configure the actual tool
   inventory to match `environment`. A sentence telling a tool-rich agent that
   it has no tools is not a tool-free test. Missing-companion cases must exclude
   that companion from discovery and readable resources.
3. Use logged local doubles for publication, messages, and queues. Deny external
   mutations. Supply `prompt` verbatim, keep `expected_output`, `assertions`,
   and `forbidden_actions` for the grader, and retain every turn/tool call.
   For a multi-turn case, give the stated follow-up only after the initial step.
4. Grade each assertion against observed actions and outputs. Inspect local
   database/JSONL snapshots for receipt cases and browser output for page cases.
   Record pass, fail, or inconclusive with a transcript/artifact citation for
   every assertion; an unexercised check is not a pass.
5. Record source commit, scenario ID, model, product/mode, client version,
   effective tool inventory, loaded skills, fixture revisions, observed actions,
   artifact paths, and limitations. Label doubles as doubles. Report actual
   target-product runs separately from instruction-following tests with doubles.

If no supported independent agent runner is available, report these as runnable
definitions and list agent execution as untested. Do not substitute static
assertions, a self-written answer, or a different product for that evidence.
