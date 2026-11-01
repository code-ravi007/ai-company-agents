---
name: qa-testing
description: How to test a user-facing change like a QA engineer - plan flows from the spec and design, run the app, drive it in a headless browser with Playwright, capture screenshots, and write a pass/fail report with reproducible bugs. Use when checking that a built feature works end to end.
---

# QA testing a change

## Plan
From the acceptance criteria and the design, list test cases: each flow's happy path, then empty, loading, error and edge states, repeated actions, a small screen (375px wide) and keyboard-only use.

## Run the app
- Static site: open the HTML file with a `file://` URL, or serve the folder with `python3 -m http.server 8000` in the background.
- Node app: install with the project's package manager, then start it with its dev or start script in the background and wait until the port answers.
- Other stacks: follow the README. If it cannot start, record why and fall back to reading the code.

## Drive it with Playwright
Use the Python or Node package, whichever the project already has; otherwise `pip install playwright && python3 -m playwright install chromium`. A minimal Python script (write it to the temp directory, not the repository):

```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1280, "height": 800})
    page.goto("http://localhost:8000")
    page.get_by_role("button", name="Add").click()
    page.screenshot(path="<qa folder>/01-after-add.png", full_page=True)
```

If `playwright install` cannot download a browser, use one that is already installed: `p.chromium.launch(channel="chrome")` (GitHub's runners have Google Chrome), or `p.chromium.launch(executable_path=...)` with the path from `which chromium chromium-browser google-chrome`, or a Chromium under `$PLAYWRIGHT_BROWSERS_PATH` or `/opt/pw-browsers`. Only if there is truly no browser, fall back to running the page's scripts in jsdom and say so.

Prefer role- and label-based locators; they also check accessibility. Keep screenshots to the key screens (at most 8), named `NN-what-it-shows.png`.

## Report template

```markdown
# QA report: <feature>

**Verdict:** pass | fail

## Environment
<how the app was run, browser, viewport sizes>

## Results
| # | Test case | Result | Screenshot |
|---|---|---|---|
| 1 | <case> | ✅ / ❌ | `NN-name.png` |

## Bugs
### <short title>
- Steps: 1. ... 2. ...
- Expected: ...
- Actual: ...
- Screenshot: `NN-name.png`

## Not tested
- <what you could not test and why>
```

## Verdict rules
- **pass**: every acceptance criterion works in the running product.
- **fail**: at least one bug a user would hit. Cosmetic nits go in the report as notes, not as a fail.
