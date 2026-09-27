import base64
import binascii
import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from app.data_sources.akshare_adapter import AkShareAdapter
from app.schemas.funds import BenchmarkHistory, BenchmarkPoint, FundBasicInfo, ScreenshotParseRequest, ScreenshotParseResult
from app.services.ocr import extract_text_from_image


logger = logging.getLogger(__name__)


def lookup_fund_basic_info(product_code: str) -> FundBasicInfo:
    code = product_code.strip()
    if not code:
        return FundBasicInfo(productCode=code, dataStatus="failed", errorMessage="productCode is required")

    name: Optional[str] = None
    market = "CN_FUND"
    errors: list[str] = []

    try:
        name = _lookup_fund_name(code)
    except Exception:  # pragma: no cover - AKShare schemas vary by upstream version.
        logger.warning("AKShare fund name lookup failed for product_code=%s", code, exc_info=True)
        errors.append("基金名称查询暂不可用")

    try:
        quote = AkShareAdapter().fetch_price(code)
        return FundBasicInfo(
            productCode=code,
            name=name,
            market=market,
            latestPrice=quote.price,
            priceDate=quote.priceDate,
            dailyChangePct=quote.dailyChangePct,
            sourceType=quote.sourceType,
            dataStatus="valid",
            errorMessage="；".join(errors) or None,
        )
    except Exception:
        logger.warning("AKShare fund price lookup failed for product_code=%s", code, exc_info=True)
        errors.append("净值查询暂不可用，请稍后重试，或先手动录入")
        return FundBasicInfo(
            productCode=code,
            name=name,
            market=market,
            sourceType="akshare",
            dataStatus="failed" if name is None else "partial",
            errorMessage="；".join(errors),
        )


STOCK_SUBTYPES = {"A股股票", "港股股票", "美股股票"}


def lookup_asset_basic_info(
    product_code: str,
    asset_type: Optional[str] = None,
    asset_sub_type: Optional[str] = None,
    market: Optional[str] = None,
) -> FundBasicInfo:
    normalized_type = (asset_type or "equity").strip() or "equity"
    code = product_code.strip()
    if not code:
        return FundBasicInfo(productCode=code, assetType=normalized_type, dataStatus="failed", errorMessage="productCode is required")

    if normalized_type == "equity":
        info = lookup_security_basic_info(code, asset_sub_type=asset_sub_type, market=market)
        info.assetType = "equity"
        info.subType = asset_sub_type or info.subType
        return info

    if normalized_type in {"cash", "fixed_income"} and _looks_like_cn_fund_code(code):
        info = lookup_fund_basic_info(code)
        info.assetType = normalized_type
        info.subType = asset_sub_type or _infer_public_fund_subtype(info.name, normalized_type)
        return info

    return FundBasicInfo(
        productCode=code,
        assetType=normalized_type,
        subType=asset_sub_type,
        market=market or "",
        sourceType="manual",
        dataStatus="partial",
        errorMessage="该资产类型的代码通常不是公开行情代码，已保留代码；名称、价格等信息请手动维护。",
    )


def lookup_security_basic_info(product_code: str, asset_sub_type: Optional[str] = None, market: Optional[str] = None) -> FundBasicInfo:
    code = product_code.strip()
    if not code:
        return FundBasicInfo(productCode=code, dataStatus="failed", errorMessage="productCode is required")
    if asset_sub_type not in STOCK_SUBTYPES and not _is_stock_market(market):
        return lookup_fund_basic_info(code)

    inferred_market = market or _market_from_stock_subtype(asset_sub_type)
    try:
        quote = AkShareAdapter().fetch_stock_price(code, market=inferred_market)
        return FundBasicInfo(
            productCode=code,
            market=inferred_market or "",
            latestPrice=quote.price,
            priceDate=quote.priceDate,
            dailyChangePct=quote.dailyChangePct,
            sourceType=quote.sourceType,
            dataStatus="valid",
        )
    except Exception:
        logger.warning("AKShare stock price lookup failed for product_code=%s market=%s", code, inferred_market, exc_info=True)
        return FundBasicInfo(
            productCode=code,
            market=inferred_market or "",
            sourceType="akshare",
            dataStatus="failed",
            errorMessage="股票价格查询暂不可用，请稍后重试，或先手动录入。",
        )


