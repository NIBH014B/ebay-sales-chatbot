"""Load repository datasets, build a logical catalog, and answer analytical queries."""

from __future__ import annotations

import io
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from services.calculation_service import add_metrics, numeric_series
from services.github_service import GitHubRepository, RepositoryError
from services.knowledge_service import KnowledgeService
from services.schema_service import classify_dataset, detect_columns

CACHE_SCHEMA_VERSION = 4


@dataclass
class Dataset:
    name: str
    frame: pd.DataFrame
    columns: dict[str, str]
    roles: list[str]


def normalize_code(value: object) -> str | None:
    if pd.isna(value):
        return None
    code = re.sub(r"\s+", "", str(value)).upper()
    if code in {"", "--", "N/A", "NA", "NONE", "NAN"}:
        return None
    embedded_codes = re.findall(r"\d{8,}", code)
    if len(embedded_codes) == 1:
        return embedded_codes[0].lstrip("0") or "0"
    if re.fullmatch(r"\d+(?:\.0+)?", code):
        return code.split(".", 1)[0].lstrip("0") or "0"
    return code or None


def _parse_dataset(name: str, content: bytes) -> pd.DataFrame:
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(io.BytesIO(content), dtype=object, encoding="utf-8-sig")
        except UnicodeDecodeError:
            return pd.read_csv(io.BytesIO(content), dtype=object, encoding="cp1252")
    if suffix in {".xlsx", ".xls"}:
        preview = pd.read_excel(io.BytesIO(content), header=None, dtype=object, nrows=40)
        header_row = 0
        best_score = 0
        header_tokens = {"date", "order", "quantity", "amount", "price", "sku", "code", "product", "item", "label", "transaction", "revenue"}
        for index, row in preview.iterrows():
            values = [re.sub(r"[^a-z0-9]", "", str(value).lower()) for value in row.dropna()]
            score = sum(any(token in value for token in header_tokens) for value in values)
            if score > best_score:
                header_row, best_score = index, score
        return pd.read_excel(io.BytesIO(content), header=header_row, dtype=object)
    if suffix == ".json":
        value = json.loads(content.decode("utf-8-sig"))
        if isinstance(value, dict):
            value = value.get("data", value.get("records", value))
        return pd.DataFrame(value)
    raise ValueError("Unsupported file format")


def _json_value(value: object) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


