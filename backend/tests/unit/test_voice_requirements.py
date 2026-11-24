"""The voice agent image installs backend/requirements.txt; the [voice] extra must match."""

import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_requirements_txt_matches_voice_extra():
    extra = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]["voice"]
    lines = (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines()
    pinned = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    assert sorted(pinned) == sorted(extra)
