# Ex7 — Handoff bridge

## Your answer

Ex7 implements `HandoffBridge`, an orchestrator above both halves that drives
loop → structured forward handoffs and structured → loop reverse handoffs across
up to `max_rounds` iterations.

**Run 1 — offline scripted (temp dir):** `FakeLLMClient` scripted 2 rounds:
round 1 hands off `party_size=12` → mock Rasa rejects (`party_too_large`);
round 2 hands off `party_size=6` → confirmed. Validated the bridge loop,
`build_forward_handoff`, and `build_reverse_task` without burning API tokens.

**Run 2 — real LLM, pre-fix (sess_e3349c3c96fc):** Qwen executor searched 4
areas for party=12, found nothing, handed off with `venue_id="N/A"` →
rejected. Round 2 executor (`tk_e0d328d9`, 3 tool calls) adapted to
`party_size=8`, Rasa confirmed. Bridge completed in 2 rounds. **Bug found:**
`logs/handoffs/` was empty — the rejected round-1 handoff was never archived.
Root cause: bridge looked for the file at `session.ipc_input_dir /
"handoff_to_structured.json"` but `write_handoff()` writes to `session.ipc_dir`.
A one-line fix: `session.ipc_dir / "handoff_to_structured.json"`.

**Run 3 — real LLM, post-fix (sess_0f43bfdceb29):** Took 3 rounds due to LLM
non-determinism. Round 1 (tk_98f57f6e, 4 tool calls): executor found Royal Oak
searching `party_size=8` but passed `party_size="12"` to the handoff — confused
search filter with booking request — rejected. Round 2 (tk_977a0749): executor
sent a malformed `action: check_max_party_size` with empty data — rejected again.
Round 3 (tk_3f49cc23): correctly set `party_size="8"` → confirmed. Both rejected
handoffs archived to `logs/handoffs/round_1_forward.json` and
`round_2_forward.json` ✅; only the successful handoff remains in `ipc/`.

**Key learnings:** (1) IPC paths must match exactly between writer and reader —
TODO comments that referenced the wrong path caused the archival bug. (2) LLMs
don't reliably carry "search filter" → "booking request" value transforms; the
executor system prompt must make `party_size` in `handoff_to_structured` explicit.
(3) `max_rounds=3` was sufficient but left no margin for an extra-exploratory LLM.

## Citations

- sessions/examples/ex7-handoff-bridge/sess_e3349c3c96fc/logs/tickets/tk_e0d328d9/raw_output.json
- sessions/examples/ex7-handoff-bridge/sess_e3349c3c96fc/logs/handoffs/ (empty — bug)
- sessions/examples/ex7-handoff-bridge/sess_0f43bfdceb29/logs/handoffs/round_1_forward.json
- sessions/examples/ex7-handoff-bridge/sess_0f43bfdceb29/logs/tickets/tk_3f49cc23/raw_output.json
