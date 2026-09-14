from pathlib import Path

import pytest

from domain.states import Mode
from infrastructure.llm.prompt_store import PromptStore
from infrastructure.llm.yaml_export import _export_text, export_prompts_yaml


def test_export_contract_and_separation(tmp_path: Path) -> None:
    store = PromptStore(tmp_path / "prompts.json")
    store.replace_all(
        system_prompt="",
        templates={},
        case_id="new_product",
        mode_prompts=dict.fromkeys(Mode, "Роль по теме {PRODUCT_NAME}\r\n{PRODUCT_DETAILS}\r\n"),
        stage_director_prompts=dict.fromkeys(Mode, "DIRECTOR_ONLY"),
    )
    out = export_prompts_yaml(store, "new_product")
    keys = [line for line in out.splitlines() if line.startswith("    new-product-")]
    assert len(keys) == 12
    assert "DIRECTOR_ONLY" not in out
    assert "{PRODUCT_NAME}" not in out
    assert "{DIALOGUE_HISTORY}" in out
    assert "```" not in out
    assert "\r" not in out
    assert "закрыть вклад" not in out
    assert "мошенников" not in out


def test_export_preserves_role_text() -> None:
    out = _export_text("demo-client-transcription-prompt", "Особый сценарий\r\n")
    assert out.startswith("Особый сценарий")
    assert "{DIALOGUE_HISTORY}" in out


@pytest.mark.parametrize("text", ["", "{UNSUPPORTED}", "TRAINING", "codeNamemd inside"])
def test_export_rejects_invalid_contract(text: str) -> None:
    with pytest.raises(ValueError):
        _export_text("demo-client-transcription-prompt", text)


def test_export_rejects_embedded_director() -> None:
    with pytest.raises(ValueError, match="Completion criteria"):
        _export_text("demo-client-transcription-prompt", "КРИТЕРИИ ЗАВЕРШЕНИЯ СТАДИИ")
