/** @odoo-module **/

/**
 * WHAT: Add a "Group by Currency" toggle to the Aged Receivable filters.
 *
 * WHY this approach? The Aged Receivable report renders its filters with the
 * `AgedPartnerBalanceFilters` component (declared in the handler's
 * custom_display_config). That component inherits `AccountReportFilters`,
 * whose `filterExtraOptionsData` getter drives the checkboxes shown in the
 * report's "Options" dropdown (e.g. "Show Currency", "Show Account").
 *
 * The base component only shows an extra option whose key already exists in
 * the report options dict. Our Python `_custom_options_initializer` adds
 * `group_by_currency` to the options of the Aged *Receivable* report only, so
 * patching the getter here makes the checkbox appear on that report and not on
 * Aged Payable. Toggling it updates the option and reloads the report for us.
 */

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { AgedPartnerBalanceFilters } from "@account_reports/components/aged_partner_balance/filters";

patch(AgedPartnerBalanceFilters.prototype, {
    get filterExtraOptionsData() {
        return {
            ...super.filterExtraOptionsData,
            group_by_currency: {
                name: _t("Group by Currency"),
            },
        };
    },
});
