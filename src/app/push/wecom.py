"""企业微信群机器人 webhook 推送。httpx 发 POST，代表"通知保安"。

纯副作用层，可单独测。消息用 markdown，便于群里一眼看清登记。
"""

from __future__ import annotations

import httpx
from loguru import logger

from app.config import get_settings


def _format_markdown(plate: str, company: str, phone: str, reason: str) -> str:
    return (
        "## 🚗 访客登记\n"
        f"> 车牌：**{plate}**\n"
        f"> 单位：**{company}**\n"
        f"> 手机：**{phone}**\n"
        f"> 事由：{reason}\n"
    )


async def push_registration(
    plate: str, company: str, phone: str, reason: str, *, webhook_url: str | None = None
) -> None:
    """把一条登记推到企微群。失败抛异常（由调用方决定如何处理）。"""
    url = webhook_url or get_settings().wecom_webhook_url
    if not url:
        raise RuntimeError("未配置 WECOM_WEBHOOK_URL")

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": _format_markdown(plate, company, phone, reason)},
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"企微推送失败: {data}")
    logger.info(f"[PUSH] 已推送登记到企微群 车牌={plate}")


async def push_text(content: str, *, webhook_url: str | None = None) -> None:
    """推一条纯文本（测试/通知用）。"""
    url = webhook_url or get_settings().wecom_webhook_url
    if not url:
        raise RuntimeError("未配置 WECOM_WEBHOOK_URL")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json={"msgtype": "text", "text": {"content": content}})
        resp.raise_for_status()
        data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"企微推送失败: {data}")
