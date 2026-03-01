#!/usr/bin/env sh
set -eu

export PYTHONPATH="/opt/collector/common${PYTHONPATH:+:$PYTHONPATH}"
python /opt/collector/collect.py "$@"
