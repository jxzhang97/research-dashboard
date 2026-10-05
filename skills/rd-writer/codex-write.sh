#!/bin/bash
# 薄层写作步：用 Codex 按提示词写页面。见 rd-writer/SKILL.md。
# 用法：codex-write.sh <课题根目录> <提示词文件> <记录目录名> [图.png …]
# 记录（提示词、完整输出、最后回复、run_info）写到 <课题根>/.dashboard/writing/<记录目录名>/
set -u
ROOT="$(cd "$1" && pwd)"; PROMPT="$2"; NAME="$3"; shift 3
REC="$ROOT/.dashboard/writing/$NAME"; mkdir -p "$REC"
cp "$PROMPT" "$REC/prompt.md"

# [writer] 配置：model / reasoning_effort（缺省 gpt-6-astra / xhigh）
read -r MODEL EFFORT <<<"$(python3 - "$ROOT/config.toml" <<'PY'
import sys, tomllib
try:
    w = tomllib.load(open(sys.argv[1], "rb")).get("writer", {})
except Exception:
    w = {}
print(w.get("model", "gpt-6-astra"), w.get("reasoning_effort", "xhigh"))
PY
)"

if ! command -v codex >/dev/null 2>&1; then
  echo "codex 不在 PATH（npm install -g @openai/codex；然后 codex login）" | tee "$REC/run_info.txt"; exit 2
fi
if ! codex login status 2>&1 | grep -qi "logged in"; then
  echo "codex 未登录（在这台机器上 codex login）" | tee "$REC/run_info.txt"; exit 3
fi

IMG_ARGS=()
for f in "$@"; do
  [ -f "$f" ] || { echo "图不存在: $f" | tee -a "$REC/run_info.txt"; exit 4; }
  IMG_ARGS+=(-i "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")")
done

START=$(date +%s)
echo "codex-cli $(codex --version 2>/dev/null | awk '{print $2}') | start $(date '+%Y-%m-%d %H:%M:%S') | model $MODEL | reasoning_effort $EFFORT | sandbox workspace-write | images: $# | prompt: $(basename "$PROMPT")" > "$REC/run_info.txt"
# stdin 必须接 /dev/null，否则 codex exec 会等标准输入
codex exec -C "$ROOT" -m "$MODEL" -c "model_reasoning_effort=$EFFORT" -s workspace-write "${IMG_ARGS[@]}" \
  -o "$REC/last_message.txt" "$(cat "$PROMPT")" < /dev/null > "$REC/codex_output.txt" 2>&1
RC=$?
END=$(date +%s)
echo "exit $RC | end $(date '+%Y-%m-%d %H:%M:%S') | duration $((END-START)) s | tokens: $(grep -A1 '^tokens used' "$REC/codex_output.txt" 2>/dev/null | tail -1 | tr -d ' ')" >> "$REC/run_info.txt"
cat "$REC/run_info.txt"
echo "--- last message ---"; cat "$REC/last_message.txt" 2>/dev/null
exit $RC
