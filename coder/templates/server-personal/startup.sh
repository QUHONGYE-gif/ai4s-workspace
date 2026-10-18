#!/bin/sh
set -eu
umask 077
repo="$HOME/ai4s-workspace"
case "$AI4S_BRANCH" in
  dev-[a-z][a-z][a-z]) ;;
  *) echo 'Use a member account named with three lowercase initials.' >&2; exit 1 ;;
esac

# Never switch, reset or overwrite an existing personal checkout on restart.
if [ -e "$repo" ]; then
  git -C "$repo" rev-parse --is-inside-work-tree >/dev/null
  echo 'Existing personal repository preserved.'
  exit 0
fi

# A temporary directory prevents an interrupted clone from looking complete.
stage=$(mktemp -d "$HOME/.ai4s-clone-XXXXXX")
trap 'rm -rf "$stage"' EXIT HUP INT TERM
git clone /opt/ai4s-seed/repository.bundle "$stage/repo"
git -C "$stage/repo" remote set-url origin "$AI4S_REPOSITORY_URL"
if git -C "$stage/repo" show-ref --verify --quiet "refs/remotes/origin/$AI4S_BRANCH"; then
  git -C "$stage/repo" switch -c "$AI4S_BRANCH" --track "origin/$AI4S_BRANCH"
else
  git -C "$stage/repo" switch --no-track -c "$AI4S_BRANCH" origin/main
fi
git -C "$stage/repo" config user.name "$AI4S_GIT_NAME"
git -C "$stage/repo" config user.email "$AI4S_GIT_EMAIL"
git -C "$stage/repo" config push.default current
mv "$stage/repo" "$repo"
echo "Personal repository ready on $AI4S_BRANCH."
