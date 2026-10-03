#!/bin/bash
# research-dashboard 命令行入口。用模板仓库自带的 .venv 运行，没有就提示先 install。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"
if [ ! -x "$PY" ]; then
  if [ "$1" = "install" ]; then
    PY="$(command -v python3)"
  else
    echo "未找到 $HERE/.venv，先运行: $HERE/rd install" >&2
    exit 1
  fi
fi
exec "$PY" -m rd_core.cli "$@"