class DataService:
    def __init__(self, repository: GitHubRepository | None = None, local_dir: str | Path = "local_data", additional_repositories: list[GitHubRepository] | None = None) -> None:
        self.repository = repository
        self.additional_repositories = additional_repositories or []
        self.local_dir = Path(local_dir)
        self.datasets: list[Dataset] = []
        self.errors: list[str] = []
        self.commit_sha: str | None = None
        self.refresh_status = "Not loaded"
        self.knowledge = KnowledgeService()

    def _snapshot_path(self) -> Path | None:
        repositories = ([self.repository] if self.repository else []) + self.additional_repositories
        if not repositories:
            return None
        return repositories[0].cache_dir / "data_service_snapshot.pkl"

    def _source_signature(self) -> list[dict[str, str]]:
        repositories = ([self.repository] if self.repository else []) + self.additional_repositories
        return [
            {"owner": repository.owner, "name": repository.name, "branch": repository.branch, "data_path": repository.data_path}
            for repository in repositories
        ]

    def _load_snapshot(self) -> bool:
        snapshot_path = self._snapshot_path()
        if not snapshot_path or not snapshot_path.is_file():
            return False
        refresh_hours = float(os.getenv("DATA_REFRESH_HOURS", "24"))
        if time.time() - snapshot_path.stat().st_mtime >= refresh_hours * 3600:
            return False
        try:
            snapshot = pd.read_pickle(snapshot_path)
            if snapshot.get("schema_version") != CACHE_SCHEMA_VERSION or snapshot.get("sources") != self._source_signature():
                return False
            self.datasets = [
                Dataset(name, frame, detect_columns(frame), classify_dataset(detect_columns(frame)))
                for name, frame in snapshot["frames"].items()
            ]
            for dataset in self.datasets:
                date_column = dataset.columns.get("date")
                if date_column:
                    dataset.frame[date_column] = pd.to_datetime(dataset.frame[date_column], errors="coerce", utc=True).dt.tz_localize(None)
            self.commit_sha = snapshot.get("commit_sha")
            self.refresh_status = f"Local data cache ({snapshot_path.stat().st_mtime})"
            self.errors = list(snapshot.get("errors", []))
            return True
        except (OSError, KeyError, TypeError, ValueError):
            return False

    def _save_snapshot(self) -> None:
        snapshot_path = self._snapshot_path()
        if not snapshot_path:
            return
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        pd.to_pickle(
            {
                "sources": self._source_signature(),
                "schema_version": CACHE_SCHEMA_VERSION,
                "commit_sha": self.commit_sha,
                "errors": self.errors,
                "frames": {dataset.name: dataset.frame for dataset in self.datasets},
            },
            snapshot_path,
        )

    def load(self) -> dict[str, object]:
        incoming: list[tuple[str, bytes]] = []
        self.errors = []
        repositories = ([self.repository] if self.repository else []) + self.additional_repositories
        if repositories:
            if self._load_snapshot():
                return self.catalog()
            discoveries = []
            for index, repository in enumerate(repositories):
                try:
                    discoveries.append((repository, *repository.discover()))
                except RepositoryError as exc:
                    if index == 0 and self.repository:
                        raise
                    self.errors.append(f"Optional purchase-price source unavailable: {exc}")
            self.commit_sha, files = discoveries[0][1], list(discoveries[0][2])
            self.refresh_status = f"GitHub commit {self.commit_sha[:12]}"
            for _, commit_sha, repository_files in discoveries[1:]:
                self.refresh_status += f"; purchase commit {commit_sha[:12]}"
                files.extend(repository_files)
            if not files:
                self.errors.append("No CSV, Excel, or JSON files were found in the configured repository.")
            for repository, commit_sha, repository_files in discoveries:
                for item in repository_files:
                    try:
                        incoming.append((item["path"], repository.read_file(commit_sha, item)))
                    except RepositoryError as exc:
                        self.errors.append(str(exc))
        elif self.local_dir.is_dir():
            incoming = [(path.name, path.read_bytes()) for path in sorted(self.local_dir.rglob("*")) if path.is_file() and path.suffix.lower() in {".csv", ".xlsx", ".xls", ".json"}]
            self.refresh_status = "Local files"
        else:
            self.refresh_status = "No data source configured"

        self.datasets = []
        for name, content in incoming:
            try:
                frame = _parse_dataset(name, content)
                if frame.empty or len(frame.columns) == 0:
                    self.errors.append(f"{name}: dataset is empty.")
                    continue
                columns = detect_columns(frame)
                self.datasets.append(Dataset(name, frame, columns, classify_dataset(columns)))
            except Exception as exc:
                self.errors.append(f"{name}: could not read this file ({type(exc).__name__}).")
        if repositories and self.datasets:
            self._save_snapshot()
        return self.catalog()

    def catalog(self) -> dict[str, object]:
        return {
            "repository_commit": self.commit_sha,
            "refresh_status": self.refresh_status,
            "datasets": [
                {"file": item.name, "rows": len(item.frame), "columns": [str(c) for c in item.frame.columns], "detected_fields": item.columns, "roles": item.roles}
                for item in self.datasets
            ],
            "warnings": list(self.errors),
        }

    @classmethod
    def from_frames(cls, frames: dict[str, pd.DataFrame]) -> "DataService":
        service = cls()
        service.datasets = [Dataset(name, frame.copy(), detect_columns(frame), classify_dataset(detect_columns(frame))) for name, frame in frames.items()]
        service.refresh_status = "Test data"
        return service

    def _find(self, role: str) -> Dataset | None:
        return next((dataset for dataset in self.datasets if role in dataset.roles), None)

    def _price_map(self, role: str, embedded: bool = False) -> dict[str, float]:
        source = self._find("sales") if embedded else self._find(role)
        if not source:
            return {}
        code_col = source.columns.get("product_code")
        price_col = source.columns.get("buying_price" if role == "buying_prices" else "selling_price")
        if not code_col or not price_col:
            return {}
        frame = pd.DataFrame({"code": source.frame[code_col].map(normalize_code), "price": numeric_series(source.frame[price_col])}).dropna()
        result = {}
        for code, values in frame.groupby("code")["price"]:
            unique = values.dropna().unique()
            if code and len(unique) == 1:
                result[code] = float(unique[0])
        return result

    def _sales_frame(self) -> tuple[pd.DataFrame, dict[str, object]]:
        sales_sources = [dataset for dataset in self.datasets if "sales" in dataset.roles]
        if not sales_sources:
            raise ValueError("No sales dataset with a product code, quantity, and sales field was identified.")
        source_frames = []
        for sales in sales_sources:
            fields = sales.columns
            code_col, quantity_col = fields.get("product_code"), fields.get("quantity")
            source_frame = pd.DataFrame(index=sales.frame.index)
            source_frame["product_code"] = sales.frame[code_col].map(normalize_code) if code_col else None
            source_frame["quantity"] = numeric_series(sales.frame[quantity_col]) if quantity_col else pd.NA
            for semantic in ("selling_price", "buying_price", "revenue"):
                column = fields.get(semantic)
                source_frame[semantic] = numeric_series(sales.frame[column]) if column else pd.NA
            source_frame["product_name"] = sales.frame[fields["product_name"]].astype("string") if fields.get("product_name") else source_frame["product_code"]
            source_frame["date"] = pd.to_datetime(sales.frame[fields["date"]], errors="coerce", format="mixed", utc=True).dt.tz_localize(None) if fields.get("date") else pd.NaT
            source_frame["account"] = Path(sales.name).stem
            source_frames.append(source_frame)
        frame = pd.concat(source_frames, ignore_index=True)

        for role, semantic in (("buying_prices", "buying_price"), ("products", "selling_price")):
            mapping = self._price_map(role)
            if mapping:
                frame[semantic] = frame[semantic].fillna(frame["product_code"].map(mapping))
        buying_mapping = self._price_map("buying_prices", embedded=True)
        selling_mapping = self._price_map("sales", embedded=True)
        if buying_mapping:
            frame["buying_price"] = frame["buying_price"].fillna(frame["product_code"].map(buying_mapping))
        if selling_mapping:
            frame["selling_price"] = frame["selling_price"].fillna(frame["product_code"].map(selling_mapping))

        products = self._find("products")
        if products and products.columns.get("product_name"):
            product_frame = products.frame.copy()
            product_frame["_code"] = product_frame[products.columns["product_code"]].map(normalize_code)
            product_frame["_name"] = product_frame[products.columns["product_name"]].astype("string")
            name_map = product_frame.dropna(subset=["_code"]).drop_duplicates("_code", keep=False).set_index("_code")["_name"].to_dict()
            frame["product_name"] = frame["product_code"].map(name_map).fillna(frame["product_name"])
        for entry in self.knowledge.all_entries():
            code = entry.get("product_code")
            name = entry.get("product_name")
            if code and name:
                frame.loc[frame["product_code"] == code, "product_name"] = name

        frame = add_metrics(frame)
        total_records = len(frame)
        matched_buying = int(frame["buying_price"].notna().sum())
        summary = {
            "sales_file": ", ".join(dataset.name for dataset in sales_sources),
            "records": total_records,
            "buying_price_matched_records": matched_buying,
            "buying_price_unmatched_records": total_records - matched_buying,
            "buying_price_match_percent": round(100 * matched_buying / total_records, 2) if total_records else 0,
            "sources": [dataset.name for dataset in self.datasets if "sales" in dataset.roles or "buying_prices" in dataset.roles or "products" in dataset.roles],
            "accounts": sorted(frame["account"].dropna().unique().tolist()),
        }
        return frame, summary

    def remember_product_code(self, product_code: str, product_name: str) -> dict[str, object]:
        result = self.knowledge.remember_product_code(product_code, product_name)
        if result.get("saved"):
            self.errors = [error for error in self.errors if not error.startswith("Knowledge")]
        return result

    def product(self, product_code: str) -> dict[str, object]:
        frame, summary = self._sales_frame()
        code = normalize_code(product_code)
        records = frame.loc[frame["product_code"] == code]
        if records.empty:
            product_source = self._find("products")
            if product_source and product_source.columns.get("product_code"):
                product_source.frame["_code"] = product_source.frame[product_source.columns["product_code"]].map(normalize_code)
                records = product_source.frame.loc[product_source.frame["_code"] == code]
        if records.empty:
            return {"found": False, "product_code": code, "message": "No matching product or sales record was found."}
        values = records.iloc[0].to_dict()
        return {"found": True, "product_code": code, "product_name": _json_value(values.get("product_name")), "buying_price": _json_value(values.get("buying_price")), "selling_price": _json_value(values.get("selling_price")), "units_sold": _json_value(records["quantity"].sum(min_count=1)), "revenue": _json_value(records["revenue"].sum(min_count=1)), "cost": _json_value(records["cost"].sum(min_count=1)), "gross_profit": _json_value(records["profit"].sum(min_count=1)), "gross_margin_percent": _json_value((records["profit"].sum(min_count=1) / records["revenue"].sum()) * 100) if records["profit"].notna().any() and records["revenue"].sum() else None, "data_quality": summary}

    def inventory(self, limit: int = 100, product_codes: list[str] | None = None) -> dict[str, object]:
        """Compare purchase quantities with all detected sales quantities."""
        purchase_source = self._find("buying_prices")
        if not purchase_source:
            return {"rows": [], "error": "No purchase-price dataset with product codes and quantities was identified."}
        purchase_code = purchase_source.columns.get("product_code")
        purchase_quantity = purchase_source.columns.get("quantity")
        if not purchase_code or not purchase_quantity:
            return {"rows": [], "error": "The purchase sheet has no usable product-code and quantity fields."}
        purchases = pd.DataFrame({
            "product_code": purchase_source.frame[purchase_code].map(normalize_code),
            "purchased_quantity": numeric_series(purchase_source.frame[purchase_quantity]),
            "product_name": purchase_source.frame[purchase_source.columns["product_name"]].astype("string") if purchase_source.columns.get("product_name") else pd.NA,
        }).dropna(subset=["product_code", "purchased_quantity"])
        purchases = purchases.groupby("product_code", as_index=False).agg(
            purchased_quantity=("purchased_quantity", "sum"),
            product_name=("product_name", "first"),
        )
        sales_frame, quality = self._sales_frame()
        sales = sales_frame.dropna(subset=["product_code", "quantity"]).groupby("product_code", as_index=False).agg(sold_quantity=("quantity", "sum"))
        result = purchases.merge(sales, on="product_code", how="left")
        matched_product_codes = int(result["sold_quantity"].notna().sum())
        result["purchased_quantity"] = result["purchased_quantity"].fillna(0)
        result["sold_quantity"] = result["sold_quantity"].fillna(0)
        result["remaining_quantity"] = result["purchased_quantity"] - result["sold_quantity"]
        result["status"] = result["remaining_quantity"].map(lambda value: "out_of_stock" if value <= 0 else "in_stock")
        if product_codes:
            wanted = {normalize_code(code) for code in product_codes}
            result = result.loc[result["product_code"].isin(wanted)]
        result = result.sort_values("remaining_quantity", ascending=True).head(max(1, min(int(limit), 500)))
        rows = [{str(key): _json_value(value) for key, value in row.items()} for row in result.to_dict(orient="records")]
        return {
            "rows": rows,
            "data_quality": {
                "purchase_records": len(purchases),
                "sales_records": quality["records"],
                "matched_product_codes": matched_product_codes,
                "sources": quality["sources"],
            },
        }

    def analyze(self, start_date: str | None = None, end_date: str | None = None, group_by: str = "product", metric: str = "revenue", limit: int = 10, product_codes: list[str] | None = None, accounts: list[str] | None = None) -> dict[str, object]:
        allowed_metrics = {"revenue", "units", "cost", "gross_profit", "margin"}
        if metric not in allowed_metrics:
            raise ValueError(f"Metric must be one of: {', '.join(sorted(allowed_metrics))}.")
        frame, summary = self._sales_frame()
        if start_date:
            start = pd.to_datetime(start_date, errors="coerce")
            if pd.isna(start):
                raise ValueError("start_date must be a valid date in YYYY-MM-DD format.")
            frame = frame.loc[frame["date"] >= start]
        if end_date:
            end = pd.to_datetime(end_date, errors="coerce")
            if pd.isna(end):
                raise ValueError("end_date must be a valid date in YYYY-MM-DD format.")
            frame = frame.loc[frame["date"] < end + pd.Timedelta(days=1)]
        if product_codes:
            wanted = {normalize_code(code) for code in product_codes}
            frame = frame.loc[frame["product_code"].isin(wanted)]
        if accounts:
            wanted_accounts = {str(account).casefold() for account in accounts}
            frame = frame.loc[frame["account"].str.casefold().isin(wanted_accounts)]

        metrics = {"revenue": "revenue", "units": "quantity", "cost": "cost", "gross_profit": "profit", "margin": "margin_percent"}
        column = metrics[metric]
        group_column = "product_code" if group_by == "product" else "date" if group_by == "date" else "account" if group_by == "account" else None
        if group_by not in {"product", "date", "account", "total"}:
            raise ValueError("group_by must be product, date, account, or total.")
        if group_column and not frame.empty:
            groups = frame.groupby(group_column, dropna=False).agg(
                product_name=("product_name", "first"),
                units=("quantity", "sum"), revenue=("revenue", "sum"), cost=("cost", "sum"),
                gross_profit=("profit", "sum"),
            ).reset_index()
            groups["margin_percent"] = groups["gross_profit"].div(groups["revenue"].where(groups["revenue"] != 0)).mul(100)
            grouped_metric = {"revenue": "revenue", "units": "units", "cost": "cost", "gross_profit": "gross_profit", "margin": "margin_percent"}[metric]
            groups = groups.sort_values(grouped_metric, ascending=False, na_position="last").head(max(1, min(int(limit), 100)))
            result_rows = [{str(key): _json_value(value) for key, value in row.items()} for row in groups.to_dict(orient="records")]
        else:
            result_rows = []
        totals = {metric_name: _json_value(frame[col].sum(min_count=1)) for metric_name, col in metrics.items() if metric_name != "margin"}
        valid_profit = frame["profit"].notna()
        totals["margin"] = _json_value(frame.loc[valid_profit, "profit"].sum() / frame.loc[valid_profit, "revenue"].sum() * 100) if valid_profit.any() and frame.loc[valid_profit, "revenue"].sum() else None
        quality = dict(summary)
        quality["records_analyzed"] = len(frame)
        quality["records_missing_buying_price"] = int(frame["buying_price"].isna().sum())
        if metric in {"cost", "gross_profit", "margin"} and quality["records_missing_buying_price"]:
            quality["warning"] = "Some records have no validated buying price; cost and profit totals exclude those records."
        return {"metric": metric, "group_by": group_by, "period": {"start": start_date, "end": end_date}, "totals": totals, "rows": result_rows, "data_quality": quality}