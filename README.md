# MWS GPT Model Selection Assistant

Сервис-ассистент для подбора моделей из MWS GPT Model Hub под продуктовый кейс, нагрузку и бюджет

Проект использует:
- динамический парсинг каталога и цен MWS
- собственное deterministic ядро для recommendation и estimation
- Google ADK как агентный слой
- OpenAI-compatible API для внешнего доступа

## Что умеет

- загружать актуальные модели и цены с сайта MWS во время работы сервиса
- рекомендовать подходящие модели под `chat`, `coding`, `analysis`, `embedding`
- оценивать стоимость использования по пользовательскому сценарию
- учитывать promo/base pricing
- строить структурированный отчет из 4 блоков:
  - `input_data`
  - `recommended_models`
  - `calculations`
  - `limitations`
- работать как через ADK, так и через OpenAI-compatible HTTP API
- отдавать обычный ответ и `stream=True`

## ТЗ

| Требование | Статус | Комментарий |
| --- | --- | --- |
| OpenAI-compatible API | Да | Реализованы `GET /v1/models`, `GET /health`, `POST /v1/chat/completions` |
| Google ADK | Да | Ассистент построен на ADK agent + tool |
| Dynamic pricing from MWS | Да | Каталог и цены динамически парсятся с сайта MWS |
| Cost estimation | Да | Есть расчет стоимости с учетом promo/base и 24h billing approximation |
| Structured report | Да | Отчет собирается в блоки `input_data`, `recommended_models`, `calculations`, `limitations` |
| Dialog in session | Да | Поддерживается через ADK `SessionService` и `session_id` |
| Tests | Да | Есть автотесты для estimation, recommendation и validation |
| Observability | Да | Есть логирование, тайминги и простые счетчики |
| Input validation | Да | Есть pydantic validation layer |
| `stream=True` | Да | Реализован event-based SSE-ответ в OpenAI-compatible формате |

## Выбранный архитектурный паттерн

Использован паттерн `single root ADK agent + deterministic tool-backed core`

Смысл такой:
- агент отвечает за диалог, сбор недостающих вводных и вызов инструмента
- бизнес-логика не прячется в prompt
- recommendation, estimation, reporting и catalog parsing реализованы отдельными Python-модулями
- tool в ADK только связывает диалоговый слой с ядром

Это уменьшает вероятность галлюцинаций и делает систему объяснимой и тестируемой

## Архитектура

Текстовая схема потока запроса

`Client -> OpenAI-compatible API -> ADK root agent -> tool run_mws_assistant -> coordinator -> catalog/recommendation/estimation/reporting -> API response`

![Архитектура сервиса](docs/architecture.png)

Роли слоев:
- `mws_assistant/mws_catalog.py` — загрузка и нормализация каталога моделей и прайсов MWS
- `mws_assistant/recommendation.py` — фильтрация и ранжирование моделей
- `mws_assistant/estimation.py` — расчет стоимости и 24h billing approximation
- `mws_assistant/reporting.py` — сбор финального структурированного отчета
- `mws_assistant/coordinator.py` — orchestration всего pipeline
- `mws_adk_app/agent.py` — ADK agent и tool behavior
- `mws_assistant/api.py` — OpenAI-compatible HTTP API

## Структура проекта

```text
.
├── mws_assistant/
│   ├── __init__.py
│   ├── api.py
│   ├── api_models.py
│   ├── coordinator.py
│   ├── estimation.py
│   ├── mws_catalog.py
│   ├── observability.py
│   ├── recommendation.py
│   ├── reporting.py
│   └── validation.py
├── mws_adk_app/
│   ├── __init__.py
│   └── agent.py
├── tests/
│   ├── test_api.py
│   ├── test_catalog_cache.py
│   ├── test_estimation.py
│   ├── test_recommendation.py
│   └── test_validation.py
├── docs/
│   └── architecture.png
└── .env_example
```

## Локальный запуск

### 1. Создать и активировать venv

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Установить зависимости

Минимальный набор библиотек уже зафиксирован в `requirements.txt`

```powershell
python -m pip install -r requirements.txt
```

### 3. Заполнить `.env`

Пример есть в `.env_example`

Нужно указать:

```env
OPENAI_API_KEY=<API key сервисного аккаунта MWS>
OPENAI_API_BASE=https://gpt.mwsapis.ru/projects/<project>/openai/v1
MODEL_NAME=qwen3-235b-instruct
PYTHONUTF8=1
```

