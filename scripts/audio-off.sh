#!/usr/bin/env bash
# 把系统音频切回正常：平时用电脑/测完后用。
set -e
SwitchAudioSource -s "MacBook Pro扬声器" -t output
SwitchAudioSource -s "MacBook Pro麦克风" -t input
echo "✅ 已切回正常  输出=MacBook Pro扬声器  输入=MacBook Pro麦克风"
