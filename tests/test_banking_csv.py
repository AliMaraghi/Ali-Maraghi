import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import banking_csv  # noqa: E402

SAMPLE_SINGLE_AMOUNT = (
    "Date,Description,Amount\n"
    "2026-11-01,TESCO STORES,-42.10\n"
    "2026-11-02,TFL TRAVEL,-5.20\n"
    "2026-11-03,SALARY,2500.00\n"
)

SAMPLE_DEBIT_CREDIT = (
    "Date,Description,Debit,Credit\n"
    "2026-11-01,SAINSBURYS,15.00,\n"
    "2026-11-05,EMPLOYER LTD,,1800.00\n"
)


class ParseTransactionsTests(unittest.TestCase):
    def test_single_amount_column_parses_signed_pence(self):
        rows = banking_csv.parse_transactions(SAMPLE_SINGLE_AMOUNT)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0], {"description": "TESCO STORES", "pence": -4210})
        self.assertEqual(rows[2]["pence"], 250000)

    def test_debit_credit_pair_always_signed_correctly(self):
        rows = banking_csv.parse_transactions(SAMPLE_DEBIT_CREDIT)
        self.assertEqual(rows[0], {"description": "SAINSBURYS", "pence": -1500})
        self.assertEqual(rows[1], {"description": "EMPLOYER LTD", "pence": 180000})

    def test_empty_csv_raises(self):
        with self.assertRaises(banking_csv.CsvParseError):
            banking_csv.parse_transactions("")

    def test_missing_description_column_raises(self):
        with self.assertRaises(banking_csv.CsvParseError):
            banking_csv.parse_transactions("Date,Amount\n2026-11-01,-5.00\n")

    def test_missing_amount_columns_raises(self):
        with self.assertRaises(banking_csv.CsvParseError):
            banking_csv.parse_transactions("Date,Description\n2026-11-01,TESCO\n")

    def test_too_large_raises(self):
        with self.assertRaises(banking_csv.CsvParseError):
            banking_csv.parse_transactions("x" * (banking_csv.MAX_CSV_CHARS + 1))

    def test_too_many_rows_raises(self):
        body = "Date,Description,Amount\n" + "\n".join(
            f"2026-01-01,ROW{i},-1.00" for i in range(banking_csv.MAX_ROWS + 1))
        with self.assertRaises(banking_csv.CsvParseError):
            banking_csv.parse_transactions(body)

    def test_parenthesized_amount_is_negative(self):
        rows = banking_csv.parse_transactions("Date,Description,Amount\n2026-11-01,FEE,(3.50)\n")
        self.assertEqual(rows[0]["pence"], -350)

    def test_semicolon_delimited_export_with_merchant_description_header(self):
        # Shape of a real UK bank "Midata" semicolon export: Date;Type;Merchant/Description;
        # Debit/Credit;Balance; (note the trailing empty column from the final ';').
        body = (
            "Date;Type;Merchant/Description;Debit/Credit;Balance;\n"
            "30/09/2026;CREDIT IN;Employer salary;+458.40;+992.32;\n"
            "16/09/2026;PAYMENTS;Rent payment;-2300.00;+533.92;\n"
        )
        rows = banking_csv.parse_transactions(body)
        self.assertEqual(rows, [
            {"description": "Employer salary", "pence": 45840},
            {"description": "Rent payment", "pence": -230000},
        ])

    def test_header_matching_ignores_punctuation_and_case(self):
        body = "date;MERCHANT_DESCRIPTION;amount\n2026-11-01;Tesco Stores;-10.00\n"
        rows = banking_csv.parse_transactions(body)
        self.assertEqual(rows[0]["description"], "Tesco Stores")
        self.assertEqual(rows[0]["pence"], -1000)


class CategorizeTests(unittest.TestCase):
    def test_real_math_llm_only_classifies(self):
        transactions = [
            {"description": "TESCO STORES", "pence": -4210},
            {"description": "TFL TRAVEL", "pence": -5200},
            {"description": "SALARY", "pence": 250000},
        ]

        def fake_call_anthropic(api_key, system, user_text, max_tokens=60):
            return "1: Groceries\n2: Transport\n3: Income\n"

        result = banking_csv.categorize(fake_call_anthropic, "fake-key", transactions)
        self.assertEqual(result["totals_pence"]["Groceries"], -4210)
        self.assertEqual(result["totals_pence"]["Transport"], -5200)
        self.assertEqual(result["totals_pence"]["Income"], 250000)
        self.assertEqual(result["uncategorized_count"], 0)

    def test_invalid_category_falls_back_to_other_never_crashes(self):
        transactions = [{"description": "MYSTERY CO", "pence": -100}]

        def fake_call_anthropic(api_key, system, user_text, max_tokens=60):
            return "1: NotARealCategory\n"

        result = banking_csv.categorize(fake_call_anthropic, "fake-key", transactions)
        self.assertEqual(result["totals_pence"]["Other"], -100)
        self.assertEqual(result["uncategorized_count"], 1)

    def test_malformed_reply_falls_back_gracefully(self):
        transactions = [{"description": "X", "pence": -500}]

        def fake_call_anthropic(api_key, system, user_text, max_tokens=60):
            return "not a mapping at all"

        result = banking_csv.categorize(fake_call_anthropic, "fake-key", transactions)
        self.assertEqual(result["totals_pence"]["Other"], -500)
        self.assertEqual(result["transaction_count"], 1)


if __name__ == "__main__":
    unittest.main()
