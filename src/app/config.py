"""集中配置：pydantic-settings 从 .env 读取。密钥永不进仓库。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # —— 阿里云百炼：STT / TTS / LLM 共用同一把 key ——
    dashscope_api_key: str = Field(default="", alias="DASHSCOPE_API_KEY")

    # —— LLM（Qwen，OpenAI 兼容端点）——
    llm_model: str = Field(default="qwen-plus", alias="LLM_MODEL")
    llm_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="LLM_BASE_URL",
    )

    # —— STT（百炼 Paraformer 实时）——
    # 阶段1本地麦 16k 用 paraformer-realtime-v2；阶段4电话(8k)切 paraformer-realtime-8k-v2 + 8000
    stt_model: str = Field(default="paraformer-realtime-v2", alias="STT_MODEL")
    stt_sample_rate: int = Field(default=16000, alias="STT_SAMPLE_RATE")

    # —— TTS（百炼 CosyVoice flash）——
    tts_model: str = Field(default="cosyvoice-v3-flash", alias="TTS_MODEL")
    tts_voice: str = Field(default="longxiaochun_v3", alias="TTS_VOICE")
    # 48k 对齐声卡名义率(虚拟声卡/微信/本机扬声器均 48k)，消除输出路径重采样打架
    tts_sample_rate: int = Field(default=48000, alias="TTS_SAMPLE_RATE")
    # 语速：>1 更利落，帮助压低对话总时长（0.5–2.0）
    tts_speech_rate: float = Field(default=1.15, alias="TTS_SPEECH_RATE")
    # 开场白单独提速，压进 3-4s（措辞固定、不便再短，故靠语速）
    tts_greeting_speech_rate: float = Field(default=1.45, alias="TTS_GREETING_SPEECH_RATE")

    # —— 音频设备（阶段4来电源）——
    # 按设备名子串匹配 PyAudio 设备；留空=系统默认（阶段1-3 本地麦）。
    # 微信语音接入：输入锁 BlackHole 2ch（访客声音），输出锁 BlackHole 16ch（回程给微信麦克风）。
    audio_input_device: str = Field(default="", alias="AUDIO_INPUT_DEVICE")
    audio_output_device: str = Field(default="", alias="AUDIO_OUTPUT_DEVICE")

    # —— PostgreSQL ——
    postgres_user: str = Field(default="voicegate", alias="POSTGRES_USER")
    postgres_password: str = Field(default="voicegate", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="voicegate", alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    # —— 企业微信群机器人 webhook ——
    wecom_webhook_url: str = Field(default="", alias="WECOM_WEBHOOK_URL")

    @property
    def database_url(self) -> str:
        """SQLAlchemy(async) 连接串。"""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def asyncpg_dsn(self) -> str:
        """asyncpg.connect/create_pool 用的 DSN。"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
