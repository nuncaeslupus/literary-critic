from typing import Any

import pytest

from litcritic import dc


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dc, "_checked", False)


def test_dc_check_rejects_other_major(monkeypatch: pytest.MonkeyPatch) -> None:
    real = dc._execute

    def fake(op: str, request: dict[str, Any]) -> dict[str, Any]:
        if op == "capabilities":
            return {"api": "2.0", "ok": True, "op": op, "result": {}}
        return real(op, request)

    monkeypatch.setattr(dc, "_execute", fake)
    with pytest.raises(dc.DocError) as err:
        dc.run("capabilities", {})
    assert err.value.code == "API_UNSUPPORTED" and "pip install" in err.value.hint


def test_dc_run_returns_result_and_raises_error_envelopes() -> None:
    assert "operations" in dc.run("capabilities", {})
    with pytest.raises(dc.DocError) as err:
        dc.run("info", {"doc": "/nonexistent/x.docx"})
    assert err.value.code and err.value.message
