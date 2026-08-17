from infrastructure.llm.content_render import render_prompt


def _patch_case(monkeypatch, facts="F", dialogues="D", product="Продукт"):
    import infrastructure.llm.content_render as render_mod
    import infrastructure.llm.variables as vars_mod

    class _Case:
        def __init__(self):
            self.facts = facts
            self.dialogues = dialogues

    monkeypatch.setattr(vars_mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(vars_mod, "case_product_name", lambda cid: product)
    monkeypatch.setattr(
        vars_mod,
        "VARIABLES_MAP",
        {
            "product-name": vars_mod.case_product_name,
            "product-details": vars_mod._product_details,
            "real-dialogues": vars_mod._real_dialogues,
            "learning-details": vars_mod._product_details,
            "checklist": vars_mod._checklist,
        },
    )
    monkeypatch.setattr(render_mod, "resolve_case_id", lambda cid: "cc")


def test_replaces_known_placeholders(monkeypatch):
    _patch_case(monkeypatch, facts="ФАКТЫ", dialogues="ДИАЛОГИ")
    out = render_prompt("A {PRODUCT_DETAILS} B {REAL_DIALOGUES} C", "cc")
    assert out == "A ФАКТЫ B ДИАЛОГИ C"


def test_legacy_placeholders_still_work(monkeypatch):
    _patch_case(monkeypatch, facts="ФАКТЫ", dialogues="ДИАЛОГИ")
    out = render_prompt("A {FACTS} B {DIALOGUES} C", "cc")
    assert out == "A ФАКТЫ B ДИАЛОГИ C"


def test_keeps_json_braces(monkeypatch):
    _patch_case(monkeypatch)
    tpl = 'JSON: {"verdict": "ok"} FACTS: {PRODUCT_DETAILS}'
    out = render_prompt(tpl, "cc")
    assert '{"verdict": "ok"}' in out
    assert "FACTS: F" in out


def test_empty_content_fallback(monkeypatch):
    _patch_case(monkeypatch, facts="", dialogues="")
    out = render_prompt("{PRODUCT_DETAILS}|{REAL_DIALOGUES}", "cc")
    assert out == "(фактология не загружена)|(образцовые диалоги не загружены)"


def test_no_placeholder_noop():
    assert render_prompt("plain text", "cc") == "plain text"


def test_product_placeholder(monkeypatch):
    _patch_case(monkeypatch, product="SPIN-продажи")
    out = render_prompt("Тема: {PRODUCT_NAME}. {PRODUCT_DETAILS}", "spin")
    assert out == "Тема: SPIN-продажи. F"
