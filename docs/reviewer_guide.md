# Reviewer Guide

Этот документ помогает быстро проверить проект без необходимости разбираться во всех файлах подряд

## Что смотреть в первую очередь

1. [README.md](../README.md)
2. [architecture_overview.md](architecture_overview.md)
3. автоматические тесты в [tests](../tests)
4. showcase-артефакты ручного прогона в [reviewer_runs/qwen3-235b-instruct](reviewer_runs/qwen3-235b-instruct)

## Что именно демонстрирует проект

- Google ADK как диалоговый слой
- OpenAI-compatible API
- dynamic parsing каталога и цен MWS
- deterministic recommendation и cost estimation
- structured report
- server-side session
- event-based streaming
- validation, observability и process cache

## Быстрый маршрут проверки

Если смотреть проект по-быстрому, я бы шел в таком порядке:

### 1. Архитектура

- [architecture_overview.md](architecture_overview.md)
- [architecture.png](architecture.png)

### 2. Автоматические тесты

Запуск:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Покрыто:

- API
- validation
- recommendation
- estimation
- catalog cache

### 3. Ручные showcase-сценарии

Основные артефакты ручной проверки лежат в:

- [reviewer_runs/qwen3-235b-instruct](reviewer_runs/qwen3-235b-instruct)

## Рекомендуемые showcase-сценарии

| Сценарий | Что показывает | Артефакты |
| --- | --- | --- |
| `1. Недостаточно вводных` | агент не делает расчет слишком рано и задает короткие уточнения | [JSON](<reviewer_runs/qwen3-235b-instruct/1. Недостаточно вводных.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/1. Недостаточно вводных.png>) |
| `2. Embedding-кейс` | special-case для embedding без output tokens | [JSON](<reviewer_runs/qwen3-235b-instruct/2. Embedding-кейс.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/2. Embedding-кейс.png>) |
| `4. Продолжение той же сессии` | server-side session и follow-up без повторного ввода всего сценария | [JSON](<reviewer_runs/qwen3-235b-instruct/4. Продолжение той же сессии.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/4. Продолжение той же сессии.png>) |
| `5. Нереалистичный бюджет` | честный ответ, когда ни одна модель не укладывается в бюджет | [JSON](<reviewer_runs/qwen3-235b-instruct/5. Нереалистичный бюджет.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/5. Нереалистичный бюджет.png>) |
| `6. RAG-кейс` | корректный use case для документного QA / RAG | [JSON](<reviewer_runs/qwen3-235b-instruct/6. RAG-кейс.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/6. RAG-кейс.png>) |
| `7. Защита от выдумывания моделей и цен` | устойчивость к попытке заставить ассистента игнорировать MWS catalog | [JSON](<reviewer_runs/qwen3-235b-instruct/7. Защита от выдумывания моделей и цен.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/7. Защита от выдумывания моделей и цен.png>) |
| `8. Follow-up после расчета` | агент не должен выдумывать новые модели после уже полученного tool result | [JSON](<reviewer_runs/qwen3-235b-instruct/8. Follow-up после расчета.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/8. Follow-up после расчета.png>) |
| `9. Сравнение базовых и акционных цен` | различение `base`, `promo` и follow-up пересчет того же сценария | [JSON](<reviewer_runs/qwen3-235b-instruct/9. Сравнение базовых и акционных цен.json>) / [PNG](<reviewer_runs/qwen3-235b-instruct/9. Сравнение базовых и акционных цен.png>) |

## Что важно в этих сценариях

Я проверял:

- не галлюцинирует ли агент модели и цены
- не делает ли молчаливые допущения по output tokens
- правильно ли обрабатывает эмбеддинг-кейсы
- правильно ли использует сессию между запросами
- различает ли базовую и промо расценку
- остаются ли recommendation и estimation в deterministic code path

## Если нужно проверить API отдельно

Ключевые endpoints:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`

API поддерживает:

- обычный ответ
- `stream=True`
- `session_id`
- `X-Session-Id`
