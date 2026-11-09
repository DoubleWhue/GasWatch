"""Dashboard average cards must report actual averages, not midpoint estimates."""
from datetime import date
from decimal import Decimal
import app as system

FUELS = [{'fuel_id': 1, 'fuel_name': 'RON 91'}, {'fuel_id': 2, 'fuel_name': 'DIESEL'},
         {'fuel_id': 3, 'fuel_name': 'KEROSENE'}]
WEEK = {'week_start': date(2026, 9, 29), 'week_end': date(2026, 10, 5)}
CITIES = [{'city': 'Manila City'}, {'city': 'Quezon City'}]


def test_doe_average_only_uses_reported_common_prices(monkeypatch):
    def mock_sql(query, params=(), one=False):
        if 'SELECT DISTINCT city' in query:
            return CITIES
        assert "r.brand='OVERALL'" in query
        assert 'r.common_price IS NOT NULL' in query
        assert 'AVG(r.common_price)' in query
        assert params == [WEEK['week_start']]
        return [{'fuel_id': 1, 'average_price': Decimal('86.50'), 'sample_count': 2}]
    monkeypatch.setattr(system, 'sql', mock_sql)
    monkeypatch.setattr(system, 'datasets', lambda: FUELS)
    with system.app.test_request_context('/'):
        result = system.dashboard_fuel_averages(WEEK)
    assert result['source'] == 'doe'
    assert result['cards'][0]['average_price'] == Decimal('86.50')
    assert result['cards'][0]['sample_count'] == 2
    assert result['cards'][1]['average_price'] is None  # never invent #N/A
    assert result['cards'][2]['sample_count'] == 0


def test_station_average_city_filter(monkeypatch):
    def mock_sql(query, params=(), one=False):
        if 'SELECT DISTINCT city' in query:
            return CITIES
        assert 'AVG(p.price_per_liter)' in query
        assert "s.status='active'" in query
        assert 's.city=%s' in query
        assert params == ['Quezon City']
        return [{'fuel_id': 2, 'average_price': Decimal('94.88'), 'sample_count': 4}]
    monkeypatch.setattr(system, 'sql', mock_sql)
    monkeypatch.setattr(system, 'datasets', lambda: FUELS)
    with system.app.test_request_context('/?average_source=stations&average_city=Quezon+City'):
        result = system.dashboard_fuel_averages(WEEK)
    assert result['city'] == 'Quezon City'
    assert result['cards'][1]['average_price'] == Decimal('94.88')
    assert result['cards'][1]['sample_count'] == 4


def test_invalid_city_reverts_to_all_cities(monkeypatch):
    def mock_sql(query, params=(), one=False):
        if 'SELECT DISTINCT city' in query:
            return CITIES
        assert params == [WEEK['week_start']]
        return []
    monkeypatch.setattr(system, 'sql', mock_sql)
    monkeypatch.setattr(system, 'datasets', lambda: FUELS)
    with system.app.test_request_context('/?average_city=Unknown'):
        result = system.dashboard_fuel_averages(WEEK)
    assert result['city'] == ''
    assert all(item['average_price'] is None for item in result['cards'])
