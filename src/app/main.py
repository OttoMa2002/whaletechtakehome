"""入口：组装并启动 pipeline。

阶段 1：本地麦克风语音闭环。对着 Mac 麦克风说话，门岗 agent 用语音回应。
"""

import asyncio

from loguru import logger

from pipecat.workers.runner import WorkerRunner

from app.config import get_settings
from app.pipeline import build_worker


async def run() -> None:
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY，请在 .env 中配置")

    logger.info("园区访客语音登记 Agent —— 阶段 1 本地麦克风闭环")
    logger.info(f"STT={settings.stt_model}@{settings.stt_sample_rate}  "
                f"LLM={settings.llm_model}  "
                f"TTS={settings.tts_model}/{settings.tts_voice}@{settings.tts_sample_rate}")

    worker = build_worker(settings)
    runner = WorkerRunner()
    await runner.add_workers(worker)
    logger.info("开始监听麦克风（Ctrl+C 退出）……")
    await runner.run()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("已退出")


if __name__ == "__main__":
    main()
