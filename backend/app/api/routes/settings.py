from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.settings import SettingList, SettingRead, SettingUpdate
from app.services import settings as settings_service


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingList)
def list_settings(session: Session = Depends(get_session)) -> SettingList:
    items = settings_service.list_settings(session)
    return SettingList(items=items, total=len(items))


@router.patch("/{setting_key}", response_model=SettingRead)
def update_setting(setting_key: str, payload: SettingUpdate, session: Session = Depends(get_session)) -> SettingRead:
    return settings_service.update_setting(session, setting_key, payload.settingValue)
