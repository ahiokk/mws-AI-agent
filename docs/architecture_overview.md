# Архитектура сервиса


## Слои системы

| Слой | Компонент | Что делает |
| --- | --- | --- |
| Внешний клиент | OpenAI-compatible client / ADK web | Отправляет запросы ассистенту |
| HTTP API | `mws_assistant/api.py` | Реализует `/health`, `/v1/models`, `/v1/chat/completions`, stream и session |
| Agent layer | `mws_adk_app/agent.py` | Ведет диалог, собирает недостающие вводные, решает когда вызывать tool |
| Tool boundary | `run_mws_assistant()` | Превращает собранные параметры в структурированный payload |
| Orchestration | `mws_assistant/coordinator.py` | Запускает весь pipeline от каталога до финального отчета |
| Catalog layer | `mws_assistant/mws_catalog.py` | Тянет и парсит каталог MWS, различает base/promo, использует process cache |
| Recommendation layer | `mws_assistant/recommendation.py` | Фильтрует и ранжирует модели |
| Estimation layer | `mws_assistant/estimation.py` | Считает стоимость и 24h billing approximation |
| Reporting layer | `mws_assistant/reporting.py` | Собирает ответ в блоки `input_data`, `recommended_models`, `calculations`, `limitations` |
| Observability | `mws_assistant/observability.py` | Счетчики, тайминги, логирование |
| Внешний источник данных | MWS documentation | Источник моделей и цен |

## Поток запроса

```text
Client
  -> api.py
  -> agent.py
  -> run_mws_assistant()
  -> coordinator.py
  -> mws_catalog.py
  -> recommendation.py
  -> estimation.py
  -> reporting.py
  -> agent.py
  -> api.py
  -> Client
```

## Почему здесь один tool

В проекте специально используется **один high-level tool**: `run_mws_assistant()`

- агенту не дается свобода самому вручную дергать каталог, расчет и ранжирование по частям
- весь критичный pipeline контролируется Python-кодом
- уменьшается вероятность галлюцинаций и ошибок в порядке шагов
- проще тестировать и логировать систему

Это осознанное архитектурное решение.


## Где именно работает LLM

LLM участвует в:

- интерпретации пользовательского сообщения
- уточнении недостающих вводных
- выборе момента для tool call
- человеко-понятном пересказе результата

LLM **не отвечает** за:

- загрузку каталога
- определение цен
- ranking моделей
- cost estimation
- структуру итогового отчета


## Почему архитектура интерпретируемая

Если ответ агента выглядит странно, можно отдельно проверить:

- что было собрано на входе
- какой payload ушел в tool
- какие модели пришли из каталога
- как именно был посчитан ranking
- как именно была рассчитана стоимость
- что попало в финальный отчет

Из-за этого система легче отлаживается и лучше подходит для практической работы на стажировку, чем prompt-only решение
