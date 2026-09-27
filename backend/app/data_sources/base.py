from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol


@dataclass
class PriceQuote:
    productCode: str
    priceDate: date
    price: Decimal
    dailyChangePct: Optional[Decimal]
    sourceType: str
    sourceName: str


class DataSourceAdapter(Protocol):
    source_type: str
    source_name: str

    def fetch_price(self, product_code: str) -> PriceQuote:
        """Fetch the latest valid price quote for a product code."""

    def fetch_recent_prices(self, product_code: str, limit: int = 7) -> list[PriceQuote]:
        """Fetch recent valid trading-day price quotes in ascending date order."""

    def fetch_price_history(
        self,
        product_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PriceQuote]:
        """Fetch valid trading-day price quotes for a date range in ascending date order."""
