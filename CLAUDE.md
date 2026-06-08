# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Windows all-in-one Odoo 19 install rooted at `C:\Users\harsh\OneDrive\Desktop\Odoo\V19`:
- `server/` — Odoo source + `odoo-bin` + `odoo.conf`. Core modules under `server/odoo/addons/` (read these to understand what you're extending — especially `account_reports/`).
- `Projects/` — custom addons (this module lives here); already on `addons_path` in `server/odoo.conf`.
- `python/python.exe` — the bundled interpreter. There is no `python` on PATH; use this.
- Postgres user/pwd `odoo_19` / `odoo_19`; HTTP on `8069`; `with_demo = False`; `db_name` is blank in the conf, so always pass `-d <db>`.

## Commands

Run from the `server/` directory (so `odoo-bin` and `odoo.conf` resolve):

```
# Upgrade the module after a Python change (also rebuilds JS/QWeb assets)
..\python\python.exe odoo-bin -c odoo.conf -d <db> -u aged_receivable_currency --stop-after-init

# Interactive dev run with live asset rebuild (no --stop-after-init)
..\python\python.exe odoo-bin -c odoo.conf -d <db> -u aged_receivable_currency --dev=all

# Run this module's tests
..\python\python.exe odoo-bin -c odoo.conf -d <db> --test-enable -u aged_receivable_currency --stop-after-init
```

There are no tests in this module yet (no `tests/` package). Front-end changes (`static/src/**`) only take effect after an `-u` upgrade or a restart with `--dev=all`; editing the `.js` without one will appear to do nothing.

## What this module does

Adds a **"Group by Currency"** toggle to the **Aged Receivable** report (and only that report — not Aged Payable). The whole feature is ~60 lines of Python + ~10 lines of JS; there are intentionally **no XML data files, no views, and no ACLs** (report handlers are AbstractModels needing none).

## Architecture — the non-obvious part

The Aged Receivable report is **engine-driven**, not line-override-driven. Do not try to hook report rendering by overriding per-line methods (e.g. `_get_report_line_partner`) — **those do not exist** on the Odoo 19 handler. The relevant core files:

- `server/odoo/addons/account_reports/models/account_aged_partner_balance.py` — handler `account.aged.receivable.report.handler`. Lines come from the custom SQL engine `_report_custom_engine_aged_receivable` → `_aged_partner_report_custom_engine_common`, which groups by whatever `current_groupby`/`next_groupby` it receives and turns each key into SQL via `_field_to_sql`. **This means you can add any `account.move.line` field to the groupby chain and the engine handles it with zero SQL changes.**
- `server/odoo/addons/account_reports/models/account_report.py` — `account.report.line._get_groupby(options)` (~line 7876) returns the line's groupby string (for Aged Receivable: `partner_id, id`, defined in `account_reports/data/aged_partner_balance.xml`). This is the single backend extension point.

The feature is wired through **three** cooperating pieces (`models/aged_receivable_currency.py` + `static/src/components/currency_filter/currency_filter.js`):

1. **Register the option.** Override `_custom_options_initializer` on the receivable handler to set `options['group_by_currency']`. This is what makes the option *exist* on this report — and only this report.
2. **Inject the groupby.** Override `account.report.line._get_groupby` to splice `currency_id` into the chain (`partner_id, id` → `partner_id, currency_id, id`) when `options['group_by_currency']` is set **and** `self.report_id._get_custom_handler_model() == 'account.aged.receivable.report.handler'`. The handler guard is essential — `_get_groupby` runs for every line of every report.
3. **Render the toggle.** Patch `AgedPartnerBalanceFilters.prototype.filterExtraOptionsData` (in `@account_reports/components/aged_partner_balance/filters`) to add a `group_by_currency` entry. The base `AccountReportFilters` renders these as the "Options" dropdown checkboxes and wires the toggle + reload automatically.

### Report-specificity is implicit, not coded

Aged Receivable and Aged Payable **share the same filters component** (`AgedPartnerBalanceFilters`). The toggle does not appear on Payable because the base filters only show an extra option whose key is present in `cachedFilterOptions` (see `isExtraOptionFilterShown` in `account_report/filters/filters.js`), and step 1 only adds `group_by_currency` to the *receivable* handler's options. So adding/removing the option from `_custom_options_initializer` is what controls which reports show the checkbox — there is no per-report check in the JS.

### Why `currency_id` goes before the final `id`

The engine's `build_result_dict` only fills detail fields (invoice date, amount, etc.) when `current_groupby == 'id'`; every other level returns subtotals. Inserting `currency_id` at the second-to-last position makes each currency a subtotal/header level above the individual journal items, and the group line's label comes for free from the `res.currency` record's display name.