def _looks_like_cn_fund_code(product_code: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", product_code.strip()))


def _infer_public_fund_subtype(name: Optional[str], asset_type: str) -> Optional[str]:
    text = name or ""
    if asset_type == "cash":
        if any(keyword in text for keyword in ["货币", "现金", "添利", "余额"]):
            return "货币基金"
        return "现金管理"
    if "债" in text:
        return "债券基金"
    if any(keyword in text for keyword in ["存单", "同业存单"]):
        return "大额存单"
    if any(keyword in text for keyword in ["理财", "稳健", "收益"]):
        return "银行理财"
    return None


BENCHMARKS = {
    "hs300": ("000300", "沪深 300"),
    "zz500": ("000905", "中证 500"),
    "sse": ("000001", "上证指数"),
    "szse": ("399001", "深证成指"),
}


def _is_stock_market(market: Optional[str]) -> bool:
    return (market or "").upper() in {"CN_A_SH", "CN_A_SZ", "HK", "CN_HK", "US", "北交所"}


def _market_from_stock_subtype(asset_sub_type: Optional[str]) -> str:
    if asset_sub_type == "港股股票":
        return "HK"
    if asset_sub_type == "美股股票":
        return "US"
    return "CN_A_SH"


def get_benchmark_history(
    benchmark_code: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    adapter: Optional[AkShareAdapter] = None,
) -> BenchmarkHistory:
    if benchmark_code not in BENCHMARKS:
        return BenchmarkHistory(
            code=benchmark_code,
            name=benchmark_code,
            dataStatus="failed",
            errorMessage="benchmarkCode must be one of hs300, zz500, sse, szse",
        )
    symbol, name = BENCHMARKS[benchmark_code]
    selected_adapter = adapter or AkShareAdapter()
    final_end = end_date or date.today()
    final_start = start_date or (final_end - timedelta(days=366))
    try:
        quotes = selected_adapter.fetch_index_history(symbol, start_date=final_start, end_date=final_end)
        return BenchmarkHistory(
            code=benchmark_code,
            name=name,
            sourceType=selected_adapter.source_type,
            dataStatus="normal",
            items=[
                BenchmarkPoint(
                    priceDate=quote.priceDate,
                    close=quote.price,
                    dailyChangePct=quote.dailyChangePct,
                )
                for quote in quotes
            ],
        )
    except Exception:
        logger.warning("AKShare benchmark lookup failed for benchmark_code=%s symbol=%s", benchmark_code, symbol, exc_info=True)
        return BenchmarkHistory(
            code=benchmark_code,
            name=name,
            sourceType=selected_adapter.source_type,
            dataStatus="failed",
            errorMessage="基准数据暂不可用，请稍后重试。",
            items=[],
        )


def parse_asset_screenshot(payload: ScreenshotParseRequest) -> ScreenshotParseResult:
    image_bytes = _decode_image(payload.imageBase64)
    raw_text, ocr_message = _extract_text(image_bytes, payload.fileName)
    if not raw_text:
        return ScreenshotParseResult(
            status="needs_review",
            message=ocr_message,
            draft={},
        )

    draft: dict[str, Any] = {"assetType": "equity", "market": "CN_FUND"}
    asset_records = _parse_text_to_asset_records(raw_text, enrich_info=False)
    if asset_records:
        draft["assets"] = asset_records
        if len(asset_records) == 1:
            draft.update(asset_records[0])
        return ScreenshotParseResult(
            status="parsed",
            message=f"已从截图中识别到 {len(asset_records)} 条资产，请在清单中核对后再保存。",
            draft=draft,
            rawText=raw_text,
        )

    single_draft = _parse_text_to_draft(raw_text)
    if _has_meaningful_screenshot_draft(single_draft):
        draft.update(single_draft)
        return ScreenshotParseResult(
            status="parsed",
            message="已从截图中识别到 1 条资产，请核对后再保存。",
            draft=draft,
            rawText=raw_text,
        )

    if not _has_meaningful_screenshot_draft(draft):
        return ScreenshotParseResult(
            status="needs_review",
            message="已读取截图文字，但未识别到可安全预填的资产字段。请查看 OCR 原始文字，或换一张更清晰的持仓页截图。",
            draft=draft,
            rawText=raw_text,
        )


def _has_meaningful_screenshot_draft(draft: dict[str, Any]) -> bool:
    meaningful_fields = {
        "name",
        "productCode",
        "currentValue",
        "holdingShare",
        "holdingCostPrice",
        "holdingGain",
        "cumulativeGain",
        "latestPrice",
        "priceDate",
        "transactions",
        "assets",
    }
    return any(draft.get(field) not in (None, "", []) for field in meaningful_fields)


def _lookup_fund_name(product_code: str) -> Optional[str]:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed") from exc

    frame = ak.fund_name_em()
    if frame is None or frame.empty:
        return None
    code_columns = ["基金代码", "基金简称", "代码", "symbol"]
    name_columns = ["基金简称", "基金名称", "名称", "name"]
    code_col = _first_existing_column(frame, code_columns)
    name_col = _first_existing_column(frame, name_columns)
    if not code_col or not name_col:
        return None
    rows = frame[frame[code_col].astype(str).str.zfill(6) == product_code.zfill(6)]
    if rows.empty:
        return None
    value = rows.iloc[0][name_col]
    return None if value is None else str(value).strip()


def _lookup_fund_code_by_name(product_name: str) -> Optional[str]:
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AKShare is not installed") from exc

    normalized_name = _normalize_fund_name(product_name)
    if not normalized_name:
        return None

    frame = ak.fund_name_em()
    if frame is None or frame.empty:
        return None
    code_col = _first_existing_column(frame, ["基金代码", "代码", "symbol"])
    name_col = _first_existing_column(frame, ["基金简称", "基金名称", "名称", "name"])
    if not code_col or not name_col:
        return None

    best_code: Optional[str] = None
    best_score = 0
    for _, row in frame.iterrows():
        candidate_name = _normalize_fund_name(str(row[name_col]))
        if not candidate_name:
            continue
        if candidate_name == normalized_name:
            return str(row[code_col]).zfill(6)
        if normalized_name in candidate_name or candidate_name in normalized_name:
            score = min(len(candidate_name), len(normalized_name))
            if score > best_score:
                best_score = score
                best_code = str(row[code_col]).zfill(6)
    return best_code


def _decode_image(image_base64: str) -> bytes:
    try:
        return base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("imageBase64 must be a valid base64 encoded image") from exc


def _extract_text(image_bytes: bytes, file_name: str) -> tuple[Optional[str], str]:
    return extract_text_from_image(image_bytes, file_name)


def _parse_text_to_draft(raw_text: str) -> dict[str, Any]:
    draft: dict[str, Any] = {"assetType": "equity", "market": "CN_FUND"}
    code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", raw_text)
    if code_match:
        draft["productCode"] = code_match.group(1)
    product_name = _parse_product_name(raw_text, draft.get("productCode"))
    if product_name:
        draft["name"] = product_name

    amount_match = re.search(r"(?:当前金额|持有金额|持仓金额|参考市值|当前市值|市值|金额)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if amount_match:
        draft["currentValue"] = _clean_number(amount_match.group(1))

    share_match = re.search(r"(?:份额|持有份额)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if share_match:
        draft["holdingShare"] = _clean_number(share_match.group(1))

    holding_cost_price_match = re.search(
        r"(?:持仓成本价|持有成本价|成本价|成本净值|持仓成本净值|持有成本净值|平均成本|单位成本)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)",
        raw_text,
    )
    if holding_cost_price_match:
        draft["holdingCostPrice"] = _clean_number(holding_cost_price_match.group(1))

    daily_income_match = re.search(r"(?:昨日收益|日收益)[^\d+-]*([+-]?[0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if daily_income_match:
        draft["dailyIncomeAmount"] = _clean_number(daily_income_match.group(1))

    holding_gain_match = re.search(r"持有收益[^\d+-]*([+-]?[0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if holding_gain_match:
        draft["holdingGain"] = _clean_number(holding_gain_match.group(1))

    cumulative_gain_match = re.search(r"累计收益[^\d+-]*([+-]?[0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if cumulative_gain_match:
        draft["cumulativeGain"] = _clean_number(cumulative_gain_match.group(1))

    buy_amount_match = re.search(r"(?:买入金额|买入|申购金额|转入金额)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if buy_amount_match:
        draft["transactionType"] = "buy"
        draft["amount"] = _clean_number(buy_amount_match.group(1))

    sell_share_match = re.search(r"(?:卖出份额|赎回份额|卖出|赎回)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if sell_share_match:
        draft["transactionType"] = "sell"
        draft["share"] = _clean_number(sell_share_match.group(1))

    fee_match = re.search(r"(?:手续费|费用)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", raw_text)
    if fee_match:
        draft["feeAmount"] = _clean_number(fee_match.group(1))

    fee_rate_match = re.search(r"(?:费率)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)\s*%?", raw_text)
    if fee_rate_match:
        draft["feeRate"] = _clean_number(fee_rate_match.group(1))

    date_match = re.search(r"((?:20)?\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", raw_text)
    if date_match:
        year = date_match.group(1)
        if len(year) == 2:
            year = f"20{year}"
        draft["transactionDate"] = f"{year}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    if re.search(r"(?:三点后|15点后|15:00后|下午3点后)", raw_text):
        draft["tradeTiming"] = "after_15"
    elif re.search(r"(?:三点前|15点前|15:00前|下午3点前)", raw_text):
        draft["tradeTiming"] = "before_15"

    return {key: value for key, value in draft.items() if value not in (None, "")}


def _parse_text_to_asset_records(raw_text: str, enrich_info: bool = True) -> list[dict[str, Any]]:
    lines = _asset_ocr_lines(raw_text)
    candidates = [
        _records_from_asset_blocks(lines),
        _records_from_asset_columns(lines),
        _records_from_inline_codes(raw_text),
    ]
    best_records = max(candidates, key=_asset_records_score, default=[])

    records: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for draft in best_records:
        normalized = _normalize_asset_record(draft)
        if enrich_info and normalized.get("productCode"):
            try:
                info = lookup_fund_basic_info(str(normalized["productCode"]))
                normalized.update({**_fund_info_to_draft(info), **normalized})
            except Exception:
                pass
        _append_asset_record(records, seen_keys, normalized)
    return records


def _asset_ocr_lines(raw_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in raw_text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or _is_asset_ocr_noise_line(line):
            continue
        lines.append(line)
    return _merge_wrapped_asset_name_lines(lines)


def _is_asset_ocr_noise_line(line: str) -> bool:
    if line.startswith("/") or line.startswith("http"):
        return True
    if re.fullmatch(r"(?:min|general|default|wechat|jpg|png|jpeg)", line, re.IGNORECASE):
        return True
    if re.fullmatch(r"\d{1,2}:\d{2}", line):
        return True
    if re.search(r"(?:资产总额|总资产|持仓详情|资产截图|上传截图|使用说明|客服|通知|公告)", line):
        return True
    return False


def _records_from_asset_blocks(lines: list[str]) -> list[dict[str, Any]]:
    indexes = [index for index, line in enumerate(lines) if _is_asset_candidate_line(line, lines, index)]
    if not indexes:
        return []

    records: list[dict[str, Any]] = []
    for position, start in enumerate(indexes):
        end = indexes[position + 1] if position + 1 < len(indexes) else min(len(lines), start + 10)
        segment_lines = lines[start:end]
        draft = _record_from_asset_segment(segment_lines)
        if draft:
            records.append(draft)
    return records


def _records_from_asset_columns(lines: list[str]) -> list[dict[str, Any]]:
    first_field_index = next((index for index, line in enumerate(lines) if _is_any_asset_field_label_line(line)), None)
    if first_field_index is None or first_field_index == 0:
        return []

    name_lines = lines[:first_field_index]
    names = [_asset_name_from_line(line) for line in name_lines if _is_asset_candidate_line(line, name_lines, name_lines.index(line))]
    names = [name for name in names if name]
    if not names:
        return []

    records = [{"name": name} for name in names]
    codes = _asset_codes_from_lines(name_lines)
    for index, code in enumerate(codes[: len(records)]):
        records[index]["productCode"] = code

    for field, label_pattern in ASSET_FIELD_LABELS.items():
        values = _extract_asset_field_values("\n".join(lines), label_pattern, signed=field in {"holdingGain", "cumulativeGain"})
        if len(values) < len(records):
            continue
        for index, value in enumerate(values[: len(records)]):
            records[index][field] = value
    return records


def _records_from_inline_codes(raw_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for match in re.finditer(r"([^\n]{2,50}?)(?<!\d)(\d{6})(?!\d)([^\n]*)", raw_text):
        segment = match.group(0)
        draft = _parse_text_to_draft(segment)
        draft.setdefault("productCode", match.group(2))
        name = _parse_product_name(segment, draft.get("productCode")) or _clean_product_name_candidate(match.group(1))
        if name:
            draft["name"] = name
        if draft.get("name"):
            records.append(draft)
    return records


def _record_from_asset_segment(segment_lines: list[str]) -> dict[str, Any]:
    segment = "\n".join(segment_lines)
    code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", segment)
    product_code = code_match.group(1) if code_match else None
    name = _parse_product_name(segment, product_code) or _asset_name_from_line(segment_lines[0])
    if not name:
        return {}

    draft: dict[str, Any] = {"name": name}
    if product_code:
        draft["productCode"] = product_code
    for field, label_pattern in ASSET_FIELD_LABELS.items():
        value = _extract_first_asset_field(segment, label_pattern, signed=field in {"holdingGain", "cumulativeGain"})
        if value:
            draft[field] = value
    return draft


def _is_asset_candidate_line(line: str, lines: list[str], index: int) -> bool:
    if _is_asset_ocr_noise_line(line) or _is_any_asset_field_label_line(line):
        return False
    if _line_date(line) or _line_transaction_type(line):
        return False
    compact = re.sub(r"\s+", "", line)
    if re.fullmatch(r"[+-]?[0-9,]+(?:\.\d+)?%?", compact):
        return False
    if re.fullmatch(r"\d{6}", compact):
        return index > 0 and _looks_like_asset_name_line(lines[index - 1])
    if _looks_like_asset_name_line(line):
        return True
    if re.search(r"(?<!\d)\d{6}(?!\d)", line) and re.search(r"[\u4e00-\u9fa5]", line):
        return True
    return False


def _asset_name_from_line(line: str) -> Optional[str]:
    code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", line)
    return _clean_product_name_candidate(line.replace(code_match.group(1), " ") if code_match else line)


def _asset_codes_from_lines(lines: list[str]) -> list[str]:
    codes: list[str] = []
    for line in lines:
        for match in re.finditer(r"(?<!\d)(\d{6})(?!\d)", line):
            code = match.group(1)
            if code not in codes:
                codes.append(code)
    return codes


def _extract_first_asset_field(text: str, label_pattern: str, signed: bool = False) -> Optional[str]:
    match = re.search(label_pattern, text)
    if not match:
        return None
    value_text = _text_until_next_asset_field_label(text[match.end() :])
    values = _numeric_values_from_text(value_text, signed=signed)
    return values[0] if values else None


def _normalize_asset_record(draft: dict[str, Any]) -> dict[str, Any]:
    record = {key: value for key, value in draft.items() if value not in (None, "", [])}
    name = _clean_product_name_candidate(str(record.get("name", "")))
    if name:
        record["name"] = name
    else:
        record.pop("name", None)
    for field in ["currentValue", "holdingShare", "holdingCostPrice", "holdingGain", "cumulativeGain", "latestPrice"]:
        if field in record:
            record[field] = _clean_number(str(record[field]))
    record.setdefault("assetType", "equity")
    record.setdefault("market", "CN_FUND")
    record.setdefault("platform", "待确认平台")
    _derive_asset_record_cost_fields(record)
    return record


def _derive_asset_record_cost_fields(record: dict[str, Any]) -> None:
    current_value = _decimal_or_none(record.get("currentValue"))
    holding_gain = _decimal_or_none(record.get("holdingGain"))
    holding_share = _decimal_or_none(record.get("holdingShare"))
    holding_cost_price = _decimal_or_none(record.get("holdingCostPrice"))
    if current_value is not None and holding_gain is not None:
        cost_amount = current_value - holding_gain
        if cost_amount >= 0:
            record.setdefault("costAmount", _format_decimal(cost_amount, 2))
            if holding_share and holding_share > 0 and "holdingCostPrice" not in record:
                record["holdingCostPrice"] = _format_decimal(cost_amount / holding_share, 4)
    elif current_value is not None and holding_cost_price is not None and holding_share and holding_share > 0:
        record.setdefault("holdingGain", _format_decimal(current_value - holding_cost_price * holding_share, 2))


def _asset_records_score(records: list[dict[str, Any]]) -> int:
    score = len(records) * 10
    for record in records:
        score += sum(1 for field in ["name", "productCode", "currentValue", "holdingShare", "holdingGain", "holdingCostPrice"] if record.get(field))
    return score


def _decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except Exception:
        return None


def _format_decimal(value: Decimal, digits: int) -> str:
    quant = Decimal("1").scaleb(-digits)
    return str(value.quantize(quant))


def _asset_records_by_product_code(raw_text: str, enrich_info: bool = True) -> list[dict[str, Any]]:
    code_matches = list(re.finditer(r"(?<!\d)(\d{6})(?!\d)", raw_text))
    if len(code_matches) <= 1:
        return []

    records: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, match in enumerate(code_matches):
        code = match.group(1)
        if code in seen_codes:
            continue
        seen_codes.add(code)
        start = raw_text.rfind("\n", 0, match.start()) + 1
        end = code_matches[index + 1].start() if index + 1 < len(code_matches) else len(raw_text)
        segment = raw_text[start:end]
        draft = _parse_text_to_draft(segment)
        if "productCode" not in draft:
            draft["productCode"] = code
        if enrich_info:
            try:
                info = lookup_fund_basic_info(str(draft["productCode"]))
                draft.update({**_fund_info_to_draft(info), **draft})
            except Exception:
                pass
        draft.setdefault("assetType", "equity")
        draft.setdefault("market", "CN_FUND")
        records.append({key: value for key, value in draft.items() if value not in (None, "", [])})
    return records


def _asset_records_by_name_lines(raw_text: str, enrich_info: bool = True) -> list[dict[str, Any]]:
    lines = _merge_wrapped_asset_name_lines([line.strip() for line in raw_text.splitlines() if line.strip()])
    indexes = [index for index, line in enumerate(lines) if _looks_like_asset_name_line(line)]
    if len(indexes) <= 1:
        return []

    records: list[dict[str, Any]] = []
    for position, start_index in enumerate(indexes):
        end_index = indexes[position + 1] if position + 1 < len(indexes) else min(len(lines), start_index + 8)
        segment = "\n".join(lines[start_index:end_index])
        draft = _parse_text_to_draft(segment)
        if "name" not in draft:
            product_name = _parse_product_name(segment, draft.get("productCode"))
            if product_name:
                draft["name"] = product_name
        if not draft.get("name"):
            continue
        if enrich_info and not draft.get("productCode"):
            try:
                product_code = _lookup_fund_code_by_name(str(draft["name"]))
                if product_code:
                    draft["productCode"] = product_code
            except Exception:
                pass
        if enrich_info and draft.get("productCode"):
            try:
                info = lookup_fund_basic_info(str(draft["productCode"]))
                draft.update({**_fund_info_to_draft(info), **draft})
            except Exception:
                pass
        draft.setdefault("assetType", "equity")
        draft.setdefault("market", "CN_FUND")
        records.append({key: value for key, value in draft.items() if value not in (None, "", [])})
    return records


def _merge_wrapped_asset_name_lines(lines: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if index + 1 < len(lines) and _looks_like_asset_name_prefix(line) and _looks_like_asset_name_continuation(lines[index + 1]):
            name = line
            cursor = index + 1
            while cursor < len(lines) and _looks_like_asset_name_continuation(lines[cursor]):
                name = f"{name}{lines[cursor].strip()}"
                cursor += 1
            merged.append(name)
            index = cursor
            continue
        if not _looks_like_asset_name_line(line):
            merged.append(line)
            index += 1
            continue

        name = line
        cursor = index + 1
        while cursor < len(lines) and _looks_like_asset_name_continuation(lines[cursor]):
            name = f"{name}{lines[cursor].strip()}"
            cursor += 1
        merged.append(name)
        index = cursor
    return merged


def _looks_like_asset_name_prefix(line: str) -> bool:
    if _line_date(line) or re.search(r"(?<!\d)\d{6}(?!\d)", line):
        return False
    if re.search(r"(?:金额|收益|份额|净值|成本|日期|交易|买入|卖出|赎回|申购|持仓详情|资产总额|总资产|平台)", line):
        return False
    compact = re.sub(r"\s+", "", line)
    return bool(re.search(r"[\u4e00-\u9fa5]", compact)) and 3 <= len(compact) <= 24


def _looks_like_asset_name_line(line: str) -> bool:
    if re.search(r"(?:金额|收益|份额|净值|成本|日期|交易|买入|卖出|赎回|申购|持仓详情|资产总额|总资产)", line):
        return False
    if _line_date(line):
        return False
    if _is_standalone_asset_type_fragment(line):
        return False
    return bool(re.search(r"(?:基金|混合|债券|指数|ETF|联接|LOF|股票|货币|QDII|黄金|红利|沪深|中证|纳指|标普)", line, re.IGNORECASE))


def _looks_like_asset_name_continuation(line: str) -> bool:
    if re.search(r"(?:金额|收益|份额|净值|成本|日期|交易|买入|卖出|赎回|申购|持仓详情|资产总额|总资产|平台)", line):
        return False
    if _line_date(line) or re.search(r"(?<!\d)\d{6}(?!\d)", line):
        return False
    if re.fullmatch(r"[A-Z]{1,3}", line, re.IGNORECASE):
        return True
    return bool(re.search(r"(?:混合|债券|指数|ETF|联接|LOF|股票|货币|QDII|黄金|红利|增强|主动|被动|优选|精选|A|C)$", line, re.IGNORECASE))


def _is_standalone_asset_type_fragment(line: str) -> bool:
    compact = re.sub(r"\s+", "", line)
    return bool(
        re.fullmatch(
            r"(?:混合|债券|股票|指数|货币|QDII|ETF|LOF|联接|增强|主动|被动|优选|精选|红利|黄金|A|C|混合A|混合C|债券A|债券C|股票A|股票C|指数A|指数C)",
            compact,
            re.IGNORECASE,
        )
    )


def _append_asset_record(records: list[dict[str, Any]], seen_keys: set[str], draft: dict[str, Any]) -> None:
    key = str(draft.get("productCode") or draft.get("name") or "").strip()
    if not key or key in seen_keys:
        return
    seen_keys.add(key)
    records.append(draft)


ASSET_FIELD_LABELS = {
    "currentValue": r"(?:当前金额|持有金额|持仓金额|参考市值|当前市值|持仓市值|总金额|市值|金额)",
    "holdingGain": r"持有收益",
    "cumulativeGain": r"累计收益",
    "holdingShare": r"(?:持有份额|持仓份额|基金份额|份额)",
    "holdingCostPrice": r"(?:持仓成本价|持有成本价|成本价|成本净值|持仓成本净值|持有成本净值|平均成本|单位成本)",
}


def _fill_asset_records_from_field_columns(records: list[dict[str, Any]], raw_text: str) -> None:
    if len(records) < 2:
        return
    for field, label_pattern in ASSET_FIELD_LABELS.items():
        values = _extract_asset_field_values(raw_text, label_pattern, signed=field in {"holdingGain", "cumulativeGain"})
        if len(values) < len(records):
            continue
        for index, record in enumerate(records):
            record[field] = values[index]


def _extract_asset_field_values(raw_text: str, label_pattern: str, signed: bool = False) -> list[str]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    values: list[str] = []
    for index, line in enumerate(lines):
        label_match = re.search(label_pattern, line)
        if not label_match:
            continue

        inline_values = _numeric_values_from_text(_text_until_next_asset_field_label(line[label_match.end() :]), signed=signed)
        if inline_values:
            values.extend(inline_values)
            continue

        cursor = index + 1
        while cursor < len(lines):
            next_line = lines[cursor]
            if _is_any_asset_field_label_line(next_line) or _looks_like_asset_name_line(next_line):
                break
            values.extend(_numeric_values_from_text(next_line, signed=signed))
            cursor += 1
    return values


def _is_any_asset_field_label_line(line: str) -> bool:
    return any(re.search(pattern, line) for pattern in ASSET_FIELD_LABELS.values())


def _text_until_next_asset_field_label(text: str) -> str:
    next_starts = [match.start() for pattern in ASSET_FIELD_LABELS.values() if (match := re.search(pattern, text))]
    if not next_starts:
        return text
    return text[: min(next_starts)]


def _numeric_values_from_text(text: str, signed: bool = False) -> list[str]:
    pattern = r"([+-]?[0-9][0-9,]*(?:\.\d+)?)" if signed else r"([0-9][0-9,]*(?:\.\d+)?)"
    values: list[str] = []
    for match in re.finditer(pattern, text):
        value = match.group(1)
        if _looks_like_fund_code(value):
            continue
        if text[match.end(1) : match.end(1) + 1] == "%":
            continue
        values.append(_clean_number(value))
    return values


def _parse_product_name(raw_text: str, product_code: Optional[str] = None) -> Optional[str]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if product_code:
        for line in lines:
            if product_code not in line:
                continue
            cleaned = _clean_product_name_candidate(line.replace(product_code, " "))
            if cleaned:
                return cleaned
    for line in lines:
        if not re.search(r"(?:基金|混合|债券|指数|ETF|联接|LOF|股票|货币|QDII)", line, re.IGNORECASE):
            continue
        cleaned = _clean_product_name_candidate(line)
        if cleaned:
            return cleaned
    return None


def _clean_product_name_candidate(value: str) -> Optional[str]:
    cleaned = re.sub(r"(?<!\d)\d{6}(?!\d)", " ", value)
    cleaned = re.sub(r"(?:持仓详情|交易记录|资产|详情|金额|昨日收益|持有收益|累计收益|净值|涨跌幅|日期|交易|买入|卖出|赎回|申购)", " ", cleaned)
    cleaned = re.sub(r"[：:·|｜,，;；]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 3:
        return None
    return cleaned[:50]


def _normalize_fund_name(value: str) -> str:
    normalized = _clean_product_name_candidate(value) or value
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"(?:证券投资基金|开放式|发起式|基金)$", "", normalized)
    return normalized.upper()


def _parse_text_to_transaction_records(raw_text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for segment in _transaction_segments(raw_text):
        transaction_type = _line_transaction_type(segment)
        if not transaction_type:
            continue
        amount = _line_amount(segment)
        share = _line_share(segment)
        if transaction_type == "buy" and not amount:
            continue
        if transaction_type == "sell" and not (share or amount):
            continue
        record: dict[str, Any] = {
            "transactionType": transaction_type,
            "tradeTiming": _line_trade_timing(segment),
            "source": "ocr",
        }
        if amount:
            record["amount"] = amount
        if share:
            record["share"] = share
        transaction_date = _line_date(segment)
        if transaction_date:
            record["transactionDate"] = transaction_date
        fee_amount = _line_fee_amount(segment)
        if fee_amount:
            record["feeAmount"] = fee_amount
        fee_rate = _line_fee_rate(segment)
        if fee_rate:
            record["feeRate"] = fee_rate
        records.append(record)
    return records


def _transaction_segments(raw_text: str) -> list[str]:
    lines = [item.strip() for item in raw_text.splitlines() if item.strip()]
    normalized = re.sub(r"\s+", " ", raw_text).strip()
    if not normalized:
        return []

    date_pattern = r"(?=(?<!\d)(?:20)?\d{2}[年/-]\d{1,2}[月/-]\d{1,2})"
    date_segments = _segments_by_pattern(normalized, date_pattern)
    valid_date_segments = [segment for segment in date_segments if _segment_has_required_transaction_fields(segment)]
    column_segments = _column_like_transaction_segments(lines)
    if column_segments and len(column_segments) > len(valid_date_segments):
        return _dedupe_segments(column_segments)
    if valid_date_segments:
        return _dedupe_segments(valid_date_segments)

    segments: list[str] = []
    for segment in _table_like_transaction_segments(lines):
        if _segment_has_required_transaction_fields(segment):
            _append_unique_segment(segments, segment)
    if segments:
        return segments

    direction_pattern = r"(?=(?:买入|申购|定投|卖出|赎回|转入|转出))"
    direction_segments = _segments_by_pattern(normalized, direction_pattern)
    for segment in direction_segments:
        if _segment_has_required_transaction_fields(segment):
            _append_unique_segment(segments, segment)
    if segments:
        return segments
    return [normalized] if _line_transaction_type(normalized) else []


def _segments_by_pattern(text: str, pattern: str) -> list[str]:
    starts = [match.start() for match in re.finditer(pattern, text)]
    segments: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        segment = text[start:end].strip(" ，,;；")
        if segment:
            segments.append(segment)
    return segments


def _dedupe_segments(segments: list[str]) -> list[str]:
    deduped: list[str] = []
    for segment in segments:
        _append_unique_segment(deduped, segment)
    return deduped


def _segment_has_required_transaction_fields(segment: str) -> bool:
    transaction_type = _line_transaction_type(segment)
    if not transaction_type:
        return False
    amount = _line_amount(segment)
    share = _line_share(segment)
    if transaction_type == "buy":
        return bool(amount)
    return bool(amount or share)


def _table_like_transaction_segments(lines: list[str]) -> list[str]:
    segments: list[str] = []
    date_indexes = [index for index, line in enumerate(lines) if _line_date(line)]
    for index, line in enumerate(lines):
        if not _line_transaction_type(line):
            continue
        if len(re.findall(r"(?<!\d)(?:20)?\d{2}[年/-]\d{1,2}[月/-]\d{1,2}", line)) > 1:
            continue
        previous_dates = [date_index for date_index in date_indexes if date_index <= index]
        next_dates = [date_index for date_index in date_indexes if date_index > index]
        start = previous_dates[-1] if previous_dates else max(0, index - 3)
        end = next_dates[0] if next_dates else min(len(lines), index + 8)
        segment = " ".join(lines[start:end]).strip(" ，,;；")
        if segment:
            segments.append(segment)
    return segments


def _column_like_transaction_segments(lines: list[str]) -> list[str]:
    dates = [_line_date(line) for line in lines if _line_date(line) and not _is_non_transaction_date_line(line)]
    types = [_line_transaction_type(line) for line in lines if _line_transaction_type(line) and _is_direction_line(line)]
    amounts = [_line_amount(line) for line in lines if _line_amount(line) and _is_amount_line(line)]
    shares = [_line_share(line) for line in lines if _line_share(line)]
    if len(dates) < 2 or len(types) < 2:
        return []

    amount_cursor = 0
    share_cursor = 0
    segments: list[str] = []
    for index, transaction_type in enumerate(types):
        if index >= len(dates):
            break
        if transaction_type == "buy":
            if amount_cursor >= len(amounts):
                return []
            segments.append(f"{dates[index]} 买入 金额 {amounts[amount_cursor]}")
            amount_cursor += 1
            continue
        if share_cursor < len(shares):
            segments.append(f"{dates[index]} 卖出 份额 {shares[share_cursor]}")
            share_cursor += 1
        elif amount_cursor < len(amounts):
            segments.append(f"{dates[index]} 卖出 金额 {amounts[amount_cursor]}")
            amount_cursor += 1
    return segments if len(segments) >= 2 else []


def _is_non_transaction_date_line(line: str) -> bool:
    return bool(re.search(r"(?:账单|生成|查询|截图|导出|更新|当前|统计)", line))


def _is_amount_line(line: str) -> bool:
    if re.search(r"(?:手续费|费用|费率|收益|净值|涨跌|份额)", line):
        return False
    if re.search(r"(?:金额|买入|申购|转入|卖出|赎回|成交|确认|申请|扣款|支付)", line):
        return True
    compact = line.replace(",", "").strip()
    return bool(re.fullmatch(r"[0-9]+(?:\.\d+)?", compact)) and not _looks_like_fund_code(compact)


def _is_direction_line(line: str) -> bool:
    if re.search(r"(?:金额|份额|手续费|费用|费率)", line):
        return False
    return bool(re.search(r"(?:买入|申购|定投|卖出|赎回|转入|转出)", line))


def _append_unique_segment(segments: list[str], segment: str) -> None:
    normalized = re.sub(r"\s+", " ", segment).strip(" ，,;；")
    if normalized and normalized not in segments:
        segments.append(normalized)


def _line_transaction_type(line: str) -> Optional[str]:
    if re.search(r"(?:买入|申购|转入|定投)", line):
        return "buy"
    if re.search(r"(?:卖出|赎回|转出)", line):
        return "sell"
    return None


def _line_amount(line: str) -> Optional[str]:
    amount_match = re.search(r"(?:买入金额|申购金额|转入金额|卖出金额|赎回金额|成交金额|确认金额|申请金额|扣款金额|支付金额|金额)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", line)
    if amount_match:
        return _clean_number(amount_match.group(1))
    compact = re.sub(r"(?:20)?\d{2}[年/-]\d{1,2}[月/-]\d{1,2}", " ", line)
    compact = re.sub(r"\d{1,2}:\d{2}", " ", compact)
    numbers = [
        value
        for value in re.findall(r"(?<!\d)([0-9][0-9,]*(?:\.\d+)?)(?!\d)", compact)
        if not re.search(rf"{re.escape(value)}\s*%", compact) and not _looks_like_fund_code(value)
    ]
    if numbers:
        decimal_numbers = [value for value in numbers if "." in value]
        return _clean_number(decimal_numbers[0] if decimal_numbers else numbers[0])
    return None


def _line_share(line: str) -> Optional[str]:
    share_match = re.search(r"(?:卖出份额|赎回份额|确认份额|成交份额|份额)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", line)
    if share_match:
        return _clean_number(share_match.group(1))
    return None


def _line_date(line: str) -> Optional[str]:
    date_match = re.search(r"((?:20)?\d{2})[年/-](\d{1,2})[月/-](\d{1,2})", line)
    if not date_match:
        return None
    year = date_match.group(1)
    if len(year) == 2:
        year = f"20{year}"
    return f"{year}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"


def _line_trade_timing(line: str) -> str:
    if re.search(r"(?:三点后|15点后|15:00后|下午3点后)", line):
        return "after_15"
    return "before_15"


def _line_fee_amount(line: str) -> Optional[str]:
    fee_match = re.search(r"(?:手续费|费用)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)", line)
    return _clean_number(fee_match.group(1)) if fee_match else None


def _line_fee_rate(line: str) -> Optional[str]:
    fee_rate_match = re.search(r"(?:费率)[^\d-]*([0-9][0-9,]*(?:\.\d+)?)\s*%?", line)
    return _clean_number(fee_rate_match.group(1)) if fee_rate_match else None


def _fund_info_to_draft(info: FundBasicInfo) -> dict[str, Any]:
    draft: dict[str, Any] = {
        "productCode": info.productCode,
        "market": info.market,
        "dataSourceType": info.sourceType,
        "dataStatus": info.dataStatus,
    }
    if info.name:
        draft["name"] = info.name
    if info.latestPrice is not None:
        draft["latestPrice"] = str(info.latestPrice)
    if info.priceDate is not None:
        draft["priceDate"] = info.priceDate.isoformat()
    if info.dailyChangePct is not None:
        draft["dailyChangePct"] = str(info.dailyChangePct)
    return draft


def _first_existing_column(frame: Any, names: list[str]) -> Optional[str]:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _clean_number(value: str) -> str:
    return str(Decimal(value.replace(",", "").replace("+", "").strip()))


def _looks_like_fund_code(value: str) -> bool:
    compact = value.replace(",", "")
    return bool(re.fullmatch(r"0\d{5}", compact))
