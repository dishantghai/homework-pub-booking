"""Ex7 — reference solution runner. Scripts a two-round round-trip:
round 1: loop picks haymarket_tap (8 seats), structured rejects (party=12 > cap=8)
round 2: loop picks royal_oak (16 seats), structured accepts."""

from __future__ import annotations

import asyncio
import json
import sys

from sovereign_agent._internal.llm_client import (
    FakeLLMClient,
    OpenAICompatibleClient,
    ScriptedResponse,
    ToolCall,
)
from sovereign_agent._internal.paths import example_sessions_dir
from sovereign_agent.config import Config
from sovereign_agent.executor import DefaultExecutor
from sovereign_agent.halves.loop import LoopHalf
from sovereign_agent.planner import DefaultPlanner
from sovereign_agent.session.directory import create_session

from starter.edinburgh_research.tools import build_tool_registry
from starter.handoff_bridge.bridge import HandoffBridge
from starter.handoff_bridge.integrity import verify_dataflow
from starter.rasa_half.structured_half import RasaStructuredHalf, spawn_mock_rasa


def _build_fake_client_two_rounds() -> FakeLLMClient:
    """Round 1: plan → venue_search → handoff_to_structured (haymarket_tap)
    Round 2: plan → venue_search → handoff_to_structured (royal_oak)"""
    plan_r1 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "find venue near haymarket for 12",
                "success_criterion": "candidate identified",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )
    # round 2 — loop gets rejection reason, retries with different area
    plan_r2 = json.dumps(
        [
            {
                "id": "sg_1",
                "description": "retry with larger venue after rejection",
                "success_criterion": "different venue with enough seats",
                "estimated_tool_calls": 2,
                "depends_on": [],
                "assigned_half": "loop",
            }
        ]
    )

    return FakeLLMClient(
        [
            # === ROUND 1 ===
            ScriptedResponse(content=plan_r1),  # planner turn 1
            ScriptedResponse(  # executor turn 1: search
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="venue_search",
                        arguments={"near": "Haymarket", "party_size": 12, "budget_max_gbp": 2000},
                    )
                ]
            ),
            ScriptedResponse(  # executor turn 2: handoff
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "loop half identified a candidate venue; passing to structured half for confirmation under policy rules",
                            "context": "party of 12 near Haymarket on 2026-04-25 19:30; chosen venue haymarket_tap",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "Haymarket Tap",
                                "date": "2026-04-25",
                                "time": "19:30",
                                "party_size": "12",
                                "deposit": "£0",
                            },
                        },
                    )
                ]
            ),
            # === ROUND 2 (after reverse handoff from structured rejecting party=12) ===
            ScriptedResponse(content=plan_r2),  # planner turn 2
            ScriptedResponse(  # executor turn 1: new search with smaller party
                tool_calls=[
                    ToolCall(
                        id="c3",
                        name="venue_search",
                        arguments={"near": "Old Town", "party_size": 6, "budget_max_gbp": 2000},
                    )
                ]
            ),
            ScriptedResponse(  # executor turn 2: handoff royal_oak with party=6
                tool_calls=[
                    ToolCall(
                        id="c4",
                        name="handoff_to_structured",
                        arguments={
                            "reason": "retry after reverse handoff — scaled down to fit policy",
                            "context": "party was originally 12; rejected; re-proposing party of 6 at royal_oak (16 seats)",
                            "data": {
                                "action": "confirm_booking",
                                "venue_id": "The Royal Oak",
                                "date": "2026-04-25",
                                "time": "19:30",
                                "party_size": "6",
                                "deposit": "£0",
                            },
                        },
                    )
                ]
            ),
        ]
    )


_EX7_EXECUTOR_SYSTEM = (
    "You are the EXECUTOR of a pub-booking agent. You have access to tools for\n"
    "researching Edinburgh venues. Your job:\n\n"
    "1. Use venue_search to find a suitable venue for the party.\n"
    "2. Once you have a candidate, call handoff_to_structured to pass the\n"
    "   booking to the structured half for policy validation and confirmation.\n\n"
    "The handoff_to_structured 'data' dict MUST include:\n"
    "  - action: 'confirm_booking'\n"
    "  - venue_id: the venue name\n"
    "  - date: YYYY-MM-DD\n"
    "  - time: HH:MM\n"
    "  - party_size: string of the number\n"
    "  - deposit: e.g. '£0'\n\n"
    "If you receive a rejection from a previous round (in the task context),\n"
    "adapt your search: try a different venue, reduce party size, etc.\n\n"
    "Do NOT call complete_task — the structured half handles completion.\n"
    "Do NOT call generate_flyer or get_weather — this is a booking scenario only."
)


async def run_scenario(real: bool) -> int:
    with example_sessions_dir("ex7-handoff-bridge", persist=real) as sessions_root:
        session = create_session(
            scenario="ex7-handoff-bridge",
            task="Book a venue for 12 people in Haymarket, Friday 19:30.",
            sessions_dir=sessions_root,
        )
        print(f"Session {session.session_id}")
        print(f"  dir: {session.directory}")

        # Always use mock Rasa for structured half (no RASA_PRO_LICENSE needed)
        server, _thread, mock_url = spawn_mock_rasa(port=5906)
        rasa_half = RasaStructuredHalf(rasa_url=mock_url)

        tools = build_tool_registry(session)

        if real:
            cfg = Config.from_env()
            print(f"  LLM: {cfg.llm_base_url} (live)")
            print(f"  planner:  {cfg.llm_planner_model}")
            print(f"  executor: {cfg.llm_executor_model}")
            client = OpenAICompatibleClient(
                base_url=cfg.llm_base_url,
                api_key_env=cfg.llm_api_key_env,
            )
            planner_model = cfg.llm_planner_model
            executor_model = cfg.llm_executor_model
        else:
            print("  LLM: FakeLLMClient (offline, scripted)")
            client = _build_fake_client_two_rounds()
            planner_model = executor_model = "fake"

        loop_half = LoopHalf(
            planner=DefaultPlanner(model=planner_model, client=client),
            executor=DefaultExecutor(
                model=executor_model,
                client=client,
                tools=tools,
                system_prompt=_EX7_EXECUTOR_SYSTEM if real else None,
            ),  # type: ignore[arg-type]
        )
        bridge = HandoffBridge(
            loop_half=loop_half,
            structured_half=rasa_half,
            max_rounds=3,
        )

        try:
            result = await bridge.run(
                session,
                {
                    "task": (
                        "Book a pub venue for 12 people near Haymarket, Edinburgh. "
                        "Date: 2026-04-25, Time: 19:30. Budget max £2000. "
                        "Find a venue using venue_search, then handoff_to_structured "
                        "for booking confirmation."
                    )
                },
            )
        finally:
            server.shutdown()

        print(f"\nBridge outcome: {result.outcome}")
        print(f"  rounds: {result.rounds}")
        print(f"  summary: {result.summary}")

        print("\n=== Dataflow integrity check ===")
        ok, summary = verify_dataflow(session)
        if ok:
            print(f"\u2713  {summary}")
        else:
            print(f"\u2717  {summary}")
            return 2

        if real:
            print(f"\nArtifacts persist at: {session.directory}")

        return 0 if result.outcome == "completed" else 1


def main() -> None:
    real = "--real" in sys.argv
    sys.exit(asyncio.run(run_scenario(real=real)))


if __name__ == "__main__":
    main()
