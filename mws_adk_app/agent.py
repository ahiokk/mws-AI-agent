import logging
import os
from decimal import Decimal

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm
from google.adk.apps import App

from mws_assistant.coordinator import run_assistant_from_payload


LOGGER = logging.getLogger(__name__)


def format_tool_call_log(
    use_case: str,
    needs_image_inputs: bool,
    min_context_k_tokens: int | None,
    quality_priority: str,
    budget_priority: str,
    max_recommendations: int,
    avg_input_tokens_per_request: int,
    avg_output_tokens_per_request: int,
    requests_per_day: int,
    period_days: int,
    budget_rub: str | None,
    price_mode: str,
    output_tokens_source: str,
    output_tokens_assumption_confirmed: bool,
    ) -> str:
    return "\n".join(
        [
            "Parsed tool arguments:",
            f"  use_case: {use_case}",
            f"  needs_image_inputs: {needs_image_inputs}",
            f"  min_context_k_tokens: {min_context_k_tokens}",
            f"  quality_priority: {quality_priority}",
            f"  budget_priority: {budget_priority}",
            f"  max_recommendations: {max_recommendations}",
            f"  avg_input_tokens_per_request: {avg_input_tokens_per_request}",
            f"  avg_output_tokens_per_request: {avg_output_tokens_per_request}",
            f"  requests_per_day: {requests_per_day}",
            f"  period_days: {period_days}",
            f"  budget_rub: {budget_rub}",
            f"  price_mode: {price_mode}",
            f"  output_tokens_source: {output_tokens_source}",
            f"  output_tokens_assumption_confirmed: {output_tokens_assumption_confirmed}",
        ]
    )


def format_payload_log(request_data: dict, scenario_data: dict) -> str:
    return "\n".join(
        [
            "Normalized payload before coordinator:",
            f"  request_data: {request_data}",
            f"  scenario_data: {scenario_data}",
        ]
    )


async def run_mws_assistant(
    use_case: str,
    needs_image_inputs: bool = False,
    min_context_k_tokens: int | None = None,
    quality_priority: str = "medium",
    budget_priority: str = "balanced",
    max_recommendations: int = 3,
    avg_input_tokens_per_request: int = 0,
    avg_output_tokens_per_request: int = 0,
    requests_per_day: int = 0,
    period_days: int = 30,
    budget_rub: str | None = None,
    price_mode: str = "auto",
    output_tokens_source: str = "user",
    output_tokens_assumption_confirmed: bool = False,
) -> dict:
    """
    Selects suitable MWS GPT models and estimates usage cost.

    Use this tool only when enough input data has been collected.
    Required inputs for a reliable estimate:
    - use_case: one of chat, coding, analysis, embedding
    - requests_per_day
    - avg_input_tokens_per_request
    - avg_output_tokens_per_request for non-embedding use cases
    - budget_rub is optional but recommended for budget fit analysis

    Optional inputs:
    - needs_image_inputs
    - min_context_k_tokens
    - quality_priority
    - budget_priority
    - max_recommendations
    - period_days
    - price_mode
    - output_tokens_source: "user" or "assumption"
    - output_tokens_assumption_confirmed

    Returns:
    - input_data
    - recommended_models
    - calculations
    - limitations

    Important:
    - do not use this tool for a final cost estimate if avg_output_tokens_per_request
      is unknown and the user has not explicitly accepted an assumption
    - do not invent models outside the tool result
    - if output_tokens_source is "assumption", output_tokens_assumption_confirmed
      must be True
    """
    LOGGER.info(
        "\n%s",
        format_tool_call_log(
            use_case=use_case,
            needs_image_inputs=needs_image_inputs,
            min_context_k_tokens=min_context_k_tokens,
            quality_priority=quality_priority,
            budget_priority=budget_priority,
            max_recommendations=max_recommendations,
            avg_input_tokens_per_request=avg_input_tokens_per_request,
            avg_output_tokens_per_request=avg_output_tokens_per_request,
            requests_per_day=requests_per_day,
            period_days=period_days,
            budget_rub=budget_rub,
            price_mode=price_mode,
            output_tokens_source=output_tokens_source,
            output_tokens_assumption_confirmed=output_tokens_assumption_confirmed,
        ),
    )

    if use_case == "embedding" and avg_output_tokens_per_request <= 0:
        avg_output_tokens_per_request = 0
        output_tokens_source = "user"
        output_tokens_assumption_confirmed = False
        LOGGER.info(
            "Embedding shortcut applied: avg_output_tokens_per_request set to 0"
        )

    missing_fields = []
    if not use_case:
        missing_fields.append("use_case")
    if requests_per_day <= 0:
        missing_fields.append("requests_per_day")
    if avg_input_tokens_per_request <= 0:
        missing_fields.append("avg_input_tokens_per_request")
    if use_case != "embedding" and avg_output_tokens_per_request <= 0:
        missing_fields.append("avg_output_tokens_per_request")

    if missing_fields:
        LOGGER.warning(
            "Tool was called with incomplete or unclear inputs: %s",
            ", ".join(missing_fields),
        )

    if output_tokens_source not in {"user", "assumption"}:
        raise ValueError(
            f"Unsupported output_tokens_source: {output_tokens_source}"
        )

    if (
        output_tokens_source == "assumption"
        and not output_tokens_assumption_confirmed
    ):
        raise ValueError(
            "Output token assumption must be explicitly confirmed by the user before final estimation."
        )

    request_data = {
        "use_case": use_case,
        "needs_image_inputs": needs_image_inputs,
        "min_context_k_tokens": min_context_k_tokens,
        "quality_priority": quality_priority,
        "budget_priority": budget_priority,
        "max_recommendations": max_recommendations,
    }

    scenario_data = {
        "avg_input_tokens_per_request": avg_input_tokens_per_request,
        "avg_output_tokens_per_request": avg_output_tokens_per_request,
        "requests_per_day": requests_per_day,
        "period_days": period_days,
        "price_mode": price_mode,
    }

    if budget_rub is not None:
        scenario_data["budget_rub"] = Decimal(budget_rub)

    LOGGER.info("\n%s", format_payload_log(request_data, scenario_data))

    report = await run_assistant_from_payload(request_data, scenario_data)
    LOGGER.info(
        "Tool result summary: recommended_models=%s calculation_rows=%s",
        len(report.get("recommended_models", [])),
        len(report.get("calculations", [])),
    )
    LOGGER.info(
        "Recommended model names: %s",
        [item.get("name") for item in report.get("recommended_models", [])],
    )
    return report


