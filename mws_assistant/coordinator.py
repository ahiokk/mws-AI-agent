import asyncio
import logging

from pydantic import ValidationError

from .estimation import UsageScenario, estimate_model_cost
from .mws_catalog import get_catalog
from .observability import increment_counter, log_metrics_snapshot, measure_time
from .recommendation import RecommendationRequest, recommend_models
from .reporting import build_report
from .validation import AssistantRunPayload


LOGGER = logging.getLogger(__name__)

async def run_assistant_flow(
        request: RecommendationRequest,
        scenario: UsageScenario,
) -> dict:
    increment_counter("assistant_flow_runs_total")
    with measure_time("assistant_flow_seconds"):
        LOGGER.info("Starting assistant flow")
        LOGGER.info("Validated request: %s", request)
        LOGGER.info("Validated scenario: %s", scenario)

        # 1. Тянем актуальные модели и цены из MWS
        catalog = await get_catalog()
        LOGGER.info("Catalog loaded: %s models", len(catalog))

        # 2. Выбираем лучшие модели под кейс
        recommendations = recommend_models(catalog, request)
        LOGGER.info(
            "Recommendations selected: %s",
            [item.get("name") for item in recommendations],
        )

        # 3. Считаем стоимость для каждой рекомендованной модели
        calculations = [
            estimate_model_cost(model, scenario)
            for model in recommendations
        ]
        LOGGER.info("Calculation rows built: %s", len(calculations))

        # 4. собираем 4 блока в один итоговый ответ
        report = build_report(
            request=request,
            scenario=scenario,
            recommendations=recommendations,
            calculations=calculations,
        )

        LOGGER.info(
            "Report built with sections: %s",
            list(report.keys()),
        )
        log_metrics_snapshot("assistant_flow_metrics")
        return report


async def run_assistant_from_payload(
        request_data: dict,
        scenario_data: dict,
) -> dict:
    try:
        payload = AssistantRunPayload(
            request_data=request_data,
            scenario_data=scenario_data,
        )
    except ValidationError:
        LOGGER.exception("Pydantic payload validation failed")
        raise

    LOGGER.info("Pydantic payload validation succeeded")
    LOGGER.info("Validated request payload: %s", payload.request_data.model_dump())
    LOGGER.info("Validated scenario payload: %s", payload.scenario_data.model_dump())

    request = RecommendationRequest(**payload.request_data.model_dump())
    scenario = UsageScenario(**payload.scenario_data.model_dump())
    return await run_assistant_flow(request, scenario)


# Проверка, что весь пайплайн грузится как надо
async def main() -> None:
    request = RecommendationRequest(
        use_case="chat",
        needs_image_inputs=False,
        min_context_k_tokens=32,
        quality_priority="medium",
        budget_priority="balanced",
        max_recommendations=3,
    )

    scenario = UsageScenario(
        avg_input_tokens_per_request=800,
        avg_output_tokens_per_request=1200,
        requests_per_day=100,
        period_days=30,
        budget_rub=None,
        price_mode="auto",
    )

    report = await run_assistant_flow(request, scenario)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
