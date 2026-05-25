# Ex5 — Edinburgh research loop scenario

## Your answer

**Run 1 (sess_688e708a3b17, tk_fe4084c2):** The task string passed to `half.run()` was
just "research Edinburgh venue and write flyer". The planner produced two vague subgoals
with no location or size details. The executor hallucinated parameters — `near="Old Town"`,
`party_size=50` — and called venue_search three times (Old Town/50, Edinburgh City Centre/30,
Princes Street/20), all returning 0 results. It then triggered `handoff_to_structured` with
reason "Venue search returned no results for multiple parameters." Root cause: SESSION.md is
never read by either the planner or executor; the task string is their only context.

**Run 2 (sess_b297c2d6e06e):** Explicit params added to the task string fixed the planner —
it produced 5 correct subgoals. sg_1 found Haymarket Tap, sg_2 got weather. But sg_3
(calculate_cost) immediately handed off with "Missing required venue_id parameter" because
each executor runs in complete isolation and had no way to access sg_1's result.

**Run 3 (sess_f50e5fd29873):** Introduced `MemoryStore` wrappers and a `recall_research`
tool so subgoals could share data. The memory bridge worked — sg_3 correctly recalled sg_1's
output. But sg_1 itself returned 0 results because the LLM passed `near="Haymarket station"`
and the filter was one-directional: `"haymarket station" in "haymarket"` is False.

**Bug fixed (Run 4, sess_7c6b1bf4a275):** Made the filter bidirectional —
`area in near OR near in area` — so "haymarket" inside "haymarket station" now matches.
All 5 subgoals succeeded, but the flyer had wrong field names (`address` instead of
`venue_address`, `total_cost_gbp` instead of `total_gbp`) because the tool schema
only said `"event_details": {"type": "object"}`, leaving the LLM to invent key names.

**Run 5 (sess_e2aa95b32b28):** Added explicit `generate_flyer` schema with all 9 required
keys. Field names corrected, but `time` came out as `18:00` — it isn't produced by any
tool, so the LLM approximated it from context.

**Run 6 (sess_2b7ec034e300, tk_46facb5b):** Seeded `task_context` (including `time: 19:30`)
into memory before subgoals ran. sg_1 executed the complete pipeline in 5 tool calls —
venue_search → calculate_cost → get_weather → generate_flyer → complete_task. Flyer written
at 1662 bytes with all 9 fields correct. Dataflow integrity verified 4 facts against tool
outputs; zero hallucinations.

## Citations

- sessions/examples/ex5-edinburgh-research/sess_688e708a3b17/logs/tickets/tk_fe4084c2/raw_output.json
- sessions/examples/ex5-edinburgh-research/sess_b297c2d6e06e/logs/tickets/tk_6d2e0dc6/raw_output.json
- sessions/examples/ex5-edinburgh-research/sess_f50e5fd29873/logs/tickets/tk_75054b0d/raw_output.json
- sessions/examples/ex5-edinburgh-research/sess_2b7ec034e300/logs/tickets/tk_46facb5b/raw_output.json
