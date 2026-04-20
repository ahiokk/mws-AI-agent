from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


# Одна реплика в формате OpenAI compatible chat API
# role показывает кто это сказал
# content это сам текст сообщения
class ChatMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None


# Входной запрос в наш /v1/chat/completions
# Здесь описываем минимальный контракт который поддерживает API
class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    model: str = "mws-assistant"
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float | None = None
    user: str | None = None
    session_id: str | None = None


# То как assistant message выглядит уже в ответе API
class ChatCompletionChoiceMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str


# Один choice в стиле OpenAI
# Пока у нас один ответ, но формат держим совместимым
class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionChoiceMessage
    finish_reason: Literal["stop"] = "stop"


# usage пока у нас упрощенный
# Но поле нужно чтобы ответ был похож на OpenAI format
class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


# Полный обычный ответ для /v1/chat/completions когда stream=False
class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


# Одна "модель" в ответе /v1/models
# По факту это не сырой MWS endpoint, а наш публичный alias ассистента
class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int
    owned_by: str = "mws-assistant"


# Ответ со списком моделей которые отдает API
class ModelListResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]
