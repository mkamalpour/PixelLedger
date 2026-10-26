def test_report_is_read_only_aggregate_and_profit_bridge_balances(client, shop):
    before = shop.state()
    response = client.get('/api/report')
    assert response.status_code == 200
    report = response.json()
    assert report['simulation'] and report['money_unit'] == 'integer cents'
    assert sum(row['amount_cents'] for row in report['profit_bridge']) == report['metrics']['profit_cents']
    assert 'customers' not in report and 'orders' not in report and 'ledger' not in report
    assert report['day'] == before['day']
    assert shop.state() == before
    assert response.headers['cache-control'] == 'no-store'
