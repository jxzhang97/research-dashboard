#!/bin/bash
# 审计步：用 Codex 按提示词独立审计推导/代码，或做薄层科学一致性检查。见 rd-audit/SKILL.md。
# 作业在独立会话里跑，不随 agent 的运行结束而死；启动后立刻返回，用 --wait 前台等。
#   codex-audit.sh <课题根目录> <提示词文件> <记录目录名> [--kind consistency] [--expect 报告路径] [--source 源文件]…
#       启动（立刻返回，打印 pid 与记录目录）。--expect 声明报告路径（相对课题根），--source 声明审的源文件（可多次，记哈希）；
#       rd finish 只认带这两项声明、且源文件之后没改过的通过报告。--kind 默认 audit（推导/代码），薄层一致性检查用 consistency。
#   codex-audit.sh --wait <课题根目录> <记录目录名> [最多等几秒]      前台等待，默认 100 秒；退出码 0 完成、7 还在跑、6 工具执行 fail closed、9 进程消失、10 声明的输出没产出、11 源文件在审核期间被改
#   codex-audit.sh --status <课题根目录> <记录目录名>                 只看状态
#   codex-audit.sh --sync <课题根目录> <提示词文件> <记录目录名> [选项…]   启动并一直等到结束（交互会话用）
# 记录（提示词、完整输出、最后回复、run_info、outcome.json、pid）在 <课题根>/.dashboard/auditing/<记录目录名>/
set -u
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
RD="$(cd "$(dirname "$SELF")/../.." && pwd)/rd"
case "${1:-}" in
  --wait)   shift; exec "$RD" codex wait "$1" --kind "${CODEX_KIND:-audit}" --name "$2" --max-seconds "${3:-100}" ;;
  --status) shift; exec "$RD" codex status "$1" --kind "${CODEX_KIND:-audit}" --name "$2" ;;
  --sync)   shift; ROOT="$1"; PROMPT="$2"; NAME="$3"; shift 3
            exec "$RD" codex start "$ROOT" --kind audit --prompt "$PROMPT" --name "$NAME" --sync "$@" ;;
  --help|-h|"") sed -n '2,10p' "$SELF"; exit 0 ;;
  *) [ $# -ge 3 ] || { sed -n '2,10p' "$SELF"; exit 1; }
     ROOT="$1"; PROMPT="$2"; NAME="$3"; shift 3
     # 其余参数原样传给 rd codex start（--kind consistency / --expect / --source / --lab）；后出现的 --kind 覆盖默认的 audit
     exec "$RD" codex start "$ROOT" --kind audit --prompt "$PROMPT" --name "$NAME" "$@" ;;
esac
