from infrastructure.content.registry import preza_file_for


def test_explicit_preza() -> None:
    assert preza_file_for("cc_novichok") == "cc_preza.pdf"


def test_derived_preza() -> None:
    assert preza_file_for("aida") == "aida_preza.pdf"
    assert preza_file_for("spin") == "spin_preza.pdf"


def test_unknown_falls_back_to_default() -> None:
    assert preza_file_for("nope") == "cc_preza.pdf"
