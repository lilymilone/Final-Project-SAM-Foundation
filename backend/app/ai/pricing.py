"""Token prices from pricing.json (official OpenAI list prices, with source + date).

A model that is not in the file has no price, and cost comes back as None.
Prices are never guessed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PRICING_FILE = Path(__file__).with_name("pricing.json")


@dataclass(frozen=True)
class PriceTable:
    source: str
    retrieved_on: str
    threshold: int
    models: dict[str, dict[str, dict[str, float]]]
    web_search_per_call: float = 0.0

    def has_price(self, model: str) -> bool:
        return model in self.models

    def cost_usd(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float | None:
        """Cost of one call. input_tokens includes cached and cache-write tokens."""
        entry = self.models.get(model)
        if entry is None:
            return None
        rates = entry["long" if input_tokens > self.threshold else "short"]
        cached = max(0, cached_input_tokens or 0)
        written = max(0, cache_write_tokens or 0)
        uncached = max(0, input_tokens - cached - written)
        total = (
            uncached * rates["input"]
            + cached * rates["cached_input"]
            + written * rates.get("cache_write_30m", rates["input"])
            + output_tokens * rates["output"]
        )
        return round(total / 1_000_000, 8)

    def public_summary(self) -> dict:
        return {
            "source": self.source,
            "retrieved_on": self.retrieved_on,
            "unit": "USD per 1M tokens (standard, short context)",
            "models": {m: v["short"] for m, v in self.models.items()},
            "web_search_per_call_usd": self.web_search_per_call,
        }


def load_price_table(path: Path = PRICING_FILE) -> PriceTable:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PriceTable(
        source=raw["source"],
        retrieved_on=raw["retrieved_on"],
        threshold=int(raw["long_context_threshold_input_tokens"]),
        models=raw["models"],
        web_search_per_call=float(raw.get("tools", {}).get("web_search", {}).get("per_call_usd", 0.0)),
    )


@lru_cache(maxsize=1)
def get_price_table() -> PriceTable:
    return load_price_table()
