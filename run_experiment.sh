#!/bin/bash
RUN_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
METRIC_RUN_ID="$RUN_ID" make experiment
