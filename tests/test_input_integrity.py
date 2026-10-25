import pytest
from shop.engine import RuleError


@pytest.mark.parametrize('discount', ['-0.001', '25.001', '12.345', 'NaN', 'Infinity', 'bad'])
def test_invalid_discount_preserves_entire_shop(shop, discount):
    before = shop.state()
    with pytest.raises(RuleError):
        shop.create_order(1, [{'product_id': 13, 'quantity': 1}], discount)
    assert shop.state() == before


def test_boolean_quantities_are_not_stock_units(shop):
    before = shop.state()
    with pytest.raises(RuleError):
        shop.restock(13, True)
    with pytest.raises(RuleError):
        shop.create_order(1, [{'product_id': 13, 'quantity': True}])
    assert shop.state() == before


def test_api_rejects_boolean_identifiers(client):
    response = client.post('/api/orders', json={'customer_id': True, 'items': [{'product_id': 13, 'quantity': 1}]})
    assert response.status_code == 422
