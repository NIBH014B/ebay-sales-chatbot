"""Context-aware semantic column discovery for sales exports."""

from __future__ import annotations

import re

import pandas as pd


ALIASES = {
    "product_code": {"sku", "code", "customlabel", "productcode", "itemcode", "stockkeepingunit", "productsku", "itemsku", "variantcode"},
    "product_name": {"productname", "itemname", "itemtitle", "title", "name", "product", "item"},
    "date": {"date", "saledate", "orderdate", "createdat", "transactiondate", "transactioncreationdate", "purchasedate"},
    "quantity": {"quantity", "qty", "units", "unitssold", "quantitysold"},
    "selling_price": {"sellingprice", "saleprice", "salesprice", "unitprice", "sp", "priceperunit", "itemprice"},
    "buying_price": {"buyingprice", "purchaseprice", "costprice", "unitcost", "buyprice"},
    "revenue": {"revenue", "salesrevenue", "salestotal", "ordertotal", "lineamount", "amount", "itemsubtotal", "grosstransactionamount"},
    "order_id": {"orderid", "ordernumber", "transactionid", "invoiceid", "amazonorderid"},
    "customer": {"customer", "customername", "customerid", "buyer"},
}


def compact(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def detect_columns(frame: pd.DataFrame) -> dict[str, str]:
    names = {compact(alias) for aliases in ALIASES.values() for alias in aliases}
    context = " ".join(compact(column) for column in frame.columns)
    detected: dict[str, str] = {}
    for semantic, aliases in ALIASES.items():
        candidates = []
        for column in frame.columns:
            token = compact(column)
            if token in aliases:
                candidates.append((3, column))
            elif semantic == "selling_price" and token == "price" and any(word in context for word in ("sale", "sales", "order", "quantity")):
                candidates.append((1, column))
            elif semantic == "buying_price" and token in {"cost", "rate"} and any(word in context for word in ("purchase", "buy", "cost", "owner")):
                candidates.append((1, column))
            elif token in names and semantic in {"product_code", "product_name"}:
                continue
        if candidates:
            detected[semantic] = max(candidates, key=lambda pair: pair[0])[1]
    return detected


def classify_dataset(columns: dict[str, str]) -> list[str]:
    roles = []
    if columns.get("product_code") and columns.get("quantity") and (
        columns.get("selling_price") or columns.get("revenue") or columns.get("order_id")
    ):
        roles.append("sales")
    if columns.get("product_code") and columns.get("buying_price"):
        roles.append("buying_prices")
    if columns.get("product_code") and columns.get("product_name"):
        roles.append("products")
    return roles