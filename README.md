# GASWATCH — Dark Navy + Red Edition

**Web-Based Gasoline Price Monitoring System for Metro Manila**

Flask + PyMySQL (XAMPP) application. The Python backend and DOE PDF extraction are contained in **one `app.py`**. The entire MySQL setup is contained in **one `gaswatch_db.sql`**. UI uses templates, stylesheets and JavaScript in their normal Flask folders.

## What's included

### Public pages
- **Dashboard** — navy hero, four system summary cards, seven fuel-category average cards with DOE or station sources, city-selectable price explorer, and recent price listings.
- **City explorer** — dark navy, red-accent clickable SVG diagram representing the 17 NCR LGUs. Clicking a city updates its DOE brand price-range listing. Accessible city dropdown is also provided. **Stylized schematic only, not an exact geographic or legal-boundary map. No Google Maps, GPS, coordinates, routing, or API keys.**
- **Fuel Prices** — filterable DOE fuel cards and tables by brand, city and type.
- **Price Trends** — historical price-range line chart and archive. No invented missing-week observations.
- **Price Comparison** — brand/city comparisons (DOE ranges) or separately recorded individual station prices.
- **Station Directory / Station Prices / Alerts / Reports** retained and recolored.

### Admin pages
- One supported administrator account only, without a registration page.
- PDF Extraction: upload DOE NCR PDF, inspect 40% change warnings and overlapping city labels, search/edit rows, confirm flagged rows, exclude records, and save reviewed values.
- Manage gas stations, fuel types, station prices; download reports as CSV/XLSX.

### Naming
- Original DOE/database code `RON 91` displays as **Regular**.
- Original DOE/database code `RON 95` displays as **Premium**.
- RON 97, RON 100, Diesel, Diesel Plus, and Kerosene retain their names.
- Stored IDs, form values, database records and DOE extraction remain in the original codes.

## Install in Windows with XAMPP

1. Extract the ZIP. Start **MySQL** in XAMPP.
2. Open phpMyAdmin and import `gaswatch_db.sql` into MySQL (the SQL creates the database `gaswatch_db`). **Back up your existing database before importing SQL**. The SQL removes discontinued address, latitude and longitude fields from existing `gas_stations` tables.
3. Open PowerShell in the project folder. Run:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`. Update the MySQL credentials as necessary (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`).
5. Start with:

   ```powershell
   python app.py
   ```

6. Public site: `http://127.0.0.1:5000/` — Admin: `http://127.0.0.1:5000/login`

**Default local login:** username **`admin`**, password **`admin123`**. Stored with Werkzeug password hashing and managed through `ADMIN_PASSWORD` in `.env`. Change it to a strong password before any real deployment. Don't expose Flask's development server publicly. There is no registration page.

For trusted LAN testing only, configure `HOST=0.0.0.0`, leave `FLASK_DEBUG=0`, and visit `http://COMPUTER_LAN_IP:5000/` from devices on the same network.

## Using the DOE sample PDF

The project includes `sample/DOE_NCR_2026-09-29_to_10-05.pdf`, for the September 29–October 5, 2026 monitoring week. Log in > **PDF Extraction** > select the report > **Extract & Review Prices**. Verify orange-highlighted rows before confirming and importing. The parser recovered **364 price-range entries across 12 cities** from this sample, including **37 Muntinlupa rows** flagged because the page-2 text layer overlaps the city label. This extraction workflow is designed for the provided text-based DOE table format, not arbitrary layout changes or scanned PDFs without a text layer.

Important distinction: **DOE city/brand price ranges are not station-level pump prices.** The PDF entries are stored in `regional_prices`/`pdf_import_batches`. Actual station prices, if entered by admin, are stored separately in `fuel_prices`/`price_history`.

## Dashboard average calculation

- DOE source: arithmetic average of the available **OVERALL city common prices** for each fuel type and selected city/monitoring week; blank `#N/A` records excluded. It is not an average across individual gas station prices.
- Station source: arithmetic average of current verified entries for active stations, without mixing DOE data.
- If no matching values exist, the page shows **—** rather than fabricating prices or graph points.

## Source files

- `app.py` — all routes, MySQL access, login, PDF extraction/validation and reporting
- `gaswatch_db.sql` — MySQL schema and seed values
- `templates/` — 18 public/admin HTML templates
- `static/style.css` — previous base components
- `static/theme.css` — navy/red design system and responsive views
- `static/app.js` — PDF review and trend chart
- `static/gaswatch-ui.js` — mobile nav and clickable city map
- `tests/` — parser and revision tests from the existing project
- `docs/` — original DFD/schema notes and reference previews
- `.env.example` — local environment configuration

## Verification performed in the authoring environment

- Python syntax: passed.
- All 18 Jinja HTML templates: parsed successfully.
- JavaScript syntax: passed both scripts.
- PDF parser against actual supplied report: 364 entries, 12 cities, monitoring week correctly read.
- Desktop/mobile static rendering: 1440px and 390px layouts checked; no horizontal page overflow.
- Browser DOM: 17 interactive city regions rendered; checked dark navy background.

**Not performed:** a complete integrated XAMPP/MySQL login/import test, because there is no MySQL server or installable Flask/PyMySQL runtime in the authoring environment. Test the app locally using the instructions above.

## Appearance

- Primary `#0B1F3A` dark navy
- Secondary `#162D50` navy
- Accent `#C62828` deep red
- Background `#F5F7FB` light gray

The NCR map is an intentionally stylized selectable city diagram, not a surveyed boundary map.
