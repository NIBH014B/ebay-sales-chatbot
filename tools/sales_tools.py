"""Small ADK-callable wrappers around deterministic data services."""

from __future__ import annotations

import json

from services.data_service import DataService


def build_tools(data_service: DataService, include_extended: bool = False) -> list:
    def discover_repository() -> str:
        """Show discovered datasets, detected fields, and repository refresh status."""
        catalog = data_service.catalog()
        compact_catalog = {
            "refresh_status": catalog["refresh_status"],
            "datasets": [
                {key: item[key] for key in ("file", "rows", "detected_fields", "roles")}
                for item in catalog["datasets"]
            ],
            "warnings": catalog["warnings"],
        }
        return json.dumps(compact_catalog, separators=(",", ":"), default=str)

    def get_product_by_code(product_code: str) -> str:
        """Look up a product code and return verified prices and sales calculations."""
        return json.dumps(data_service.product(product_code), default=str)

    def inspect_dataset(dataset_name: str = "") -> str:
        """Inspect the logical schema of one dataset or the complete catalog."""
        catalog = data_service.catalog()
        if not dataset_name:
            return json.dumps(catalog, default=str)
        matches = [
            item for item in catalog["datasets"]
            if dataset_name.casefold() in str(item["file"]).casefold()
        ]
        return json.dumps({"datasets": matches}, default=str)

    def get_sales_data(
        start_date: str = "",
        end_date: str = "",
        product_codes: list[str] | None = None,
    ) -> str:
        """Return compact sales totals and rows for an optional filter."""
        return analyze_sales(
            metric="revenue",
            group_by="product",
            start_date=start_date,
            end_date=end_date,
            limit=100,
            product_codes=product_codes,
        )

    def get_buying_price(product_code: str) -> str:
        """Return the validated buying price for a product code."""
        product = data_service.product(product_code)
        return json.dumps(
            {
                "product_code": product.get("product_code"),
                "buying_price": product.get("buying_price"),
                "found": product.get("found", False),
                "data_quality": product.get("data_quality"),
            },
            default=str,
        )

    def get_product_data(product_code: str) -> str:
        """Return all verified data available for a product code."""
        return get_product_by_code(product_code)

    def calculate_revenue(product_code: str = "") -> str:
        """Calculate revenue deterministically for all sales or one product."""
        return analyze_sales(metric="revenue", group_by="total", product_codes=[product_code] if product_code else None)

    def calculate_profit(product_code: str = "") -> str:
        """Calculate gross profit only where buying and selling prices exist."""
        return analyze_sales(metric="gross_profit", group_by="total", product_codes=[product_code] if product_code else None)

    def calculate_margin(product_code: str = "") -> str:
        """Calculate gross margin only where buying and selling prices exist."""
        return analyze_sales(metric="margin", group_by="total", product_codes=[product_code] if product_code else None)

    def analyze_sales(
        metric: str = "revenue",
        group_by: str = "product",
        start_date: str = "",
        end_date: str = "",
        limit: int = 10,
        product_codes: list[str] | None = None,
        accounts: list[str] | None = None,
    ) -> str:
        """Calculate sales, units, cost, gross profit, or margin for an optional date range."""
        try:
            result = data_service.analyze(start_date or None, end_date or None, group_by, metric, limit, product_codes, accounts)
        except ValueError as exc:
            result = {"error": str(exc)}
        return json.dumps(result, default=str)

    def search_products(search_text: str, limit: int = 20) -> str:
        """Find matching products by product code or product name."""
        matches = []
        for dataset in data_service.datasets:
            if "products" not in dataset.roles and "sales" not in dataset.roles:
                continue
            frame = dataset.frame
            code_column = dataset.columns.get("product_code")
            name_column = dataset.columns.get("product_name")
            mask = frame[code_column].astype("string").str.contains(search_text, case=False, na=False, regex=False) if code_column else False
            if name_column:
                mask = mask | frame[name_column].astype("string").str.contains(search_text, case=False, na=False, regex=False)
            for _, row in frame.loc[mask].head(max(1, min(limit, 100))).iterrows():
                matches.append({
                    "product_code": row.get(code_column) if code_column else None,
                    "product_name": row.get(name_column) if name_column else None,
                })
        return json.dumps({"matches": matches[:limit]}, separators=(",", ":"), default=str)

    def analyze_inventory(limit: int = 100, product_codes: list[str] | None = None) -> str:
        """Compare purchase quantities with total sold quantities by product code."""
        return json.dumps(data_service.inventory(limit, product_codes), separators=(",", ":"), default=str)

    def remember_product_code(product_code: str, product_name: str) -> str:
        """Persist an explicit user-provided product-code to product-name mapping."""
        return json.dumps(data_service.remember_product_code(product_code, product_name), separators=(",", ":"), default=str)

    core_tools = [
        discover_repository,
        get_product_by_code,
        analyze_sales,
        search_products,
        analyze_inventory,
        remember_product_code,
    ]
    if not include_extended:
        return core_tools
    return core_tools + [
        inspect_dataset,
        get_sales_data,
        get_product_data,
        get_buying_price,
        calculate_revenue,
        calculate_profit,
        calculate_margin,
    ]