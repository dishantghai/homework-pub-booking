# Ex9 — Reflection

## Q1 — Planner handoff decision

### Your answer

In my Ex7 real-mode run (`sess_e3349c3c96fc`), the Round 1 planner
(ticket `tk_7f38f706`) produced two subgoals. The second one explicitly
targets the structured half:

```json
{
  "id": "sg_2",
  "description": "Confirm booking details via structured process for the selected venue",
  "assigned_half": "structured",
  "depends_on": ["sg_1"]
}
```

The signal that drove this decision is in the task string fed to the
planner (trace line 2, `planner.called` event):

> "Book a pub venue for 12 people near Haymarket, Edinburgh. Date:
> 2026-04-25, Time: 19:30. Budget max £2000. Find a venue using
> venue_search, then **handoff_to_structured for booking confirmation**."

The phrase "handoff_to_structured for booking confirmation" is the
trigger. The DefaultPlanner is prompted with descriptions of both
halves — the loop half handles open-ended research, while the
structured half handles deterministic rule-checking. When the task
explicitly names the structured half and frames sg_2 as "confirmation"
(a policy-enforced action), the planner assigns it there.

Independently, the sg_1 executor (`tk_83e5356c`) also called the
`handoff_to_structured` tool directly after exhausting venue_search
(trace line 11). So the handoff happened operationally during sg_1
execution — the planner's architectural assignment of sg_2 was never
reached. Both signals (planner assignment and executor tool call)
converged on the same routing decision, showing the system is
robust even when the executor acts proactively.

The broader lesson: the planner's `assigned_half` is advisory — the
actual handoff is triggered by whichever mechanism fires first
(executor tool call or planner-driven routing). The structured half's
Python rules (`MAX_PARTY_SIZE_FOR_AUTO_BOOKING = 8` in
`rasa_project/actions/actions.py:29`) are the real constraint
enforcement, not the planner's prose interpretation. This run proves
it: party_size 12 was rejected (trace line 13), party_size 8 was
accepted (trace line 21).

### Citation

- `sessions/examples/ex7-handoff-bridge/sess_e3349c3c96fc/logs/tickets/tk_7f38f706/raw_output.json` — planner output with `assigned_half: "structured"` for sg_2
- `sessions/examples/ex7-handoff-bridge/sess_e3349c3c96fc/logs/trace.jsonl` — line 2 (task_preview with "handoff_to_structured"), line 11 (executor calls handoff_to_structured tool), line 12 (state_changed to structured)
- `sessions/examples/ex7-handoff-bridge/sess_e3349c3c96fc/logs/tickets/tk_83e5356c/summary.md` — executor sg_1 handoff confirmation

---

## Q2 — Dataflow integrity catch

### Your answer

In session `sess_1dc800cdf095` (`make ex5-real`, executor: Qwen3-32B),
`verify_dataflow` returned exit code 2 — a failure the flyer's visual
appearance gave no hint of.

**What was planted.** A hard-coded `£299` "Admin & Licensing Fee" was
embedded in the `generate_flyer` HTML template — not in `event_details`,
not returned by any tool. The LLM (ticket `tk_5c4febe4`) called all four
tools correctly: `venue_search` returned Haymarket Tap; `get_weather`
first hallucinated date `2023-10-05` (trace event 5, success=false), then
self-corrected to `2026-04-24` returning rainy/11°C (event 7);
`calculate_cost` returned total=£356, deposit=£71 (event 9); `generate_flyer`
wrote a correct 1,747-byte flyer (event 10).

**Why human review misses it.** The flyer shows £356 and £71 — both
accurate. A reviewer verifies those two numbers, sees they match the
`calculate_cost` summary, and moves on. "Admin & Licensing Fee: £299"
looks like a standard venue charge. Spotting it requires cross-referencing
every `£<N>` in the HTML against `_TOOL_CALL_LOG` — exactly what no human
does at speed.

**What the check did.** `extract_money_facts` pulled `['£356', '£71', '£299']`.
`fact_appears_in_log` confirmed £356 and £71 against `calculate_cost` output.
`299` appeared in no tool output or argument:

