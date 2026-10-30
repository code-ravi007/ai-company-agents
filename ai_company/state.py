"""Run state, saved after every stage so a run can resume after a pause.

State lives in two places:
- a JSON file under `.ai-company/state/` in the working copy (local runs)
- a hidden marker inside the team's status comment on the GitHub issue, so a
  fresh CI runner can pick the run up where the last one stopped.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STAGES = ("manager", "designer", "developer", "reviewer", "pr", "done")
MARKER_RE = re.compile(r"<!-- ai-company-state:([A-Za-z0-9+/=]+) -->")


@dataclass
class RunState:
    key: str
    title: str = ""
    request: str = ""
    issue: int | None = None
    branch: str = ""
    stage: str = "manager"
    spec: dict[str, Any] = field(default_factory=dict)
    design: dict[str, Any] = field(default_factory=dict)
    dev: dict[str, Any] = field(default_factory=dict)
    review: dict[str, Any] = field(default_factory=dict)
    review_round: int = 0
    test_output: str = ""
    pr_number: int | None = None
    pr_url: str = ""
    status_comment_id: int | None = None
    paused_until: float | None = None
    error: str = ""
    cost_usd: float = 0.0
    log: list[str] = field(default_factory=list)

    def stage_done(self, stage: str) -> bool:
        return STAGES.index(self.stage) > STAGES.index(stage)

    def advance(self, to: str) -> None:
        if STAGES.index(to) > STAGES.index(self.stage):
            self.stage = to

    # -- persistence --------------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "RunState":
        data = json.loads(raw)
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def marker(self) -> str:
        # Keep the marker small: drop the bulky test output.
        slim = RunState.from_json(self.to_json())
        slim.test_output = ""
        encoded = base64.b64encode(slim.to_json().encode()).decode()
        return f"<!-- ai-company-state:{encoded} -->"

    @classmethod
    def from_comment(cls, body: str) -> "RunState | None":
        match = MARKER_RE.search(body or "")
        if not match:
            return None
        return cls.from_json(base64.b64decode(match.group(1)).decode())


class StateStore:
    def __init__(self, repo_root: Path):
        self.dir = repo_root / ".ai-company" / "state"

    def _path(self, key: str) -> Path:
        return self.dir / f"{re.sub(r'[^A-Za-z0-9_.-]', '_', key)}.json"

    def load(self, key: str) -> RunState | None:
        path = self._path(key)
        return RunState.from_json(path.read_text()) if path.exists() else None

    def save(self, state: RunState) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(state.key).write_text(state.to_json())
