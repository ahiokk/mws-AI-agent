from dataclasses import dataclass
from decimal import Decimal

@dataclass(slots=True)
class RecommendationRequest:
    use_case: str = 'chat'                  # Для чего модель нужна
    needs_image_inputs: bool = False        # Нужна ли поддержка картинок
    min_context_k_tokens: int | None = None # Минимально нужный контекст
    quality_priority: str = 'medium'        # Насколько важнее качество, чем цена
    budget_priority: str = 'balanced'       # Насколько важна низкая цена
    max_recommendations: int = 3            # Сколько моделей хотим вернуть


    def __post_init__(self) -> None:
        '''
        Встроенный механизм dataclass. Он автоматически вызывается
        после __init__, и держит всю логику валидности объекта
        рядом с самим объектом. Ошибка возникнет сразу в момент 
        создания объекта, а не всплывет где то потом.
        '''
        allowed_use_cases = {'chat', 'coding', 'analysis', 'embedding'}
        allowed_quality_priorities = {'low', 'medium', 'high'}
        allowed_budget_priorities = {'low', 'balanced', 'high'}

        # Проверяем, что use_case в доступном сценарии
        if self.use_case not in allowed_use_cases:
            raise ValueError(
                f'Unsupported use_case: {self.use_case}'
                f'Expected one of {sorted(allowed_use_cases)}'
            )
        
        # Проверяем, что приоритет бюджета задан корректно
        if self.quality_priority not in allowed_quality_priorities:
            raise ValueError(
                f'Unsupported quality_priority: {self.quality_priority}'
                f'Expected one of {sorted(allowed_quality_priorities)}'
            )
        # Минимальный контекст не может быть отрицательным
        if self.min_context_k_tokens is not None and self.min_context_k_tokens <= 0:
            raise ValueError('min_context_k_tokens must be > 0')
        
        # Количество рекомендаций тоже не может быть отрицательным
        if self.max_recommendations <= 0:
            raise ValueError('max_recommendations must be > 0')
        
        #...
        if self.budget_priority not in allowed_budget_priorities:
            raise ValueError(
                f'Unsupported budget_priority: {self.budget_priority}'
                f'Expected one of {sorted(allowed_budget_priorities)}'
            )

# Проверяем, эмбеддер это, или нет.
def is_embedding_model(model: dict) -> bool:
    return model['output_modality'] == 'Embedding'

# Проверяем есть ли в модальностях image
def supports_image_input(model: dict) -> bool:
    return 'Image' in model['input_modalities']

#Если в имени есть coder - считаем ее coding-ориентированной
def is_coding_model(model: dict) -> bool:
    return 'coder' in model['name'].lower()


def is_model_compatible(model: dict, request: RecommendationRequest) -> bool:
    # embedding-сценарий: подходят только embedding-модели
    if request.use_case == "embedding" and not is_embedding_model(model):
        return False

    # все остальные сценарии: embedding-модели исключаем
    if request.use_case != "embedding" and is_embedding_model(model):
        return False

    # если нужны входные изображения, модель обязана их поддерживать
    if request.needs_image_inputs and not supports_image_input(model):
        return False

    # если задан минимальный контекст, модель должна ему соответствовать
    if (
        request.min_context_k_tokens is not None
        and model["context_k_tokens"] < request.min_context_k_tokens
    ):
        return False

    return True


# Вспомогательная метрика для recommendation
def get_effective_total_price_per_1k(model: dict, price_mode: str = 'base') -> Decimal | None:
    # Если есть акционная цена, берем. Если нет - берем обычную
    # Через get() чтобы не словить KeyError, если поля вдруг нет
    if price_mode == "promo":
        input_price = model.get("promo_input_price_per_1k")
        output_price = model.get("promo_output_price_per_1k")
    else:
        input_price = model.get("base_input_price_per_1k")
        output_price = model.get("base_output_price_per_1k")
    # Если нет вообще никакой цены, функцию нельзя использовать для ranking по бюджету
    if input_price is None and output_price is None:
        return None
    
    # Это важно для эмбеддеров, у них может не быть output price
    if input_price is None:
        return output_price
    if output_price is None:
        return input_price
    
    # Основной случай
    return input_price + output_price


