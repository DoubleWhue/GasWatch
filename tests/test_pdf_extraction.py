from pathlib import Path
import pytest
from app import parse_doe_pdf, number, source_week_from_text

FILE = Path(__file__).resolve().parents[1] / 'sample' / 'DOE_NCR_2026-09-29_to_10-05.pdf'


def test_sample_pdf_counts_and_dates():
    data = parse_doe_pdf(FILE.read_bytes())
    assert data['week_start'] == '2026-09-29'
    assert data['week_end'] == '2026-10-05'
    assert len(data['rows']) == 364
    assert len({row['city'] for row in data['rows']}) == 12
    assert any(row['city'] == 'Muntinlupa City' for row in data['rows'])
    assert len([row for row in data['rows'] if row['brand']=='OVERALL']) == 76


def test_known_pdf_prices():
    data = parse_doe_pdf(FILE.read_bytes())
    def find(city, brand, fuel):
        return next(r for r in data['rows'] if r['city']==city and r['brand']==brand and r['fuel_name']==fuel)
    petron = find('Caloocan City', 'PETRON', 'RON 95')
    assert (petron['min_price'], petron['max_price']) == ('87.30', '92.90')
    overall = find('Caloocan City', 'OVERALL', 'RON 91')
    assert (overall['min_price'], overall['max_price'], overall['common_price']) == ('76.70','91.99','90.60')


def test_bad_input_is_rejected():
    with pytest.raises(Exception):
        parse_doe_pdf(b'not a PDF')
    with pytest.raises(ValueError):
        source_week_from_text('No DOE week available')
    with pytest.raises(ValueError):
        number('-10')
    with pytest.raises(ValueError):
        number('INVALID')
