"""入口：组装并启动 pipeline。

阶段 0 只做"空跑"——加载配置、初始化日志、打印就绪信息后退出，
用于验证脚手架可启动、配置可读。后续阶段在此组装 Pipecat 管线。
"""

from app.config import get_settings
from app.logging_utils import get_logger, setup_logging


def main() -> None:
    setup_logging()
    log = get_logger("app.main")

    settings = get_settings()

    log.info("园区访客语音登记 Agent —— 阶段 0 脚手架启动")
    log.info("LLM 模型: %s", settings.llm_model)
    log.info("STT 模型: %s (%dHz)", settings.stt_model, settings.stt_sample_rate)
    log.info("TTS 模型: %s (%dHz)", settings.tts_model, settings.tts_sample_rate)
    log.info("数据库: %s:%s/%s", settings.postgres_host, settings.postgres_port, settings.postgres_db)
    log.info("DASHSCOPE_API_KEY 是否已配置: %s", bool(settings.dashscope_api_key))
    log.info("WECOM webhook 是否已配置: %s", bool(settings.wecom_webhook_url))
    log.info("脚手架就绪，空跑结束。")


if __name__ == "__main__":
    main()
