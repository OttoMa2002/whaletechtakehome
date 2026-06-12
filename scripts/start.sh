#!/usr/bin/env bash
# 一键开测：起库 + 切门岗音频 + 循环启动门岗 app。
# app 每完成一通登记会自动结束，本脚本自动重启等下一通——方便连着找多个人测。
# 全部测完：按 Ctrl+C 停止，会自动把音频切回正常。
set -uo pipefail
cd "$(dirname "$0")/.."

echo "① 起 postgres ……"
docker compose up -d >/dev/null 2>&1 || echo "  (docker 起库失败，若库已在跑可忽略)"

echo "② 切音频到门岗模式 ……"
"$(dirname "$0")/audio-on.sh"

# 退出时(Ctrl+C 或正常退出)自动切回正常音频
cleanup() { echo; echo "停止，切回正常音频 ……"; "$(dirname "$0")/audio-off.sh"; exit 0; }
trap cleanup INT

echo "③ 启动门岗 app。对方现在可以拨入(微信语音 / 真电话都行)，在本 Mac 接听。"
echo "   每通登记完会自动结束并重启等下一通；全部测完按 Ctrl+C 退出。"
echo
while true; do
  echo "==== 门岗就绪，等待来电 ===="
  uv run python -m app.main || true
  echo "---- 本通结束，2 秒后重启等下一通(Ctrl+C 退出)----"
  sleep 2
done
