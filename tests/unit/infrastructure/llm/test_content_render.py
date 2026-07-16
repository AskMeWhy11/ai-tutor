from infrastructure.llm.content_render import render_prompt


def test_replaces_known_placeholders(monkeypatch):
    import infrastructure.llm.content_render as mod

    class _Case:
        facts = "ФАКТЫ"
        dialogues = "ДИАЛОГИ"

    monkeypatch.setattr(mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(mod, "resolve_case_id", lambda cid: "cc")

    out = render_prompt("A {FACTS} B {DIALOGUES} C", "cc")
    assert out == "A ФАКТЫ B ДИАЛОГИ C"


def test_keeps_json_braces(monkeypatch):
    import infrastructure.llm.content_render as mod

    class _Case:
        facts = "F"
        dialogues = "D"

    monkeypatch.setattr(mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(mod, "resolve_case_id", lambda cid: "cc")

    tpl = 'JSON: {"verdict": "ok"} FACTS: {FACTS}'
    out = render_prompt(tpl, "cc")
    assert '{"verdict": "ok"}' in out
    assert "FACTS: F" in out


def test_empty_content_fallback(monkeypatch):
    import infrastructure.llm.content_render as mod

    class _Case:
        facts = ""
        dialogues = ""

    monkeypatch.setattr(mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(mod, "resolve_case_id", lambda cid: "cc")

    out = render_prompt("{FACTS}|{DIALOGUES}", "cc")
    assert out == "(фактология не загружена)|(образцовые диалоги не загружены)"


def test_no_placeholder_noop():
    assert render_prompt("plain text", "cc") == "plain text"


def test_product_placeholder(monkeypatch):
    import infrastructure.llm.content_render as mod

    class _Case:
        facts = "F"
        dialogues = "D"

    monkeypatch.setattr(mod, "load_case", lambda cid: _Case())
    monkeypatch.setattr(mod, "resolve_case_id", lambda cid: "spin")
    monkeypatch.setattr(mod, "case_product_name", lambda cid: "SPIN-продажи")

    out = render_prompt("Тема: {PRODUCT}. {FACTS}", "spin")
    assert out == "Тема: SPIN-продажи. F"
