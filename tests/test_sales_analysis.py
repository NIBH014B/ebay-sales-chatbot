import json
import unittest

import pandas as pd

from services.calculation_service import add_metrics, numeric_series
from services.data_service import DataService
from services.schema_service import detect_columns
from tools.sales_tools import build_tools


def sample_service() -> DataService:
    return DataService.from_frames(
        {
            "sales_august.csv": pd.DataFrame(
                {
                    "Sale Date": ["2026-08-01", "2026-08-05", "2026-07-09", "2026-08-12"],
                    "SKU": ["A-1", "B-2", "A-1", "C-3"],
                    "Product Name": ["Alpha", "Beta", "Alpha", "Gamma"],
                    "Sale Price": [750, 400, 750, 120],
                    "Quantity": [2, 3, 1, 1],
                }
            ),
            "buying_prices.csv": pd.DataFrame(
                {"SKU": ["A-1", "B-2"], "Purchase Price": [500, 300]}
            ),
            "products.csv": pd.DataFrame(
                {"Product Code": ["A-1", "B-2", "C-3"], "Product Name": ["Alpha", "Beta", "Gamma"]}
            ),
        }
    )


class SalesAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = sample_service()

    def test_schema_detects_common_column_names(self) -> None:
        columns = detect_columns(pd.DataFrame(columns=["Item Code", "Qty", "Cost Price", "Sale Price", "Order Date"]))
        self.assertEqual(columns["product_code"], "Item Code")
        self.assertEqual(columns["quantity"], "Qty")
        self.assertEqual(columns["buying_price"], "Cost Price")
        self.assertEqual(columns["selling_price"], "Sale Price")
        self.assertEqual(columns["date"], "Order Date")

    def test_currency_normalization_and_deterministic_metrics(self) -> None:
        prices = numeric_series(pd.Series(["₹1,250.50", "($25.00)", "bad", None]))
        self.assertEqual(prices.iloc[0], 1250.5)
        self.assertEqual(prices.iloc[1], -25.0)
        self.assertTrue(pd.isna(prices.iloc[2]))
        measured = add_metrics(pd.DataFrame({"selling_price": [750], "buying_price": [500], "quantity": [20]}))
        self.assertEqual(measured.loc[0, "revenue"], 15000)
        self.assertEqual(measured.loc[0, "cost"], 10000)
        self.assertEqual(measured.loc[0, "profit"], 5000)
        self.assertAlmostEqual(measured.loc[0, "margin_percent"], 100 / 3)

    def test_product_code_lookup_joins_buying_price(self) -> None:
        product = self.service.product("a-1")
        self.assertTrue(product["found"])
        self.assertEqual(product["buying_price"], 500)
        self.assertEqual(product["selling_price"], 750)
        self.assertEqual(product["units_sold"], 3)
        self.assertEqual(product["gross_profit"], 750)

    def test_date_filter_and_product_ranking_are_deterministic(self) -> None:
        result = self.service.analyze("2026-08-01", "2026-08-31", "product", "gross_profit", 10)
        self.assertEqual(result["data_quality"]["records_analyzed"], 3)
        self.assertEqual(result["rows"][0]["product_code"], "A-1")
        self.assertEqual(result["rows"][0]["gross_profit"], 500)
        self.assertEqual(result["data_quality"]["buying_price_unmatched_records"], 2)

    def test_margin_is_aggregated_from_profit_and_revenue(self) -> None:
        result = self.service.analyze("2026-08-01", "2026-08-31", "product", "margin", 10)
        alpha = next(row for row in result["rows"] if row["product_code"] == "A-1")
        self.assertAlmostEqual(alpha["margin_percent"], 100 / 3)

    def test_missing_buying_price_never_creates_profit(self) -> None:
        result = self.service.product("C-3")
        self.assertIsNone(result["buying_price"])
        self.assertIsNone(result["gross_profit"])
        self.assertEqual(result["data_quality"]["buying_price_unmatched_records"], 2)

    def test_adk_tools_return_compact_json_results(self) -> None:
        tools = build_tools(self.service)
        catalog = json.loads(tools[0]())
        analysis = json.loads(tools[2](metric="units", group_by="product", start_date="2026-08-01", end_date="2026-08-31", limit=2))
        self.assertEqual(len(catalog["datasets"]), 3)
        self.assertEqual(analysis["rows"][0]["product_code"], "A-1")


if __name__ == "__main__":
    unittest.main()