def build_price_scores(models: list[dict], price_mode: str = 'base') -> dict[str, float]:
    '''
    Нормализуем цену каждой модели:
    cамой дешевой модели даем 1.0,
    cамой дорогой модели даем 0.0,
    всем остальным что-то между
    '''
    # Создаем словарь 
    prices_by_name: dict[str, Decimal] = {}
    # Берём модель, считаем ее цену
    for model in models:
        total_price = get_effective_total_price_per_1k(model, price_mode=price_mode)
        if total_price is None:
            continue # Чтобы код не падал из-за одной ошибки, лучше просто ее не использовать

        prices_by_name[model['name']] = total_price
    # Это защита от пустого набора
    if not prices_by_name:
        return {}
    # Ищем минимальную и максимальную цену. Это нужно для нормализации
    min_price = min(prices_by_name.values())
    max_price = max(prices_by_name.values())
    # Проверка на "если все цены одинаковые". Нужно т.к. делить нельзя будет в таком случае
    if min_price == max_price:
        return {name: 0.5 for name in prices_by_name} # 0.5 нейтральный средний балл
    # Это расстояние между самой дешевой и самой дорогой моделью
    price_range = max_price - min_price
    scores: dict[str, float] = {}
    # Нормализуем цену каждой модели
    for name, current_price in prices_by_name.items():
        normalized_score = (max_price - current_price) / price_range
        scores[name] = float(normalized_score)

    return scores


def score_by_use_case(model: dict, request: RecommendationRequest) -> float:
    '''
    Эта функция отвечает на вопрос:
    "насколько модель хороша именно для данного типа задачи?"
    '''
    score = 0.0
    # 1. Сценарий coding
    if request.use_case == 'coding':
        # Если модель явно coding-ориентированная, это сильный плюс
        if is_coding_model(model):
            score += 4.0
        # Если у нее еще и большой контекст, это дополнительный плюс
        if model['context_k_tokens'] >= 128:
            score += 1.0
    # 2. Сценарий analysis
    elif request.use_case == 'analysis':
        # Для анализа часто нужен длинный контекст
        if model['context_k_tokens'] >= 128:
            score += 2.0
        # Размер модели не гарантирует качество, но как слабый бонус он допустим
        if model['size_b_params'] >= 70:
            score += 1.0
    # 3. Сценарий chat
    elif request.use_case == 'chat':
        # Для обычного чата полезен нормальный контекст
        if model['context_k_tokens'] >= 128:
            score += 1.0
        # Плюс просто за то, что это не embedding
        if not is_embedding_model(model):
            score += 1.0
    # 3. Сценарий embedding
    elif request.use_case == 'embedding':
        # Для эмбеддинг задачи нужны эмбеддеры. Даем сильный бонус
        if is_embedding_model(model):
            score += 4.0
    
    return score


def score_by_quality(model: dict, request: RecommendationRequest) -> float:
    '''
    Функция отвечает на вопрос:
    если пользователь говорит, что ему важно качество, 
    насколько эта модель выглядит сильной по грубым признакам?

    Для этого используем size_b_params, то есть размер модели в млрд параметров
    '''
    size = model['size_b_params']
    # пользователь явно говорит, что для него качество важно
    if request.quality_priority == 'high':
        if size >= 200: # Очень сильный кандидат
            return 4.0
        if size >= 70:  # Тоже серьёзный кандидат
            return 2.5
        if size >= 30:  # Уже неплохо
            return 1.5
        return 0.5      # совсем компактные - почти без бонуса
    # Пользователь говорит что качество важно, но не доминирует
    if request.quality_priority == 'medium':
        if size >= 70:  # Средние модели получают бонус
            return 2.0
        if size >= 30:  # Средние модели получают бонус
            return 1.0
        return 0.5
    # если качество не заявлено как приоритет, этот фактор почти не влияет на рекомендацию
    return 0.0

 

