# Ex6 — Rasa structured half

## Your answer

Ex6 implements a fully deterministic structured half — no LLM. The pipeline is:
raw booking dict → `normalise_booking_payload()` → HTTP POST to Rasa webhook →
parse `{action: committed/rejected}` → `HalfResult`. Four runs were executed
across two tiers on 2026-05-24.

**Run 1 (mock tier, sess_d6835de85b03 — temp dir, not persisted):** Spawned a
stdlib `ThreadingHTTPServer` mock on port 5905. Input `"Haymarket Tap"`, `"25th April 2026"`, `"7:30pm"`, party `"6"`, deposit `"£200"` was normalised to
`haymarket_tap / 2026-04-25 / 19:30 / 6 / 200`. Mock confirmed:
`BK-7D401E9E`, `next_action="complete"`. Stable `sender="homework-185d7d73"`
computed via `sha1("haymarket_tap-2026-04-25-19:30")[:8]`.

**Run 2 (real Rasa, sess_d89df9cda82d):** Same booking against live Rasa CALM.
Confirmed `BK-7D401E9E` — identical reference, proving mock/real rule
equivalence. Real Rasa added a second follow-up message (`"Is there anything else I can help you with?"`) absent from mock; the parser handled it by scanning each
message independently with `m.get("custom") or {}`.

**Run 3 — rejection test (sess_479be406ae56):** Deposit raised to `"£500"` to
exercise the `deposit_too_high` rejection path. Rasa returned `"Sorry, we can't accept this booking. Reason: deposit_too_high"` → `next_action="escalate"`,
exit code 2. Confirmed `ActionValidateBooking`'s £300 threshold works end-to-end.

**Run 4 (sess_034b978e5baf):** Deposit reset to `"£200"`, confirmed again →
`BK-7D401E9E`.

**Bugs fixed:** (1) `canonicalise_venue_id` had a `raise NotImplementedError()`
stub with no `pytest.skip` guard — caused a hard FAIL (not skip) on
`test_canonicalise_venue_id`; implemented the regex normaliser. (2) `urlopen` is
blocking I/O inside an `async def` — wrapped in
`run_in_executor(None, lambda: urlopen(...))` to avoid blocking the event loop.

## Citations

- sessions/examples/ex6-rasa-half/sess_d89df9cda82d/session.json — confirmed run
- sessions/examples/ex6-rasa-half/sess_479be406ae56/session.json — rejection test (deposit=£500)
- sessions/examples/ex6-rasa-half/sess_034b978e5baf/ — final confirmed run
