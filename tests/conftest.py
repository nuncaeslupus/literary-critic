from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_user_state(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Never read or write the real workspace home or registry during tests."""
    state = tmp_path_factory.mktemp("user-state")
    monkeypatch.setenv("LITCRITIC_HOME", str(Path(state) / "home"))
    monkeypatch.setenv("LITCRITIC_REGISTRY", str(Path(state) / "registry.txt"))
