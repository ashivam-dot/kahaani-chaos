#!/usr/bin/env bash
# The state branch as a worktree at ./state.
#   .github/state.sh checkout        check it out (an empty orphan branch on the very first run)
#   .github/state.sh save MESSAGE    commit and push it, replaying onto any newer state
set -euo pipefail

case "$1" in
  checkout)
    if git fetch -q --depth 1 origin state; then
      git worktree add -q state FETCH_HEAD
      git -C state switch -q -c state-run
    else
      git worktree add -q --orphan -b state-run state
    fi
    ;;
  save)
    cd state
    git add -A
    git -c user.name="kahaani-chaos bot" -c user.email="335661989+ashivam-dot@users.noreply.github.com" \
      commit -q -m "$2" || exit 0
    for attempt in 1 2 3; do
      if git ls-remote -q --exit-code origin state > /dev/null; then
        git pull -q --rebase origin state || { git rebase --abort || true; sleep 5; continue; }
      fi
      git push -q origin HEAD:state && exit 0
      sleep 5
    done
    exit 1
    ;;
  *)
    echo "usage: state.sh checkout | save MESSAGE" >&2
    exit 2
    ;;
esac
