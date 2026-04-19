import asyncio
import logging
import re

from datetime import date
from decimal import Decimal

import httpx
from bs4 import BeautifulSoup


LOGGER = logging.getLogger(__name__)


MODELS_URL = "https://mws.ru/docs/cloud-platform/gpt/general/gpt-models.html"
PRICING_URL = "https://mws.ru/docs/cloud-platform/gpt/general/pricing.html"

MODELS_REQUIRED_HEADERS = {
    "Параметр",
    "Разработчик",
    "Формат ввода",
    "Формат вывода",
    "Контекст, в тысячах токенов",
    "Размер модели, в млрд. параметров",
}

PRICING_REQUIRED_HEADERS = {
    "Модель",
    "Отпускная единица, в токенах",
}

RUSSIAN_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}
# шаблон поиска даты начало и конца акций
PROMO_PERIOD_RE = re.compile(
    r"в период акции с (\d{1,2}) ([а-я]+) по (\d{1,2}) ([а-я]+)",
    re.IGNORECASE,
)


async def fetch_html(client: httpx.AsyncClient, url: str) -> str:
    LOGGER.info("Fetching HTML from %s", url)
    response = await client.get(url)
    response.raise_for_status()
    LOGGER.info("Fetched %s with status %s", url, response.status_code)
    return response.text


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").split()).strip()


