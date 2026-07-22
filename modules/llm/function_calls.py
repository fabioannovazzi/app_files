def function_specs():
    specs = {
        "name": "map_journal_columns",
        "description": "Identify the journal layout and map each column to canonical keys.",
        "parameters": {
            "type": "object",
            "properties": {
                "layout": {
                    "type": "string",
                    "enum": [
                        "posting_signed",  # 1 account + signed Amount ±
                        "posting_amount_flag",  # 1 account + Amount + D/C flag
                        "posting_split_amt",  # 1 account + Debit & Credit
                        "entry_split_acc",  # 2 accounts + Debit & Credit
                        "entry_split_amt",  # 2 accounts + ONE Amount
                    ],
                },
                "fields": {
                    "type": "object",
                    "description": "For every key below give the source column name, or null.",
                    "properties": {
                        k: {"type": ["string", "null"]}
                        for k in [
                            "date",
                            "amount",
                            "account",
                            "account_desc",
                            "debit_account",
                            "debit_amount",
                            "credit_account",
                            "credit_amount",
                            "dc_flag",
                            "account_desc",
                            "line_desc",
                            "movement_number",
                            "beneficiary",
                        ]
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["layout", "fields"],
            "additionalProperties": False,
        },
    }
    return specs


def mapping_examples() -> str:
    examples = """\
        Example 1 (Italian – classic split)
        Columns: ["Data","Conto Dare","Importo Dare","Conto Avere","Importo Avere","Descrizione"]
        Row 0 : 02/01/24 | 4000 | 120,00 | 1000 | 120,00 | Pagamento bolletta
        → {"layout":"entry_split_acc",
           "fields":{"date":"Data",
                    "debit_account":"Conto Dare",
                    "debit_amount":"Importo Dare",
                    "credit_account":"Conto Avere",
                    "credit_amount":"Importo Avere",
                    "line_desc":"Descrizione"}}

        Example 2 (Italian – reversed split)
        Columns: ["Data","Conto Avere","Importo Avere","Conto Dare","Importo Dare","Descrizione"]
        Row 0 : 02/01/24 | 4000 | 120,00 | 1000 | 120,00 | Pagamento bolletta
        → {"layout":"entry_split_acc",
           "fields":{"date":"Data",
                    "debit_account":"Conto Avere",
                    "debit_amount":"Importo Avere",
                    "credit_account":"Conto Dare",
                    "credit_amount":"Importo Dare",
                    "line_desc":"Descrizione"}}

        Example 3 (Italian – libro giornale)
        Columns: ["Data reg.","Num. reg.","Codice conto","Descr. conto","Dare","Avere","Descr. agg."]
        Row 0 : 2024-12-03 | 6770 | 15 / 5 / 1013 | Example Bank spa |   | 70000.00 | ASSEGNO CIRCOLARE VERSATO AD ADE RISCOSSIONE
        → {"layout":"posting_split_amt",
           "fields":{"date":"Data reg.",
                    "account":"Codice conto",
                    "account_desc":"Descr. conto",
                    "debit_amount":"Dare",
                    "credit_amount":"Avere",
                    "line_desc":"Descr. agg.",
                    "movement_number":"Num. reg."}}

        Example 4 (French)
        Columns: ["Date","Compte","Débit","Crédit","Libellé"]
        Row 0 : 03/01/24 | 512000 | 0 | 350.75 | FRAIS BANCAIRES
        → {"layout":"posting_split_amt",
           "fields":{"date":"Date",
                     "account":"Compte",
                     "debit_amount":"Débit",
                     "credit_amount":"Crédit",
                     "line_desc":"Libellé"}}

        Example 5 (German)
        Columns: ["Buchungsdatum","Konto","Betrag","Soll/Haben"]
        Row 0 : 04.01.24 | 1200 | -99.90 | S
        → {"layout":"posting_amount_flag",
           "fields":{"date":"Buchungsdatum",
                     "account":"Konto",
                     "amount":"Betrag",
                     "dc_flag":"Soll/Haben"}}

        Example 6 (English with beneficiary)
        Columns: ["Date","Account","Amount","Beneficiary"]
        Row 0 : 2024-01-01 | 4000 | 100.00 | ACME Corp
        → {"layout":"posting_signed",
           "fields":{"date":"Date",
                     "account":"Account",
                     "amount":"Amount",
                     "beneficiary":"Beneficiary"}}

        Example 7 (Spanish – libro diario)
        Columns: ["Fecha","N.º asiento","Cuenta","Descripción cuenta","Debe","Haber","Concepto"]
        Row 0 : 05/01/24 | 1082 | 572000 | Banco | 250,00 | 0,00 | Cobro de cliente
        → {"layout":"posting_split_amt",
           "fields":{"date":"Fecha",
                     "movement_number":"N.º asiento",
                     "account":"Cuenta",
                     "account_desc":"Descripción cuenta",
                     "debit_amount":"Debe",
                     "credit_amount":"Haber",
                     "line_desc":"Concepto"}}
        """
    return examples
