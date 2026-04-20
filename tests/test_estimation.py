from mws_assistant.estimation import calculate_period_billed_tokens


def test_carryover_expires_after_24h_window() -> None:
    assert calculate_period_billed_tokens([45, 45, 45], 100) == (0, 90, 45)


def test_single_billing_unit_and_partial_expiration() -> None:
    assert calculate_period_billed_tokens([60, 60, 60], 100) == (100, 20, 60)
