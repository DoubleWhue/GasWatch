# GasWatch — Revised DFD and schema implementation notes

The provided DFD includes users/access, station/fuel management, price management, browsing, comparison, history, price alerts, and reports. This revision keeps those process responsibilities except for the user-requested removal of map functionality, registration, and multiple user accounts.

| Data store | SQL table | Notes |
|---|---|---|
| D1 Users | `users` | Only `admin` may log in. Hashed password, no registration or admin role management UI. The username field was added to the data dictionary so login is possible. |
| D2 Gas Stations | `gas_stations` | Station name, brand, city, status. Detailed address and map coordinates removed as requested. |
| D3 Fuel Types | `fuel_types` | Seven standard fuel types initially seeded. |
| D4 Fuel Prices | `fuel_prices` | Unique station/fuel current price, update timestamp and editor. |
| D5 Price History | `price_history` | Appends historical prices on actual changes. |
| PDF support | `pdf_import_batches`, `regional_prices` | Keeps DOE city/brand price **ranges** separate from actual station prices. |

**PDF extraction support:** The DOE NCR sample has minimum/maximum ranges and sometimes a common value. It is not valid to assign a range to a precise gas station without verified additional data. The preview therefore saves city/brand/fuel-level observations. Uploads must be searched, edited where necessary, and confirmed when flagged.

**Removed functionality:** interactive map, address and geographic coordinates, public registration, user management/role assignment. City is retained as a grouping/filter, not a map location. The original DFD illustration may be updated in your academic report to remove the mapping and multiple-account details; this is a software implementation revision, not a redrawing of the submitted DFD.

**Alert rules:** More than 40% price change versus earlier comparable price raises a review flag. No forecasts were added: the submitted GasWatch DFD and dictionary do not specify ARIMA.
