set dotenv-load := true
set shell := ["bash", "-uc"]

@default:
    just --list

version := `uv version --short`

publish:
    @echo "The version in pyproject.toml is currently: v{{version}}"
    @echo "Did you bump it for this release? (Press Enter to continue, or Ctrl+C to cancel)"
    @read _

    uv build
    uv publish

    git tag v{{version}}
    git push origin v{{version}}

test:
    uv run pytest

check-type:
    uv run mypy .
    uv run pyrefly check

lint:
    uv run ruff check .

check-format:
    uv run black --check .

check: check-type test lint check-format
