#!/bin/bash

# only do refresh pull once
PULL_SH=/tmp/.pull
SYNC_CMD=$(grep "git" $PULL_SH)
if [ -n "$SYNC_CMD" ]; then
  # do sync
  cp scripts/testrunner-orig testrunner
  $PULL_SH || true
  cp scripts/testrunner-docker testrunner

  # make sure don't sync again
  echo "" > $PULL_SH

  # re apply constants
  sed -i 's/IS_CONTAINER.*/IS_CONTAINER = True/' lib/testconstants.py
  sed -i 's/ALLOW_HTP.*/ALLOW_HTP=False/' lib/testconstants.py
fi
