"""Revision regression tests. Run with python -m pytest tests -q after installing requirements."""
from pathlib import Path
import app as system

ROOT = Path(__file__).resolve().parents[1]


def test_registration_and_map_removed():
    assert '/register' not in [r.rule for r in system.app.url_map.iter_rules()]
    assert '/admin/users' not in [r.rule for r in system.app.url_map.iter_rules()]
    assert 'L.map(' not in (ROOT / 'templates' / 'stations.html').read_text()
    assert 'name="address"' not in (ROOT / 'templates' / 'admin_stations.html').read_text()
    assert 'name="latitude"' not in (ROOT / 'templates' / 'admin_stations.html').read_text()
    assert 'name="longitude"' not in (ROOT / 'templates' / 'admin_stations.html').read_text()


def test_only_admin_sessions_are_accepted():
    with system.app.test_request_context('/'):
        from flask import session
        session.update({'user_id': 2, 'username': 'ordinary', 'role': 'user'})
        assert system.current_user() is None
        session.update({'user_id': 1, 'username': 'admin', 'role': 'admin'})
        assert system.current_user()['username'] == 'admin'


def test_pdf_review_flags_overprinted_city():
    source = (ROOT / 'sample' / 'DOE_NCR_2026-09-29_to_10-05.pdf').read_bytes()
    result = system.parse_doe_pdf(source)
    sample = [r for r in result['rows'] if r['city']=='Muntinlupa City' and r['page']==2]
    assert sample and all(r['needs_review'] for r in sample)
