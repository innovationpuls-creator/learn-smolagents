#!/bin/sh
# Usage: sh scripts/environment.sh development|test|production [setup|run]
set -eu
cd "$(dirname "$0")/.."
mode="${1:-development}"
action="${2:-run}"
case "$mode" in
  development) environment_path="$PWD/.venv" ;;
  test) environment_path="$PWD/.venv-test" ;;
  production) environment_path="$PWD/.venv-production" ;;
  *) echo '环境必须是 development、test 或 production' >&2; exit 2 ;;
esac
case "$action" in
  setup|run) ;;
  *) echo '操作必须是 setup 或 run' >&2; exit 2 ;;
esac
export LEARN_SMOLAGENTS_ENV="$mode"
if [ ! -f "$environment_path/pyvenv.cfg" ]; then
  uv venv "$environment_path"
fi
export VIRTUAL_ENV="$environment_path"
if [ "$mode" = production ]; then
  uv sync --active --locked --no-dev --no-editable
else
  uv sync --active --locked
fi
if [ "$action" = setup ]; then
  exit 0
fi
if [ "$mode" = test ]; then
  exec env -u NO_COLOR uv run --active --no-sync python -m pytest -q
fi
exec uv run --active --no-sync local-codeagent
