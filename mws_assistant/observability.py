import logging

from collections import Counter, defaultdict
from contextlib import contextmanager
from time import perf_counter
from typing import Iterator


# Через него будем печатать метрики в общий лог проекта
LOGGER = logging.getLogger(__name__)

# Храним счетчики событий
# Например: сколько раз сходили в MWS
_COUNTERS = Counter()

# Здесь храним тайминги по именам метрик
# Для каждой метрики будет список значений в секундах
_TIMINGS = defaultdict(list)


def increment_counter(name: str, amount: int = 1) -> None:
    # Увеличиваем счетчик события
    # По умолчанию на 1
    _COUNTERS[name] += amount


def observe_duration(name: str, seconds: float) -> None:
    # Сохраняем время для метрики
    # Потом можно собрать среднее и последнее время
    _TIMINGS[name].append(seconds)


@contextmanager
def measure_time(name: str) -> Iterator[None]:
    # Функция для измерения времени блока кода
    started_at = perf_counter()
    try:
        yield
    finally:
        # Даже если внутри была ошибка, время все равно зафиксируем
        observe_duration(name, perf_counter() - started_at)


def snapshot_metrics() -> dict:
    # Собираем текущее состояние всех метрик в обычный dict
    # Это удобно и для логов, и для API/README
    timing_snapshot = {}
    for metric_name, values in _TIMINGS.items():
        # Пустые метрики пропускаем, чтобы не засорять
        if not values:
            continue

        # Для каждой timing-метрики храним:
        # сколько раз измеряли,
        # последнее значение,
        # среднее значение.
        timing_snapshot[metric_name] = {
            "count": len(values),
            "last_seconds": round(values[-1], 6),
            "avg_seconds": round(sum(values) / len(values), 6),
        }

    return {
        # Приводим Counter к обычному dict, чтобы легко сериализовалось
        "counters": dict(_COUNTERS),
        "timings": timing_snapshot,
    }


def log_metrics_snapshot(prefix: str = "metrics") -> None:
    # Печатаем текущий снапшот метрик в лог.
    # префикс нужен, чтобы в логах было понятно, кто именно его вывел.
    LOGGER.info("%s: %s", prefix, snapshot_metrics())
