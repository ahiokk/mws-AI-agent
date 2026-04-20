import json
import logging
import time
import uuid

from aiohttp import web
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

load_dotenv()

from .api_models import (
    ChatCompletionChoice,
    ChatCompletionChoiceMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ModelCard,
    ModelListResponse,
)
from mws_adk_app import app as adk_app


LOGGER = logging.getLogger(__name__)

APP_NAME = "mws_adk_app"
PUBLIC_MODEL_NAME = "mws-assistant"

# Здесь живет серверная история диалога
# Для локальной разработки этого достаточно
SESSION_SERVICE = InMemorySessionService()

# Runner знает про SessionService
# Диалог можно продолжать между запросами
RUNNER = Runner(
    app=adk_app,
    app_name=APP_NAME,
    session_service=SESSION_SERVICE,
    auto_create_session=False,
)


def error_response(message: str, error_type: str, status: int) -> web.Response:
    # Небольшой хелпер чтобы все ошибки были в одном формате
    return web.json_response(
        {
            "error": {
                "message": message,
                "type": error_type,
            }
        },
        status=status,
    )


def messages_to_prompt(messages) -> str:
    parts = []
    for message in messages:
        role = message.role.upper()
        content = message.content or ""
        parts.append(f"{role}: {content}")
    return "\n\n".join(parts)


def extract_latest_user_message(messages) -> str:
    # Для уже существующей серверной сессии берем только новое сообщение юзера
    for message in reversed(messages):
        if message.role == "user" and message.content:
            return message.content
    return ""


def build_user_content(text: str) -> types.Content:
    '''
    Маленький адаптер между нашим API и ADK
    '''
    # ADK run_async ждет Content, а не просто str
    return types.Content(
        role="user",
        parts=[types.Part(text=text)],
    )


def extract_text_from_event(event) -> str:
    # Достаем текст из одного события
    if not event.content or not event.content.parts:
        return ""

    text_parts = [
        part.text
        for part in event.content.parts
        if getattr(part, "text", None)
    ]
    return "".join(text_parts)


def extract_final_text_from_events(events: list) -> str:
    # Для обычного non-stream режима собираем финальный текст из event-ов
    streamed_parts: list[str] = []

    for event in events:
        event_text = extract_text_from_event(event)

        if getattr(event, "partial", False):
            if event_text:
                streamed_parts.append(event_text)
            continue

        if event.is_final_response():
            if streamed_parts:
                if event_text:
                    streamed_parts.append(event_text)
                return "".join(streamed_parts).strip()

            if event_text:
                return event_text.strip()

    if streamed_parts:
        return "".join(streamed_parts).strip()

    return "Assistant returned no text response."


def extract_usage_from_events(events: list) -> ChatCompletionUsage:
    # usage берем из последнего event где ADK уже отдал token metadata
    for event in reversed(events):
        usage = getattr(event, "usage_metadata", None)
        if usage is None:
            continue

        return ChatCompletionUsage(
            prompt_tokens=usage.prompt_token_count or 0,
            completion_tokens=usage.candidates_token_count or 0,
            total_tokens=usage.total_token_count or 0,
        )

    # Если backend usage не прислал, даем безопасный fallback
    return ChatCompletionUsage(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
    )


def build_stream_chunk(
    *,
    completion_id: str,
    created: int,
    delta: dict,
    finish_reason: str | None = None,
) -> dict:
    # Один chunk в формате OpenAI-compatible streaming response
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": PUBLIC_MODEL_NAME,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def resolve_user_id(request: web.Request, payload: ChatCompletionRequest) -> str:
    # Сначала берем user из body
    # Потом смотрим optional header
    # Потом даем дефолт
    return payload.user or request.headers.get("X-User-Id") or "openai_api_user"


def resolve_session_id(request: web.Request, payload: ChatCompletionRequest) -> str:
    # session_id можно прислать либо в body, либо в header
    # если ничего нет, создаем новую серверную сессию
    return (
        payload.session_id
        or request.headers.get("X-Session-Id")
        or f"session-{uuid.uuid4().hex}"
    )


async def ensure_session_exists(user_id: str, session_id: str) -> bool:
    # Проверяем, была ли сессия до этого запроса
    session = await SESSION_SERVICE.get_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    if session is not None:
        return True

    await SESSION_SERVICE.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={},
    )
    return False


def build_new_message_text(payload: ChatCompletionRequest, session_exists: bool) -> str:
    # Если серверная сессия уже существует, передаем только новый user input
    latest_user_message = extract_latest_user_message(payload.messages)

    if session_exists and latest_user_message:
        return latest_user_message

    # Если сессия новая или user-сообщение не удалось выделить,
    # один раз seed-им ее всей историей
    return messages_to_prompt(payload.messages)


async def collect_runner_events(
    *,
    user_id: str,
    session_id: str,
    new_message: types.Content,
) -> list:
    events = []
    async for event in RUNNER.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        events.append(event)
    return events


async def health(request: web.Request) -> web.Response:
    # быстрый тест, жив ли сервер
    return web.json_response({"status": "ok"})


