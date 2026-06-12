"""Agent 工具：submit_registration（四字段采齐 + 复述确认后触发）、lookup_visitor（回访，延后）。

业务逻辑与 Pipecat 解耦：这里是纯 async 函数，校验→写库→推企微，返回结构化结果。
Pipecat 的工具注册/回调在 pipeline 侧包装。

校验策略（按约定）：
- 手机号：硬校验，必须 11 位且以 1 开头（挡住 ASR 漏网）。
- 车牌：宽松，仅非空。新能源6位/使领馆/警学挂/港澳格式各异，严正则会误杀合法车牌；
  车牌正确性主要由对话里的"复述确认"兜底，工具不硬驳回。
- 单位/事由：非空。
"""

from __future__ import annotations

import re

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.services.llm_service import FunctionCallParams, LLMService

from app import logging_utils
from app.db import repo
from app.push import wecom

_PHONE_RE = re.compile(r"^1\d{10}$")


def _normalize_plate(plate: str) -> str:
    # 去空格、字母转大写；不做格式裁决
    return re.sub(r"\s+", "", plate or "").upper()


def _normalize_phone(phone: str) -> str:
    # 去掉空格、连字符等分隔符
    return re.sub(r"[\s\-]", "", phone or "")


async def submit_registration(plate: str, company: str, phone: str, reason: str) -> dict:
    """采齐并复述确认后调用：校验 → 写库 → 推企微。

    返回 {"ok": True, "id": int} 或 {"ok": False, "error": str, "ask": str}。
    ask 是给 LLM 的提示，告诉它该向来访者追问/复述什么。
    """
    plate = _normalize_plate(plate)
    phone = _normalize_phone(phone)
    company = (company or "").strip()
    reason = (reason or "").strip()

    # —— 第二道网：格式校验（主门是对话里的复述确认）——
    missing = [
        name
        for name, val in [("车牌", plate), ("单位", company), ("手机号", phone), ("事由", reason)]
        if not val
    ]
    if missing:
        return {
            "ok": False,
            "error": f"缺少字段: {'、'.join(missing)}",
            "ask": f"还差 {'、'.join(missing)} 没采到，请继续询问。",
        }

    if not _PHONE_RE.match(phone):
        return {
            "ok": False,
            "error": f"手机号格式不对: {phone}",
            "ask": "手机号应是 11 位、以 1 开头。请向来访者复述并确认手机号。",
        }

    # 车牌宽松：不硬驳回，但极短明显异常时提示复述
    if len(plate) < 5:
        return {
            "ok": False,
            "error": f"车牌疑似不完整: {plate}",
            "ask": "车牌偏短、可能没听全，请向来访者复述确认车牌。",
        }

    # —— 写库 + 推企微 ——
    try:
        reg = await repo.insert_registration(plate, company, phone, reason)
        await wecom.push_registration(plate, company, phone, reason)
    except Exception as e:  # noqa: BLE001
        logger.exception("[TOOL] submit_registration 失败")
        return {"ok": False, "error": f"提交失败: {e}", "ask": "登记提交出了点问题，请稍等再试。"}

    # 企微推送成功 = "接通→推送" 终点
    logging_utils.mark_pushed()
    logger.info(f"[TOOL] 登记完成 id={reg.id}")
    return {"ok": True, "id": reg.id}


# —— Pipecat 工具注册 ——

SUBMIT_REGISTRATION_SCHEMA = FunctionSchema(
    name="submit_registration",
    description=(
        "把采集齐全、且车牌和手机号已向来访者复述并确认无误的访客登记提交给保安。"
        "只有在四个字段都拿到、并完成复述确认后才调用。"
    ),
    properties={
        "plate": {"type": "string", "description": "车牌号，如 沪A12345 或新能源 沪AD12345"},
        "company": {"type": "string", "description": "来访单位/公司名称"},
        "phone": {"type": "string", "description": "来访者手机号，11 位"},
        "reason": {"type": "string", "description": "来访事由，如 送货、面试、开会"},
    },
    required=["plate", "company", "phone", "reason"],
)


def build_tools_schema() -> ToolsSchema:
    """构造挂到 LLMContext 的工具集。"""
    return ToolsSchema(standard_tools=[SUBMIT_REGISTRATION_SCHEMA])


def register_tools(llm: LLMService) -> None:
    """把 submit_registration 注册到 LLM service。"""

    async def _handle_submit(params: FunctionCallParams) -> None:
        args = params.arguments
        result = await submit_registration(
            plate=args.get("plate", ""),
            company=args.get("company", ""),
            phone=args.get("phone", ""),
            reason=args.get("reason", ""),
        )
        await params.result_callback(result)

    llm.register_function("submit_registration", _handle_submit)
