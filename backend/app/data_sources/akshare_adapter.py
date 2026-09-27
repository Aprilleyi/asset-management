from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.data_sources.base import PriceQuote


class AkShareAdapter:
    source_type = "akshare"
    source_name = "AKShare"

    def fetch_price(self, product_code: str) -> PriceQuote:
        prices = self.fetch_recent_prices(product_code, limit=1)
        if not prices:
            raise RuntimeError(f"No AKShare price data for productCode={product_code}")
        return prices[-1]

    def fetch_recent_prices(self, product_code: str, limit: int = 7) -> list[PriceQuote]:
        quotes = self.fetch_price_history(product_code)
        if not quotes:
            raise RuntimeError(f"No AKShare price data for productCode={product_code}")
        return quotes[-limit:]

    def fetch_price_history(
        self,
        product_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PriceQuote]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed") from exc

        frame = ak.fund_open_fund_info_em(symbol=product_code, indicator="单位净值走势")
        if frame is None or frame.empty:
            raise RuntimeError(f"No AKShare price data for productCode={product_code}")

        quotes: list[PriceQuote] = []
        for _, row in frame.iterrows():
            price_date = _read_date(row, ["净值日期", "日期", "FSRQ"])
            if start_date and price_date < start_date:
                continue
            if end_date and price_date > end_date:
                continue
            price = _read_decimal(row, ["单位净值", "净值", "DWJZ"])
            daily_change = _read_optional_decimal(row, ["日增长率", "涨跌幅", "JZZZL"])
            quotes.append(
                PriceQuote(
                    productCode=product_code,
                    priceDate=price_date,
                    price=price,
                    dailyChangePct=daily_change,
                    sourceType=self.source_type,
                    sourceName=self.source_name,
                )
            )
        return sorted(quotes, key=lambda quote: quote.priceDate)

    def fetch_stock_price(self, product_code: str, market: Optional[str] = None) -> PriceQuote:
        prices = self.fetch_stock_price_history(product_code, market=market, limit=1)
        if not prices:
            raise RuntimeError(f"No AKShare stock price data for productCode={product_code}")
        return prices[-1]

    def fetch_stock_price_history(
        self,
        product_code: str,
        market: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> list[PriceQuote]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed") from exc

        errors: list[str] = []
        for symbol in _stock_symbol_candidates(product_code, market):
            try:
                frame = _fetch_stock_frame(ak, symbol=symbol, market=market, start_date=start_date, end_date=end_date)
            except Exception as exc:  # pragma: no cover - upstream network/schema errors vary.
                errors.append(f"{symbol}: {exc}")
                continue
            if frame is None or frame.empty:
                errors.append(f"{symbol}: empty response")
                continue
            quotes = _stock_frame_to_quotes(frame, product_code=product_code, source_type=self.source_type, source_name=self.source_name)
            if limit:
                quotes = quotes[-limit:]
            if quotes:
                return quotes
        raise RuntimeError(f"No AKShare stock price data for productCode={product_code}; {'; '.join(errors)}")

    def fetch_index_history(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PriceQuote]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("AKShare is not installed") from exc

        frame = ak.index_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=_format_ak_date(start_date),
            end_date=_format_ak_date(end_date),
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"No AKShare index data for symbol={symbol}")

        quotes: list[PriceQuote] = []
        for _, row in frame.iterrows():
            price_date = _read_date(row, ["日期", "date", "trade_date"])
            price = _read_decimal(row, ["收盘", "close", "收盘价"])
            daily_change = _read_optional_decimal(row, ["涨跌幅", "pct_chg", "涨跌幅(%)"])
            quotes.append(
                PriceQuote(
                    productCode=symbol,
                    priceDate=price_date,
                    price=price,
                    dailyChangePct=daily_change,
                    sourceType=self.source_type,
                    sourceName=self.source_name,
                )
            )
        return sorted(quotes, key=lambda quote: quote.priceDate)


def _read_date(row: Any, keys: list[str]) -> date:
    for key in keys:
        if key in row and row[key] is not None:
            return date.fromisoformat(str(row[key])[:10])
    raise RuntimeError(f"AKShare response missing date column; columns={list(row.index)}")


