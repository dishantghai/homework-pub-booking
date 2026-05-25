# Ex8 — Voice pipeline

## Your answer

Ex8 implements a turn-based voice pipeline: mic → Speechmatics STT → Llama-3.3-70B
`ManagerPersona` (Alasdair MacLeod character) → Rime.ai TTS → speakers. Both text
and voice modes emit identical `voice.utterance_in` / `voice.utterance_out` trace
events so the grader never depends on audio hardware.

**Text Run 1 (sess_d2a6c87654fd):** 3-turn booking confirmed. Party=6, deposit=£200
— manager accepted both constraints. Trace has 6 events with correct actor/mode
fields. Verified grader requirements (≥3 turns, both event types present).

**Text Run 2 (sess_55f8aee708b5):** 3-turn rejection scenario. Party=10 → manager
replied "Sorry, too many folk... try The Royal Oak or Bennet's Bar" — rule enforcement
(party > 8) working correctly through persona system prompt.

**Voice Run (sess_276b7d7faef6):** Full STT+TTS end-to-end. 4 turns, 8 trace events,
all `mode="voice"`. Turn 0: STT transcribed "Hi, Alastair... birthday party of six on
June 25th" → manager confirmed. Turn 2: booking confirmed. Trace written to
`sessions/homework/ex8/sess_276b7d7faef6/logs/trace.jsonl`.

**Bugs found and fixed:**
1. **Immediate silence on voice start (sess_24c0fee6da60):** Grace period was 3000ms —
   too short for the user to begin speaking after the prompt appeared. Fixed by
   increasing to 8000ms: `if not speech_started and total_ms >= 8000: return b""`.
2. **`pkg_resources` ImportError (sess_f45866ad6588):** `uv sync --extra voice` removed
   `setuptools` (not declared in `pyproject.toml`), causing `speechmatics` to fail at
   import with `pkg_resources` missing. Fix: `uv add setuptools` to persist it in the
   lockfile. `uv run` is hermetic — `pip install` alone is not enough.
3. **`_speak_rime` TODO:** Implemented 4-line async HTTP POST using `httpx.AsyncClient`
   — native async chosen over `urllib` + `run_in_executor` because TTS is on the hot
   path (called every turn, user is actively waiting).

**Key learning:** Graceful degradation through four tiers (no key → no deps → no TTS →
full voice) means every path still produces valid trace events — CI passes on text mode
alone while voice mode earns the +4pt bonus.

## Citations

- sessions/homework/ex8/sess_276b7d7faef6/logs/trace.jsonl — voice mode trace (8 events)
- sessions/homework/ex8/sess_24c0fee6da60/ — immediate-silence failure (grace bug)
- sessions/homework/ex8/sess_f45866ad6588/ — pkg_resources import failure
- sessions/homework/ex8/sess_d2a6c87654fd/ — text run 1 (confirmed)
- sessions/homework/ex8/sess_55f8aee708b5/ — text run 2 (rejected, party=10)
