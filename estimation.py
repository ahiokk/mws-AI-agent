from dataclasses import dataclass
from decimal import Decimal
from typing import Tuple
from datetime import date

@dataclass(slots=True)
class UsageScenario:
    avg_input_tokens_per_request: int = 0
    avg_output_tokens_per_request: int = 0
    requests_per_day: int = 0
    period_days: int = 30
    budget_rub: Decimal | None = None
    price_mode: str = 'auto'


def __post_init__(self) -> None:
    allowed_price_modes = {'auto', 'base', 'promo'}

    if self.price_mode not in allowed_price_modes:
        raise ValueError(f'Unsupported price_mode: {self.price_mode}')
    
    if self.avg_input_tokens_per_request < 0 or self. avg_output_tokens_per_request < 0:
        raise ValueError('Token counst must be >= 0')
    
    if self.requests_per_day < 0 or self.period_days <= 0:
        raise ValueError('requests_per_day must ne >= 0 and periond_days must be > 0')


def is_promo_active(model: dict, on_date: date | None = None) -> bool:
    on_date = on_date or date.today()

    promo_start_date = model.get('promo_start_date')
    promo_end_date = model.get('promo_end_date')
    has_promo_prices = (
        model.get('promo_input_price_per_1k') is not None
        or model.get('promo_output_price_per_1k') is not None
    )


    if not has_promo_prices:
        return False
    
    if promo_start_date is None or promo_end_date is None:
        return False
    
    return promo_start_date <= on_date <= promo_end_date



def resolve_price_mode(model: dict, requested_price_mode: str, on_date: date | None = None) -> str:
    if requested_price_mode == 'base':
        return 'base'

    if requested_price_mode == 'promo':
        return 'promo' if is_promo_active(model, on_date=on_date) else 'base'

    return 'promo' if is_promo_active(model, on_date=on_date) else 'base'



def get_price_fields(
    model: dict,
    price_mode: str = 'auto',
    on_date: date | None = None,
) -> tuple[Decimal | None, Decimal | None, str]:
    effective_price_mode = resolve_price_mode(model, price_mode, on_date=on_date)

    if effective_price_mode == 'promo':
        return (
            model.get('promo_input_price_per_1k'),
            model.get('promo_output_price_per_1k'),
            effective_price_mode,
        )

    return (
        model.get('base_input_price_per_1k'),
        model.get('base_output_price_per_1k'),
        effective_price_mode,
    )



def round_up_to_billing_unit(tokens: int, billing_unit_tokens: int) -> int:
    if tokens <= 0:
        return 0
    
    remainder = tokens % billing_unit_tokens
    if remainder == 0:
        return tokens
    
    return tokens + (billing_unit_tokens - remainder)


def calculate_direction_cost(
        tokens: int,
        price_per_1k: Decimal | None,
        billing_unit_tokens: int,
) -> Tuple[int, Decimal]:
    if tokens <= 0 or price_per_1k is None:
        return 0, Decimal('0')
    
    billed_tokens = round_up_to_billing_unit(tokens, billing_unit_tokens)
    cost = (Decimal(billed_tokens) / Decimal('1000')) * price_per_1k
    return billed_tokens, cost


def estimate_model_cost(model: dict, scenario: UsageScenario) -> dict:
    input_price_per_1k, output_price_per_1k, effective_price_mode = get_price_fields(
    model,
    scenario.price_mode,
)
    total_input_tokens = scenario.avg_input_tokens_per_request * scenario.requests_per_day * scenario.period_days
    total_output_tokens = scenario.avg_output_tokens_per_request * scenario.requests_per_day * scenario.period_days

    billed_input_tokens, input_cost = calculate_direction_cost(
        tokens=total_input_tokens,
        price_per_1k=input_price_per_1k,
        billing_unit_tokens=model['billing_unit_tokens'],
    )

    billed_output_tokens, output_cost = calculate_direction_cost(
        tokens=total_output_tokens,
        price_per_1k=output_price_per_1k,
        billing_unit_tokens=model['billing_unit_tokens']
    )

    total_cost = input_cost + output_cost

    return {
        'model_name': model['name'],
        'price_mode': scenario.price_mode,
        'billing_unit_tokens': model['billing_unit_tokens'],
        'input_price_per_1k': input_price_per_1k,
        'output_price_per_1k': output_price_per_1k,
        'estimated_input_tokens': total_input_tokens,
        'estimated_output_tokens': total_output_tokens,
        'billed_input_tokens': billed_input_tokens,
        'billed_output_tokens': billed_output_tokens,
        'input_cost_rub': input_cost,
        'output_cost_rub': output_cost,
        'total_cost_rub': total_cost,       
        'requested_price_mode': scenario.price_mode,
        'effective_price_mode': effective_price_mode,
        'promo_active': is_promo_active(model),
        'fit_budget': scenario.budget_rub is None or total_cost <= scenario.budget_rub
    }