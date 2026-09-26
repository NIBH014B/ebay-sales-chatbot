"""Optional TypeSafe Jev intent routing for sales questions."""

from __future__ import annotations

import re

INTENTS = {
    "product_lookup": "A product or code price/details lookup",
    "sales_analysis": "A sales, revenue, units, cost, profit, or margin calculation",
    "trend_analysis": "A date-based trend, period comparison, or time analysis",
    "product_search": "Finding products by name, SKU, or code",
    "schema_discovery": "Asking about available files, fields, or data sources",
    "clarification": "Ambiguous, non-analytical, or unrelated request",
}


class JevIntentService:
    def __init__(self) -> None:
        try:
            from typesafe_sdk import Choice, TypeSafeClient
        except ImportError as exc:
            raise RuntimeError("TypeSafe Jev is not installed. Install typesafe-sdk to enable intent routing.") from exc
        self._choice = Choice
        self._client = TypeSafeClient()

    def classify(self, question: str) -> dict[str, object]:
        response = self._client.system_one(
            state=question,
            questions={
                "intent": self._choice(
                    instructions="What is the primary intent of this sales-data question?",
                    criteria=INTENTS,
                )
            },
        )
        answer = response.answers["intent"]
        return {
            "intent": answer.choice,
            "confidence": float(answer.confidence),
        }


class DisabledJevIntentService:
    def classify(self, question: str) -> dict[str, object]:
        return {"intent": "unknown", "confidence": 0.0}


def fallback_intent(question: str) -> dict[str, object]:
    """Classify common sales intents locally when Jev is unavailable."""
    text = question.casefold()
    if re.search(r"\b(sku|product code|item code|buying price|selling price)\b", text):
        intent = "product_lookup"
    elif re.search(r"\b(trend|compare|compared|last month|this month|over time|august|july)\b", text):
        intent = "trend_analysis"
    elif re.search(r"\b(find|search|show).*(product|sku|code)\b", text):
        intent = "product_search"
    elif re.search(r"\b(sales|revenue|units|quantity|cost|profit|margin|made)\b", text):
        intent = "sales_analysis"
    elif re.search(r"\b(field|schema|column|file|dataset|data source)\b", text):
        intent = "schema_discovery"
    else:
        intent = "clarification"
    return {"intent": intent, "confidence": 0.65, "source": "local_fallback"}
