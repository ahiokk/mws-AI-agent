from decimal import Decimal

#helper
def serialize_decimal(value):
    '''
    Если значение Decimal, превращает его в строку
    Если нет, возвращает как есть

    Нужно для будущего перевода в JSON
    '''
    if isinstance(value, Decimal):
        return str(value)
    return value

def build_input_data_block(request, scenario) -> dict:
    return {
        'use_case': request.use_case,
        'needs_image_input': request.needs_image_inputs,
        'min_context_k_tokens': request.min_context_k_tokens,
        'quality_priority': request. quality_priority,
        'budget_priority': request.budget_priority,
        'max_recommendations': request.max_recommendations,
        'avg_input_tokens_per_request': scenario.avg_input_tokens_per_request,
        'avg_output_tokens_per_request': scenario.avg_output_tokens_per_request,
        'requests_per_day': scenario.requests_per_day,
        'period_days': scenario.period_days,
        'budget_rub': serialize_decimal(scenario.budget_rub),
        'requested_price_mode': scenario.price_mode,
    }


def build_recommended_models_block(recommendations: list[dict]) -> list[dict]:
    '''
    Берем сырые рекомендации, и оставляем в отчете только то, что реально полезно юзеру
    '''
    
    result = []

    for model in recommendations:
        result.append(
            {
                "name": model["name"],                          # имя модели
                "developer": model["developer"],                # кто ее сделал
                "input_modalities": model["input_modalities"],  # text-only или multimodal
                "output_modality": model["output_modality"],    # text или embedding
                "context_k_tokens": model["context_k_tokens"],  # контекст
                "size_b_params": model["size_b_params"],        # размер модели 
                "score": model["score"],                        # баллы
                "reasons": model["reasons"],                    # объяснение выбора
            }
        )

    return result

def build_calculations_block(calculations: list[dict]) -> list[dict]:
    '''
    берем результаты из estimation.py и превращаем их в отчетный блок 'Расчеты'.
     '''
    result = []

    for item in calculations:
        result.append(
            {
                "model_name": item["model_name"],
                "requested_price_mode": item["requested_price_mode"],       # что просил пользователь: auto/base/promo
                "effective_price_mode": item["effective_price_mode"],       #что применилось после проверки promo-активности
                "promo_active": item["promo_active"],                       # активная ли акция сейчас?
                "billing_unit_tokens": item["billing_unit_tokens"],
                "estimated_input_tokens": item["estimated_input_tokens"],
                "estimated_output_tokens": item["estimated_output_tokens"],
                "billed_input_tokens": item["billed_input_tokens"],
                "billed_output_tokens": item["billed_output_tokens"],
                "input_cost_rub": serialize_decimal(item["input_cost_rub"]),
                "output_cost_rub": serialize_decimal(item["output_cost_rub"]),
                "total_cost_rub": serialize_decimal(item["total_cost_rub"]),
                "fit_budget": item["fit_budget"],
                "expired_input_tokens": item["expired_input_tokens"],
                "expired_output_tokens": item["expired_output_tokens"],
                "ending_input_carryover_tokens": item["ending_input_carryover_tokens"],
                "ending_output_carryover_tokens": item["ending_output_carryover_tokens"],
            }
        )

    return result

def build_limitations_block(calculations: list[dict]) -> list[str]: 
    # собираем, какие режимы цены применились
    effective_price_modes = {item["effective_price_mode"] for item in calculations}
    
    # базовые пояснения
    limitations = [
        "Модели и цены загружаются из публичной документации MWS на момент расчета.",
        "Оценка стоимости является приблизительной и зависит от средних токенов на запрос и числа запросов в день.",
        "Правило 24 часов моделируется на уровне дневной агрегации: остаток токенов переносится только на следующий день.",
        "Фактический биллинг может отличаться при неравномерном распределении запросов внутри суток.",
    ]

    if "promo" in effective_price_modes:
        limitations.append(
            "Для части моделей применены акционные цены, если акция была активна на дату расчета."
        )
    else:
        limitations.append(
            "В расчете использованы базовые цены MWS."
        )

    return limitations


def build_report(
    request,
    scenario,
    recommendations: list[dict],
    calculations: list[dict],
) -> dict:
    return {
        "input_data": build_input_data_block(request, scenario),
        "recommended_models": build_recommended_models_block(recommendations),
        "calculations": build_calculations_block(calculations),
        "limitations": build_limitations_block(calculations),
    }

