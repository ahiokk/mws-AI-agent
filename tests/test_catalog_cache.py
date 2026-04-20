import asyncio

from mws_assistant import mws_catalog


def test_get_catalog_uses_process_cache(monkeypatch) -> None:
    calls = {"count": 0}

    async def fake_load_catalog_from_mws() -> list[dict]:
        calls["count"] += 1
        return [{"name": "cached-model"}]

    mws_catalog.clear_catalog_cache()
    monkeypatch.setattr(
        mws_catalog,
        "load_catalog_from_mws",
        fake_load_catalog_from_mws,
    )

    first = asyncio.run(mws_catalog.get_catalog())
    second = asyncio.run(mws_catalog.get_catalog())

    assert calls["count"] == 1
    assert first == second
    assert first is not second

    mws_catalog.clear_catalog_cache()