root_agent = Agent(
    name="mws_selection_agent",
    model=LiteLlm(
        model=f"openai/{os.getenv('MODEL_NAME', 'qwen3-235b-instruct')}"
    ),
    instruction=(
        "You are a specialized MWS GPT Model Hub assistant. "
        "Your role is to help users choose suitable MWS models, compare options, "
        "estimate costs, and explain tradeoffs and limitations. "

        "On the first user message, do not respond like a generic chatbot. "
        "Briefly introduce yourself as an MWS model selection and cost estimation assistant, "
        "say that you work specifically with MWS GPT Model Hub, "
        "and explain in one short message what information you need. "

        "If the user request is underspecified, ask only the minimum missing questions needed "
        "to make a valid recommendation and estimate. "
        "Ask at most one or two short questions per turn, not a long questionnaire. "
        "When the user gives a messy or compact message, first briefly restate how you parsed it, "
        "then ask only for the highest-priority missing field. "
        "If the user says they do not know, continue with one short guiding question, not a long list. "

        "For cost estimation, do not make a final calculation unless you know both "
        "avg_input_tokens_per_request and avg_output_tokens_per_request, or unless you explicitly "
        "state a fallback assumption and get the user’s acceptance. "
        "Do not silently assume output tokens. "
        "Special case: for embedding use_case, do not ask for avg_output_tokens_per_request. "
        "Proceed with avg_output_tokens_per_request=0 unless the tool result requires otherwise. "

        "If the user provides only one token number, clarify whether it is input only or total traffic, "
        "and ask for the expected output tokens per request. "
        "If the user does not know output tokens, offer a simple fallback assumption, for example "
        "20%, 50%, or 100% of input tokens, and clearly label it as an assumption. "
        "Only continue the final estimate after the user agrees with the assumption. "
        "Do not ask follow-up questions about output tokens for embedding requests. "
        "Responses like 'не знаю', 'maybe', 'probably', or vague hesitation do not count as confirmation. "
        "Only explicit acceptance like 'да', 'ок', 'согласен', or 'подходит' counts as confirmation of an assumption. "
        "If output tokens are based on an assumption, call the tool only with "
        "output_tokens_source='assumption' and output_tokens_assumption_confirmed=True after explicit user confirmation. "

        "Never invent models, prices, or limits. "
        "Always rely on the tool result for recommendations and calculations. "
        "Never mention any model that is not present in the tool result. "
        "If nothing fits the budget, say so clearly and only suggest reducing load, "
        "changing assumptions, or considering options outside the current MWS catalog "
        "without naming unavailable models. "

        "Valid use_case values: chat, coding, analysis, embedding. "
        "Valid quality_priority values: low, medium, high. "
        "Valid budget_priority values: low, balanced, high. "
        "Valid price_mode values: auto, base, promo."
    ),

    tools=[run_mws_assistant],
)

app = App(
    name='mws_adk_app',
    root_agent=root_agent,
)
