#!/bin/bash
#
# Entrypoint wrapper for sequoiatools/cmd.
#
# Some templates (e.g. tests/templates/rebalance.yml's kill_process) run
# `kill -SIG... $(pgrep -f TERM)` as a remote SSH command to kill a named
# process for chaos/failure testing. `pgrep -f` matches a process's entire
# command line, not just its name - and the shell SSH spawns to run this
# very command has TERM embedded verbatim in its own cmdline (e.g.
# `sh -c "kill -SIGKILL $(pgrep -f indexer)"` literally contains "indexer").
# pgrep only excludes its own PID, never its parent shell, so `pgrep -f TERM`
# also matches the invoking shell - kill then kills its own SSH session
# mid-command, so SSH reports the channel closed via exit-signal instead of
# a normal exit status, which surfaces client-side as exit code 255. This
# happens even though the real target process was correctly killed.
#
# Fix: rewrite `pgrep -f TERM` to the standard self-match-safe bracket-class
# form `pgrep -f "[T]ERM"` (same idiom as `ps -ef | grep "[t]omcat"`), which
# still matches the real target's cmdline but can never match our own
# invoking command line.

kill_pgrep_f_re='^(kill[[:space:]]+(-[A-Za-z0-9]+)?[[:space:]]*)\$\(pgrep[[:space:]]+-f[[:space:]]+([^[:space:])]+)\)(.*)$'

if [ "$#" -gt 0 ]; then
  last=$#
  cmd="${!last}"
  if [[ "$cmd" =~ $kill_pgrep_f_re ]]; then
    prefix="${BASH_REMATCH[1]}"
    term="${BASH_REMATCH[3]}"
    suffix="${BASH_REMATCH[4]}"
    safe_term="[${term:0:1}]${term:1}"
    cmd="${prefix}\$(pgrep -f \"${safe_term}\")${suffix}"
    set -- "${@:1:$(($#-1))}" "$cmd"
  fi
fi

exec "$@"
