"""企微推送测试。

默认跳过真实网络推送（避免 CI 往群里发消息）。
本地手动验证真实推送：RUN_WECOM_PUSH=1 uv run pytest tests/test_push.py -q -s
"""

import os

import pytest

from app.push import wecom


def test_format_markdown_contains_fields():
    md = wecom._format_markdown("沪A12345", "蓝色鲸鱼", "13800000000", "送货")
    for token in ["沪A12345", "蓝色鲸鱼", "13800000000", "送货"]:
        assert token in md


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_WECOM_PUSH") != "1", reason="设 RUN_WECOM_PUSH=1 才发真实推送"
)
async def test_push_registration_real():
    await wecom.push_registration(
        plate="沪AD12345", company="蓝色鲸鱼（测试）", phone="13800000000", reason="阶段2推送测试"
    )
