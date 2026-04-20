from decimal import Decimal

import pytest
from pydantic import ValidationError

from mws_assistant.validation import AssistantRunPayload


def test_invalid_use_case_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AssistantRunPayload(
            request_data={"use_case": "unsupported"},
            scenario_data={},
        )


def test_budget_string_is_parsed_to_decimal() -> None:
    payload = AssistantRunPayload(
        request_data={"use_case": "chat"},
        scenario_data={"budget_rub": "30000"},
    )

    assert payload.scenario_data.budget_rub == Decimal("30000")
