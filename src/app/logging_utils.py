"""结构化延迟日志。每轮 STT / LLM / TTS 耗时与"接通到推送"总耗时，
作为 25 秒达标的证据。"""

import logging
import sys
import time

from loguru import logger

_CONFIGURED = False

# —— 接通→推送 总耗时计时 ——
# 本地麦克风单通话场景，模块级单例即可（多路并发是后续加分项）。
DEADLINE_SECONDS = 25.0
_call_t0: float | None = None


def start_call() -> None:
    """接通（门岗开始说第一句开场白）时调用，作为总耗时起点。"""
    global _call_t0
    _call_t0 = time.monotonic()
    logger.info("[计时] 接通——门岗开始说话，开始计时")


def mark_pushed() -> None:
    """企微推送成功返回时调用，落总耗时日志（25s 达标证据）。"""
    global _call_t0
    if _call_t0 is None:
        logger.warning("[计时] mark_pushed 时没有起点（未调用 start_call）")
        return
    elapsed = time.monotonic() - _call_t0
    verdict = "达标 ✅" if elapsed < DEADLINE_SECONDS else "超时 ❌"
    logger.info(f"[计时] 接通→推送 总耗时 {elapsed:.2f}s（阈值 {DEADLINE_SECONDS:.0f}s）{verdict}")
    _call_t0 = None


def setup_logging(level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
