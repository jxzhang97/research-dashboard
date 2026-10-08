#!/bin/bash
# 审计步：用 Codex 按提示词独立审计推导或代码。见 rd-audit/SKILL.md。
# 作业在独立会话里跑，不随 agent 的运行结束而死；启动后立刻返回，用 --wait 前台等。
#   codex-audit.sh <课题根目录> <提示词文件> <记录目录名>            启动（立刻返回，打印 pid 与记录目录）
#   codex-audit.sh --wait <课题根目录> <记录目录名> [最多等几秒]      前台等待，默认 100 秒；退出码 0 完成、7 还在跑、6 工具执行 fail closed、9 进程消失
#   codex-audit.sh --status <课题根目录> <记录目录名>                 只看状态
#   codex-audit.sh --sync <课题根目录> <提示词文件> <记录目录名>      启动并一直等到结束（交互会话用）
# 记录（提示词、完整输出、最后回复、run_info、pid）在 <课题根>/.dashboard/auditing/<记录目录名>/
set -u
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
RD="$(cd "$(dirname "$SELF")/../.." && pwd)/rd"
case "${1:-}" in
  --wait)   shift; exec "$RD" codex wait "$1" --kind audit --name "$2" --max-seconds "${3:-100}" ;;
  --status) shift; exec "$RD" codex status "$1" --kind audit --name "$2" ;;
  --sync)   shift; exec "$RD" codex start "$1" --kind audit --prompt "$2" --name "$3" --sync ;;
  --help|-h|"") sed -n '2,9p' "$SELF"; exit 0 ;;
  *) [ $# -ge 3 ] || { sed -n '2,9p' "$SELF"; exit 1; }; exec "$RD" codex start "$1" --kind audit --prompt "$2" --name "$3" ;;
esac
