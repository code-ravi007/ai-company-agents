"""The orchestrator: idea -> spec -> design -> code -> review -> QA -> docs -> PR.

Each stage is one agent run. The orchestrator owns everything with side
effects outside the working copy (commits, pushes, PRs, issue comments), so
agents never need GitHub credentials.

    Manager ──spec──▶ Designer ──design──▶ Developer ◀──feedback── Reviewer
                                              ▲  │                    ▲
                                         bugs │  └──────diff──────────┘
                                              │           │ approved
                                              └───────── QA (user-facing changes only)
                                                          │ pass
                                                          ▼
                                     Tech writer ──▶ commit, push, open PR for the owner

Besides the build pipeline it runs single-document tasks (research brief,
launch kit, blog post) that each end in their own PR, and triages new issues
with the support agent.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ai_company import render
from ai_company.config import Config
from ai_company.github import Git, GitHub
from ai_company.roles import SUPPORT_LABELS, TASK_ROLES, Role, build_roles
from ai_company.runner import AgentRunner, AgentRunError, RoleResult, UsageLimitPause
from ai_company.state import RunState, StateStore

log = logging.getLogger(__name__)

LABELS = {
    "ai:build": "5319e7",
    "ai:in-progress": "fbca04",
    "ai:needs-info": "d93f0b",
    "ai:paused": "c5def5",
    "ai:pr-open": "0e8a16",
    "ai:failed": "b60205",
    "ai:research": "1d76db",
    "ai:marketing": "e99695",
    "ai:content": "0e8a16",
}
# Label that asks for each document task.
TASK_LABELS = {"ai:research": "researcher", "ai:marketing": "marketing", "ai:content": "content-writer"}
SUPPORT_LABEL_COLORS = {
    "bug": "d73a4a", "question": "d876e3", "enhancement": "a2eeef", "duplicate": "cfd3d7",
    "needs-info": "fbca04", "invalid": "e4e669", "good first issue": "7057ff",
}
MAX_DIFF_CHARS = 120_000
MAX_TEST_OUTPUT_CHARS = 12_000


def slugify(text: str, limit: int = 5) -> str:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words[:limit]) or "change"


@dataclass
class Pipeline:
    config: Config
    runner: AgentRunner
    git: Git
    github: GitHub | None = None
    roles: dict[str, Role] = field(default_factory=dict)
    clock: Any = time.time

    def __post_init__(self) -> None:
        self.roles = self.roles or build_roles(self.config.docs_dir)
        self.store = StateStore(self.config.repo_root)
        self._exclude_state_dir()

    # ------------------------------------------------------------------ setup
    def _exclude_state_dir(self) -> None:
        exclude = self.config.repo_root / ".git" / "info" / "exclude"
        if exclude.parent.exists():
            current = exclude.read_text() if exclude.exists() else ""
            if ".ai-company/" not in current:
                exclude.write_text(current.rstrip("\n") + "\n.ai-company/\n")

    def _docs_path(self, state: RunState, name: str) -> str:
        return f"{self.config.docs_dir}/{state.branch.removeprefix(self.config.branch_prefix)}/{name}"

    # ------------------------------------------------------------ state + status
    def _save(self, state: RunState) -> None:
        self.store.save(state)
        if self.github and state.issue:
            body = render.status_comment(state, self.config) + "\n\n" + state.marker()
            if state.status_comment_id:
                self.github.update_comment(state.status_comment_id, body)
            else:
                state.status_comment_id = self.github.comment(state.issue, body)["id"]
                self.store.save(state)

    def _load_from_issue(self, issue: int) -> RunState | None:
        if not self.github:
            return None
        bot_states = [RunState.from_comment(c.get("body", "")) for c in self.github.issue_comments(issue)]
        found = [s for s in bot_states if s]
        return found[-1] if found else None

    def _load_paused_from_issue(self, issue: int) -> RunState | None:
        """The most recent run on the issue that paused (build or task), else the latest."""
        if not self.github:
            return None
        found = [s for s in (RunState.from_comment(c.get("body", "")) for c in self.github.issue_comments(issue)) if s]
        paused = [s for s in found if s.paused_until is not None and s.stage != "done"]
        return (paused or found or [None])[-1]

    def _load_task_from_issue(self, issue: int, kind: str) -> RunState | None:
        if not self.github:
            return None
        found = [s for s in (RunState.from_comment(c.get("body", "")) for c in self.github.issue_comments(issue)) if s and s.kind == kind]
        return found[-1] if found else None

    def _set_label(self, state: RunState, label: str) -> None:
        if not (self.github and state.issue):
            return
        for other in ("ai:in-progress", "ai:needs-info", "ai:paused", "ai:pr-open", "ai:failed"):
            if other != label:
                self.github.remove_label(state.issue, other)
        self.github.add_labels(state.issue, [label])

    async def _run_role(self, state: RunState, role_name: str, prompt: str) -> RoleResult:
        settings = self.config.role(role_name)
        result = await self.runner.run(self.roles[role_name], settings, prompt, self.config.repo_root)
        state.cost_usd += result.cost_usd
        note = f"{role_name}: {result.turns} turns, ${result.cost_usd:.2f}"
        if result.denials:
            note += f", {len(result.denials)} blocked tool calls"
            for denial in result.denials:
                log.info("%s blocked: %s", role_name, denial)
        state.log.append(note)
        state.log.extend(f"  blocked: {d[:200]}" for d in result.denials)
        return result

    # ------------------------------------------------------------- entry points
    async def run_idea(self, idea: str, title: str | None = None) -> RunState:
        """Start from a plain idea. Opens an issue first when GitHub is set up."""
        if self.github:
            issue = self.github.create_issue(title or idea.splitlines()[0][:80], idea, ["ai:build"])
            return await self.run_issue(issue["number"])
        state = self.store.load(f"idea-{slugify(idea)}") or RunState(key=f"idea-{slugify(idea)}", title=title or idea[:80], request=idea)
        return await self._drive(state)

    async def run_issue(self, number: int) -> RunState:
        assert self.github, "GitHub is required to run from an issue"
        issue = self.github.get_issue(number)
        state = self._load_from_issue(number) or self.store.load(f"issue-{number}")
        if state is None or state.stage == "done":
            if state and state.stage == "done":
                log.info("Issue #%s already has a finished run; starting a fresh one.", number)
            state = RunState(key=f"issue-{number}", issue=number)
        state.title = issue["title"]
        state.request = render.issue_request(issue, self._human_comments(number))
        state.paused_until = None
        state.error = ""
        self.github.ensure_labels(LABELS)
        self._set_label(state, "ai:in-progress")
        return await self._drive(state)

    async def resume_paused(self) -> list[RunState]:
        """Resume every paused run whose usage-limit window has reset."""
        assert self.github, "GitHub is required to resume runs"
        resumed = []
        for issue in self.github.issues_with_label("ai:paused"):
            state = self._load_paused_from_issue(issue["number"])
            if state and state.paused_until and state.paused_until > self.clock():
                log.info("Issue #%s is paused until %s; skipping.", issue["number"], state.paused_until)
                continue
            if state and state.kind != "build":
                resumed.append(await self.run_task(state.kind, issue["number"]))
            else:
                resumed.append(await self.run_issue(issue["number"]))
        return resumed

    def _human_comments(self, number: int) -> list[dict[str, Any]]:
        assert self.github
        return [
            c
            for c in self.github.issue_comments(number)
            if not RunState.from_comment(c.get("body", "")) and c.get("user", {}).get("login") != self.config.git_author_name
        ]

    # -------------------------------------------------------------- the loop
    async def _drive(self, state: RunState, work: Any = None) -> RunState:
        try:
            await (work or self._stages)(state)
        except UsageLimitPause as pause:
            state.paused_until = pause.resets_at or (self.clock() + 3600)
            state.log.append(f"paused at {state.stage}: usage limit, resumes after {render.ts(state.paused_until)}")
            self._checkpoint_branch(state, f"wip: {state.title} (paused at {state.stage})")
            self._set_label(state, "ai:paused")
            self._save(state)
        except (AgentRunError, RuntimeError) as exc:
            state.error = str(exc)
            state.log.append(f"failed at {state.stage}: {exc}")
            self._checkpoint_branch(state, f"wip: {state.title} (failed at {state.stage})")
            self._set_label(state, "ai:failed")
            self._save(state)
        return state

    def _checkpoint_branch(self, state: RunState, message: str) -> None:
        """Save work in progress to the branch so a resumed run keeps it."""
        if not state.branch or self.git.current_branch() != state.branch:
            return
        try:
            if self.git.commit_all(message) and self.github:
                self.git.push(state.branch)
        except RuntimeError as exc:
            log.warning("Could not checkpoint branch: %s", exc)

    async def _stages(self, state: RunState) -> None:
        # 1. Manager: request -> spec
        if not state.stage_done("manager"):
            result = await self._run_role(state, "manager", render.manager_prompt(state, self.config))
            state.spec = result.output
            if state.spec.get("blocked") and state.spec.get("open_questions"):
                self._save(state)
                if self.github and state.issue:
                    self.github.comment(state.issue, render.questions_comment(state, self.config))
                    self._set_label(state, "ai:needs-info")
                state.log.append("manager: blocked on questions")
                self._save(state)
                return
            slug = slugify(state.spec.get("branch_slug") or state.title)
            prefix = f"{state.issue}-" if state.issue else ""
            state.branch = f"{self.config.branch_prefix}{prefix}{slug}"
            state.advance("designer")
            self._save(state)

        self.git.start_branch(state.branch, self.config.base_branch)
        spec_path = self.config.repo_root / self._docs_path(state, "spec.md")
        if not spec_path.exists():
            spec_path.parent.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(render.spec_markdown(state))

        # 2. Designer: spec -> design doc (skipped for non-visual work)
        if not state.stage_done("designer"):
            if state.spec.get("needs_design"):
                design_path = self._docs_path(state, "design.md")
                result = await self._run_role(state, "designer", render.designer_prompt(state, self.config, design_path))
                state.design = {**result.output, "path": design_path}
                if not (self.config.repo_root / design_path).exists():
                    raise AgentRunError(f"Designer did not write {design_path}")
            else:
                state.design = {}
                state.log.append("designer: skipped (no user-facing change)")
            state.advance("developer")
            self._save(state)

        # 3-5. Developer <-> Reviewer until approved (or out of rounds), then QA,
        # which sends real bugs back to the developer.
        while state.stage in ("developer", "reviewer", "qa"):
            if state.stage == "developer":
                result = await self._run_role(state, "developer", render.developer_prompt(state, self.config))
                state.dev = result.output
                state.test_output = self._run_tests(state)
                state.advance("reviewer")
                if state.review_round:
                    message = f"Address review feedback (round {state.review_round})"
                elif state.qa_round:
                    message = f"Fix QA findings (round {state.qa_round})"
                else:
                    message = render.commit_message(state)
                self._checkpoint_branch(state, message)
                self._save(state)
            if state.stage == "reviewer":
                diff = self.git.diff_against(self.config.base_branch)
                result = await self._run_role(state, "reviewer", render.reviewer_prompt(state, self.config, diff[:MAX_DIFF_CHARS]))
                state.review = result.output
                state.review_round += 1
                approved = state.review.get("verdict") == "approve"
                if approved:
                    state.stage = "qa" if self._wants_qa(state) else "docs"
                elif state.review_round > self.config.max_review_rounds:
                    state.stage = "pr"  # out of rounds: a draft PR, no QA or docs
                else:
                    state.stage = "developer"
                self._save(state)
            if state.stage == "qa":
                qa_dir = self._docs_path(state, "qa")
                result = await self._run_role(state, "qa", render.qa_prompt(state, self.config, qa_dir))
                self._assert_lane("qa", (self.config.docs_dir,))
                state.qa = {**result.output, "path": qa_dir}
                state.qa_round += 1
                if state.qa.get("verdict") == "pass" or state.qa_round > self.config.max_qa_rounds:
                    state.stage = "docs"
                else:
                    state.review = {}  # the next developer round fixes QA's bugs
                    state.review_round = 0  # ...and gets a full set of review rounds
                    state.stage = "developer"
                self._checkpoint_branch(state, f"QA report (round {state.qa_round})")
                self._save(state)

        # 6. Tech writer updates README, docs and changelog
        if state.stage == "docs":
            if self.config.docs_enabled:
                stat = self.git.run("diff", "--stat", f"origin/{self.config.base_branch}...HEAD", check=False)
                result = await self._run_role(state, "tech-writer", render.tech_writer_prompt(state, self.config, stat))
                state.docs = result.output
                self._checkpoint_branch(state, "Update docs and changelog")
            else:
                state.log.append("tech-writer: skipped (docs_enabled = false)")
            state.advance("pr")
            self._save(state)

        # 7. Commit, push, open the PR for the owner
        if state.stage == "pr":
            self._open_pr(state)
            state.advance("done")
            self._save(state)

    def _assert_lane(self, role: str, prefixes: tuple[str, ...]) -> None:
        """Fail the run if a role changed files outside its lane (e.g. from a script)."""
        status = self.git.run("status", "--porcelain", "--untracked-files=all", check=False)
        stray = []
        for line in status.splitlines():
            path = line[3:].split(" -> ")[-1].strip().strip('"')
            if path and not any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes):
                stray.append(path)
        if stray:
            raise AgentRunError(f"{role} changed files outside its lane: {', '.join(sorted(stray)[:10])}")

    def _wants_qa(self, state: RunState) -> bool:
        return self.config.qa_enabled and bool(state.spec.get("needs_design"))

    def _run_tests(self, state: RunState) -> str:
        command = self.config.test_command or state.dev.get("test_command", "")
        if not command:
            return ""
        try:
            proc = subprocess.run(
                command, shell=True, cwd=self.config.repo_root, capture_output=True, text=True, timeout=900
            )
            output = f"$ {command}\nexit code {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
        except subprocess.TimeoutExpired:
            output = f"$ {command}\ntimed out after 900s"
        return output[-MAX_TEST_OUTPUT_CHARS:]

    def _open_pr(self, state: RunState) -> None:
        approved = state.review.get("verdict") == "approve" and state.qa.get("verdict") != "fail"
        title = state.spec.get("title") or state.title
        self.git.commit_all(render.commit_message(state))
        if not self.github:
            state.log.append(f"local run finished on branch {state.branch}")
            return
        self.git.push(state.branch)
        body = render.pr_body(state, self.config)
        existing = self.github.find_pr(state.branch)
        if existing:
            pr = existing
            self.github.update_pr(pr["number"], body)
        else:
            pr = self.github.create_pr(state.branch, self.config.base_branch, title, body, draft=not approved)
        state.pr_number, state.pr_url = pr["number"], pr["html_url"]
        if self.config.owner_login != self.config.git_author_name:
            # GitHub refuses a review request from a PR's own author.
            self.github.assign(pr["number"], self.config.owner_login)
            self.github.request_review(pr["number"], self.config.owner_login)
        if state.issue:
            self._set_label(state, "ai:pr-open")
            self.github.comment(state.issue, render.done_comment(state, self.config))

    # ---------------------------------------------------------- PR revisions
    async def revise_pr(self, pr_number: int) -> RunState:
        """Address the owner's review feedback on an existing team PR."""
        assert self.github, "GitHub is required to revise a PR"
        pr = self.github.get_pr(pr_number)
        branch = pr["head"]["ref"]
        issue_match = re.search(r"(?:Closes|Fixes|Resolves) #(\d+)", pr.get("body") or "")
        issue = int(issue_match.group(1)) if issue_match else None
        state = (self._load_from_issue(issue) if issue else None) or RunState(key=f"pr-{pr_number}", issue=issue)
        state.branch, state.pr_number, state.pr_url = branch, pr_number, pr["html_url"]
        state.title = state.title or pr["title"]
        feedback = render.owner_feedback(
            self.github.pr_reviews(pr_number),
            self.github.pr_review_comments(pr_number),
            self.github.issue_comments(pr_number),
            self.config,
        )
        if not feedback.strip():
            self.github.comment(pr_number, "I could not find any review feedback from the owner to address.")
            return state
        self.git.start_branch(branch, self.config.base_branch)
        if state.kind != "build":
            return await self._revise_task(state, feedback)
        try:
            result = await self._run_role(state, "developer", render.revision_prompt(state, self.config, feedback))
            state.dev = result.output
            state.test_output = self._run_tests(state)
            diff = self.git.diff_against(self.config.base_branch)
            review = await self._run_role(state, "reviewer", render.reviewer_prompt(state, self.config, diff[:MAX_DIFF_CHARS]))
            state.review = review.output
            if self.git.commit_all(f"Address review feedback on #{pr_number}\n\n{state.dev.get('summary', '')}"):
                self.git.push(branch)
            self.github.update_pr(pr_number, render.pr_body(state, self.config))
            self.github.comment(pr_number, render.revision_comment(state))
            if self.config.owner_login != self.config.git_author_name:
                self.github.request_review(pr_number, self.config.owner_login)
        except UsageLimitPause as pause:
            self._checkpoint_branch(state, f"wip: address review on #{pr_number}")
            self.github.comment(
                pr_number,
                f"I hit the usage limit while addressing this review. Work so far is pushed. "
                f"Comment `/ai revise` again after {render.ts(pause.resets_at)} to continue.",
            )
        self.store.save(state)
        return state

    # -------------------------------------------------------- document tasks
    def _task_path(self, role: str, slug: str) -> str:
        """`slug` includes the issue number, so two issues never share a file."""
        return {
            "researcher": f"{self.config.docs_dir}/research/{slug}.md",
            "marketing": f"marketing/{slug}/launch-kit.md",
            "content-writer": f"content/{slug}.md",
        }[role]

    async def run_task(self, role: str, number: int) -> RunState:
        """One document from an issue or PR: a research brief, launch kit or post."""
        assert self.github, "GitHub is required to run a task from an issue"
        assert role in TASK_ROLES, role
        issue = self.github.get_issue(number)
        state = self._load_task_from_issue(number, role)
        if state is None or state.stage == "done":
            state = RunState(key=f"{role}-{number}", issue=number, kind=role)
        state.title = issue["title"]
        state.request = render.issue_request(issue, self._human_comments(number))
        state.task["source_is_pr"] = "pull_request" in issue
        state.paused_until = None
        state.error = ""
        self.github.ensure_labels(LABELS)
        self._set_label(state, "ai:in-progress")
        return await self._drive(state, self._task_stages)

    async def _task_stages(self, state: RunState) -> None:
        if not state.branch:
            short = {"researcher": "research", "marketing": "launch", "content-writer": "content"}[state.kind]
            state.branch = f"{self.config.branch_prefix}{short}-{state.issue}-{slugify(state.title)}"
            state.task["path"] = self._task_path(state.kind, f"{state.issue}-{slugify(state.title)}")
            state.stage = "developer"  # "working"; task runs reuse the build stage names
            self._save(state)
        self.git.start_branch(state.branch, self.config.base_branch)
        path = state.task["path"]
        if state.stage == "developer":
            result = await self._run_role(state, state.kind, render.task_prompt(state.kind, state.request, path))
            changed = self.git.run("status", "--porcelain", "--untracked-files=all", "--", path, check=False).strip()
            if not (self.config.repo_root / path).exists() or not changed:
                raise AgentRunError(f"{state.kind} did not write {path}")
            state.task.update(result.output)
            state.stage = "pr"
            self._save(state)
        if state.stage == "pr":
            self._open_task_pr(state)
            state.stage = "done"
            self._save(state)

    def _open_task_pr(self, state: RunState) -> None:
        title = f"{render.TASK_TITLES[state.kind]}: {state.task.get('title') or state.title}"
        self.git.commit_all(f"{title}\n\n{state.task.get('summary', '')}\n\nRefs #{state.issue}")
        assert self.github
        self.git.push(state.branch)
        body = render.task_pr_body(state, self.config, state.task["path"], state.task.get("source_is_pr", False))
        existing = self.github.find_pr(state.branch)
        pr = existing or self.github.create_pr(state.branch, self.config.base_branch, title, body, draft=False)
        if existing:
            self.github.update_pr(pr["number"], body)
        state.pr_number, state.pr_url = pr["number"], pr["html_url"]
        if self.config.owner_login != self.config.git_author_name:
            self.github.assign(pr["number"], self.config.owner_login)
            self.github.request_review(pr["number"], self.config.owner_login)
        self._set_label(state, "ai:pr-open")
        self.github.comment(state.issue, render.done_comment(state, self.config))

    async def _revise_task(self, state: RunState, feedback: str) -> RunState:
        assert self.github and state.pr_number
        path = state.task.get("path", "")
        prompt = (
            render.task_prompt(state.kind, state.request, path)
            + f"\n\nThe document already exists at `{path}`. The owner reviewed it; revise it to address every point:\n\n"
            f"<owner_feedback>\n{feedback}\n</owner_feedback>"
        )
        try:
            result = await self._run_role(state, state.kind, prompt)
            state.task.update(result.output)
            if self.git.commit_all(f"Address review feedback on #{state.pr_number}"):
                self.git.push(state.branch)
            self.github.update_pr(state.pr_number, render.task_pr_body(state, self.config, path, state.task.get("source_is_pr", False)))
            self.github.comment(state.pr_number, f"I revised `{path}` to address the feedback.\n\n{state.task.get('summary', '')}" + render.FOOTER)
        except UsageLimitPause as pause:
            self._checkpoint_branch(state, f"wip: address review on #{state.pr_number}")
            self.github.comment(
                state.pr_number,
                f"I hit the usage limit while revising this. Comment `/ai revise` again after {render.ts(pause.resets_at)}.",
            )
        self.store.save(state)
        return state

    # --------------------------------------------------------------- support
    async def triage_issue(self, number: int) -> dict[str, Any]:
        """Label a new issue and post a reply (or a draft reply for the owner)."""
        assert self.github, "GitHub is required to triage an issue"
        issue = self.github.get_issue(number)
        state = RunState(key=f"support-{number}", issue=number, kind="support")
        try:
            result = await self._run_role(state, "support", render.support_prompt(issue))
        except UsageLimitPause:
            log.warning("Usage limit reached; issue #%s was not triaged.", number)
            return {}
        triage = result.output
        labels = [l for l in triage.get("labels", []) if l in SUPPORT_LABELS]
        if labels:
            self.github.ensure_labels({l: SUPPORT_LABEL_COLORS[l] for l in labels})
            self.github.add_labels(number, labels)
        self.github.comment(number, render.support_comment(triage, self.config, self.config.support_auto_reply))
        return triage
