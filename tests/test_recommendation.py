from decimal import Decimal

from mws_assistant.recommendation import RecommendationRequest, recommend_models


CATALOG = [
    {
        "name": "generic-text",
        "developer": "VendorA",
        "input_modalities": ["Text"],
        "output_modality": "Text",
        "context_k_tokens": 32,
        "size_b_params": 32.0,
        "base_input_price_per_1k": Decimal("1.0"),
        "base_output_price_per_1k": Decimal("1.0"),
        "promo_input_price_per_1k": Decimal("0.1"),
        "promo_output_price_per_1k": Decimal("0.1"),
    },
    {
        "name": "bge-m3",
        "developer": "BAAI",
        "input_modalities": ["Text"],
        "output_modality": "Embedding",
        "context_k_tokens": 8,
        "size_b_params": 0.6,
        "base_input_price_per_1k": Decimal("0.5"),
        "base_output_price_per_1k": None,
        "promo_input_price_per_1k": Decimal("0.05"),
        "promo_output_price_per_1k": None,
    },
    {
        "name": "coder-small",
        "developer": "VendorB",
        "input_modalities": ["Text"],
        "output_modality": "Text",
        "context_k_tokens": 128,
        "size_b_params": 32.0,
        "base_input_price_per_1k": Decimal("1.0"),
        "base_output_price_per_1k": Decimal("1.0"),
        "promo_input_price_per_1k": Decimal("0.1"),
        "promo_output_price_per_1k": Decimal("0.1"),
    },
]


def test_embedding_use_case_returns_only_embedding_models() -> None:
    request = RecommendationRequest(use_case="embedding", max_recommendations=3)

    recommendations = recommend_models(CATALOG, request)

    assert recommendations
    assert all(item["output_modality"] == "Embedding" for item in recommendations)


def test_coding_use_case_prefers_coder_model() -> None:
    request = RecommendationRequest(use_case="coding", max_recommendations=1)

    recommendations = recommend_models(CATALOG, request)

    assert recommendations[0]["name"] == "coder-small"


def test_chat_use_case_does_not_prioritize_coder_model() -> None:
    request = RecommendationRequest(use_case="chat", max_recommendations=1)

    recommendations = recommend_models(CATALOG, request)

    assert recommendations[0]["name"] == "generic-text"
