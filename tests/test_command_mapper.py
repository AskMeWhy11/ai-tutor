from domain.states import FSMState
from infrastructure.web.command_mapper import available_commands_for


def test_training_only_user_message():
    cmds = available_commands_for(FSMState.TRAINING)
    assert [c.type for c in cmds] == ["user_message"]


def test_example_only_user_message():
    assert [c.type for c in available_commands_for(FSMState.EXAMPLE)] == ["user_message"]


def test_practice_only_user_message():
    assert [c.type for c in available_commands_for(FSMState.PRACTICE)] == ["user_message"]


def test_knowledge_only_user_message():
    assert [c.type for c in available_commands_for(FSMState.KNOWLEDGE)] == ["user_message"]


def test_technical_states_no_commands():
    for s in (
        FSMState.TRAINING_DONE,
        FSMState.EXAMPLE_DONE,
        FSMState.PRACTICE_EVAL,
        FSMState.PRACTICE_PARTIAL,
        FSMState.PRACTICE_SUCCESS,
        FSMState.KNOWLEDGE_DONE,
    ):
        assert available_commands_for(s) == []