def get_budget_weight(request: RecommendationRequest) -> float:
    # Если бюджет почти не важен, влияние цены должно быть слабым
    if request.budget_priority == 'low':
        return 0.7
    
    # Сбалансированный режим. Цена важна, но не доминирует
    if request.budget_priority == 'balanced':
        return 1.5
    # Если бюджет очень важен, цена должна сильнее влиять на ранжирование
    if request.budget_priority == 'high':
        return 3.0

    raise ValueError(f"Unsupported budget_priority: {request.budget_priority}")


def score_model(
        model: dict,
        request: RecommendationRequest,
        price_scores: dict[str, float],
 ) -> float:
    '''
    Это функция, которая отвечает на вопрос:
    “какой общий вес получает модель после учета всех факторов?”

    Объединяем все веса
    '''
    score = 0.0

    score += score_by_use_case(model, request)                 # 1. Добавляем score по use case
    score += score_by_quality(model, request)                  # 2. Добавляем quality score
    score += price_scores.get(model['name'], 0.5) * get_budget_weight(request)  # 3. Добавляем price score
    # 4. Бонус за image support
    if request.needs_image_inputs and supports_image_input(model):
        score += 2.0
    # 5. Бонус за достаточный контекст
    if (
        request.min_context_k_tokens is not None
        and model['context_k_tokens'] >= request.min_context_k_tokens
    ):
        score += 1.0

    return score



def recommend_models(
        catalog: list[dict],
        request: RecommendationRequest,
) -> list[dict]:
    '''
    Она отвечает на вопрос:
    “какие модели я рекомендую пользователю из всего каталога?"

    Это уже главная точка входа для recommendation-слоя.
    '''

    compatible_models = [
        model for model in catalog
        if is_model_compatible(model, request)
    ]

    price_scores = build_price_scores(compatible_models, price_mode='base')

    ranked_models = sorted(
        compatible_models,
        key=lambda model: score_model(model, request, price_scores), reverse=True)
    
    recommendations = []
    for model in ranked_models[: request.max_recommendations]:
        recommendations.append(
            {
                **model,
                "score": score_model(model, request, price_scores),
                "reasons": build_reasons(model, request),
            }
        )

    
    return recommendations


def build_reasons(model: dict, request: RecommendationRequest) -> list[str]:
    '''
    Рекомендация должна быть объяснимой, для этого эта функция.
    Понятные формулировки, которые потом можно показывать в отчете.
    '''
    reasons = []

    # если пользователь просил coding
    # и модель coding-ориентированная
    # это хорошая причина упомянуть
    if request.use_case == 'coding' and is_coding_model(model):
        reasons.append('Ориентирована на задачи генерации и анализа кода')

    # пользователь хочет embedding-задачу
    # модель реально подходит по типу выхода
    if request.use_case == 'embedding' and is_embedding_model(model):
        reasons.append('Возвращает embedding, а не текстовый ответ')

    # пользовательский сценарий требует картинки
    # значит это не просто приятный бонус, а реальное основание для выбора
    if request.needs_image_inputs and supports_image_input(model):
        reasons.append('Поддерживает входные изображения')

    # большой контекст часто реально полезен
    # это хороший и понятный плюс
    if model['context_k_tokens'] >= 128:
        reasons.append(f"Имеет большой контекст: {model['context_k_tokens']}k токенов")

    # если пользователь говорит, что качество важно
    # и модель крупная
    # можно это упомянуть как дополнительное основание
    if request.quality_priority in {'medium', 'high'} and model['size_b_params'] >= 70:
        reasons.append('Выглядит сильной по размеру модели для приоритета на качество')

    # чтобы не вернуть пустой список причин
    # иначе отчет получится сухим и неполным
    if not reasons:
        reasons.append('Проходит базовые требования по типу задачи и ограничениям')

    return reasons
