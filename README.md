# Aged Receivable — Group by Currency

**Version:** 19.0.1.0.0  
**Category:** Accounting / Accounting  
**License:** LGPL-3  
**Depends:** `account_reports`

Adds a **"Group by Currency"** toggle to the Aged Receivable report. When enabled, each partner row expands into per-currency subtotals before showing individual journal items.

---

## Features

- New **"Group by Currency"** checkbox in the Aged Receivable Options dropdown.
- Grouped view: **Partner → Currency → Journal Items** (subtotals at each level).
- Appears only on Aged Receivable — not on Aged Payable.
- State is preserved across page navigations (stored in report options).
- Zero schema changes: no new tables, views, XML data files, or ACLs.

---

## How It Works

The feature is wired through three cooperating pieces:

### 1. Register the option (Python)

`AgedReceivableCurrencyHandler` inherits `account.aged.receivable.report.handler` and overrides `_custom_options_initializer` to add `group_by_currency` to the report options. This is what makes the option available on Aged Receivable only — the base filters component shows a checkbox only when its key exists in the options dict.

### 2. Inject the groupby (Python)

`AccountReportLine._get_groupby` is overridden to splice `currency_id` into the groupby chain when the option is active and the line belongs to the Aged Receivable handler:

```
partner_id, id  →  partner_id, currency_id, id
```

The custom SQL engine (`_report_custom_engine_aged_receivable`) already converts any `account.move.line` field in the groupby chain into SQL via `_field_to_sql`, so no SQL changes are needed.

### 3. Render the toggle (JavaScript)

`AgedPartnerBalanceFilters.prototype.filterExtraOptionsData` is patched to include a `group_by_currency` entry. The base `AccountReportFilters` component renders it as a checkbox in the "Options" dropdown and handles the toggle + report reload automatically.

---

## Installation

1. Copy the `aged_receivable_currency` folder into your custom addons path (e.g. `V19/Projects/`).
2. Ensure the path is listed in `server/odoo.conf` under `addons_path`.
3. Upgrade/install the module:

```powershell
# Run from V19\server\
..\python\python.exe odoo-bin -c odoo.conf -d <db> -u aged_receivable_currency --stop-after-init
```

---

## Development

### Environment

| Item | Value |
|------|-------|
| Odoo version | 19 (community) |
| Python | `V19/python/python.exe` (bundled, not on PATH) |
| Database | `odoo_19` / `odoo_19` |
| HTTP port | 8069 |

### Useful commands

```powershell
# Run from V19\server\

# Upgrade after a Python or JS change
..\python\python.exe odoo-bin -c odoo.conf -d <db> -u aged_receivable_currency --stop-after-init

# Dev server with live asset rebuild
..\python\python.exe odoo-bin -c odoo.conf -d <db> -u aged_receivable_currency --dev=all

# Run module tests (no tests exist yet)
..\python\python.exe odoo-bin -c odoo.conf -d <db> --test-enable -u aged_receivable_currency --stop-after-init
```

> **Note:** Front-end changes under `static/src/` only take effect after an `-u` upgrade or a restart with `--dev=all`.

### File structure

```
aged_receivable_currency/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── aged_receivable_currency.py   # Python backend (option + groupby)
└── static/src/components/currency_filter/
    └── currency_filter.js            # JS patch (filters toggle)
```

### Key core files (read-only reference)

| File | Purpose |
|------|---------|
| `server/odoo/addons/account_reports/models/account_aged_partner_balance.py` | Aged Receivable handler and custom SQL engine |
| `server/odoo/addons/account_reports/models/account_report.py` | `account.report.line._get_groupby` (~line 7876) |
| `server/odoo/addons/account_reports/components/aged_partner_balance/filters.js` | `AgedPartnerBalanceFilters` component |

---

## Notes

- The handler guard (`self.report_id._get_custom_handler_model() == 'account.aged.receivable.report.handler'`) in `_get_groupby` is essential — that method runs for every line of every report.
- `currency_id` is inserted at position `len(fields) - 1` (just before the final `id`), because the engine only fills detail columns (invoice date, amounts) when `current_groupby == 'id'`. Any level above `id` yields a subtotal/header row.
- Report-specificity on the JS side is implicit: the checkbox only appears when `group_by_currency` is present in `cachedFilterOptions`, and step 1 only adds it to the receivable handler.
