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

echo "② 切回本机音频(MacBook 麦克风/扬声器) ……"
"$(dirname "$0")/audio-off.sh"

# 空字符串覆盖 .env 里写死的 BlackHole 设备 → app 走系统默认(本机麦/扬声器)
export AUDIO_INPUT_DEVICE=
export AUDIO_OUTPUT_DEVICE=

echo "③ 启动门岗 app(本地麦)。⚠️ 戴耳机防回声。门岗启动即问候，你接着说即可。"
echo "   每通登记完自动重启等下一通；Ctrl+C 退出。"
echo

trap 'echo; echo "已停止。"; exit 0' INT
while true; do
  echo "==== 门岗就绪(本地麦)，对麦说话 ===="
  uv run python -m app.main || true
  echo "---- 本通结束，2 秒后重启等下一通(Ctrl+C 退出)----"
  sleep 2
done
