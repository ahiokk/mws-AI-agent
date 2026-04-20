from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# Схема входных данных для recommendation.py.
# Внешний слой валидации: что нам вообще можно прислать в request_data.
class RecommendationRequestPayload(BaseModel):
    # Автоматически подчищаем пробелы у строковых полей
    model_config = ConfigDict(str_strip_whitespace=True)

    # use_case ограничиваем фиксированным набором значений,
    # чтобы отлавливать мусор прямо на входе.
    use_case: Literal["chat", "coding", "analysis", "embedding"]
    needs_image_inputs: bool = False

    # Если контекст задан, он должен быть строго больше 0
    min_context_k_tokens: int | None = Field(default=None, gt=0)
    quality_priority: Literal["low", "medium", "high"] = "medium"
    budget_priority: Literal["low", "balanced", "high"] = "balanced"

    # Количество рекомендаций не может быть нулевым или отрицательным
    max_recommendations: int = Field(default=3, gt=0)


# Схема входных данных для estimation.py.
# Здесь валидируем параметры нагрузки и бюджета
class UsageScenarioPayload(BaseModel):
    # Тоже подчищаем строковые поля, если они пришли с лишними пробелами
    model_config = ConfigDict(str_strip_whitespace=True)

    # Токены и запросы не могут быть отрицательными
    avg_input_tokens_per_request: int = Field(default=0, ge=0)
    avg_output_tokens_per_request: int = Field(default=0, ge=0)
    requests_per_day: int = Field(default=0, ge=0)

    # Период должен быть хотя бы 1 день
    period_days: int = Field(default=30, gt=0)

    # Бюджет может отсутствовать, но если он есть, то должен быть >= 0
    budget_rub: Decimal | None = Field(default=None, ge=0)
    price_mode: Literal["auto", "base", "promo"] = "auto"


# Общая схема всего payload, который приходит в coordinator.py
class AssistantRunPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    request_data: RecommendationRequestPayload
    scenario_data: UsageScenarioPayload