async def list_models(request: web.Request) -> web.Response:
    # Возвращает GET /v1/models
    response = ModelListResponse(
        data=[
            ModelCard(
                id=PUBLIC_MODEL_NAME,
                created=int(time.time()),
            )
        ]
    )
    return web.json_response(response.model_dump())


async def chat_completions(request: web.Request) -> web.StreamResponse | web.Response:
    # Сначала пробуем прочитать raw JSON из тела запроса
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return error_response(
            "Request body must be valid JSON",
            "invalid_request_error",
            400,
        )

    # Потом валидируем структуру уже через pydantic модель
    try:
        payload = ChatCompletionRequest(**body)
    except ValidationError as exc:
        return error_response(
            f"Invalid request payload: {exc.errors()}",
            "invalid_request_error",
            400,
        )

    # Наружу даем только один публичный alias модели
    if payload.model != PUBLIC_MODEL_NAME:
        return error_response(
            f"Unknown model: {payload.model}",
            "invalid_request_error",
            400,
        )

    LOGGER.info("OpenAI compatible request received for model=%s", payload.model)

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    # Разруливаем user и session чтобы можно было продолжать диалог
    user_id = resolve_user_id(request, payload)
    session_id = resolve_session_id(request, payload)
    session_exists = await ensure_session_exists(user_id, session_id)

    # Для новой сессии seed-им историю целиком
    # Для существующей берем только новый user input
    new_message_text = build_new_message_text(payload, session_exists)
    new_message = build_user_content(new_message_text)

    LOGGER.info(
        "Resolved session for request: user_id=%s session_id=%s session_exists=%s",
        user_id,
        session_id,
        session_exists,
    )

    if payload.stream:
        # В stream режиме сразу открываем SSE ответ
        # И дальше шлем чанки по мере прихода ADK event-ов
        LOGGER.info("Returning real event-based streaming response")

        stream_response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-Id": session_id,
            },
        )
        await stream_response.prepare(request)

        # Первый chunk сообщает клиенту что дальше говорит assistant
        initial_chunk = build_stream_chunk(
            completion_id=completion_id,
            created=created,
            delta={"role": "assistant"},
        )
        await stream_response.write(
            f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
        )

        try:
            async for event in RUNNER.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                # Из каждого event достаем текст если он там есть
                event_text = extract_text_from_event(event)

                if event_text:
                    # Текст сразу отдаем наружу как content chunk
                    content_chunk = build_stream_chunk(
                        completion_id=completion_id,
                        created=created,
                        delta={"content": event_text},
                    )
                    await stream_response.write(
                        f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                    )

                if event.is_final_response():
                    # Как только ADK прислал финальный ответ, закрываем поток красиво
                    final_chunk = build_stream_chunk(
                        completion_id=completion_id,
                        created=created,
                        delta={},
                        finish_reason="stop",
                    )
                    await stream_response.write(
                        f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
                    )
                    await stream_response.write(b"data: [DONE]\n\n")
                    await stream_response.write_eof()
                    return stream_response

        except Exception:
            # Ошибку тоже отдаём внутрь SSE чтобы клиент не повис молча
            LOGGER.exception("Failed to stream assistant response via ADK runner")
            error_chunk = {
                "error": {
                    "message": "Internal error while streaming assistant response",
                    "type": "internal_server_error",
                }
            }
            await stream_response.write(
                f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
            )
            await stream_response.write(b"data: [DONE]\n\n")
            await stream_response.write_eof()
            return stream_response

        # На случай если поток закончился без явного final event
        final_chunk = build_stream_chunk(
            completion_id=completion_id,
            created=created,
            delta={},
            finish_reason="stop",
        )
        await stream_response.write(
            f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode("utf-8")
        )
        await stream_response.write(b"data: [DONE]\n\n")
        await stream_response.write_eof()
        return stream_response

    # В обычном режиме сначала собираем все runner events
    # Потом уже достаем из них финальный assistant text
    try:
        events = await collect_runner_events(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        )
        assistant_text = extract_final_text_from_events(events)
        usage = extract_usage_from_events(events)
    except Exception:
        LOGGER.exception("Failed to generate assistant response via ADK runner")
        return error_response(
            "Internal error while generating assistant response",
            "internal_server_error",
            500,
        )

    # Собираем обычный OpenAI-compatible JSON ответ
    response = ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=PUBLIC_MODEL_NAME,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionChoiceMessage(content=assistant_text),
                finish_reason="stop",
            )
        ],
        usage=usage,
    )

    # session_id возвращаем клиенту чтобы он мог продолжить тот же диалог
    return web.json_response(
        response.model_dump(),
        headers={"X-Session-Id": session_id},
    )


def create_app() -> web.Application:
    # Регистрирует маршруты:
    # /health
    # /v1/models
    # /v1/chat/completions
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/v1/models", list_models)
    app.router.add_post("/v1/chat/completions", chat_completions)
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    web.run_app(create_app(), host="127.0.0.1", port=8080)
