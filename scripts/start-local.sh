#!/usr/bin/env bash
# 本地麦克风测试：起库 + 切回本机音频 + 用系统默认设备循环启动 app。
# 与 start.sh(电话/微信)的区别：这里清空 AUDIO_*_DEVICE 让 app 走 MacBook 麦克风/扬声器，
# 而不是 .env 里写死的 BlackHole 虚拟声卡。
# ⚠️ 戴耳机！本地外放会被麦克风收回，门岗会听到自己。
# 门岗启动即问候(本地不需要接通检测)；每通登记完自动重启等下一通；Ctrl+C 退出。
set -uo pipefail
cd "$(dirname "$0")/.."

echo "① 起 postgres ……"
docker compose up -d >/dev/null 2>&1 || echo "  (docker 起库失败，若库已在跑可忽略)"

echo "② 配本机音频：输入=MacBook麦克风；输出优先耳机(防回声) ……"
SwitchAudioSource -s "MacBook Pro麦克风" -t input >/dev/null
# 自动挑一个"耳机"作输出：排除虚拟声卡/多输出/内置扬声器后剩下的(通常就是连着的耳机)
OUT=$(SwitchAudioSource -a -t output | grep -vE "BlackHole|门岗监听|MacBook Pro扬声器" | head -1)
if [ -n "$OUT" ]; then
  SwitchAudioSource -s "$OUT" -t output >/dev/null
  echo "   输出=${OUT}  (耳机，无回声)"
else
  SwitchAudioSource -s "MacBook Pro扬声器" -t output >/dev/null
  echo "   ⚠️ 没检测到耳机，退回 MacBook 扬声器——会有回声！请连上耳机重跑本脚本。"
fi

# 空字符串覆盖 .env 里写死的 BlackHole 设备 → app 走系统默认(上面设好的本机麦/耳机)
export AUDIO_INPUT_DEVICE=
export AUDIO_OUTPUT_DEVICE=
# 本地：启动即问候(你就在跟前)，不用首声触发
export GREET_ON_FIRST_SOUND=false

echo "③ 启动门岗 app(本地麦)。门岗启动即问候，你接着说即可。"
echo "   每通登记完自动重启等下一通；Ctrl+C 退出。"
echo

trap 'echo; echo "已停止。"; exit 0' INT
while true; do
  echo "==== 门岗就绪(本地麦)，对麦说话 ===="
  uv run python -m app.main || true
  echo "---- 本通结束，2 秒后重启等下一通(Ctrl+C 退出)----"
  sleep 2
done
