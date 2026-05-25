"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations

from pathlib import Path

from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import ToolRegistry, ToolResult, _RegisteredTool

_SAMPLE_DATA = Path(__file__).parent / "sample_data"


# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp

    Returns a ToolResult with:
      output: {"near": ..., "party_size": ..., "results": [<venue dicts>], "count": int}
      summary: "venue_search(<near>, party=<N>): <count> result(s)"

    MUST call record_tool_call(...) before returning so the integrity
    check can see what data was produced.
    """
    # TODO 1a: load venues.json. Raise ToolError(SA_TOOL_DEPENDENCY_MISSING)
    #          if the file is absent.
    import json

    from starter.edinburgh_research.integrity import _TOOL_CALL_LOG, record_tool_call

    # Spiral guard: count previous venue_search calls and surface prior results
    prior_calls = [r for r in _TOOL_CALL_LOG if r.tool_name == "venue_search"]
    if len(prior_calls) >= 3:
        # Scan prior calls for venues already found
        found_venues = []
        for r in prior_calls:
            if isinstance(r.output, dict) and r.output.get("count", 0) > 0:
                for v in r.output.get("results", []):
                    name = v.get("name", v.get("id", "unknown"))
                    vid = v.get("id", "")
                    found_venues.append(f"{name} (id={vid})")
        venue_msg = f" Already found: {', '.join(found_venues)}." if found_venues else ""
        # Pass the last successful output so the LLM has usable data
        last_good = next(
            (
                r.output
                for r in reversed(prior_calls)
                if isinstance(r.output, dict) and r.output.get("count", 0) > 0
            ),
            {"error": "too_many_searches", "count": len(prior_calls)},
        )
        record_tool_call("venue_search", {"near": near, "party_size": party_size}, last_good)
        return ToolResult(
            success=bool(found_venues),
            output=last_good,
            summary=f"STOP calling venue_search.{venue_msg} Use these results.",
        )

    venues_path = _SAMPLE_DATA / "venues.json"
    if not venues_path.exists():
        return ToolResult(
            success=False,
            output={"error": "SA_TOOL_DEPENDENCY_MISSING", "path": str(venues_path)},
            summary="venues.json not found",
        )

    venues = json.loads(venues_path.read_text(encoding="utf-8"))

    results = [
        v
        for v in venues
        if v.get("open_now") is True
        and (near.lower() in v.get("area", "").lower() or v.get("area", "").lower() in near.lower())
        and v.get("seats_available_evening", 0) >= party_size
        and (v.get("hire_fee_gbp", 0) + v.get("min_spend_gbp", 0)) <= budget_max_gbp
    ]

    args = {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp}
    output = {"near": near, "party_size": party_size, "results": results, "count": len(results)}
    record_tool_call("venue_search", args, output)

    return ToolResult(
        success=True,
        output=output,
        summary=f"venue_search({near!r}, party={party_size}): {len(results)} result(s)",
    )


# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD).

    Reads sample_data/weather.json. Returns:
      output: {"city": str, "date": str, "condition": str, "temperature_c": int, ...}
      summary: "get_weather(<city>, <date>): <condition>, <temp>C"

    If the city or date is not in the fixture, return success=False with
    a clear ToolError (SA_TOOL_INVALID_INPUT). Do NOT raise.

    MUST call record_tool_call(...) before returning.
    """
    import json

    from starter.edinburgh_research.integrity import record_tool_call

    weather_path = _SAMPLE_DATA / "weather.json"
    if not weather_path.exists():
        return ToolResult(
            success=False,
            output={"error": "SA_TOOL_DEPENDENCY_MISSING"},
            summary="weather.json not found",
        )

    data = json.loads(weather_path.read_text(encoding="utf-8"))

    city_key = city.lower().strip()
    city_data = data.get(city_key)
    if city_data is None:
        output = {"error": "SA_TOOL_INVALID_INPUT", "city": city, "available": list(data.keys())}
        record_tool_call("get_weather", {"city": city, "date": date}, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather: city {city!r} not found",
        )

    day_data = city_data.get(date)
    if day_data is None:
        output = {
            "error": "SA_TOOL_INVALID_INPUT",
            "city": city,
            "date": date,
            "available_dates": list(city_data.keys()),
        }
        record_tool_call("get_weather", {"city": city, "date": date}, output)
        return ToolResult(
            success=False,
            output=output,
            summary=f"get_weather: date {date!r} not found for city {city!r}",
        )

    output = {"city": city, "date": date, **day_data}
    record_tool_call("get_weather", {"city": city, "date": date}, output)

    condition = day_data.get("condition", "unknown")
    temp = day_data.get("temperature_c", "?")
    return ToolResult(
        success=True,
        output=output,
        summary=f"get_weather({city!r}, {date}): {condition}, {temp}°C",
    )


# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking.

    Formula:
      base_per_head = base_rates_gbp_per_head[catering_tier]
      venue_mult    = venue_modifiers[venue_id]
      subtotal      = base_per_head * venue_mult * party_size * max(1, duration_hours)
      service       = subtotal * service_charge_percent / 100
      total         = max(subtotal, venue.min_spend_gbp) + service + venue.hire_fee_gbp
      deposit_rule  = per deposit_policy thresholds

    Returns:
      output: {
        "venue_id": str,
        "party_size": int,
        "duration_hours": int,
        "catering_tier": str,
        "subtotal_gbp": int,
        "service_gbp": int,
        "total_gbp": int,
        "deposit_required_gbp": int,
      }
      summary: "calculate_cost(<venue>, <party>): total £<N>, deposit £<M>"

    MUST call record_tool_call(...) before returning.
    """
    import json

    from starter.edinburgh_research.integrity import record_tool_call

    catering_path = _SAMPLE_DATA / "catering.json"
    venues_path = _SAMPLE_DATA / "venues.json"

    for p in (catering_path, venues_path):
        if not p.exists():
            return ToolResult(
                success=False,
                output={"error": "SA_TOOL_DEPENDENCY_MISSING", "path": str(p)},
                summary=f"{p.name} not found",
            )

    catering = json.loads(catering_path.read_text(encoding="utf-8"))
    venues = json.loads(venues_path.read_text(encoding="utf-8"))

    venue = next((v for v in venues if v["id"] == venue_id), None)
    if venue is None:
        output = {"error": "SA_TOOL_INVALID_INPUT", "venue_id": venue_id}
        record_tool_call(
            "calculate_cost",
            {"venue_id": venue_id, "party_size": party_size, "duration_hours": duration_hours},
            output,
        )
        return ToolResult(success=False, output=output, summary=f"venue {venue_id!r} not found")

    base_rates = catering["base_rates_gbp_per_head"]
    if catering_tier not in base_rates:
        catering_tier = "bar_snacks"

    base_per_head = base_rates[catering_tier]
    venue_mult = catering["venue_modifiers"].get(venue_id, 1.0)
    service_pct = catering["service_charge_percent"]
    hire_fee = venue.get("hire_fee_gbp", 0)
    min_spend = venue.get("min_spend_gbp", 0)

    subtotal = int(base_per_head * venue_mult * party_size * max(1, duration_hours))
    service = int(subtotal * service_pct / 100)
    total = max(subtotal, min_spend) + service + hire_fee

    if total < 300:
        deposit = 0
    elif total < 1000:
        deposit = int(total * 0.20)
    else:
        deposit = int(total * 0.30)

    args = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
    }
    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": subtotal,
        "service_gbp": service,
        "total_gbp": total,
        "deposit_required_gbp": deposit,
    }
    record_tool_call("calculate_cost", args, output)

    return ToolResult(
        success=True,
        output=output,
        summary=f"calculate_cost({venue_id}, party={party_size}): total £{total}, deposit £{deposit}",
    )


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html.

    event_details is expected to contain at least:
      venue_name, venue_address, date, time, party_size, condition,
      temperature_c, total_gbp, deposit_required_gbp

    Write a self-contained HTML flyer (inline CSS, no external assets). Tag every key fact with data-testid="<n>" so the integrity check can parse it.

    Write a formatted HTML flyer with an H1 title, the event
    facts, a weather summary, and the cost breakdown.

    Returns:
      output: {"path": "workspace/flyer.html", "bytes_written": int}
      summary: "generate_flyer: wrote <path> (<N> chars)"

    MUST call record_tool_call(...) before returning — the integrity
    check compares the flyer's contents against earlier tool outputs.

    IMPORTANT: this tool MUST be registered with parallel_safe=False
    because it writes a file.
    """
    from starter.edinburgh_research.integrity import record_tool_call

    venue_name = event_details.get("venue_name", "Edinburgh Pub")
    venue_address = event_details.get("venue_address", "Edinburgh")
    date = event_details.get("date", "TBD")
    time = event_details.get("time", "TBD")
    party_size = event_details.get("party_size", "?")
    condition = event_details.get("condition", "unknown")
    temperature_c = event_details.get("temperature_c", "?")
    total_gbp = event_details.get("total_gbp", 0)
    deposit_gbp = event_details.get("deposit_required_gbp", 0)

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Edinburgh Pub Event — {venue_name}</title>
  <style>
    body {{ font-family: sans-serif; max-width: 620px; margin: 2rem auto; padding: 1.5rem;
           background: #fffdf8; border: 2px solid #c8a87a; border-radius: 8px; }}
    h1   {{ color: #4a2c0a; font-size: 1.6rem; margin-bottom: 0.5rem; }}
    .subtitle {{ color: #7a5c3a; margin-bottom: 1.5rem; font-style: italic; }}
    dl   {{ display: grid; grid-template-columns: 140px 1fr; gap: 0.4rem 1rem; }}
    dt   {{ font-weight: bold; color: #4a2c0a; }}
    dd   {{ margin: 0; color: #2a1a0a; }}
    .costs {{ margin-top: 1rem; padding: 0.8rem; background: #f5e8d0;
              border-radius: 4px; border: 1px solid #c8a87a; }}
    .costs h2 {{ font-size: 1rem; margin: 0 0 0.5rem; color: #4a2c0a; }}
  </style>
</head>
<body>
  <h1>Edinburgh Pub Booking</h1>
  <p class="subtitle">Your event is ready to book!</p>
  <dl>
    <dt>Venue</dt>
    <dd data-testid="venue_name">{venue_name}</dd>
    <dt>Address</dt>
    <dd data-testid="venue_address">{venue_address}</dd>
    <dt>Date</dt>
    <dd data-testid="date">{date}</dd>
    <dt>Time</dt>
    <dd data-testid="time">{time}</dd>
    <dt>Party Size</dt>
    <dd data-testid="party_size">{party_size}</dd>
    <dt>Weather</dt>
    <dd data-testid="condition">{condition}</dd>
    <dt>Temperature</dt>
    <dd data-testid="temperature_c">{temperature_c}°C</dd>
  </dl>
  <div class="costs">
    <h2>Cost Breakdown</h2>
    <dl>
      <dt>Total</dt>
      <dd data-testid="total">£{total_gbp}</dd>
      <dt>Deposit Required</dt>
      <dd data-testid="deposit">£{deposit_gbp}</dd>
    </dl>
  </div>
</body>
</html>
"""

    flyer_path = session.workspace_dir / "flyer.html"
    flyer_path.parent.mkdir(parents=True, exist_ok=True)
    flyer_path.write_text(html, encoding="utf-8")
    bytes_written = len(html.encode("utf-8"))

    args = {"event_details": event_details}
    output = {"path": "workspace/flyer.html", "bytes_written": bytes_written}
    record_tool_call("generate_flyer", args, output)

    return ToolResult(
        success=True,
        output=output,
        summary=f"generate_flyer: wrote workspace/flyer.html ({bytes_written} bytes)",
    )


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # --- Memory layer: persist tool results so later subgoals can recall them ---
    import json as _json

    from sovereign_agent.memory import MemoryStore, MemoryType

    mem = MemoryStore(session)

    def _venue_search_with_memory(
        near: str,
        party_size: int,
        budget_max_gbp: int = 1000,
    ) -> ToolResult:
        result = venue_search(near, party_size, budget_max_gbp)
        if result.success:
            mem.write_fact(
                MemoryType.EPISODIC,
                "venue_search_result",
                _json.dumps(result.output),
                metadata={"tool": "venue_search"},
            )
        return result

    def _get_weather_with_memory(city: str, date: str) -> ToolResult:
        result = get_weather(city, date)
        if result.success:
            mem.write_fact(
                MemoryType.EPISODIC,
                "weather_result",
                _json.dumps(result.output),
                metadata={"tool": "get_weather"},
            )
        return result

    def _calculate_cost_with_memory(
        venue_id: str,
        party_size: int,
        duration_hours: int,
        catering_tier: str = "bar_snacks",
    ) -> ToolResult:
        result = calculate_cost(venue_id, party_size, duration_hours, catering_tier)
        if result.success:
            mem.write_fact(
                MemoryType.EPISODIC,
                "cost_result",
                _json.dumps(result.output),
                metadata={"tool": "calculate_cost"},
            )
        return result

    def _recall_research() -> ToolResult:
        """Retrieve results from prior tool calls stored in session memory."""
        entries = mem.list_facts(memory_type=MemoryType.EPISODIC)
        if not entries:
            return ToolResult(
                success=True,
                output={"results": {}},
                summary="No prior research results in session memory",
            )
        results = {}
        for entry in entries:
            try:
                results[entry.id] = _json.loads(entry.content)
            except (_json.JSONDecodeError, ValueError):
                results[entry.id] = entry.content
        return ToolResult(
            success=True,
            output=results,
            summary=f"Recalled {len(results)} result(s): {', '.join(results.keys())}",
        )

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="Search Edinburgh venues by area, party size, and max budget.",
            fn=_venue_search_with_memory,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=_get_weather_with_memory,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="Compute total cost and deposit for a booking.",
            fn=_calculate_cost_with_memory,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description=(
                "Write an HTML flyer for the event to workspace/flyer.html. "
                "This MUST be called before complete_task — the scenario is graded "
                "by the existence of this file. "
                "event_details MUST include these exact keys: venue_name, venue_address, "
                "date, time, party_size, condition, temperature_c, total_gbp, "
                "deposit_required_gbp. Use real data from prior tool calls only."
            ),
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {
                    "event_details": {
                        "type": "object",
                        "properties": {
                            "venue_name": {"type": "string"},
                            "venue_address": {"type": "string"},
                            "date": {"type": "string", "description": "YYYY-MM-DD"},
                            "time": {"type": "string", "description": "HH:MM"},
                            "party_size": {"type": "integer"},
                            "condition": {"type": "string", "description": "weather condition"},
                            "temperature_c": {"type": "integer"},
                            "total_gbp": {"type": "integer", "description": "total cost"},
                            "deposit_required_gbp": {"type": "integer"},
                        },
                        "required": [
                            "venue_name",
                            "venue_address",
                            "date",
                            "time",
                            "party_size",
                            "condition",
                            "temperature_c",
                            "total_gbp",
                            "deposit_required_gbp",
                        ],
                    }
                },
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "venue_address": "12 Dalry Rd, Edinburgh EH11 2BG",
                            "date": "2026-04-25",
                            "time": "19:30",
                            "party_size": 6,
                            "condition": "cloudy",
                            "temperature_c": 12,
                            "total_gbp": 356,
                            "deposit_required_gbp": 71,
                        }
                    },
                    "output": {"path": "workspace/flyer.html", "bytes_written": 1629},
                }
            ],
        )
    )

    # recall_research — lets executors access results from prior subgoals
    reg.register(
        _RegisteredTool(
            name="recall_research",
            description=(
                "Retrieve results from prior tool calls in this session. "
                "Call this FIRST when your subgoal needs data produced by an earlier "
                "subgoal (e.g. a venue_id from venue_search, or weather data). "
                "Do NOT fabricate values — always recall them."
            ),
            fn=_recall_research,
            parameters_schema={"type": "object", "properties": {}},
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,
            examples=[
                {
                    "input": {},
                    "output": {
                        "venue_search_result": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                        "weather_result": {"condition": "cloudy", "temperature_c": 12},
                    },
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
