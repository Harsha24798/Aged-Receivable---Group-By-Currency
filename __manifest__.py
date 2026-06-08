{
    'name': 'Aged Receivable - Group By Currency',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Add a "Group by Currency" filter to the Aged Receivable report',
    'author': 'Your Name',
    'depends': [
        'account_reports',
    ],
    'assets': {
        'web.assets_backend': [
            'aged_receivable_currency/static/src/**/*.js',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
}
