"""独立验证 CosyVoice TTS：文本 → 音频文件。

用法：
    uv run python scripts/test_tts.py ["要合成的文本"]
产物：scripts/out_tts.wav
"""

import sys
import time
import wave
from pathlib import Path

import dashscope
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

# 让 `python scripts/xxx.py` 也能 import app
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.config import get_settings  # noqa: E402

_RATE_TO_FORMAT = {
    8000: AudioFormat.PCM_8000HZ_MONO_16BIT,
    16000: AudioFormat.PCM_16000HZ_MONO_16BIT,
    24000: AudioFormat.PCM_24000HZ_MONO_16BIT,
}


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else "您好，这里是园区门岗，请问您要找哪家单位？"
    s = get_settings()
    dashscope.api_key = s.dashscope_api_key

    chunks: list[bytes] = []

    class Callback(ResultCallback):
        def on_data(self, data: bytes) -> None:
            chunks.append(data)

        def on_error(self, message) -> None:
            print(f"[TTS] 错误: {message}")

    synth = SpeechSynthesizer(
        model=s.tts_model,
        voice=s.tts_voice,
        format=_RATE_TO_FORMAT[s.tts_sample_rate],
        callback=Callback(),
    )

    t0 = time.monotonic()
    synth.streaming_call(text)
    synth.streaming_complete()
    elapsed = time.monotonic() - t0

    pcm = b"".join(chunks)
    out = Path(__file__).resolve().parent / "out_tts.wav"
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(s.tts_sample_rate)
        w.writeframes(pcm)

    secs = len(pcm) / 2 / s.tts_sample_rate
    print(f"[TTS] 文本: {text}")
    print(f"[TTS] 模型={s.tts_model} voice={s.tts_voice} sr={s.tts_sample_rate}")
    print(f"[TTS] 收到 {len(pcm)} 字节 PCM（约 {secs:.1f}s 音频），合成总耗时 {elapsed:.2f}s")
    print(f"[TTS] 已写入 {out}")
    print(f"[TTS] 试听: afplay {out}")


if __name__ == "__main__":
    main()
