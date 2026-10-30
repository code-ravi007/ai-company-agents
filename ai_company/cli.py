"""Command line entry point.

    ai-company idea "Add a dark mode toggle"     # opens an issue, then builds it
    ai-company idea --local "Add a dark mode toggle"   # no GitHub: branch + commit only
    ai-company issue 12                          # build from issue #12
    ai-company revise 34                         # address owner feedback on PR #34
    ai-company resume                            # resume runs paused by the usage limit
    ai-company event                             # dispatch a GitHub Actions event
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from ai_company.config import Config, load_config
from ai_company.credentials import Credentials
from ai_company.github import Git, GitHub, take_token
from ai_company.pipeline import Pipeline
from ai_company.runner import SdkRunner

log = logging.getLogger("ai_company")


def _build(args: argparse.Namespace, local: bool = False) -> Pipeline:
    repo_root = Path(args.repo_root).resolve()
    config = load_config(repo_root)
    token = take_token()  # removes the token from os.environ before any agent starts
    github = None
    if not local:
        repo = args.repo or os.environ.get("GITHUB_REPOSITORY", "")
        if not repo or not token:
            raise SystemExit("Set GITHUB_REPOSITORY (or --repo) and AI_COMPANY_GITHUB_TOKEN, or use --local.")
        github = GitHub(repo=repo, token=token, repo_root=repo_root)
        config = _fill_identities(config, github, repo)
    git = Git(
        repo_root,
        token=token,
        # Empty locally: git then uses your own name and email.
        author_name=config.git_author_name,
        author_email=config.git_author_email,
    )
    credentials = Credentials.take_from_env(config.auth_mode, config.api_fallback_on_limit)
    log.info("Running agents on: %s", credentials.describe())
    runner = SdkRunner(credentials=credentials, docs_dir=config.docs_dir)
    return Pipeline(config=config, runner=runner, git=git, github=github)


def _fill_identities(config: Config, github: GitHub, repo: str) -> Config:
    """Default the owner to the repo owner and the git author to the token's account."""
    updates: dict[str, str] = {}
    if not config.owner_login:
        updates["owner_login"] = os.environ.get("GITHUB_REPOSITORY_OWNER") or repo.split("/")[0]
    if not config.git_author_name:
        me = github.whoami()
        updates["git_author_name"] = me["login"]
        updates["git_author_email"] = config.git_author_email or f"{me['id']}+{me['login']}@users.noreply.github.com"
    return replace(config, **updates)


def _dispatch_event(args: argparse.Namespace) -> int:
    """Turn a GitHub Actions event into a pipeline call."""
    name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()) if os.environ.get("GITHUB_EVENT_PATH") else {}
    pipeline = _build(args)
    allowed = pipeline.config.triggerers()
    actor = event.get("sender", {}).get("login", "")

    if name == "schedule":
        asyncio.run(pipeline.resume_paused())
        return 0
    if name == "workflow_dispatch":
        inputs = event.get("inputs", {})
        if actor not in allowed:
            log.warning("Ignoring dispatch from %s (not in allowed_triggerers).", actor)
            return 0
        if inputs.get("issue"):
            asyncio.run(pipeline.run_issue(int(inputs["issue"])))
        elif inputs.get("idea"):
            asyncio.run(pipeline.run_idea(inputs["idea"], inputs.get("title") or None))
        else:
            asyncio.run(pipeline.resume_paused())
        return 0

    if actor not in allowed:
        log.warning("Ignoring %s event from %s (not in allowed_triggerers).", name, actor)
        return 0

    if name == "issues" and event.get("label", {}).get("name") == "ai:build":
        asyncio.run(pipeline.run_issue(event["issue"]["number"]))
    elif name == "issue_comment":
        body = (event.get("comment", {}).get("body") or "").strip()
        number = event["issue"]["number"]
        is_pr = "pull_request" in event["issue"]
        if body.startswith("/ai revise") and is_pr:
            asyncio.run(pipeline.revise_pr(number))
        elif body.startswith("/ai build") and not is_pr:
            asyncio.run(pipeline.run_issue(number))
        else:
            log.info("Comment is not an /ai command; nothing to do.")
    elif name == "pull_request_review" and (event.get("review", {}).get("body") or "").strip().startswith("/ai revise"):
        asyncio.run(pipeline.revise_pr(event["pull_request"]["number"]))
    else:
        log.info("Event %s needs no action.", name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-company", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=".", help="Path to the target repository checkout.")
    parser.add_argument("--repo", default="", help="owner/name on GitHub (defaults to $GITHUB_REPOSITORY).")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_idea = sub.add_parser("idea", help="Build from a plain-text idea.")
    p_idea.add_argument("text")
    p_idea.add_argument("--title", default=None)
    p_idea.add_argument("--local", action="store_true", help="Do not touch GitHub; branch and commit locally.")
    p_issue = sub.add_parser("issue", help="Build from a GitHub issue.")
    p_issue.add_argument("number", type=int)
    p_rev = sub.add_parser("revise", help="Address the owner's feedback on a PR.")
    p_rev.add_argument("number", type=int)
    sub.add_parser("resume", help="Resume runs paused by the usage limit.")
    sub.add_parser("event", help="Handle the current GitHub Actions event.")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "event":
        return _dispatch_event(args)
    pipeline = _build(args, local=getattr(args, "local", False))
    if args.command == "idea":
        state = asyncio.run(pipeline.run_idea(args.text, args.title))
    elif args.command == "issue":
        state = asyncio.run(pipeline.run_issue(args.number))
    elif args.command == "revise":
        state = asyncio.run(pipeline.revise_pr(args.number))
    else:
        for state in asyncio.run(pipeline.resume_paused()):
            print(f"#{state.issue}: {state.stage}")
        return 0
    print(f"stage={state.stage} branch={state.branch} pr={state.pr_url or '-'} cost=${state.cost_usd:.2f}")
    if state.error:
        print(f"error: {state.error}", file=sys.stderr)
        return 1
    return 0
