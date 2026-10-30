#!/usr/bin/env bash
# Turn the AI company team on for one or more GitHub repositories.
#
#   scripts/enable-repo.sh owner/repo [owner/repo ...]
#   scripts/enable-repo.sh --all            # asks about each of your repositories
#
# Run it from your own computer, signed in to the GitHub CLI as the repository
# owner (gh auth login; gh auth refresh -s workflow). For each repository it:
#   1. if the repository belongs to another account, invites the bot account
#      as a collaborator (and accepts the invite with the bot token),
#   2. stores the secrets the team needs,
#   3. creates the ai:build label,
#   4. opens a pull request that adds .github/workflows/ai-company.yml.
#
# Secrets are read from these environment variables, or asked for without
# echoing if unset. They are passed to `gh secret set` on stdin and never
# printed or written to disk:
#   CLAUDE_CODE_OAUTH_TOKEN   from `claude setup-token` (or leave empty and set ANTHROPIC_API_KEY)
#   AI_COMPANY_GITHUB_TOKEN   token of the account the team works as (see docs/SETUP.md)
#   ANTHROPIC_API_KEY         optional
#
# Options (environment): AI_COMPANY_BOT=code-ravi007, AI_COMPANY_REF=main
#
# Nothing is deleted or overwritten: existing secrets are only replaced when
# you answer yes, and an existing workflow file is left alone.

set -euo pipefail

BOT="${AI_COMPANY_BOT:-code-ravi007}"
REF="${AI_COMPANY_REF:-main}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$HERE/templates/ai-company.yml"
BRANCH="ai-company-setup"

say() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*" >&2; }
confirm() { local reply; read -r -p "$1 [y/N] " reply; [[ "$reply" =~ ^[Yy]$ ]]; }

need() {
  command -v "$1" >/dev/null 2>&1 || { warn "Missing $1. Install it first."; exit 1; }
}

ask_secret() {
  local name="$1" optional="${2:-}"
  if [[ -z "${!name:-}" ]]; then
    local prompt="Paste $name"
    [[ -n "$optional" ]] && prompt+=" (Enter to skip)"
    read -r -s -p "$prompt: " "$name"
    echo
    export "${name?}"
  fi
}

set_secret() {
  local repo="$1" name="$2"
  [[ -z "${!name:-}" ]] && return 0
  if gh secret list --repo "$repo" --json name -q '.[].name' | grep -qx "$name"; then
    confirm "  $name already exists in $repo. Replace it?" || { echo "  kept existing $name"; return 0; }
  fi
  printf '%s' "${!name}" | gh secret set "$name" --repo "$repo" >/dev/null
  echo "  set secret $name"
}

invite_bot() {
  local repo="$1"
  if [[ "${repo%%/*}" == "$BOT" ]]; then
    return 0  # the bot owns this repository; nothing to invite
  fi
  if gh api "repos/$repo/collaborators/$BOT" >/dev/null 2>&1; then
    echo "  $BOT is already a collaborator"
    return 0
  fi
  gh api -X PUT "repos/$repo/collaborators/$BOT" -f permission=push >/dev/null
  echo "  invited $BOT with Write access"
  if [[ -n "${AI_COMPANY_GITHUB_TOKEN:-}" ]]; then
    local id
    id="$(GH_TOKEN="$AI_COMPANY_GITHUB_TOKEN" gh api user/repository_invitations \
      -q ".[] | select(.repository.full_name == \"$repo\") | .id" 2>/dev/null | head -n1 || true)"
    if [[ -n "$id" ]]; then
      GH_TOKEN="$AI_COMPANY_GITHUB_TOKEN" gh api -X PATCH "user/repository_invitations/$id" >/dev/null
      echo "  accepted the invite as $BOT"
    else
      warn "  could not find the invite for $BOT; accept it from the bot account at https://github.com/$repo/invitations"
    fi
  fi
}

ensure_label() {
  local repo="$1"
  gh label create "ai:build" --repo "$repo" --color 5319e7 \
    --description "Ask the AI company team to build this issue" >/dev/null 2>&1 \
    && echo "  created label ai:build" || echo "  label ai:build already exists"
}

open_workflow_pr() {
  local repo="$1" base sha content
  if gh api "repos/$repo/contents/.github/workflows/ai-company.yml" >/dev/null 2>&1; then
    echo "  workflow already present; left unchanged"
    return 0
  fi
  base="$(gh api "repos/$repo" -q .default_branch)"
  sha="$(gh api "repos/$repo/git/ref/heads/$base" -q .object.sha)"
  if ! gh api "repos/$repo/git/ref/heads/$BRANCH" >/dev/null 2>&1; then
    gh api -X POST "repos/$repo/git/refs" -f ref="refs/heads/$BRANCH" -f sha="$sha" >/dev/null
  fi
  content="$(sed "s#team.yml@main#team.yml@$REF#" "$TEMPLATE" | base64 | tr -d '\n')"
  gh api -X PUT "repos/$repo/contents/.github/workflows/ai-company.yml" \
    -f message="Turn on the AI company team" -f content="$content" -f branch="$BRANCH" >/dev/null
  gh pr create --repo "$repo" --base "$base" --head "$BRANCH" \
    --title "Turn on the AI company team" \
    --body "Adds the AI company workflow. After merging, label an issue \`ai:build\` and the team opens a pull request for it. See https://github.com/code-ravi007/ai-company-agents for details." \
    | sed 's/^/  opened /'
}

enable() {
  local repo="$1"
  say "== $repo"
  invite_bot "$repo"
  set_secret "$repo" CLAUDE_CODE_OAUTH_TOKEN
  set_secret "$repo" ANTHROPIC_API_KEY
  set_secret "$repo" AI_COMPANY_GITHUB_TOKEN
  ensure_label "$repo"
  open_workflow_pr "$repo"
}

main() {
  need gh
  gh auth status >/dev/null 2>&1 || { warn "Run 'gh auth login' first."; exit 1; }
  [[ $# -gt 0 ]] || { sed -n '2,8p' "$0"; exit 1; }

  local repos=()
  if [[ "$1" == "--all" ]]; then
    local me
    me="$(gh api user -q .login)"
    while IFS= read -r r; do
      confirm "Enable the team for $r?" && repos+=("$r")
    done < <(gh repo list "$me" --no-archived --source --limit 200 --json nameWithOwner -q '.[].nameWithOwner')
  else
    repos=("$@")
  fi
  [[ ${#repos[@]} -gt 0 ]] || { echo "Nothing to do."; exit 0; }

  ask_secret CLAUDE_CODE_OAUTH_TOKEN optional
  ask_secret AI_COMPANY_GITHUB_TOKEN
  ask_secret ANTHROPIC_API_KEY optional
  if [[ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" && -z "${ANTHROPIC_API_KEY:-}" ]]; then
    warn "Set CLAUDE_CODE_OAUTH_TOKEN (from 'claude setup-token') or ANTHROPIC_API_KEY."
    exit 1
  fi

  for repo in "${repos[@]}"; do
    enable "$repo"
  done
  say "Done. Merge each 'Turn on the AI company team' pull request, then label an issue ai:build."
}

main "$@"
