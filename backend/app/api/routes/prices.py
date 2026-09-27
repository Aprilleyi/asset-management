from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.prices import ManualPriceCreate, PriceUpdateResult
from app.services import prices as price_service


router = APIRouter(prefix="/assets", tags=["prices"])


@router.post("/{asset_id}/price/update", response_model=PriceUpdateResult)
def update_asset_price(asset_id: str, session: Session = Depends(get_session)) -> PriceUpdateResult:
    asset, record, success = price_service.update_asset_price(session, asset_id)
    return PriceUpdateResult(
        assetId=asset.id,
        productCode=asset.productCode,
        success=success,
        priceRecord=record,
    )


@router.post("/{asset_id}/price/manual", response_model=PriceUpdateResult)
def manual_asset_price(
    asset_id: str,
    payload: ManualPriceCreate,
    session: Session = Depends(get_session),
) -> PriceUpdateResult:
    asset, record, success = price_service.manual_price(session, asset_id, payload)
    return PriceUpdateResult(
        assetId=asset.id,
        productCode=asset.productCode,
        success=success,
        priceRecord=record,
    )
