# Complete Learning Guide — `aged_receivable_currency`

This document explains everything about this module from the ground up: what Odoo's report engine is, how the Aged Receivable report works internally, what problem this module solves, how every line of code wires together, and how to run and test it all.

Read this top-to-bottom the first time. After that, use the section headings as a quick reference.

---

## Table of Contents

1. [Background — Odoo's Report Engine](#1-background--odos-report-engine)
2. [The Aged Receivable Report — Core Internals](#2-the-aged-receivable-report--core-internals)
3. [What This Module Adds](#3-what-this-module-adds)
4. [File Structure](#4-file-structure)
5. [Deep Dive — Python Backend](#5-deep-dive--python-backend)
6. [Deep Dive — JavaScript Frontend](#6-deep-dive--javascript-frontend)
7. [How the Three Pieces Connect](#7-how-the-three-pieces-connect)
8. [Data Flow — Step by Step](#8-data-flow--step-by-step)
9. [Installation & Running](#9-installation--running)
10. [Making Changes](#10-making-changes)
11. [Common Mistakes](#11-common-mistakes)
12. [Glossary](#12-glossary)

---

## 1. Background — Odoo's Report Engine

### What is `account_reports`?

`account_reports` is the Odoo module that powers financial reports: Balance Sheet, Profit & Loss, Aged Receivable, Aged Payable, and many others. It provides a generic engine so each report does not need to write its own rendering logic.

### The three layers of every report

```
┌─────────────────────────────────────────┐
│  account.report  (the "definition")     │  ← XML data: columns, lines, filters
├─────────────────────────────────────────┤
│  account.report.line  (each row rule)   │  ← groupby, expressions, engines
├─────────────────────────────────────────┤
│  Custom Handler  (the "engine")         │  ← Python: SQL, computation, options
└─────────────────────────────────────────┘
```

**`account.report`** — A database record that describes the report: its name, which columns to show, what filters to expose, and which custom handler to use. For Aged Receivable, this record is created by the XML file at:
```
server/odoo/addons/account_reports/data/aged_partner_balance.xml
```

**`account.report.line`** — Each line in the report definition. For Aged Receivable there is one line named "Aged Receivable" with `groupby = "partner_id, id"`. The `groupby` string tells the engine what SQL GROUP BY levels to use.

**Custom Handler** — An `AbstractModel` that contains the actual computation. For Aged Receivable the handler is `account.aged.receivable.report.handler`. It inherits from `account.aged.partner.balance.report.handler`, which holds the shared logic between Receivable and Payable.

### What is an AbstractModel?

In Odoo, an `AbstractModel` (`models.AbstractModel`) is a Python class that participates in Odoo's ORM and inheritance system but has **no database table**. It exists purely to hold methods. Report handlers use AbstractModels because they only need logic — no stored data.

### What is `_inherit`?

When you write `_inherit = 'some.model'` without `_name`, Odoo patches your new methods directly onto the existing model. Any instance of `some.model` will now also have your methods. This is how this module adds behaviour to the existing Odoo handler and report line without touching Odoo's source files.

---

## 2. The Aged Receivable Report — Core Internals

Understanding this section is the key to understanding why the module is built the way it is.

### The XML definition (read-only reference)

The report is defined in `aged_partner_balance.xml`. The critical part for this module is the line definition:

```xml
<record id="aged_receivable_line" model="account.report.line">
    <field name="name">Aged Receivable</field>
    <field name="groupby">partner_id, id</field>
    ...
</record>
```

`groupby = "partner_id, id"` means:
- **First level:** group by `partner_id` → one row per customer.
- **Second level (detail):** group by `id` → one row per journal item within that customer.

### How groupby becomes SQL

When the engine renders a line, it calls `account.report.line._get_groupby(options)` to get the current groupby string. It then splits this string by comma, takes the first field as `current_groupby` and the rest as `next_groupby`, and calls the custom engine function (`_report_custom_engine_aged_receivable`) with those values.

The custom engine does this (simplified):

```python
if current_groupby:
    groupby_field_sql = env['account.move.line']._field_to_sql(
        "account_move_line", current_groupby, query
    )
    groupby_clause = SQL("%s, %s", groupby_field_sql, period_table.period_index)
```

`_field_to_sql` is an ORM method that converts a field name string (`"partner_id"`, `"currency_id"`, `"id"`) into safe, correct SQL. **This means any valid `account.move.line` field can be used as a groupby level with zero SQL changes.** You just need to insert its name into the groupby string.

### What `current_groupby == 'id'` means

The engine has a special branch:

```python
def build_result_dict(report, query_res_lines):
    ...
    if current_groupby == 'id':
        # Fill detail columns: invoice date, due date, amount currency, etc.
        rslt.update({
            'invoice_date': query_res['invoice_date'][0],
            'amount_currency': query_res['amount_currency'],
            'currency_id': ...,
            ...
        })
    else:
        # Subtotal row: only period amounts and total, no detail columns
        rslt.update({
            'invoice_date': None,
            'amount_currency': None,
            'total': sum(rslt[f'period{i}'] for i in range(len(periods))),
        })
```

When `current_groupby == 'id'`, the engine fills all detail columns (invoice date, currency, account name). For every other groupby level it produces a **subtotal row** — just the aged period amounts and a total, with the detail columns blank. This is how the report shows collapsed partner rows with expandable detail lines.

### The period calculation (aging)

The SQL query joins `account_move_line` against a `period_table` CTE (Common Table Expression) that defines date buckets:

```
period0: Not yet due (date_maturity >= report date)
period1: 1–30 days overdue
period2: 31–60 days overdue
period3: 61–90 days overdue
period4: 91–120 days overdue
period5: Older (> 120 days)
```

Each journal item falls into exactly one period bucket based on its `date_maturity` (or `invoice_date`, depending on settings). The SQL uses `CASE WHEN period_table.period_index = N THEN amount ELSE 0 END` so that one row in the result has non-zero values in only one period column.

### The inheritance chain for handlers

```
account.report.custom.handler          (abstract base for all handlers)
    └── account.aged.partner.balance.report.handler   (shared receivable/payable logic)
            ├── account.aged.receivable.report.handler  (receivable-specific)
            └── account.aged.payable.report.handler     (payable-specific)
```

This module's `AgedReceivableCurrencyHandler` extends `account.aged.receivable.report.handler` using `_inherit`, so it only affects the receivable report.

---

## 3. What This Module Adds

Without this module, Aged Receivable groups like this when you expand a partner:

```
Customer A                    $5,000
  Invoice INV/2024/001        $2,000
  Invoice INV/2024/002        $3,000
```

With this module and "Group by Currency" enabled:

```
Customer A                    $5,000
  USD                         $3,000
    Invoice INV/2024/001      $2,000
    Invoice INV/2024/002      $1,000
  EUR                         $2,000
    Invoice INV/2024/003      $2,000
```

The groupby chain changes from:
```
partner_id, id
```
to:
```
partner_id, currency_id, id
```

`currency_id` becomes a subtotal level. Its label (e.g. "USD") comes automatically from `res.currency.display_name` via the ORM — no extra code needed.

---

## 4. File Structure

```
aged_receivable_currency/
│
├── __manifest__.py                         # Module metadata and asset registration
├── __init__.py                             # Imports the models package
│
├── models/
│   ├── __init__.py                         # Imports aged_receivable_currency
│   └── aged_receivable_currency.py         # All Python logic (2 classes)
│
└── static/src/components/currency_filter/
    └── currency_filter.js                  # Frontend patch (1 patch)
```

No XML data files, no views, no security files — deliberately. Report handlers are AbstractModels and need none of those. The only "registration" needed is in `__manifest__.py`.

---

## 5. Deep Dive — Python Backend

File: `models/aged_receivable_currency.py`

### Class 1 — `AgedReceivableCurrencyHandler`

```python
class AgedReceivableCurrencyHandler(models.AbstractModel):
    _inherit = 'account.aged.receivable.report.handler'
```

`_inherit` without `_name` means: add these methods to the existing model. No new model is created.

#### `_custom_options_initializer`

```python
def _custom_options_initializer(self, report, options, previous_options):
    super()._custom_options_initializer(report, options, previous_options)
    options['group_by_currency'] = (previous_options or {}).get(
        'group_by_currency', False
    )
```

**What it does:** Every time the Aged Receivable report is opened or refreshed, Odoo calls `_custom_options_initializer` to build the `options` dict. This dict is passed everywhere — to the engine, to the frontend, to filters. By adding `options['group_by_currency']`, this module:

1. Makes the key available for the Python groupby logic to read.
2. Makes the key available in `cachedFilterOptions` on the frontend, which is what causes the checkbox to appear in the Options dropdown.
3. Restores the previous state from `previous_options` so the toggle survives a page refresh.

**Why `super()` first?** The base `_custom_options_initializer` builds all the standard options (columns, multi_currency, show_account, aging_interval, etc.). You must call it first so those options exist before you add yours on top.

**Why `(previous_options or {}).get(..., False)`?** `previous_options` is `None` the very first time the report is opened. The `or {}` guard prevents a `NoneType` error. Defaulting to `False` means the toggle starts unchecked.

### Class 2 — `AccountReportLine`

```python
class AccountReportLine(models.Model):
    _inherit = 'account.report.line'
```

Note: this is `models.Model`, not `models.AbstractModel`, because `account.report.line` itself is a regular model with a database table.

#### `_get_groupby`

```python
def _get_groupby(self, options):
    groupby = super()._get_groupby(options)

    if (
        options.get('group_by_currency')
        and groupby
        and self.report_id._get_custom_handler_model()
        == 'account.aged.receivable.report.handler'
    ):
        groupby_fields = [part.strip() for part in groupby.split(',')]
        if 'currency_id' not in groupby_fields:
            insert_at = max(len(groupby_fields) - 1, 0)
            groupby_fields.insert(insert_at, 'currency_id')
        return ','.join(groupby_fields)

    return groupby
```

**What it does:** `_get_groupby` is called for every line of every report in the system. This override intercepts that call and potentially modifies the groupby string.

**The three guards explained:**

| Guard | Why it's needed |
|-------|----------------|
| `options.get('group_by_currency')` | Only modify if the user toggled the checkbox on |
| `and groupby` | Don't modify if there's no groupby (some report lines have none) |
| `self.report_id._get_custom_handler_model() == 'account.aged.receivable.report.handler'` | `_get_groupby` runs for ALL reports. Without this guard, enabling the option on any report would accidentally inject `currency_id` into the Aged Payable groupby and every other report that uses `_get_groupby`. This guard ensures the injection only happens for Aged Receivable lines. |

**The insertion logic:**

```python
groupby_fields = [part.strip() for part in groupby.split(',')]
# groupby_fields = ['partner_id', 'id']

insert_at = max(len(groupby_fields) - 1, 0)
# insert_at = max(2 - 1, 0) = 1

groupby_fields.insert(1, 'currency_id')
# groupby_fields = ['partner_id', 'currency_id', 'id']

return 'partner_id,currency_id,id'
```

`currency_id` is inserted at `len - 1` (second-to-last), which places it just before the final `id`. This is intentional: the `id` level must remain last because that is the only level where the engine fills detail columns. If you put `currency_id` after `id`, the detail rows would appear before the currency subtotals, which makes no sense.

**The `if 'currency_id' not in groupby_fields` check** prevents double-insertion if something else already added it.

---

## 6. Deep Dive — JavaScript Frontend

File: `static/src/components/currency_filter/currency_filter.js`

### Why JavaScript is needed at all

The backend added `group_by_currency` to the options dict. The backend knows the option exists. But the user needs a checkbox to toggle it. Odoo's `AccountReportFilters` component renders checkboxes for extra options dynamically from a getter called `filterExtraOptionsData`. If you add a key to that getter, the checkbox appears. If you don't, no UI shows up and the option can never be enabled.

### The patch

```javascript
import { patch } from "@web/core/utils/patch";
import { AgedPartnerBalanceFilters } from
    "@account_reports/components/aged_partner_balance/filters";

patch(AgedPartnerBalanceFilters.prototype, {
    get filterExtraOptionsData() {
        return {
            ...super.filterExtraOptionsData,   // keep Show Currency, Show Account
            group_by_currency: {
                name: _t("Group by Currency"),
            },
        };
    },
});
```

**`patch`** is Odoo's safe monkey-patching utility. It wraps the original method and lets you call `super` to get the original return value. It is the correct Odoo 17+ way to extend component behaviour without subclassing.

**`AgedPartnerBalanceFilters`** is the filters component used by both Aged Receivable and Aged Payable. We patch it here instead of `AccountReportFilters` (the base) because we only want this checkbox on the aged reports, not every financial report.

**Why does the checkbox still not appear on Aged Payable?** The `AccountReportFilters` base component checks `isExtraOptionFilterShown` before rendering each checkbox. That check looks at whether the option key exists in `cachedFilterOptions` (the options dict from the server). Since step 1 (`_custom_options_initializer`) only adds `group_by_currency` to the Aged Receivable handler's options, the key is absent from Aged Payable's options, and the checkbox is hidden. **The JS patch adds the entry unconditionally, but the Python controls visibility.** This is by design.

**`_t("Group by Currency")`** — `_t` is Odoo's translation function. Always use it for user-visible strings so the module is translatable.

**`...super.filterExtraOptionsData`** — Spreading the super result is critical. Without it, you would replace the "Show Currency" and "Show Account" checkboxes rather than adding to them.

### How the toggle works automatically

Once the checkbox is rendered, Odoo's base `AccountReportFilters` component handles the rest: clicking the checkbox calls `this.updateOption('group_by_currency', newValue)`, which updates the options dict on the server and reloads the report. No custom click handler is needed in this module.

---

## 7. How the Three Pieces Connect

```
User clicks "Group by Currency" checkbox
        │
        ▼
AccountReportFilters.updateOption('group_by_currency', true)
        │  (built-in Odoo behavior, no custom code needed)
        ▼
Server: _custom_options_initializer runs
  └─ options['group_by_currency'] = True   ← registered by Piece 1
        │
        ▼
Server: builds report lines
  └─ for each line, calls account.report.line._get_groupby(options)
       └─ our override fires (Piece 2)
          └─ injects 'currency_id': partner_id, id → partner_id, currency_id, id
        │
        ▼
Engine: _report_custom_engine_aged_receivable(
    current_groupby='currency_id',
    next_groupby='id'
  )
  └─ _field_to_sql('currency_id') → SQL GROUP BY account_move_line.currency_id
  └─ produces subtotal rows keyed by currency
        │
        ▼
Frontend renders: Partner → Currency subtotals → Journal item detail rows
        │
        ▼
JS patch (Piece 3) made the checkbox visible in the first place
```

---

## 8. Data Flow — Step by Step

This traces exactly what happens when a user opens Aged Receivable with the toggle on.

### Step 1 — Page Load

The browser fetches the report. The server calls `_custom_options_initializer` on `account.aged.receivable.report.handler`. Our patch adds `options['group_by_currency'] = False` (or `True` if previously set). Options dict is serialised and sent to the frontend.

### Step 2 — Frontend renders filters

`AgedPartnerBalanceFilters.filterExtraOptionsData` is read. Because of our JS patch it now includes `group_by_currency`. The base component sees this key also exists in `cachedFilterOptions` (the options from step 1), so it renders the "Group by Currency" checkbox.

### Step 3 — User enables the toggle

`updateOption('group_by_currency', true)` fires. The options dict is updated and a new report load is triggered.

### Step 4 — Server rebuilds the report

`_custom_options_initializer` runs again, this time restoring `options['group_by_currency'] = True` from `previous_options`.

### Step 5 — Engine processes each line

For the "Aged Receivable" line (the only line in this report), the engine calls `_get_groupby(options)`.

Our `AccountReportLine._get_groupby` override runs:
- `groupby = super()._get_groupby(options)` returns `"partner_id, id"` (from the XML definition, via `self.user_groupby`).
- The option is `True`, the report is Aged Receivable → inject `currency_id`.
- Returns `"partner_id,currency_id,id"`.

### Step 6 — First groupby level: `partner_id`

The engine is called with `current_groupby='partner_id'`, `next_groupby='currency_id,id'`. It runs this SQL (simplified):

```sql
SELECT
    account_move_line.partner_id AS grouping_key,
    CASE WHEN period_index = 0 THEN SUM(balance) ELSE 0 END AS period0,
    ...
FROM account_move_line
JOIN period_table ON ...
WHERE account_type = 'asset_receivable'
GROUP BY account_move_line.partner_id, period_table.period_index
```

Result: one row per partner per period, aggregated into one subtotal per partner. The UI shows a collapsed partner row.

### Step 7 — Second groupby level: `currency_id`

When the user expands a partner row, the engine is called with `current_groupby='currency_id'`, `next_groupby='id'`. The SQL groups by `account_move_line.currency_id`. Each distinct currency becomes a subtotal row under that partner.

The row label comes from the ORM: since `currency_id` is a Many2one to `res.currency`, Odoo automatically fetches `res.currency.display_name` (e.g. "USD") to label the row.

### Step 8 — Third groupby level: `id`

When the user expands a currency row, `current_groupby='id'`, `next_groupby=None`. The engine runs the query grouped by `account_move_line.id`. Each row is one journal item. Because `current_groupby == 'id'`, `build_result_dict` fills all detail columns: invoice date, amount currency, currency name, account name, etc.

---

## 9. Installation & Running

### Prerequisites

- Odoo 19 (all-in-one Windows install at `C:\Users\harsh\OneDrive\Desktop\Odoo\V19`)
- The module folder must be at `V19\Projects\aged_receivable_currency\`
- `V19\Projects\` must be on `addons_path` in `server\odoo.conf`
- A PostgreSQL database already exists (e.g. `odoo19_db`)

### First install

Run from `V19\server\`:

```powershell
..\python\python.exe odoo-bin -c odoo.conf -d odoo19_db -u aged_receivable_currency --stop-after-init
```

If the module is not yet installed, `-u` (update) also installs it. After this command exits (it stops itself due to `--stop-after-init`), the module is active in the database.

### Verify it is installed

Open `http://localhost:8069/web#action=base_setup.action_general_configuration` → Apps → search `aged_receivable_currency` → should show as Installed.

Or from the Odoo shell, open Accounting → Reporting → Aged Receivable → click the Options dropdown. "Group by Currency" should appear.

### After changing Python files

Any change to `.py` files requires an upgrade:

```powershell
..\python\python.exe odoo-bin -c odoo.conf -d odoo19_db -u aged_receivable_currency --stop-after-init
```

### After changing JavaScript files

JavaScript changes also require an upgrade (to rebuild assets):

```powershell
..\python\python.exe odoo-bin -c odoo.conf -d odoo19_db -u aged_receivable_currency --stop-after-init
```

Or, if you are running in dev mode, a browser hard-refresh (Ctrl+Shift+R) may be enough because `--dev=all` enables live asset loading.

### Dev mode (live reload)

```powershell
..\python\python.exe odoo-bin -c odoo.conf -d odoo19_db -u aged_receivable_currency --dev=all
```

`--dev=all` enables:
- Python method hot-reload on file save (no server restart needed for most Python changes).
- JS/QWeb asset live rebuild on page load.
- Detailed error tracebacks in the browser.

Leave this running while developing. After editing a `.py` file, refresh the browser. After editing a `.js` file, hard-refresh (Ctrl+Shift+R).

### Running tests

There are no tests yet in this module. When you add them to a `tests/` package:

```powershell
..\python\python.exe odoo-bin -c odoo.conf -d odoo19_db --test-enable -u aged_receivable_currency --stop-after-init
```

---

## 10. Making Changes

### Add the option to Aged Payable as well

Only one change is needed in Python: add the same option registration to the payable handler.

```python
class AgedPayableCurrencyHandler(models.AbstractModel):
    _inherit = 'account.aged.payable.report.handler'

    def _custom_options_initializer(self, report, options, previous_options):
        super()._custom_options_initializer(report, options, previous_options)
        options['group_by_currency'] = (previous_options or {}).get(
            'group_by_currency', False
        )
```

And update the handler guard in `_get_groupby` to also match `account.aged.payable.report.handler`. No JS change is needed — the checkbox will appear automatically once the key exists in the payable options.

### Change the groupby position

Currently `currency_id` goes at position `len - 1` (second-to-last). To put it first (before partners):

```python
groupby_fields.insert(0, 'currency_id')
# Result: currency_id, partner_id, id
```

This would show currencies as the top-level grouping, partners within each currency.

### Add another groupby field (e.g. `account_id`)

Follow the same pattern as `currency_id`. In `_get_groupby`, insert `'account_id'` at the desired position. No SQL changes needed — `_field_to_sql` handles it.

### Change the checkbox label

Edit the string in `currency_filter.js`:

```javascript
group_by_currency: {
    name: _t("Group by Currency"),  // change this string
},
```

After editing, run an upgrade or hard-refresh in dev mode.

---

## 11. Common Mistakes

### Mistake 1 — Forgetting `super()` in `_custom_options_initializer`

```python
# WRONG
def _custom_options_initializer(self, report, options, previous_options):
    options['group_by_currency'] = False   # base options never built!
```

Without `super()`, the standard columns, show_currency, aging_interval, etc. are never set, and the report breaks.

### Mistake 2 — Missing the handler guard in `_get_groupby`

```python
# WRONG
def _get_groupby(self, options):
    groupby = super()._get_groupby(options)
    if options.get('group_by_currency') and groupby:
        # inserts currency_id into EVERY report's groupby!
```

`_get_groupby` runs for every line of every report. Without the handler check, enabling the option would corrupt Aged Payable, the Balance Sheet, and any other report that has a line with a groupby.

### Mistake 3 — Putting `currency_id` after `id`

```python
# WRONG: currency_id after id
# partner_id, id, currency_id
```

The engine fills detail columns only when `current_groupby == 'id'`. If `currency_id` comes after `id`, the `id` rows (detail rows) would appear above the `currency_id` subtotals, meaning you would see all invoices first and then a meaningless currency row below them.

### Mistake 4 — Not spreading `super.filterExtraOptionsData` in JS

```javascript
// WRONG
get filterExtraOptionsData() {
    return {
        group_by_currency: { name: _t("Group by Currency") },
        // "Show Currency" and "Show Account" are now gone!
    };
}
```

Always spread `super.filterExtraOptionsData` first to preserve the existing options.

### Mistake 5 — Editing `.py` files without upgrading

Python changes require the module to be upgraded (`-u aged_receivable_currency`). The server must be restarted or upgraded for changes to take effect. Simply saving the file is not enough unless `--dev=all` is running.

### Mistake 6 — Using `models.AbstractModel` for `AccountReportLine`

`account.report.line` is a regular `models.Model` (has a DB table). Using `models.AbstractModel` for its subclass would cause an Odoo ORM error. Always match the base class type when using `_inherit`.

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| `AbstractModel` | An Odoo model with no database table; holds logic only |
| `_inherit` | Extends an existing Odoo model in-place (monkey-patch at the ORM level) |
| `options` dict | A Python dictionary built fresh on every report render; carries all filter/toggle state |
| `previous_options` | The options dict from the last render; used to restore toggle states across page navigations |
| `_custom_options_initializer` | Hook called by the report engine to let handlers add their own options |
| `_get_groupby` | Method on `account.report.line` that returns the SQL GROUP BY fields as a comma-separated string |
| `current_groupby` | The groupby field being processed right now (e.g. `"currency_id"`) |
| `next_groupby` | The remaining groupby fields for deeper levels (e.g. `"id"`) |
| `_field_to_sql` | ORM helper that converts a field name string into a safe SQL fragment |
| `build_result_dict` | Inner function in the engine that decides whether a row is a subtotal or a detail line |
| `period_table` CTE | A SQL Common Table Expression defining the aging date buckets |
| `patch` | Odoo's safe JS monkey-patching utility (`@web/core/utils/patch`) |
| `filterExtraOptionsData` | Getter on `AccountReportFilters` whose returned object drives the "Options" dropdown checkboxes |
| `cachedFilterOptions` | Frontend cache of the server's options dict; used to decide which checkboxes to show |
| `AgedPartnerBalanceFilters` | The OWL component that renders the filter panel for both Aged Receivable and Aged Payable |
| `--stop-after-init` | CLI flag that stops Odoo immediately after module loading; used for headless upgrades |
| `--dev=all` | CLI flag enabling dev mode: hot-reload, live assets, detailed errors |
| `_t(...)` | Odoo's JS translation function; always use for user-visible strings |
