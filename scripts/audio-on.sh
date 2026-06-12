#!/usr/bin/env bash
# 把系统音频切到「门岗模式」：测试来电源时用。
# 输出=门岗监听(微信/电话播放的访客声音→BlackHole 16ch→管线)；输入=BlackHole 2ch(管线 TTS 回程给通话麦克风)。
set -e
SwitchAudioSource -s "门岗监听" -t output
SwitchAudioSource -s "BlackHole 2ch" -t input
echo "✅ 已切到门岗模式  输出=门岗监听  输入=BlackHole 2ch"
echo "   测完记得跑 scripts/audio-off.sh 切回正常音频。"
