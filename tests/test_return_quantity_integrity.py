import pytest
from shop.engine import RuleError


@pytest.mark.parametrize("quantity", [True, 1.5, "1", None])
def test_noninteger_return_preserves_shop(shop, quantity):
    # Seeded orders 7 and 8 are delivered; select an actual delivered line.
    before = shop.state()
    order = next(row for row in before["orders"] if row["status"] == "Delivered")
    with pytest.raises(RuleError, match="whole number"):
        shop.return_items(order["id"], order["items"][0]["id"], quantity)
    assert shop.state() == before
