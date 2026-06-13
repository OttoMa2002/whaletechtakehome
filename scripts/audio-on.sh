#!/usr/bin/env bash
# 把系统音频切到「门岗模式」：测试来电源时用。
# 输出=BlackHole 16ch(对端声音→管线)；输入=BlackHole 2ch(管线 TTS 回程给通话麦克风)。
# 故意不走"门岗监听"多输出(它含扬声器/可能含2ch)，避免对端声音绕回微信麦造成回声。
# 代价：Mac 上听不到通话(无监听)；对端手机能完整听到门岗，demo 录音从手机端录。
set -e
SwitchAudioSource -s "BlackHole 16ch" -t output
SwitchAudioSource -s "BlackHole 2ch" -t input
echo "✅ 已切到门岗模式  输出=BlackHole 16ch  输入=BlackHole 2ch（无回声，无本地监听）"
echo "   ⚠️ 一次性前置：音频MIDI设置里 BlackHole 2ch 的名义率(输入+输出)须为 16000Hz"
echo "      (否则 48k 被电话/微信 8k 读端坏转换→音质稀烂；重置音频后需复查)。"
echo "   测完记得跑 scripts/audio-off.sh 切回正常音频。"
