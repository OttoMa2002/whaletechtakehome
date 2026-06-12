"""独立验证 Paraformer 实时识别：音频 → 文本。

不带参数时自洽往返：先用 CosyVoice 合成一段 16k 音频，再喂给 Paraformer 识别，
打印识别结果（验证 STT + TTS + key 全通，无需麦克风）。
带 wav 路径参数则识别该文件（自动重采样到 STT 采样率）。

用法：
    uv run python scripts/test_stt.py [path/to/audio.wav]
"""

import sys
import time
import wave
from pathlib import Path

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.config import get_settings  # noqa: E402


def _synth_16k(text: str, s) -> bytes:
    """用 CosyVoice 合成一段 16k PCM，供 STT 自洽测试。"""
    chunks: list[bytes] = []

    class Callback(ResultCallback):
        def on_data(self, data: bytes) -> None:
            chunks.append(data)

    synth = SpeechSynthesizer(
        model=s.tts_model,
        voice=s.tts_voice,
        format=AudioFormat.PCM_16000HZ_MONO_16BIT,
        callback=Callback(),
    )
    synth.streaming_call(text)
    synth.streaming_complete()
    return b"".join(chunks)


def _read_wav_as(path: str, target_rate: int) -> bytes:
    import audioop

    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        pcm = wf.readframes(wf.getnframes())
    if ch == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if sr != target_rate:
        pcm, _ = audioop.ratecv(pcm, 2, 1, sr, target_rate, None)
    return pcm


def main() -> None:
    s = get_settings()
    dashscope.api_key = s.dashscope_api_key
    rate = s.stt_sample_rate

    if len(sys.argv) > 1:
        pcm = _read_wav_as(sys.argv[1], rate)
        source = sys.argv[1]
    else:
        sentence = "您好，我要登记访客，车牌是京A12345。"
        pcm = _synth_16k(sentence, s)
        source = f"（自洽往返，原文：{sentence}）"

    finals: list[str] = []

    class Handler(RecognitionCallback):
        def on_event(self, result: RecognitionResult) -> None:
            sentence = result.get_sentence()
            if not sentence:
                return
            text = sentence.get("text", "") if isinstance(sentence, dict) else ""
            if not text:
                return
            if RecognitionResult.is_sentence_end(sentence):
                finals.append(text)
                print(f"[STT] 终稿: {text}")
            else:
                print(f"[STT] 中间: {text}")

        def on_complete(self) -> None:
            print("[STT] (会话完成)")

        def on_error(self, result) -> None:
            print(f"[STT] (错误) {getattr(result, 'message', result)}")

    recog = Recognition(
        model=s.stt_model, callback=Handler(), format="pcm", sample_rate=rate
    )
    print(f"[STT] 模型={s.stt_model} sr={rate}  来源={source}")
    t0 = time.monotonic()
    recog.start()
    # 按 100ms 分帧实时送入；会话若被服务端结束则停止送帧
    frame = int(rate * 0.1) * 2
    for i in range(0, len(pcm), frame):
        try:
            recog.send_audio_frame(pcm[i : i + frame])
        except Exception as e:  # noqa: BLE001
            print(f"[STT] 送帧中断（会话已停）: {e}")
            break
        time.sleep(0.05)
    try:
        recog.stop()
    except Exception:  # noqa: BLE001
        pass
    time.sleep(0.5)
    print(f"[STT] 完整识别: {''.join(finals)}")
    print(f"[STT] 总耗时 {time.monotonic() - t0:.2f}s")


if __name__ == "__main__":
    main()
