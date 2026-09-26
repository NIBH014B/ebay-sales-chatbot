"""Deterministic currency and sales metric calculations."""

from __future__ import annotations

import re

import pandas as pd


def numeric_series(values: pd.Series) -> pd.Series:
    def parse(value: object) -> object:
        if pd.isna(value):
            return pd.NA
        if isinstance(value, (int, float)):
            return value
        text = str(value).strip()
        if not text:
            return pd.NA
        negative = text.startswith("(") and text.endswith(")")
        cleaned = re.sub(r"[^0-9.\-]", "", text)
        try:
            result = float(cleaned)
            return -abs(result) if negative else result
        except ValueError:
            return pd.NA

    return pd.to_numeric(values.map(parse), errors="coerce")


def add_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    calculated_revenue = result["selling_price"] * result["quantity"]
    if "revenue" not in result:
        result["revenue"] = calculated_revenue
    else:
        result["revenue"] = result["revenue"].fillna(calculated_revenue)
    result["cost"] = result["buying_price"] * result["quantity"]
    result["profit"] = result["revenue"] - result["cost"]
    result.loc[result["buying_price"].isna() | result["selling_price"].isna(), "profit"] = pd.NA
    result["profit_per_unit"] = result["selling_price"] - result["buying_price"]
    result.loc[result["buying_price"].isna() | result["selling_price"].isna(), "profit_per_unit"] = pd.NA
    result["margin_percent"] = (result["profit"] / result["revenue"].where(result["revenue"] != 0)) * 100
    return result