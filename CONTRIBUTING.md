# Contributing to Jardinier

Welcome to Jardinier, a project born from the noble pursuit of not paying for budgeting software. Here's how to get set up and how we operate.

## Setup

```bash
git clone <repo-url>
cd jardinier
uv sync --all-extras --dev
```

## Development

```bash
uv run ruff format .          # format code
uv run ruff check .           # lint
uv run ruff check --fix .     # lint with auto-fix
uv run pytest                 # run tests
```

## Environment

Create `~/.config/jardinier/.env` with your Firefly-III credentials (works from any directory):

```
FIREFLY_API_URL=https://your-firefly-instance.com/api/v1
FIREFLY_API_TOKEN=your-token
```

Alternatively, export them as environment variables, or place a `.env` in the project root.

## Releasing

```bash
uv version <new-version>
git tag -a v<new-version> -m v<new-version>
git push --tags
```

The publish workflow builds and uploads to PyPI automatically on tag push.

---

## Community Rules

### Be nice or be gone

Any form of insult, harassment, or abuse will result in an immediate block. No appeals, no drama, no second chances. Life is too short and this is free software.

### Bug reports

If you're going to report a bug, give me clear reproduction steps. "It doesn't work" is not a bug report, it's a cry for help I can't answer. What did you do ? What command did you run ? What flags ? what is your environment ? I NEED TO KNOW IT ALL. There CANNOT be too many details in a bug report. Actually use AI for that, it's super great ! Proofread it though, because the steps have to be reproductible. Issues without reproduction steps will be ignored, unaddressed, and unceremoniously closed after 24 hours. I'm not your IT department (unless you're actually my IT department, in which case, hi, I love you, you are the best).

### Feature requests

Feature requests will be considered, or maybe they won't, or maybe they will, maybe not. Some days I'll be generous. Other days I've just had a long day at work and the answer is no. It's nothing personal. It might even become personal, but that's between me and my therapist.

### Questions

Questions are always welcome. Genuinely. I'm happy to help. This is the one rule that doesn't have a sarcastic caveat. Ask away.

### AI slop

Providing Github is not having yet another major incident and you can open an issue or a PR, please give it a little effort. Things that is are clearly copy-pasted from $YOUR_FAVORITE_AI_TOOL without any thought, review, or basic proofreading will be dismissed immediately. I can spot it. Everyone can spot it. Heck even AI can spot it. It's not fooling anyone. Repeat offenders will be banned without warning. If you're going to use AI, at least have the decency to read what it wrote before hitting submit.

### Pull requests

PRs are welcome and appreciated. Just keep them short — ideally under 10 modified files and under 500 lines of code. I'm willing to be a little flexible on that, but if you drop a 2,000 line refactor and Github happens to not be down that day, I will stare at it, feel overwhelmed, and quietly close the tab. Nobody wins. Run `ruff format`, `ruff check`, and `pytest` before pushing. One logical change per PR.
