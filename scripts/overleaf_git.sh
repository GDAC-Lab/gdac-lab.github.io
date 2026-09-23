#!/usr/bin/env bash
# git, signed in to Overleaf. Used by the workflows that read or write the CV's
# Overleaf project: researchmap-sync.yml and cv-pdf.yml.
#
# Overleaf's git bridge takes the user name "git" and a Git authentication
# token as the password. The token is read from OVERLEAF_GIT_TOKEN by a
# credential helper when git asks for it, so it never appears in a URL, a file
# or the log. The empty helper first drops any other helper configured on the
# machine.
set -euo pipefail
: "${OVERLEAF_GIT_TOKEN:?OVERLEAF_GIT_TOKEN is not set}"
# The single quotes are deliberate: the helper's own shell expands the variable
# when git runs it, so the token is not on git's command line either.
# shellcheck disable=SC2016
exec git -c credential.helper= \
  -c credential.helper='!f() { echo username=git; echo "password=$OVERLEAF_GIT_TOKEN"; }; f' \
  "$@"
