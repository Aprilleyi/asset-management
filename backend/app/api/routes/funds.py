from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.funds import BenchmarkHistory, FundBasicInfo, ScreenshotParseRequest, ScreenshotParseResult
from app.services.funds import get_benchmark_history, lookup_asset_basic_info, parse_asset_screenshot


router = APIRouter(prefix="/funds", tags=["funds"])


@router.get("/{product_code}/basic-info", response_model=FundBasicInfo)
def get_fund_basic_info(
    product_code: str,
    assetType: Optional[str] = Query(default=None),
    assetSubType: Optional[str] = Query(default=None),
    market: Optional[str] = Query(default=None),
) -> FundBasicInfo:
    return lookup_asset_basic_info(product_code, asset_type=assetType, asset_sub_type=assetSubType, market=market)


@router.get("/benchmarks/{benchmark_code}/history", response_model=BenchmarkHistory)
def get_benchmark_history_api(
    benchmark_code: str,
    startDate: Optional[date] = Query(default=None),
    endDate: Optional[date] = Query(default=None),
) -> BenchmarkHistory:
    return get_benchmark_history(benchmark_code, start_date=startDate, end_date=endDate)


@router.post("/screenshot/parse", response_model=ScreenshotParseResult)
def parse_screenshot(payload: ScreenshotParseRequest) -> ScreenshotParseResult:
    try:
        return parse_asset_screenshot(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