```
✗  dataflow FAIL: 1 unverified fact(s): ['£299']
```

**Test case — steps to reproduce.**

*Precondition:* Ex5 tools implemented; valid `NEBIUS_KEY` in `.env`.

1. In `starter/edinburgh_research/tools.py`, `generate_flyer` template,
   add after the `deposit` row (line ~360):
   ```html
   <dt>Admin &amp; Licensing Fee</dt>
   <dd data-testid="admin_fee">£299</dd>
   ```
2. Verify `299` is absent from all fixtures (`hire_fee_gbp=0`,
   `min_spend_gbp=200`, `total_gbp=356`, `deposit_required_gbp=71`).
3. Run `make ex5-real`.
4. **Expected:** `✗  dataflow FAIL: 1 unverified fact(s): ['£299']`, exit 2.
5. Revert step 1. Re-run `make ex5-real`.
6. **Expected:** `✓  dataflow OK: verified 4 fact(s)`, exit 0.

### Citation

- `sessions/examples/ex5-edinburgh-research/sess_1dc800cdf095/logs/trace.jsonl`
  — event 5 (`get_weather` hallucinated date 2023-10-05, success=false),
    event 7 (self-corrected 2026-04-24, rainy 11°C),
    event 9 (calculate_cost: total £356, deposit £71),
    event 10 (generate_flyer: 1,747 bytes written)
- `sessions/examples/ex5-edinburgh-research/sess_1dc800cdf095/workspace/flyer.html`
  — contains `data-testid="admin_fee">£299</dd>` alongside correct £356/£71
- `sessions/examples/ex5-edinburgh-research/sess_1dc800cdf095/logs/tickets/tk_5c4febe4/`
  — executor ticket showing all four tool calls completing successfully

---

## Q3 — First production failure and the primitive that surfaces it

### Your answer

**Failure mode.** Every Ex5 session in this repo has `session.state=executing`
in `session.json` even after all work completed successfully — including
`sess_2b7ec034e300`, where `complete_task` ran twice and the trace records
"session marked complete" both times. A real pub-booking business would build
its booking dashboard on `session.json` state. Every booking request would
appear permanently in-flight: no confirmation sent to the customer, no
table held, retry logic kicking in and re-submitting the same booking. The
failure is silent — `make ex5-real` exits 0, the terminal output says
"complete", but the persisted state says otherwise.

The root cause is that `LoopHalf`'s `complete_task` tool logs the trace
event but does not flush the session state machine to disk. The `HandoffBridge`
in Ex7 calls `session.mark_complete()` explicitly, so Ex7 sessions correctly
show `state=completed` — confirmed across both sessions in
`sessions/examples/ex7-handoff-bridge/`.

**Primitive.** The ticket state machine surfaces this immediately. Each
subgoal writes its outcome to `logs/tickets/<id>/state.json` independently
of the session envelope. In `sess_2b7ec034e300`, all three tickets
(`tk_32991d99` planner.plan, `tk_46facb5b` executor.run_subgoal/sg_1,
`tk_611f2455` executor.run_subgoal/sg_2) show `state=success` while the
session shows `state=executing`. The gap is unambiguous: every unit of work
succeeded; only the final session-level commit is missing. Without the ticket
state machine, `state=executing` is the only signal and you cannot distinguish
"stuck in a tool call" from "completed but not persisted". With it, all-tickets-
success + session-executing = exactly one known bug in the completion path,
not an unknown hang.

### Citation

- `sessions/examples/ex5-edinburgh-research/sess_2b7ec034e300/session.json`
  — `state=executing`, `result=null`, despite `complete_task` in trace
- `sessions/examples/ex5-edinburgh-research/sess_2b7ec034e300/logs/tickets/`
  — `tk_32991d99`, `tk_46facb5b`, `tk_611f2455` all `state=success`
- `sessions/examples/ex7-handoff-bridge/sess_0f43bfdceb29/session.json`
  — `state=completed`: bridge calls `session.mark_complete()` explicitly;
  all 6 tickets also `state=success`