def parse_html_tables(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    parsed_tables = []
    tables = soup.find_all("table")

    LOGGER.info("Found %s HTML tables", len(tables))

    for table_index, table in enumerate(tables):
        first_row = table.find("tr")
        if not first_row:
            LOGGER.warning("Skipping table %s without header row", table_index)
            continue

        headers = [
            normalize_text(cell.get_text(" ", strip=True))
            for cell in first_row.find_all(["th", "td"])
        ]

        rows = []
        for row in table.find_all("tr")[1:]:
            cells = [
                normalize_text(cell.get_text(" ", strip=True))
                for cell in row.find_all(["th", "td"])
            ]

            if not cells or len(cells) != len(headers):
                LOGGER.warning(
                    "Skipping row in table %s because cells count %s does not match headers count %s",
                    table_index,
                    len(cells),
                    len(headers),
                )
                continue

            rows.append(dict(zip(headers, cells)))

        parsed_tables.append({"headers": headers, "rows": rows})
        LOGGER.info(
            "Parsed table %s with %s headers and %s rows",
            table_index,
            len(headers),
            len(rows),
        )

    return parsed_tables


def find_table_by_headers(tables: list[dict], required_headers: set[str]) -> dict:
    for table_index, table in enumerate(tables):
        headers = set(table["headers"])
        if required_headers.issubset(headers):
            LOGGER.info(
                "Matched table %s by required headers: %s",
                table_index,
                sorted(required_headers),
            )
            return table

    LOGGER.error("Could not find table with required headers: %s", sorted(required_headers))
    raise ValueError("Подходящая таблица не найдена")


def parse_modalities(raw_value: str) -> list[str]:
    parts = [part.strip() for part in raw_value.split(",")]
    return [part for part in parts if part]


def parse_price(raw_value: str) -> Decimal | None:
    value = normalize_text(raw_value)

    if value in {"–", "-", ""}:
        return None

    value = value.replace("₽", "").replace(" ", "").replace(",", ".")
    return Decimal(value)


def parse_int(raw_value: str) -> int:
    return int(normalize_text(raw_value).replace(" ", ""))


def parse_float(raw_value: str) -> float:
    return float(normalize_text(raw_value).replace(",", "."))


def find_column_name(
    row: dict,
    include_text: str,
    exclude_text: str | None = None,
) -> str:
    for column_name in row:
        if include_text not in column_name:
            continue
        if exclude_text and exclude_text in column_name:
            continue
        return column_name

    LOGGER.error(
        "Could not find column. include_text=%r exclude_text=%r available_columns=%s",
        include_text,
        exclude_text,
        list(row.keys()),
    )
    raise ValueError(f"Колонка не найдена: {include_text}")


def find_optional_column_name(
        row: dict,
        include_text: str,
        exclude_text: str | None = None,
) -> str | None:
    for column_name in row:
        if include_text not in column_name:
            continue
        if exclude_text and exclude_text in column_name:
            return column_name
        
    return None


def parse_promo_period(
        column_name: str | None,
        reference_date: date | None = None,
) -> tuple[date | None, date | None]:
    if not column_name:
        return None, None
    
    match = PROMO_PERIOD_RE.search(column_name)
    if not match:
        return None, None
    
    reference_date = reference_date or date.today()
    start_day = int(match.group(1))
    start_month = RUSSIAN_MONTHS[match.group(2).lower]
    end_day = int(match.group(3))
    end_month = RUSSIAN_MONTHS[match.group(4).lower()]

    start_year = reference_date.year
    end_year = reference_date.year if end_month >= start_month else reference_date.year + 1

    promo_start = date(start_year, start_month, start_year)
    promo_end = date(end_year, end_month, end_day)

    return promo_start, promo_end


def normalize_pricing_row(row: dict) -> dict:
    promo_input_column = find_optional_column_name(
        row,
        "Цена за 1000 входящих токенов, с НДС 22% в период акции",
    )
    promo_output_column = find_optional_column_name(
        row,
        "Цена за 1000 исходящих токенов, с НДС 22% в период акции",
    )
    base_input_column = find_column_name(
        row,
        "Цена за 1000 входящих токенов, с НДС 22%",
        exclude_text="в период акции",
    )
    base_output_column = find_column_name(
        row,
        "Цена за 1000 исходящих токенов, с НДС 22%",
        exclude_text="в период акции",
    )

    promo_period_source = promo_input_column or promo_output_column
    promo_start_date, promo_end_date = parse_promo_period(promo_period_source)


    return {
        "name": row["Модель"],
        "promo_input_price_per_1k": parse_price(row[promo_input_column]) if promo_input_column else None,
        "promo_output_price_per_1k": parse_price(row[promo_output_column]) if promo_output_column else None,
        "promo_start_date": promo_start_date,
        "promo_end_date": promo_end_date,
        "base_input_price_per_1k": parse_price(row[base_input_column]),
        "base_output_price_per_1k": parse_price(row[base_output_column]),
        "billing_unit_tokens": parse_int(row['Отпускная единица, в токенах']),
    }


def normalize_pricing_row(row: dict) -> dict:
    promo_input_column = find_column_name(
        row,
        "Цена за 1000 входящих токенов, с НДС 22% в период акции",
    )
    promo_output_column = find_column_name(
        row,
        "Цена за 1000 исходящих токенов, с НДС 22% в период акции",
    )
    base_input_column = find_column_name(
        row,
        "Цена за 1000 входящих токенов, с НДС 22%",
        exclude_text="в период акции",
    )
    base_output_column = find_column_name(
        row,
        "Цена за 1000 исходящих токенов, с НДС 22%",
        exclude_text="в период акции",
    )

    return {
        "name": row["Модель"],
        "promo_input_price_per_1k": parse_price(row[promo_input_column]),
        "promo_output_price_per_1k": parse_price(row[promo_output_column]),
        "base_input_price_per_1k": parse_price(row[base_input_column]),
        "base_output_price_per_1k": parse_price(row[base_output_column]),
        "billing_unit_tokens": parse_int(row["Отпускная единица, в токенах"]),
    }


def extract_models(html: str) -> list[dict]:
    tables = parse_html_tables(html)
    models_table = find_table_by_headers(tables, MODELS_REQUIRED_HEADERS)
    models = [normalize_model_row(row) for row in models_table["rows"]]
    LOGGER.info("Extracted %s models", len(models))
    return models


def extract_pricing(html: str) -> list[dict]:
    tables = parse_html_tables(html)
    pricing_table = find_table_by_headers(tables, PRICING_REQUIRED_HEADERS)
    pricing = [normalize_pricing_row(row) for row in pricing_table["rows"]]
    LOGGER.info("Extracted %s pricing rows", len(pricing))
    return pricing


def merge_models_and_pricing(models: list[dict], pricing: list[dict]) -> list[dict]:
    LOGGER.info(
        "Merging %s models with %s pricing rows",
        len(models),
        len(pricing),
    )
    pricing_by_name = {item["name"]: item for item in pricing}
    model_names = {item["name"] for item in models}

    result = []
    for model in models:
        price_info = pricing_by_name.get(model["name"])
        if not price_info:
            LOGGER.warning("No pricing found for model %s", model["name"])
            continue

        merged_item = {
            **model,
            **price_info,
        }
        result.append(merged_item)

    extra_pricing_names = set(pricing_by_name) - model_names
    if extra_pricing_names:
        LOGGER.warning("Pricing exists for unknown models: %s", sorted(extra_pricing_names))

    LOGGER.info("Merged catalog contains %s records", len(result))
    return result


async def get_catalog() -> list[dict]:
    LOGGER.info('Loading full MWS catalog')

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        models_html = await fetch_html(client, MODELS_URL)
        pricing_html = await fetch_html(client, PRICING_URL)

    models = extract_models(models_html)
    pricing = extract_pricing(pricing_html)
    merged_catalog = merge_models_and_pricing(models, pricing)

    LOGGER.info('Loaded full catalog with %s records', len(merged_catalog))
    return merged_catalog


async def main() -> None:
    catalog = await get_catalog()
    LOGGER.info("Sample merged catalog: %s", catalog[:2])


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(main())