def _read_decimal(row: Any, keys: list[str]) -> Decimal:
    for key in keys:
        if key in row and row[key] is not None:
            value = str(row[key]).replace("%", "").strip()
            if value and value != "nan":
                return Decimal(value)
    raise RuntimeError(f"AKShare response missing price column; columns={list(row.index)}")


def _read_optional_decimal(row: Any, keys: list[str]) -> Optional[Decimal]:
    for key in keys:
        if key in row and row[key] is not None:
            value = str(row[key]).replace("%", "").strip()
            if value and value != "nan":
                return Decimal(value)
    return None


def _format_ak_date(value: Optional[date]) -> str:
    return value.strftime("%Y%m%d") if value else ""


def _fetch_stock_frame(ak: Any, symbol: str, market: Optional[str], start_date: Optional[date], end_date: Optional[date]) -> Any:
    normalized_market = (market or "").upper()
    start = _format_ak_date(start_date) or "19700101"
    end = _format_ak_date(end_date) or "22220101"
    if normalized_market in {"HK", "CN_HK"} or _looks_like_hk_stock(symbol):
        return ak.stock_hk_hist(symbol=_normalize_hk_symbol(symbol), period="daily", start_date=start, end_date=end, adjust="")
    if normalized_market == "US" or _looks_like_us_stock(symbol):
        return ak.stock_us_hist(symbol=symbol.upper(), period="daily", start_date=start, end_date=end, adjust="")
    return ak.stock_zh_a_hist(symbol=_normalize_a_stock_symbol(symbol), period="daily", start_date=start, end_date=end, adjust="")


def _stock_frame_to_quotes(frame: Any, product_code: str, source_type: str, source_name: str) -> list[PriceQuote]:
    quotes: list[PriceQuote] = []
    for _, row in frame.iterrows():
        price_date = _read_date(row, ["日期", "date", "trade_date"])
        price = _read_decimal(row, ["收盘", "close", "收盘价"])
        daily_change = _read_optional_decimal(row, ["涨跌幅", "pct_chg", "涨跌幅(%)"])
        quotes.append(
            PriceQuote(
                productCode=product_code,
                priceDate=price_date,
                price=price,
                dailyChangePct=daily_change,
                sourceType=source_type,
                sourceName=source_name,
            )
        )
    return sorted(quotes, key=lambda quote: quote.priceDate)


def _stock_symbol_candidates(product_code: str, market: Optional[str]) -> list[str]:
    raw = product_code.strip().upper()
    compact = raw.removeprefix("SH").removeprefix("SZ").removeprefix("HK")
    for suffix in [".SH", ".SZ", ".SS", ".HK"]:
        if compact.endswith(suffix):
            compact = compact[: -len(suffix)]
    candidates = [compact]
    normalized_market = (market or "").upper()
    if normalized_market in {"HK", "CN_HK"} and compact.isdigit():
        candidates.append(compact.zfill(5))
    if normalized_market == "US" and "." not in compact:
        candidates.append(f"105.{compact}")
    seen: set[str] = set()
    return [item for item in candidates if item and not (item in seen or seen.add(item))]


def _normalize_a_stock_symbol(symbol: str) -> str:
    compact = symbol.strip().upper()
    for prefix in ["SH", "SZ"]:
        compact = compact.removeprefix(prefix)
    for suffix in [".SH", ".SZ", ".SS"]:
        if compact.endswith(suffix):
            compact = compact[: -len(suffix)]
    return compact


def _normalize_hk_symbol(symbol: str) -> str:
    compact = symbol.strip().upper().removeprefix("HK")
    if compact.endswith(".HK"):
        compact = compact[:-3]
    return compact.zfill(5) if compact.isdigit() else compact


def _looks_like_hk_stock(symbol: str) -> bool:
    compact = symbol.strip().upper()
    return compact.startswith("HK") or compact.endswith(".HK")


def _looks_like_us_stock(symbol: str) -> bool:
    compact = symbol.strip().upper()
    return bool(compact) and not compact.replace(".", "").isdigit()
