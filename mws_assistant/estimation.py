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



def calculate_period_billed_tokens(
        daily_tokens: list[int],
        billing_unit_tokens: int,
) -> tuple[int, int, int]:
    if billing_unit_tokens <= 0:
        raise ValueError('billing_unit_tokens must be > 0')
    '''
    остаток со вчера переносится только на сегодня
    если сегодня до полной единицы не добрали, вчерашний остаток сгорает
    на завтра можно перенести только то, что осталось от сегодняшних токенов
'''
    total_billed_tokens = 0
    total_expired_tokens = 0
    carryover_tokens = 0

    for today_tokens in daily_tokens:
        if today_tokens < 0:
            raise ValueError('daily token counts must be >= 0')
    
        available_tokens = carryover_tokens + today_tokens
        full_units = available_tokens // billing_unit_tokens
        billed_tokens_today = full_units * billing_unit_tokens
        total_billed_tokens += billed_tokens_today

        #Сначала считаем, сколько из тарифицированного объема пришлось на сегодняшние токены
        billed_from_today = max(0, billed_tokens_today - carryover_tokens)
        

        # Что осталось от сегодняшних токенов после списания можно перенести на следующий день
        remaining_today_tokens = today_tokens - billed_from_today

        # Невыбранный остаток со вчерашнего дня живет 24 часа, значит теперь сгорает
        expired_tokens_today = max(0, carryover_tokens - billed_tokens_today)
        total_expired_tokens += expired_tokens_today

        # На следующий день переносим только остаток сегодняшних токенов
        carryover_tokens = remaining_today_tokens
    
    return total_billed_tokens, total_expired_tokens, carryover_tokens


def build_daily_token_series(
    avg_tokens_per_request: int,
    requests_per_day: int,
    period_days: int,
) -> list[int]:
    daily_tokens = avg_tokens_per_request * requests_per_day
    return [daily_tokens] * period_days


def estimate_model_cost(model: dict, scenario: UsageScenario) -> dict:
    input_price_per_1k, output_price_per_1k, effective_price_mode = get_price_fields(
    model,
    scenario.price_mode,
)
    input_daily_tokens = build_daily_token_series(
        scenario.avg_input_tokens_per_request,
        scenario.requests_per_day,
        scenario.period_days,
    )

    output_daily_tokens = build_daily_token_series(
        scenario.avg_output_tokens_per_request,
        scenario.requests_per_day,
        scenario.period_days,
    )

    billed_input_tokens, expired_input_tokens, input_carryover_tokens = calculate_period_billed_tokens(
        daily_tokens=input_daily_tokens,
        billing_unit_tokens=model["billing_unit_tokens"],
    )

    billed_output_tokens, expired_output_tokens, output_carryover_tokens = calculate_period_billed_tokens(
        daily_tokens=output_daily_tokens,
        billing_unit_tokens=model["billing_unit_tokens"],
    )

    total_input_tokens = sum(input_daily_tokens)
    total_output_tokens = sum(output_daily_tokens)

    input_cost = (Decimal(billed_input_tokens) / Decimal("1000")) * input_price_per_1k if input_price_per_1k is not None else Decimal("0")
    output_cost = (Decimal(billed_output_tokens) / Decimal("1000")) * output_price_per_1k if output_price_per_1k is not None else Decimal("0")

    total_cost = input_cost + output_cost

    return {
        'model_name': model['name'],
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
        'fit_budget': scenario.budget_rub is None or total_cost <= scenario.budget_rub,
        "expired_input_tokens": expired_input_tokens,
        "expired_output_tokens": expired_output_tokens,
        "ending_input_carryover_tokens": input_carryover_tokens,
        "ending_output_carryover_tokens": output_carryover_tokens,

    }