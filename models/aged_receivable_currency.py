from odoo import models


class AgedReceivableCurrencyHandler(models.AbstractModel):
    """Extend the Aged Receivable report handler to register a
    ``group_by_currency`` option.

    WHY _inherit on the AbstractModel? Report handlers in Odoo 19 are
    AbstractModels (no DB table). We extend the existing handler so our
    ``_custom_options_initializer`` runs on top of the original one.
    """
    _inherit = 'account.aged.receivable.report.handler'

    def _custom_options_initializer(self, report, options, previous_options):
        # Always call super() first so the base options are built.
        super()._custom_options_initializer(report, options, previous_options)

        # Register the option so:
        #  - the backend (account.report.line._get_groupby) can read it, and
        #  - the frontend filters component shows the checkbox. The base
        #    filters component only displays an extra option whose key is
        #    present in the options dict, so this line is what makes the
        #    "Group by Currency" toggle appear on this report only.
        options['group_by_currency'] = (previous_options or {}).get(
            'group_by_currency', False
        )


class AccountReportLine(models.Model):
    """Inject ``currency_id`` into the Aged Receivable line's groupby.

    WHY here? The Aged Receivable report is built by the custom SQL engine
    ``_report_custom_engine_aged_receivable``. That engine already groups by
    whatever ``current_groupby``/``next_groupby`` it receives (it turns each
    groupby key into SQL via ``_field_to_sql``). The groupby chain comes from
    ``account.report.line._get_groupby`` -- for the receivable line it is
    ``partner_id, id``. So to "group by currency" we only need to insert
    ``currency_id`` into that chain; no SQL override is required.
    """
    _inherit = 'account.report.line'

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
                # Insert currency grouping just above the final 'id' detail
                # level: partner_id, id -> partner_id, currency_id, id.
                # Each partner therefore expands into one subgroup per
                # currency before showing the individual journal items.
                insert_at = max(len(groupby_fields) - 1, 0)
                groupby_fields.insert(insert_at, 'currency_id')
            return ','.join(groupby_fields)

        return groupby
