"""db/repo.py 增查测试。需要本地 postgres 已起（docker compose up -d）。"""

import pytest

from app.db import repo


@pytest.mark.asyncio
async def test_insert_and_find_by_plate():
    plate = "测A·TEST1"
    reg = await repo.insert_registration(
        plate=plate, company="测试单位", phone="13800000000", reason="送货"
    )
    assert reg.id > 0
    assert reg.plate == plate
    assert reg.created_at is not None

    found = await repo.find_by_plate(plate)
    assert any(r.id == reg.id for r in found)

    await repo.close_pool()
