#!/bin/bash
# 薄层写作步：用 Codex 按提示词写页面。见 rd-writer/SKILL.md。
# 作业在独立会话里跑，不随 agent 的运行结束而死；启动后立刻返回，用 --wait 前台等。
#   codex-write.sh <课题根目录> <提示词文件> <记录目录名> [图.png …]    启动（立刻返回，打印 pid 与记录目录）
#   codex-write.sh --wait <课题根目录> <记录目录名> [最多等几秒]         前台等待，默认 100 秒；退出码 0 完成、7 还在跑、6 工具执行 fail closed、9 进程消失
#   codex-write.sh --status <课题根目录> <记录目录名>                    只看状态
#   codex-write.sh --sync <课题根目录> <提示词文件> <记录目录名> [图 …]  启动并一直等到结束（交互会话用）
# 记录（提示词、完整输出、最后回复、run_info、pid）在 <课题根>/.dashboard/writing/<记录目录名>/
set -u
SELF="$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "${BASH_SOURCE[0]}")"
RD="$(cd "$(dirname "$SELF")/../.." && pwd)/rd"
case "${1:-}" in
  --wait)   shift; exec "$RD" codex wait "$1" --kind write --name "$2" --max-seconds "${3:-100}" ;;
  --status) shift; exec "$RD" codex status "$1" --kind write --name "$2" ;;
  --sync)   shift; ROOT="$1"; PROMPT="$2"; NAME="$3"; shift 3; ARGS=(); for f in "$@"; do ARGS+=(--image "$f"); done
            exec "$RD" codex start "$ROOT" --kind write --prompt "$PROMPT" --name "$NAME" --sync ${ARGS[@]+"${ARGS[@]}"} ;;
  --help|-h|"") sed -n '2,9p' "$SELF"; exit 0 ;;
  *) [ $# -ge 3 ] || { sed -n '2,9p' "$SELF"; exit 1; }
     ROOT="$1"; PROMPT="$2"; NAME="$3"; shift 3; ARGS=(); for f in "$@"; do ARGS+=(--image "$f"); done
     exec "$RD" codex start "$ROOT" --kind write --prompt "$PROMPT" --name "$NAME" ${ARGS[@]+"${ARGS[@]}"} ;;
esac
