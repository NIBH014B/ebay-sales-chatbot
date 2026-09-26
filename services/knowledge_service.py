"""Persistent user-provided sales knowledge, separate from model training."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path



def normalize_code(value: object) -> str | None:
    code = re.sub(r"\s+", "", str(value)).upper()
    if not code or code in {"--", "N/A", "NA", "NONE", "NAN"}:
        return None
    embedded = re.findall(r"\d{8,}", code)
    if len(embedded) == 1:
        return embedded[0].lstrip("0") or "0"
    if re.fullmatch(r"\d+(?:\.0+)?", code):
        return code.split(".", 1)[0].lstrip("0") or "0"
    return code


class KnowledgeService:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.getenv("KNOWLEDGE_STORE_PATH", ".cache/knowledge.json"))

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.is_file():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def remember_product_code(self, product_code: str, product_name: str, source: str = "user") -> dict[str, object]:
        code = normalize_code(product_code)
        name = " ".join(str(product_name).split()).strip()
        if not code or not name:
            return {"saved": False, "error": "Both a product code and product name are required."}
        memory = self._read()
        previous = memory.get(code)
        memory[code] = {
            "product_code": code,
            "product_name": name,
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix="knowledge-", suffix=".json", dir=self.path.parent)
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(memory, handle, indent=2, ensure_ascii=True)
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return {"saved": True, "entry": memory[code], "replaced": previous is not None}

    def product_name(self, product_code: str) -> str | None:
        code = normalize_code(product_code)
        entry = self._read().get(code or "")
        return str(entry["product_name"]) if entry and entry.get("product_name") else None

    def all_entries(self) -> list[dict[str, object]]:
        return list(self._read().values())