### 4. Запустить HTTP API

```powershell
.venv\Scripts\python.exe -m mws_assistant.api
```

Сервер поднимется на:

```text
http://127.0.0.1:8080
```

### 5. Запустить ADK web UI

```powershell
adk web
```

После этого можно открыть локальный ADK UI и поработать с агентом напрямую

## Запуск через Docker

### Поднять API

```powershell
docker compose up --build api
```

После этого API будет доступен на:

```text
http://127.0.0.1:8080
```

Контейнер использует переменные из `.env`

### Прогнать тесты в контейнере

```powershell
docker compose --profile test up --build tests
```

### Остановить контейнеры

```powershell
docker compose down
```

Что именно завернуто в Docker:
- OpenAI-compatible API
- ADK agent, который вызывается из API
- все deterministic модули ядра

Что не завернуто отдельно:
- `adk web`

## Доступные API endpoints

### `GET /health`

Проверка, что сервер жив

Пример ответа:

```json
{"status": "ok"}
```

### `GET /v1/models`

Возвращает список доступных публичных моделей API

Сейчас наружу отдается один alias:
- `mws-assistant`

### `POST /v1/chat/completions`

Основной OpenAI-compatible endpoint

Поддерживает:
- `model`
- `messages`
- `stream`
- `user`
- `session_id`

Также можно передавать `X-Session-Id` header

## Пример обычного запроса

PowerShell:

```powershell
$body = @{
  model = "mws-assistant"
  messages = @(
    @{
      role = "user"
      content = "Подбери дешевую модель для эмбеддингов"
    }
  )
  stream = $false
} | ConvertTo-Json -Depth 5

Invoke-RestMethod `
  -Uri "http://127.0.0.1:8080/v1/chat/completions" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body
```

Сервер вернет `X-Session-Id`, который можно использовать для продолжения того же диалога

Пример ответа:

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1776687907,
  "model": "mws-assistant",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1227,
    "completion_tokens": 106,
    "total_tokens": 1333
  }
}
```

## Пример stream запроса

PowerShell:

```powershell
$body = @{
  model = "mws-assistant"
  messages = @(
    @{
      role = "user"
      content = "Подбери дешевую модель для эмбеддингов"
    }
  )
  stream = $true
} | ConvertTo-Json -Depth 5

Set-Content -Path stream_request.json -Value $body -Encoding utf8
curl.exe -N -X POST "http://127.0.0.1:8080/v1/chat/completions" -H "Content-Type: application/json" --data-binary "@stream_request.json"
```

Ответ идет как SSE:
- `chat.completion.chunk`
- затем `data: [DONE]`
- чанки отдаются из ADK event stream

## Как собирается итоговый ответ

После tool-вызова API возвращает структуру, которая опирается на отчет из:
- `input_data`
- `recommended_models`
- `calculations`
- `limitations`

То есть ассистент использует реальный вычисленный отчет

## Тесты

Запуск:

```powershell
.venv\Scripts\python.exe -m pytest -v
```

Что покрыто:
- 24h billing approximation
- recommendation logic
- входная pydantic validation
- OpenAI-compatible API endpoints
- server-side session behavior
- SSE streaming response format

## Observability

В проекте есть минимальная observability:
- счетчики запросов к MWS
- cache hit / miss для каталога
- тайминги каталога
- тайминг полного assistant flow
- подробные логи agent/tool/coordinator

Основной код метрик лежит в `mws_assistant/observability.py`

## Ограничения текущей реализации

- server-side session хранится в `InMemorySessionService`, то есть теряется после рестарта процесса
- каталог кешируется только в рамках Python процесса и тоже теряется после рестарта
- `usage` в обычном non-stream ответе заполняется из ADK usage metadata
- для `stream=True` отдельный финальный usage block пока не добавлен
- 24h billing rule смоделирован на дневной агрегации, а не на почасовом уровне
- каталог MWS парсится по HTML, поэтому при серьезных изменениях в верстке MWS может потребоваться адаптация парсера

## Почему решение выглядит инженерно

- прайсы не захардкожены
- recommendation и estimation не спрятаны в prompt
- agent не делает молчаливые assumptions для cost estimation
- вход валидируется отдельным слоем
- есть тесты и базовые метрики

## Что можно улучшить дальше

- сделать persistent cache каталога между рестартами
- добавить usage block и для `stream=True`
- покрыть тестами API и parser
