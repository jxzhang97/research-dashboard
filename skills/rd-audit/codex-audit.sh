#!/bin/bash
# 审计步：用 Codex 按提示词独立审计推导或代码。见 rd-audit/SKILL.md。
# 用法：codex-audit.sh <课题根目录> <提示词文件> <记录目录名>
# 记录（提示词、完整输出、最后回复、run_info）写到 <课题根>/.dashboard/auditing/<记录目录名>/
set -u
ROOT="$(cd "$1" && pwd)"; PROMPT="$2"; NAME="$3"
REC="$ROOT/.dashboard/auditing/$NAME"; mkdir -p "$REC"
cp "$PROMPT" "$REC/prompt.md"

# [auditor] 配置：model / reasoning_effort（缺省 gpt-6-astra / xhigh）
read -r MODEL EFFORT <<<"$(python3 - "$ROOT/config.toml" <<'PY'
import sys, tomllib
try:
    a = tomllib.load(open(sys.argv[1], "rb")).get("auditor", {})
except Exception:
    a = {}
print(a.get("model", "gpt-6-astra"), a.get("reasoning_effort", "xhigh"))
PY
)"

CODEX="${CODEX_BIN:-}"
for cand in "$CODEX" "$(command -v codex 2>/dev/null)" "$HOME/.local/bin/codex" "/opt/homebrew/bin/codex" \
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"; do
  [ -n "$cand" ] && [ -x "$cand" ] && { CODEX="$cand"; break; }
done
if [ -z "$CODEX" ]; then
  echo "找不到 codex（npm install -g @openai/codex，或把独立二进制放 ~/.local/bin；然后 codex login）" | tee "$REC/run_info.txt"; exit 2
fi
codex() { "$CODEX" "$@"; }
if ! codex login status 2>&1 | grep -qi "logged in"; then
  echo "codex 未登录（在这台机器上 codex login）" | tee "$REC/run_info.txt"; exit 3
fi

# 提示词里的 {{MODEL}} {{EFFORT}} {{DATE}} 由这里填，其余占位符应已由研究 agent 填好
TODAY=$(date '+%Y-%m-%d')
sed -e "s/{{MODEL}}/$MODEL/g" -e "s/{{EFFORT}}/$EFFORT/g" -e "s/{{DATE}}/$TODAY/g" "$PROMPT" > "$REC/prompt.filled.md"
if grep -q '{{[A-Z_]*}}' "$REC/prompt.filled.md"; then
  echo "提示词还有没填的占位符: $(grep -o '{{[A-Z_]*}}' "$REC/prompt.filled.md" | sort -u | tr '\n' ' ')" | tee "$REC/run_info.txt"; exit 5
fi

START=$(date +%s)
echo "codex-cli $(codex --version 2>/dev/null | awk '{print $2}') | start $(date '+%Y-%m-%d %H:%M:%S') | model $MODEL | reasoning_effort $EFFORT | sandbox workspace-write | prompt: $(basename "$PROMPT")" > "$REC/run_info.txt"
# stdin 必须接 /dev/null，否则 codex exec 会等标准输入
codex exec -C "$ROOT" -m "$MODEL" -c "model_reasoning_effort=$EFFORT" -s workspace-write \
  -o "$REC/last_message.txt" "$(cat "$REC/prompt.filled.md")" < /dev/null > "$REC/codex_output.txt" 2>&1
RC=$?
END=$(date +%s)
echo "exit $RC | end $(date '+%Y-%m-%d %H:%M:%S') | duration $((END-START)) s | tokens: $(grep -A1 '^tokens used' "$REC/codex_output.txt" 2>/dev/null | tail -1 | tr -d ' ')" >> "$REC/run_info.txt"
cat "$REC/run_info.txt"
echo "--- last message ---"; cat "$REC/last_message.txt" 2>/dev/null
exit $RC
