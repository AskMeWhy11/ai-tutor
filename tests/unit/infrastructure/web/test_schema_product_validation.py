from __future__ import annotations

import pytest
from pydantic import ValidationError

from infrastructure.content.registry import available_case_ids
from infrastructure.web.schemas import CreateSessionRequest, StartTrainingCmd


def test_default_product_ok() -> None:
    assert CreateSessionRequest().product_id == "cc_novichok"
    assert StartTrainingCmd().product_id == "cc_novichok"


@pytest.mark.parametrize("product_id", sorted(available_case_ids()))
def test_available_products_accepted(product_id: str) -> None:
    assert CreateSessionRequest(product_id=product_id).product_id == product_id
    assert StartTrainingCmd(product_id=product_id).product_id == product_id


def test_unknown_product_rejected() -> None:
    with pytest.raises(ValidationError):
        CreateSessionRequest(product_id="nope")
    with pytest.raises(ValidationError):
        StartTrainingCmd(product_id="nope")
