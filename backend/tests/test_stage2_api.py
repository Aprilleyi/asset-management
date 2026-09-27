from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.data_sources.base import PriceQuote
from app.models import AlertRecord, Asset, Backup, DailySnapshot, MonthlyReview, PriceRecord, TaskLog, Transaction
from app.schemas.funds import ScreenshotParseRequest
from app.services import funds as fund_service
from app.services.funds import _parse_text_to_asset_records, _parse_text_to_draft, _parse_text_to_transaction_records, get_benchmark_history
from app.services.prices import seed_recent_price_history, update_asset_price
from app.services.transactions import generate_due_dca_transactions


class FakeSuccessAdapter:
    source_type = "fake"
    source_name = "FakeSource"

    def fetch_price(self, product_code: str) -> PriceQuote:
        return PriceQuote(
            productCode=product_code,
            priceDate=date(2026, 7, 5),
            price=Decimal("2.5"),
            dailyChangePct=Decimal("1.2"),
            sourceType=self.source_type,
            sourceName=self.source_name,
        )


class FakeFailAdapter:
    source_type = "fake"
    source_name = "FakeSource"

    def fetch_price(self, product_code: str) -> PriceQuote:
        raise RuntimeError("HTTPSConnectionPool(host='80.push2.eastmoney.com', port=443): Max retries exceeded")


class FakeHistoryAdapter:
    source_type = "fake"
    source_name = "FakeSource"

    def fetch_price(self, product_code: str) -> PriceQuote:
        return self.fetch_recent_prices(product_code, limit=1)[-1]

    def fetch_recent_prices(self, product_code: str, limit: int = 7) -> list[PriceQuote]:
        start = date(2026, 7, 1)
        return [
            PriceQuote(
                productCode=product_code,
                priceDate=start + timedelta(days=index),
                price=Decimal("2.0") + Decimal(index) / Decimal("10"),
                dailyChangePct=Decimal("1.0"),
                sourceType=self.source_type,
                sourceName=self.source_name,
            )
            for index in range(limit)
        ]


class FakeDateRangeAdapter:
    source_type = "fake"
    source_name = "FakeSource"

    def fetch_price(self, product_code: str) -> PriceQuote:
        return self.fetch_price_history(product_code)[-1]

    def fetch_recent_prices(self, product_code: str, limit: int = 7) -> list[PriceQuote]:
        return self.fetch_price_history(product_code)[-limit:]

    def fetch_price_history(
        self,
        product_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PriceQuote]:
        dates = [date(2026, 7, 8), date(2026, 7, 9), date(2026, 7, 10)]
        quotes = [
            PriceQuote(
                productCode=product_code,
                priceDate=price_date,
                price=Decimal("2.0") + Decimal(index) / Decimal("10"),
                dailyChangePct=Decimal("1.0"),
                sourceType=self.source_type,
                sourceName=self.source_name,
            )
            for index, price_date in enumerate(dates)
        ]
        return [
            quote
            for quote in quotes
            if (start_date is None or quote.priceDate >= start_date) and (end_date is None or quote.priceDate <= end_date)
        ]


class FakeStockAdapter:
    source_type = "fake_stock"
    source_name = "FakeStockSource"

    def __init__(self):
        self.product_code: Optional[str] = None
        self.market: Optional[str] = None

    def fetch_price_history(self, product_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> list[PriceQuote]:
        raise AssertionError("stock assets must not use fund price history")

    def fetch_stock_price_history(
        self,
        product_code: str,
        market: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[PriceQuote]:
        self.product_code = product_code
        self.market = market
        return [
            PriceQuote(
                productCode=product_code,
                priceDate=date(2026, 7, 10),
                price=Decimal("10.25"),
                dailyChangePct=Decimal("0.8"),
                sourceType=self.source_type,
                sourceName=self.source_name,
            )
        ]


class FakeBenchmarkAdapter:
    source_type = "fake"
    source_name = "FakeBenchmark"

    def fetch_index_history(self, symbol: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> list[PriceQuote]:
        assert symbol == "000300"
        return [
            PriceQuote(
                productCode=symbol,
                priceDate=date(2026, 7, 8),
                price=Decimal("4000"),
                dailyChangePct=Decimal("1.0"),
                sourceType=self.source_type,
                sourceName=self.source_name,
            ),
            PriceQuote(
                productCode=symbol,
                priceDate=date(2026, 7, 9),
                price=Decimal("4040"),
                dailyChangePct=Decimal("1.0"),
                sourceType=self.source_type,
                sourceName=self.source_name,
            ),
        ]


def test_create_cash_asset_writes_to_sqlite_with_owner(client):
    test_client, engine = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "招商银行活期",
            "platform": "招商银行",
            "currentValue": 10000,
            "targetTag": "应急金",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("asset_")
    assert body["ownerId"] == "local_user"
    assert body["assetType"] == "cash"

    with Session(engine) as session:
        asset = session.get(Asset, body["id"])
        assert asset is not None
        assert asset.ownerId == "local_user"


def test_create_all_asset_types(client):
    test_client, _ = client
    payloads = [
        {
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 1000,
        },
        {
            "assetType": "fixed_income",
            "name": "定期存款",
            "platform": "银行",
            "currentValue": 2000,
            "principalAmount": 2000,
            "expectedReturnRate": 2.5,
        },
        {
            "assetType": "equity",
            "name": "指数基金",
            "platform": "基金平台",
            "productCode": "000000",
            "holdingShare": 100,
            "costAmount": 1000,
            "latestPrice": 10,
        },
        {
            "assetType": "debt",
            "name": "信用卡",
            "platform": "银行",
            "currentValue": 300,
            "interestRate": 8,
        },
    ]

    for payload in payloads:
        response = test_client.post("/api/assets", json=payload)
        assert response.status_code == 201
        assert response.json()["assetType"] == payload["assetType"]

    assert test_client.get("/api/assets").json()["total"] == 4


def test_equity_asset_cost_amount_is_optional(client):
    test_client, _ = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "可选本金基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "latestPrice": 2.5,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["costAmount"] is None
    assert Decimal(body["currentValue"]) == Decimal("250.0000")


def test_equity_asset_product_code_is_optional(client):
    test_client, engine = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "未填代码权益资产",
            "platform": "基金平台",
            "holdingShare": 100,
            "currentValue": 250,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["productCode"] is None
    assert body["ownerId"] == "local_user"
    with Session(engine) as session:
        asset = session.get(Asset, body["id"])
        assert asset is not None
        assert asset.productCode is None


def test_equity_holding_gain_infers_holding_cost_on_create(client):
    test_client, _ = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "收益反推成本基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "currentValue": 260,
            "holdingGain": 60,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert Decimal(body["costAmount"]) == Decimal("200.0000")
    assert Decimal(body["holdingCostPrice"]) == Decimal("2.000000")


def test_equity_holding_gain_infers_holding_cost_on_update(client):
    test_client, _ = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "编辑收益反推成本基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "currentValue": 260,
        },
    ).json()

    response = test_client.patch(
        f"/api/assets/{created['id']}",
        json={"holdingGain": 50},
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["costAmount"]) == Decimal("210.0000")
    assert Decimal(body["holdingCostPrice"]) == Decimal("2.100000")


def test_equity_holding_cost_price_infers_holding_gain_on_update(client):
    test_client, _ = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "成本反推收益基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "currentValue": 260,
        },
    ).json()

    response = test_client.patch(
        f"/api/assets/{created['id']}",
        json={"holdingCostPrice": 2.2},
    )

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["holdingGain"]) == Decimal("40.0000")


def test_equity_asset_explicit_current_value_persists_with_latest_price(client):
    test_client, engine = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "当前金额手动基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "latestPrice": 2.5,
            "currentValue": 260,
        },
    )

    assert created.status_code == 201
    assert Decimal(created.json()["currentValue"]) == Decimal("260.0000")

    updated = test_client.patch(
        f"/api/assets/{created.json()['id']}",
        json={"currentValue": 280},
    )

    assert updated.status_code == 200
    assert Decimal(updated.json()["currentValue"]) == Decimal("280.0000")
    with Session(engine) as session:
        asset = session.get(Asset, created.json()["id"])
        assert asset is not None
        assert asset.currentValue == Decimal("280.0000")


def test_equity_asset_can_clear_cost_fields(client):
    test_client, engine = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "清空成本字段基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "holdingCostPrice": 2,
            "latestPrice": 2.5,
        },
    ).json()

    response = test_client.patch(f"/api/assets/{created['id']}", json={"costAmount": None, "holdingCostPrice": None})

    assert response.status_code == 200
    body = response.json()
    assert body["costAmount"] is None
    assert body["holdingCostPrice"] is None

    with Session(engine) as session:
        asset = session.get(Asset, created["id"])
        assert asset is not None
        assert asset.costAmount is None
        assert asset.holdingCostPrice is None


def test_dca_frequency_validation(client):
    test_client, _ = client

    daily_response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "每日定投基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "latestPrice": 2.5,
            "isDca": True,
            "dcaAmount": 100,
            "dcaFrequency": "daily",
        },
    )
    assert daily_response.status_code == 201

    weekly_response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "每周定投基金",
            "platform": "基金平台",
            "productCode": "009777",
            "holdingShare": 100,
            "latestPrice": 1.5,
            "isDca": True,
            "dcaAmount": 100,
            "dcaFrequency": "weekly",
        },
    )
    assert weekly_response.status_code == 422


def test_equity_asset_can_save_holding_gain_correction(client):
    test_client, engine = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "收益校正基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "holdingCostPrice": 1.8,
            "holdingGain": -15.5,
            "cumulativeGain": 22.2,
            "dailyIncomeAmount": -1.23,
            "latestPrice": 2,
        },
    )

    assert created.status_code == 201
    asset_id = created.json()["id"]
    assert Decimal(created.json()["holdingCostPrice"]) == Decimal("1.800000")
    assert Decimal(created.json()["holdingGain"]) == Decimal("20.0000")
    assert Decimal(created.json()["cumulativeGain"]) == Decimal("22.2000")
    assert Decimal(created.json()["cumulativeNetBasis"]) == Decimal("177.8000")
    assert Decimal(created.json()["dailyIncomeAmount"]) == Decimal("-1.2300")

    updated = test_client.patch(
        f"/api/assets/{asset_id}",
        json={"holdingCostPrice": 1.9, "holdingGain": 12.34, "cumulativeGain": -8.88, "dailyIncomeAmount": -2.34},
    )

    assert updated.status_code == 200
    assert Decimal(updated.json()["holdingCostPrice"]) == Decimal("1.900000")
    assert Decimal(updated.json()["holdingGain"]) == Decimal("10.0000")
    assert Decimal(updated.json()["cumulativeGain"]) == Decimal("-8.8800")
    assert Decimal(updated.json()["cumulativeNetBasis"]) == Decimal("208.8800")
    assert Decimal(updated.json()["dailyIncomeAmount"]) == Decimal("-2.3400")
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        assert asset.holdingCostPrice == Decimal("1.900000")
        assert asset.holdingGain == Decimal("10.0000")
        assert asset.cumulativeGain == Decimal("-8.8800")
        assert asset.cumulativeNetBasis == Decimal("208.8800")
        assert asset.dailyIncomeAmount == Decimal("-2.3400")


def test_fixed_income_asset_can_save_net_value_metrics(client):
    test_client, engine = client

    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "fixed_income",
            "name": "净值型银行理财",
            "subType": "银行理财",
            "platform": "银行",
            "currentValue": 10120,
            "productCode": "LC0001",
            "holdingShare": 10000,
            "holdingCostPrice": 1,
            "holdingGain": 120,
            "cumulativeGain": 150,
            "latestPrice": 1.012,
            "priceDate": "2026-07-24",
            "expectedReturnRate": 3.2,
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert Decimal(body["holdingShare"]) == Decimal("10000.000000")
    assert Decimal(body["holdingCostPrice"]) == Decimal("1.000000")
    assert Decimal(body["holdingGain"]) == Decimal("120.0000")
    assert Decimal(body["cumulativeGain"]) == Decimal("150.0000")
    assert Decimal(body["cumulativeNetBasis"]) == Decimal("9970.0000")

    updated = test_client.patch(
        f"/api/assets/{body['id']}",
        json={"currentValue": 10200, "holdingCostPrice": 1.01},
    )

    assert updated.status_code == 200
    assert Decimal(updated.json()["holdingGain"]) == Decimal("100.0000")
    with Session(engine) as session:
        asset = session.get(Asset, body["id"])
        assert asset is not None
        assert asset.subType == "银行理财"
        assert asset.holdingGain == Decimal("100.0000")


def test_equity_asset_requires_holding_share_and_does_not_write_dirty_data(client):
    test_client, engine = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "纳指基金",
            "platform": "支付宝",
            "productCode": "000000",
            "costAmount": 2000,
            "latestPrice": 2.1,
        },
    )

    assert response.status_code == 422
    with Session(engine) as session:
        assert session.exec(select(Asset)).all() == []


def test_stock_account_equity_asset_does_not_require_product_code_or_share(client):
    test_client, engine = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "subType": "股票账户",
            "name": "券商账户汇总",
            "platform": "证券公司",
            "currentValue": 50000,
            "costAmount": 48000,
            "holdingGain": 2000,
            "cumulativeGain": 2500,
            "market": "CN_A_SH",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["productCode"] is None
    assert body["holdingShare"] is None
    assert Decimal(body["holdingGain"]) == Decimal("2000.0000")
    assert Decimal(body["cumulativeGain"]) == Decimal("2500.0000")
    assert Decimal(body["cumulativeNetBasis"]) == Decimal("47500.0000")
    with Session(engine) as session:
        asset = session.get(Asset, body["id"])
        assert asset is not None
        assert asset.subType == "股票账户"
        assert asset.productCode is None


def test_stock_holding_equity_asset_uses_stock_fields(client):
    test_client, _ = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "subType": "A股股票",
            "name": "示例股票",
            "platform": "证券公司",
            "productCode": "600000",
            "market": "CN_A_SH",
            "currentValue": 10200,
            "holdingShare": 1000,
            "holdingCostPrice": 10,
            "latestPrice": 10.2,
        },
    )

    assert response.status_code == 201
    assert Decimal(response.json()["holdingGain"]) == Decimal("200.0000")
    assert Decimal(response.json()["holdingCostPrice"]) == Decimal("10.000000")


def test_stock_holding_price_update_uses_stock_adapter(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "subType": "A股股票",
            "name": "浦发银行",
            "platform": "证券公司",
            "productCode": "600000",
            "market": "CN_A_SH",
            "holdingShare": 1000,
            "holdingCostPrice": 10,
        },
    ).json()
    adapter = FakeStockAdapter()

    with Session(engine) as session:
        updated, record, success = update_asset_price(session, asset["id"], adapter=adapter)

    assert success is True
    assert adapter.product_code == "600000"
    assert adapter.market == "CN_A_SH"
    assert record.sourceType == "fake_stock"
    assert record.priceDate == date(2026, 7, 10)
    assert updated.latestPrice == Decimal("10.250000")
    assert updated.currentValue == Decimal("10250.0000")
    assert updated.holdingGain == Decimal("250.0000")


def test_list_assets_returns_sqlite_data(client):
    test_client, _ = client
    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 500,
        },
    ).json()

    response = test_client.get("/api/assets")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == created["id"]


def test_update_asset_changes_updated_at(client):
    test_client, _ = client
    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 500,
        },
    ).json()

    response = test_client.patch(created["id"].join(["/api/assets/", ""]), json={"name": "现金账户 A", "currentValue": 600})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "现金账户 A"
    assert body["currentValue"] == "600.0000"
    assert body["updatedAt"] != created["updatedAt"]


def test_deactivate_asset_hides_from_default_list_but_detail_remains(client):
    test_client, _ = client
    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 500,
        },
    ).json()

    response = test_client.post(f"/api/assets/{created['id']}/deactivate")
    assert response.status_code == 200
    assert response.json()["assetStatus"] == "inactive"

    default_list = test_client.get("/api/assets").json()
    assert default_list["total"] == 0

    detail = test_client.get(f"/api/assets/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["assetStatus"] == "inactive"


def test_delete_asset_removes_asset_and_related_records(client):
    test_client, engine = client
    created = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "待删除现金",
            "platform": "银行",
            "currentValue": 500,
        },
    ).json()
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        session.add(
            Transaction(
                id="transaction_delete_asset",
                ownerId="local_user",
                assetId=created["id"],
                transactionType="manual_adjustment",
                amount=Decimal("500"),
                transactionDate=date(2026, 7, 5),
                source="manual",
            )
        )
        session.add(
            PriceRecord(
                id="price_delete_asset",
                ownerId="local_user",
                assetId=created["id"],
                productCode=created["id"],
                priceDate=date(2026, 7, 5),
                price=Decimal("1.250000"),
                sourceType="manual",
                sourceName="手动补录",
                fetchedAt=now,
                dataStatus="manual",
                isValid=True,
            )
        )
        session.add(
            AlertRecord(
                id="alert_delete_asset",
                ownerId="local_user",
                ruleId="rule_cash_safety",
                ruleCode="cash_safety",
                alertLevel="attention",
                title="现金提醒",
                targetAssetId=created["id"],
                targetAssetName=created["name"],
                reason="测试删除关联提醒",
                triggeredAt=now,
            )
        )
        session.commit()

    response = test_client.delete(f"/api/assets/{created['id']}")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "assetId": created["id"]}
    assert test_client.get(f"/api/assets/{created['id']}").status_code == 404
    with Session(engine) as session:
        assert session.get(Asset, created["id"]) is None
        assert session.exec(select(Transaction).where(Transaction.assetId == created["id"])).first() is None
        assert session.exec(select(PriceRecord).where(PriceRecord.assetId == created["id"])).first() is None
        assert session.exec(select(AlertRecord).where(AlertRecord.targetAssetId == created["id"])).first() is None


def test_settings_defaults_and_update_persist(client):
    test_client, _ = client

    response = test_client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["total"] == 14

    update = test_client.patch("/api/settings/monthly_required_expense", json={"settingValue": "10000"})
    assert update.status_code == 200
    assert update.json()["settingValue"] == "10000"

    refreshed = test_client.get("/api/settings").json()
    monthly = [item for item in refreshed["items"] if item["settingKey"] == "monthly_required_expense"][0]
    assert monthly["settingValue"] == "10000"


def test_negative_number_setting_is_rejected(client):
    test_client, _ = client

    response = test_client.patch("/api/settings/cash_safety_months", json={"settingValue": "-1"})

    assert response.status_code == 422


def test_alert_rules_defaults_and_update(client):
    test_client, _ = client

    response = test_client.get("/api/alert-rules")
    assert response.status_code == 200
    assert response.json()["total"] == 11

    update = test_client.patch(
        "/api/alert-rules/cash_safety",
        json={
            "isEnabled": True,
            "thresholdValue": "4",
            "alertLevel": "must",
            "repeatIntervalDays": 3,
        },
    )

    assert update.status_code == 200
    body = update.json()
    assert body["thresholdValue"] == "4"
    assert body["repeatIntervalDays"] == 3


def test_dashboard_summary_uses_assets_from_sqlite(client):
    test_client, _ = client
    test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 12000,
        },
    )
    test_client.post(
        "/api/assets",
        json={
            "assetType": "debt",
            "name": "信用卡",
            "platform": "银行",
            "currentValue": 2000,
        },
    )

    response = test_client.get("/api/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert float(body["totalAsset"]) == 12000
    assert float(body["totalDebt"]) == 2000
    assert float(body["netAsset"]) == 10000
    assert body["activeAssetCount"] == 2


def test_settings_support_tables_have_real_empty_or_default_data(client):
    test_client, _ = client

    data_sources = test_client.get("/api/data-sources")
    task_logs = test_client.get("/api/task-logs")
    alerts = test_client.get("/api/alerts")
    reviews = test_client.get("/api/monthly-reviews")

    assert data_sources.status_code == 200
    assert data_sources.json()["total"] == 2
    assert task_logs.status_code == 200
    assert task_logs.json()["total"] == 0
    assert alerts.status_code == 200
    assert alerts.json()["total"] == 0
    assert reviews.status_code == 200
    assert reviews.json()["total"] == 0


def test_manual_price_updates_asset_and_writes_price_record(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "测试基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{asset['id']}/price/manual",
        json={"priceDate": "2026-07-05", "price": 2.5, "dailyChangePct": 1.2, "dailyIncomeAmount": -12.34},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    with Session(engine) as session:
        refreshed = session.get(Asset, asset["id"])
        assert refreshed.latestPrice == Decimal("2.500000")
        assert refreshed.currentValue == Decimal("250.0000")
        assert refreshed.holdingGain == Decimal("50.0000")
        assert refreshed.cumulativeNetBasis == Decimal("200.0000")
        assert refreshed.cumulativeGain == Decimal("50.0000")
        assert refreshed.dailyIncomeAmount == Decimal("-12.3400")
        assert refreshed.dataSourceType == "manual"
        assert refreshed.dataStatus == "manual"
        records = session.exec(select(PriceRecord)).all()
        assert len(records) == 1
        assert records[0].sourceType == "manual"
        assert records[0].dailyIncomeAmount == Decimal("-12.3400")
        assert records[0].isValid is True


def test_cash_asset_can_save_yield_fields(client):
    test_client, engine = client

    response = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "活期现金",
            "platform": "招商银行",
            "currentValue": 10000,
            "expectedReturnRate": 1.35,
            "latestPrice": 1.35,
            "priceDate": "2026-07-05",
            "dailyIncomeAmount": 1.23,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert Decimal(body["expectedReturnRate"]) == Decimal("1.3500")
    assert Decimal(body["latestPrice"]) == Decimal("1.350000")
    assert Decimal(body["dailyIncomeAmount"]) == Decimal("1.2300")
    assert body["ownerId"] == "local_user"
    with Session(engine) as session:
        asset = session.get(Asset, body["id"])
        assert asset is not None
        assert asset.ownerId == "local_user"
        assert asset.expectedReturnRate == Decimal("1.3500")
        assert asset.latestPrice == Decimal("1.350000")
        assert asset.priceDate == date(2026, 7, 5)
        assert asset.dailyIncomeAmount == Decimal("1.2300")


def test_manual_price_supports_cash_and_writes_price_record(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金管理",
            "platform": "银行",
            "currentValue": 10000,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{asset['id']}/price/manual",
        json={
            "priceDate": "2026-07-05",
            "price": 1.45,
            "currentValue": 10020,
            "dailyChangePct": 0.02,
            "dailyIncomeAmount": 1.88,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    with Session(engine) as session:
        refreshed = session.get(Asset, asset["id"])
        assert refreshed.latestPrice == Decimal("1.450000")
        assert refreshed.expectedReturnRate == Decimal("1.4500")
        assert refreshed.currentValue == Decimal("10020.0000")
        assert refreshed.priceDate == date(2026, 7, 5)
        assert refreshed.dailyIncomeAmount == Decimal("1.8800")
        assert refreshed.dataSourceType == "manual"
        assert refreshed.dataStatus == "manual"
        records = session.exec(select(PriceRecord).where(PriceRecord.assetId == asset["id"])).all()
        assert len(records) == 1
        assert records[0].productCode == asset["id"]
        assert records[0].price == Decimal("1.450000")
        assert records[0].priceDate == date(2026, 7, 5)
        assert records[0].dailyIncomeAmount == Decimal("1.8800")
        assert records[0].sourceType == "manual"
        assert records[0].isValid is True


def test_manual_price_supports_fixed_income_and_preserves_amount_without_share(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "fixed_income",
            "subType": "银行理财",
            "name": "测试理财",
            "platform": "银行",
            "currentValue": 10000,
            "costAmount": 9800,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{asset['id']}/price/manual",
        json={"priceDate": "2026-07-05", "price": 1.0321, "dailyChangePct": 0.03},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    with Session(engine) as session:
        refreshed = session.get(Asset, asset["id"])
        assert refreshed.latestPrice == Decimal("1.032100")
        assert refreshed.priceDate == date(2026, 7, 5)
        assert refreshed.currentValue == Decimal("10000.0000")
        assert refreshed.dataSourceType == "manual"
        assert refreshed.dataStatus == "manual"
        records = session.exec(select(PriceRecord).where(PriceRecord.assetId == asset["id"])).all()
        assert len(records) == 1
        assert records[0].productCode == asset["id"]
        assert records[0].price == Decimal("1.032100")
        assert records[0].priceDate == date(2026, 7, 5)
        assert records[0].sourceType == "manual"
        assert records[0].isValid is True


def test_success_adapter_updates_asset_market_value(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "测试基金",
            "platform": "基金平台",
            "productCode": "009777",
            "holdingShare": 100,
            "costAmount": 200,
        },
    ).json()

    with Session(engine) as session:
        updated, record, success = update_asset_price(session, asset["id"], adapter=FakeSuccessAdapter())
        assert success is True
        assert record.isValid is True
        assert updated.latestPrice == Decimal("2.500000")
        assert updated.currentValue == Decimal("250.0000")
        assert updated.holdingGain == Decimal("50.0000")
        assert updated.cumulativeGain == Decimal("50.0000")
        assert updated.dataStatus == "normal"


def test_price_update_recalculates_cumulative_gain_from_manual_basis(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "累计收益校正基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "currentValue": 260,
            "holdingCostPrice": 2,
            "cumulativeGain": -40,
        },
    ).json()

    assert Decimal(asset["cumulativeNetBasis"]) == Decimal("300.0000")
    assert Decimal(asset["cumulativeGain"]) == Decimal("-40.0000")

    response = test_client.post(
        f"/api/assets/{asset['id']}/price/manual",
        json={"priceDate": "2026-07-06", "price": 3},
    )

    assert response.status_code == 200
    with Session(engine) as session:
        refreshed = session.get(Asset, asset["id"])
        assert refreshed.currentValue == Decimal("300.0000")
        assert refreshed.holdingGain == Decimal("100.0000")
        assert refreshed.cumulativeNetBasis == Decimal("300.0000")
        assert refreshed.cumulativeGain == Decimal("0.0000")


def test_price_update_backfills_missing_trading_days_without_projecting_current_share(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "广发双擎升级混合A",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
        },
    ).json()

    with Session(engine) as session:
        asset_model = session.get(Asset, asset["id"])
        assert asset_model is not None
        session.add(
            PriceRecord(
                id="price_existing_latest_only",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.2"),
                sourceType="fake",
                fetchedAt=datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.commit()

        updated, record, success = update_asset_price(session, asset["id"], adapter=FakeDateRangeAdapter())
        assert success is True
        assert record.priceDate == date(2026, 7, 10)
        assert updated.latestPrice == Decimal("2.200000")

    response = test_client.get(f"/api/assets/{asset['id']}/prices")
    assert response.status_code == 200
    body = response.json()
    assert [item["priceDate"] for item in reversed(body["items"])] == ["2026-07-08", "2026-07-09", "2026-07-10"]
    assert body["items"][0]["dailyIncomeAmount"] is None


def test_seed_recent_price_history_writes_last_seven_trading_days_idempotently(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "历史净值基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "entryDate": "2026-07-10",
        },
    ).json()

    with Session(engine) as session:
        asset_model = session.get(Asset, asset["id"])
        count, latest_record, success = seed_recent_price_history(session, asset_model, adapter=FakeHistoryAdapter(), limit=7)
        assert success is True
        assert count == 7
        assert latest_record.priceDate == date(2026, 7, 7)

        count, latest_record, success = seed_recent_price_history(session, asset_model, adapter=FakeHistoryAdapter(), limit=7)
        assert success is True
        assert count == 7
        records = session.exec(select(PriceRecord).where(PriceRecord.assetId == asset["id"])).all()
        assert len(records) == 7
        refreshed = session.get(Asset, asset["id"])
        assert refreshed.latestPrice == Decimal("2.600000")
        assert refreshed.currentValue == Decimal("260.0000")


def test_price_update_backfills_existing_assets_from_one_year_window(client):
    test_client, engine = client

    class CapturingHistoryAdapter:
        source_type = "fake"
        source_name = "FakeSource"

        def __init__(self):
            self.start_date: Optional[date] = None
            self.end_date: Optional[date] = None

        def fetch_price_history(
            self,
            product_code: str,
            start_date: Optional[date] = None,
            end_date: Optional[date] = None,
        ) -> list[PriceQuote]:
            self.start_date = start_date
            self.end_date = end_date
            assert product_code == "005911"
            return [
                PriceQuote(
                    productCode=product_code,
                    priceDate=end_date or date.today(),
                    price=Decimal("2.5000"),
                    dailyChangePct=Decimal("1.0"),
                    sourceType=self.source_type,
                    sourceName=self.source_name,
                )
            ]

    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "旧资产补齐基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
        },
    ).json()
    adapter = CapturingHistoryAdapter()

    with Session(engine) as session:
        update_asset_price(session, asset["id"], adapter=adapter)

    assert adapter.start_date is not None
    assert adapter.start_date <= date.today() - timedelta(days=settings.seed_price_history_days)


def test_asset_price_list_returns_latest_record_per_day_with_calculated_daily_income(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "数据记录基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "entryDate": "2026-07-10",
        },
    ).json()

    with Session(engine) as session:
        session.add(
            PriceRecord(
                id="price_day1",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 9),
                price=Decimal("2.0000"),
                sourceType="akshare",
                sourceName="AKShare",
                fetchedAt=datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_day2_old",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.4000"),
                sourceType="akshare",
                sourceName="AKShare",
                fetchedAt=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_day2_new",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.5000"),
                sourceType="manual",
                sourceName="手动补录",
                fetchedAt=datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc),
                dataStatus="manual",
                isValid=True,
            )
        )
        session.commit()

    response = test_client.get(f"/api/assets/{asset['id']}/prices")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["items"][0]["id"] == "price_day2_new"
    assert Decimal(body["items"][0]["dailyIncomeAmount"]) == Decimal("50.0000")


def test_asset_price_list_daily_income_uses_share_after_transactions(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "份额变化基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 150,
            "costAmount": 300,
            "latestPrice": 2,
            "entryDate": "2026-07-10",
        },
    ).json()

    with Session(engine) as session:
        session.add(
            PriceRecord(
                id="price_share_1",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 9),
                price=Decimal("2.0000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_share_2",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.1000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            Transaction(
                id="transaction_share_buy",
                ownerId="local_user",
                assetId=asset["id"],
                transactionType="buy",
                amount=Decimal("100"),
                share=Decimal("50"),
                price=Decimal("2"),
                transactionDate=date(2026, 7, 10),
            )
        )
        session.commit()

    response = test_client.get(f"/api/assets/{asset['id']}/prices")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["items"][0]["dailyIncomeAmount"]) == Decimal("10.0000")


def test_buy_transaction_income_starts_on_next_valid_price_date(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "T加一确认基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 150,
            "costAmount": 300,
            "latestPrice": 2,
            "entryDate": "2026-07-09",
        },
    ).json()

    with Session(engine) as session:
        session.add(
            PriceRecord(
                id="price_confirm_1",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 9),
                price=Decimal("2.0000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_confirm_2",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.1000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_confirm_3",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 13),
                price=Decimal("2.2000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            Transaction(
                id="transaction_confirm_buy",
                ownerId="local_user",
                assetId=asset["id"],
                transactionType="buy",
                amount=Decimal("100"),
                share=Decimal("50"),
                price=Decimal("2"),
                transactionDate=date(2026, 7, 10),
            )
        )
        session.commit()

    response = test_client.get(f"/api/assets/{asset['id']}/prices")

    assert response.status_code == 200
    body = response.json()
    by_date = {item["priceDate"]: item for item in body["items"]}
    assert Decimal(by_date["2026-07-10"]["dailyIncomeAmount"]) == Decimal("10.0000")
    assert Decimal(by_date["2026-07-13"]["dailyIncomeAmount"]) == Decimal("15.0000")


def test_asset_price_list_calculates_daily_income_from_entry_date_without_transactions(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "录入日起算基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "entryDate": "2026-07-10",
        },
    ).json()

    with Session(engine) as session:
        session.add(
            PriceRecord(
                id="price_entry_before",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 9),
                price=Decimal("2.0000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 9, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.add(
            PriceRecord(
                id="price_entry_day",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.5000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 10, 20, 0, tzinfo=timezone.utc),
                dataStatus="normal",
                isValid=True,
            )
        )
        session.commit()

    response = test_client.get(f"/api/assets/{asset['id']}/prices")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["items"][0]["dailyIncomeAmount"]) == Decimal("50.0000")
    assert body["items"][1]["dailyIncomeAmount"] is None


def test_ocr_text_parser_returns_batch_transaction_drafts():
    records = _parse_text_to_transaction_records(
        """
        2026-07-10 14:30 买入 广发双擎 买入金额 1000.00 手续费 1.00
        2026-07-11 15点后 买入 广发双擎 买入金额 2000.00 费率 0.15%
        """
    )

    assert len(records) == 2
    assert records[0]["transactionType"] == "buy"
    assert records[0]["transactionDate"] == "2026-07-10"
    assert records[0]["amount"] == "1000.00"
    assert records[0]["tradeTiming"] == "before_15"
    assert records[1]["tradeTiming"] == "after_15"


def test_ocr_text_parser_extracts_holding_cost_price():
    draft = _parse_text_to_draft(
        """
        广发双擎升级混合A 005911
        金额 20,660.46
        持有份额 9527.07
        持仓成本价 2.6001
        持有收益 -891.64
        累计收益 -4,574.44
        """
    )

    assert draft["productCode"] == "005911"
    assert draft["currentValue"] == "20660.46"
    assert draft["holdingShare"] == "9527.07"
    assert draft["holdingCostPrice"] == "2.6001"
    assert draft["holdingGain"] == "-891.64"
    assert draft["cumulativeGain"] == "-4574.44"


def test_ocr_text_parser_extracts_batch_asset_records():
    records = _parse_text_to_asset_records(
        """
        广发双擎升级混合A 005911
        金额 20,660.46
        持有份额 9527.07
        持仓成本价 2.6001

        易方达消费行业股票 110022
        金额 10,200.00
        持有份额 3000.00
        成本净值 3.1000
        """,
        enrich_info=False,
    )

    assert len(records) == 2
    assert records[0]["productCode"] == "005911"
    assert records[0]["currentValue"] == "20660.46"
    assert records[0]["holdingCostPrice"] == "2.6001"
    assert records[1]["productCode"] == "110022"
    assert records[1]["holdingShare"] == "3000.00"
    assert records[1]["holdingCostPrice"] == "3.1000"


def test_ocr_text_parser_extracts_batch_asset_records_without_codes():
    records = _parse_text_to_asset_records(
        """
        广发双擎升级混合A
        当前金额 20,660.46
        持有份额 9527.07
        持仓成本价 2.6001

        易方达消费行业股票
        当前金额 10,200.00
        持有份额 3000.00
        成本净值 3.1000
        """,
        enrich_info=False,
    )

    assert len(records) == 2
    assert records[0]["name"] == "广发双擎升级混合A"
    assert records[0]["currentValue"] == "20660.46"
    assert records[0]["holdingShare"] == "9527.07"
    assert "productCode" not in records[0]
    assert records[1]["name"] == "易方达消费行业股票"
    assert records[1]["currentValue"] == "10200.00"
    assert records[1]["holdingCostPrice"] == "3.1000"


def test_ocr_text_parser_merges_wrapped_asset_names():
    records = _parse_text_to_asset_records(
        """
        广发双擎升级
        混合A
        当前金额 20,660.46
        持有收益 -891.64
        持有份额 9527.07

        易方达消费行业
        股票
        当前金额 10,200.00
        持有收益 120.00
        持有份额 3000.00
        """,
        enrich_info=False,
    )

    assert len(records) == 2
    assert records[0]["name"] == "广发双擎升级混合A"
    assert records[0]["currentValue"] == "20660.46"
    assert records[0]["holdingGain"] == "-891.64"
    assert records[1]["name"] == "易方达消费行业股票"
    assert records[1]["holdingGain"] == "120.00"


def test_ocr_text_parser_backfills_column_layout_asset_values():
    records = _parse_text_to_asset_records(
        """
        广发双擎升级
        混合A
        易方达消费行业
        股票
        当前金额
        20,660.46
        10,200.00
        持有收益
        -891.64
        120.00
        持有份额
        9,527.07
        3,000.00
        持仓成本价
        2.6001
        3.1000
        """,
        enrich_info=False,
    )

    assert len(records) == 2
    assert records[0]["name"] == "广发双擎升级混合A"
    assert records[0]["currentValue"] == "20660.46"
    assert records[0]["holdingGain"] == "-891.64"
    assert records[0]["holdingShare"] == "9527.07"
    assert records[0]["holdingCostPrice"] == "2.6001"
    assert records[1]["name"] == "易方达消费行业股票"
    assert records[1]["currentValue"] == "10200.00"
    assert records[1]["holdingGain"] == "120.00"
    assert records[1]["holdingShare"] == "3000.00"
    assert records[1]["holdingCostPrice"] == "3.1000"


def test_ocr_text_parser_splits_batch_transactions_without_line_breaks():
    records = _parse_text_to_transaction_records(
        "2026-07-10 14:30 买入 广发双擎 买入金额 1000.00 手续费 1.00 2026-07-11 15点后 买入 广发双擎 买入金额 2000.00 费率 0.15%"
    )

    assert len(records) == 2
    assert records[0]["transactionDate"] == "2026-07-10"
    assert records[0]["amount"] == "1000.00"
    assert records[1]["transactionDate"] == "2026-07-11"
    assert records[1]["amount"] == "2000.00"


def test_ocr_text_parser_rebuilds_table_like_batch_transactions():
    records = _parse_text_to_transaction_records(
        """
        交易日期
        交易方向
        交易金额
        2026-07-08
        广发双擎升级混合A 005911
        买入
        交易金额 1000.00
        手续费 1.00
        2026-07-09
        广发双擎升级混合A 005911
        15点后
        买入
        确认金额 2000.00
        费率 0.15%
        2026-07-10
        广发双擎升级混合A 005911
        卖出
        赎回份额 300.00
        费用 0.50
        """
    )

    assert len(records) == 3
    assert records[0]["transactionType"] == "buy"
    assert records[0]["transactionDate"] == "2026-07-08"
    assert records[0]["amount"] == "1000.00"
    assert records[0]["feeAmount"] == "1.00"
    assert records[1]["transactionDate"] == "2026-07-09"
    assert records[1]["amount"] == "2000.00"
    assert records[1]["tradeTiming"] == "after_15"
    assert records[1]["feeRate"] == "0.15"
    assert records[2]["transactionType"] == "sell"
    assert records[2]["share"] == "300.00"


def test_ocr_text_parser_ignores_non_transaction_dates():
    records = _parse_text_to_transaction_records(
        """
        账单生成日期 2026-07-18
        2026-07-10 15点前 买入 广发双擎 买入金额 1000.00
        2026-07-11 15点后 买入 广发双擎 买入金额 2000.00
        """
    )

    assert len(records) == 2
    assert [record["transactionDate"] for record in records] == ["2026-07-10", "2026-07-11"]
    assert [record["amount"] for record in records] == ["1000.00", "2000.00"]


def test_ocr_text_parser_pairs_column_like_dates_and_amounts_by_order():
    records = _parse_text_to_transaction_records(
        """
        交易日期
        2026-07-08
        2026-07-09
        2026-07-10
        交易方向
        买入
        买入
        买入
        交易金额
        1000.00
        2000.00
        3000.00
        """
    )

    assert len(records) == 3
    assert [record["transactionDate"] for record in records] == ["2026-07-08", "2026-07-09", "2026-07-10"]
    assert [record["amount"] for record in records] == ["1000.00", "2000.00", "3000.00"]


def test_ocr_asset_parser_reads_product_name():
    draft = _parse_text_to_draft(
        """
        持仓详情
        广发双擎升级混合A 005911
        金额 20678.50
        持有份额 9527.07
        """
    )

    assert draft["name"] == "广发双擎升级混合A"
    assert draft["productCode"] == "005911"


def test_screenshot_parse_returns_needs_review_for_ocr_text_without_asset_fields(monkeypatch):
    monkeypatch.setattr(fund_service, "_extract_text", lambda image_bytes, file_name: ("这是一段没有资产字段的普通文字", "本地 PaddleOCR Python 识别完成。"))

    result = fund_service.parse_asset_screenshot(ScreenshotParseRequest(fileName="test.jpg", imageBase64="dGVzdA=="))

    assert result.status == "needs_review"
    assert result.rawText == "这是一段没有资产字段的普通文字"
    assert result.draft["assetType"] == "equity"
    assert "assets" not in result.draft


def test_asset_basic_info_route_passes_asset_type(client, monkeypatch):
    test_client, _ = client
    from app.api.routes import funds as fund_routes

    def fake_lookup(product_code, asset_type=None, asset_sub_type=None, market=None):
        assert product_code == "000198"
        assert asset_type == "cash"
        return fund_service.FundBasicInfo(
            productCode=product_code,
            assetType=asset_type,
            subType="货币基金",
            name="测试货币基金",
            market="CN_FUND",
            sourceType="akshare",
            dataStatus="valid",
        )

    monkeypatch.setattr(fund_routes, "lookup_asset_basic_info", fake_lookup)

    response = test_client.get("/api/funds/000198/basic-info?assetType=cash")

    assert response.status_code == 200
    assert response.json()["assetType"] == "cash"
    assert response.json()["subType"] == "货币基金"
    assert response.json()["name"] == "测试货币基金"


def test_lookup_asset_basic_info_supports_fixed_income_public_fund_code(monkeypatch):
    def fake_lookup(product_code):
        return fund_service.FundBasicInfo(
            productCode=product_code,
            name="测试债券基金",
            market="CN_FUND",
            latestPrice=Decimal("1.0123"),
            priceDate=date(2026, 7, 10),
            dailyChangePct=Decimal("0.12"),
            sourceType="akshare",
            dataStatus="valid",
        )

    monkeypatch.setattr(fund_service, "lookup_fund_basic_info", fake_lookup)

    info = fund_service.lookup_asset_basic_info("005911", asset_type="fixed_income")

    assert info.assetType == "fixed_income"
    assert info.subType == "债券基金"
    assert info.name == "测试债券基金"
    assert info.latestPrice == Decimal("1.0123")


def test_lookup_asset_basic_info_keeps_non_public_debt_code_manual():
    info = fund_service.lookup_asset_basic_info("LOAN-001", asset_type="debt", asset_sub_type="消费贷")

    assert info.assetType == "debt"
    assert info.subType == "消费贷"
    assert info.productCode == "LOAN-001"
    assert info.sourceType == "manual"
    assert info.dataStatus == "partial"
    assert "手动维护" in (info.errorMessage or "")


def test_get_benchmark_history_uses_whitelisted_akshare_symbol():
    history = get_benchmark_history(
        "hs300",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 10),
        adapter=FakeBenchmarkAdapter(),
    )

    assert history.dataStatus == "normal"
    assert history.name == "沪深 300"
    assert history.items[0].priceDate == date(2026, 7, 8)
    assert history.items[1].close == Decimal("4040")


def test_create_buy_transaction_writes_to_sqlite_and_updates_asset(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "指数基金",
            "platform": "基金平台",
            "productCode": "000000",
            "holdingShare": 100,
            "costAmount": 1000,
            "latestPrice": 10,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{asset['id']}/transactions",
        json={
            "transactionType": "buy",
            "amount": 250,
            "share": 20,
            "price": 12.5,
            "transactionDate": "2026-07-12",
            "note": "追加记录",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("transaction_")
    assert body["ownerId"] == "local_user"
    assert body["assetId"] == asset["id"]
    assert body["transactionType"] == "buy"

    with Session(engine) as session:
        saved = session.get(Transaction, body["id"])
        updated_asset = session.get(Asset, asset["id"])
        assert saved is not None
        assert updated_asset is not None
        assert updated_asset.holdingShare == Decimal("120.000000")
        assert updated_asset.costAmount == Decimal("1250.0000")
        assert updated_asset.currentValue == Decimal("1250.0000")

    list_response = test_client.get(f"/api/assets/{asset['id']}/transactions")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_buy_transaction_does_not_overwrite_manual_holding_cost_price(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "手动成本价基金",
            "platform": "基金平台",
            "productCode": "000000",
            "holdingShare": 100,
            "costAmount": 1000,
            "holdingCostPrice": 9.99,
            "latestPrice": 10,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{asset['id']}/transactions",
        json={
            "transactionType": "buy",
            "amount": 250,
            "share": 20,
            "price": 12.5,
            "transactionDate": "2026-07-12",
        },
    )

    assert response.status_code == 201
    with Session(engine) as session:
        updated_asset = session.get(Asset, asset["id"])
        assert updated_asset is not None
        assert updated_asset.costAmount == Decimal("1250.0000")
        assert updated_asset.holdingCostPrice == Decimal("9.990000")


def test_transaction_auto_calculates_share_or_amount_from_confirmation_price(client, monkeypatch):
    test_client, engine = client

    class FakeTransactionAkShareAdapter:
        def fetch_price_history(self, product_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> list[PriceQuote]:
            return [
                PriceQuote(
                    productCode=product_code,
                    priceDate=date(2026, 7, 12),
                    price=Decimal("2.5"),
                    dailyChangePct=Decimal("1.0"),
                    sourceType="fake",
                    sourceName="FakeSource",
                ),
                PriceQuote(
                    productCode=product_code,
                    priceDate=date(2026, 7, 13),
                    price=Decimal("2.6"),
                    dailyChangePct=Decimal("1.0"),
                    sourceType="fake",
                    sourceName="FakeSource",
                ),
            ]

    import app.services.transactions as transaction_service

    monkeypatch.setattr(transaction_service, "AkShareAdapter", FakeTransactionAkShareAdapter)
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "自动计算基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 250,
            "latestPrice": 2.5,
        },
    ).json()

    buy_response = test_client.post(
        f"/api/assets/{asset['id']}/transactions",
        json={
            "transactionType": "buy",
            "amount": 260,
            "feeRate": 1,
            "transactionDate": "2026-07-12",
            "tradeTiming": "after_15",
        },
    )
    assert buy_response.status_code == 201
    buy = buy_response.json()
    assert buy["transactionDate"] == "2026-07-13"
    assert Decimal(buy["price"]) == Decimal("2.600000")
    assert Decimal(buy["feeAmount"]) == Decimal("2.6000")
    assert Decimal(buy["share"]).quantize(Decimal("0.000001")) == Decimal("99.000000")

    sell_response = test_client.post(
        f"/api/assets/{asset['id']}/transactions",
        json={
            "transactionType": "sell",
            "amount": 26,
            "transactionDate": "2026-07-12",
            "tradeTiming": "before_15",
        },
    )
    assert sell_response.status_code == 201
    sell = sell_response.json()
    assert sell["transactionDate"] == "2026-07-12"
    assert Decimal(sell["price"]) == Decimal("2.500000")
    assert Decimal(sell["share"]).quantize(Decimal("0.000001")) == Decimal("10.400000")

    with Session(engine) as session:
        updated_asset = session.get(Asset, asset["id"])
        assert updated_asset is not None
        assert updated_asset.holdingShare.quantize(Decimal("0.000001")) == Decimal("188.600000")


def test_due_dca_generates_transactions_and_updates_holding_metrics(client, monkeypatch):
    test_client, engine = client

    class FakeDcaAkShareAdapter:
        def fetch_price_history(self, product_code: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> list[PriceQuote]:
            return [
                PriceQuote(productCode=product_code, priceDate=date(2026, 7, 10), price=Decimal("2.0"), dailyChangePct=Decimal("0"), sourceType="fake", sourceName="FakeSource"),
                PriceQuote(productCode=product_code, priceDate=date(2026, 7, 11), price=Decimal("2.5"), dailyChangePct=Decimal("0"), sourceType="fake", sourceName="FakeSource"),
                PriceQuote(productCode=product_code, priceDate=date(2026, 7, 12), price=Decimal("4.0"), dailyChangePct=Decimal("0"), sourceType="fake", sourceName="FakeSource"),
            ]

    import app.services.transactions as transaction_service

    monkeypatch.setattr(transaction_service, "AkShareAdapter", FakeDcaAkShareAdapter)
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "定投生成基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
            "isDca": True,
            "dcaAmount": 100,
            "dcaFrequency": "daily",
            "dcaNextDate": "2026-07-10",
        },
    ).json()

    with Session(engine) as session:
        count = generate_due_dca_transactions(session, today=date(2026, 7, 12))

    assert count == 3
    with Session(engine) as session:
        transactions = session.exec(select(Transaction).where(Transaction.assetId == asset["id"]).order_by(Transaction.transactionDate.asc())).all()
        updated_asset = session.get(Asset, asset["id"])
        assert [transaction.transactionType for transaction in transactions] == ["dca", "dca", "dca"]
        assert all(transaction.source == "system_dca" for transaction in transactions)
        assert updated_asset.dcaNextDate == date(2026, 7, 13)
        assert updated_asset.costAmount == Decimal("500.0000")
        assert updated_asset.cumulativeNetBasis == Decimal("500.0000")
        assert updated_asset.currentValue == Decimal("500.0000")
        assert updated_asset.holdingShare.quantize(Decimal("0.000001")) == Decimal("215.000000")

    patch_response = test_client.patch(
        f"/api/assets/{asset['id']}/transactions/{transactions[0].id}",
        json={"amount": 150},
    )
    assert patch_response.status_code == 200
    patched_transaction = patch_response.json()
    assert Decimal(patched_transaction["amount"]) == Decimal("150.0000")
    assert Decimal(patched_transaction["share"]).quantize(Decimal("0.000001")) == Decimal("75.000000")

    with Session(engine) as session:
        updated_asset = session.get(Asset, asset["id"])
        assert updated_asset.costAmount == Decimal("550.0000")
        assert updated_asset.cumulativeNetBasis == Decimal("550.0000")
        assert updated_asset.currentValue == Decimal("550.0000")
    assert updated_asset.holdingShare.quantize(Decimal("0.000001")) == Decimal("240.000000")


def test_listing_transactions_never_generates_due_dca(client, monkeypatch):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "定投只读测试",
            "platform": "测试平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
            "isDca": True,
            "dcaAmount": 100,
            "dcaFrequency": "daily",
            "dcaNextDate": "2026-07-10",
        },
    ).json()

    import app.services.transactions as transaction_service

    def unexpected_generation(*args, **kwargs):
        raise AssertionError("GET /transactions must not generate DCA transactions")

    monkeypatch.setattr(transaction_service, "generate_due_dca_transactions", unexpected_generation)
    response = test_client.get(f"/api/assets/{asset['id']}/transactions")

    assert response.status_code == 200
    assert response.json()["total"] == 0
    with Session(engine) as session:
        assert session.exec(select(Transaction).where(Transaction.assetId == asset["id"])).all() == []
        assert session.get(Asset, asset["id"]).dcaNextDate == date(2026, 7, 10)


def test_create_conversion_creates_related_out_and_in_transactions(client):
    test_client, engine = client
    source = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "转出基金",
            "platform": "基金平台",
            "productCode": "111111",
            "holdingShare": 100,
            "costAmount": 1000,
            "latestPrice": 10,
        },
    ).json()
    target = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "转入基金",
            "platform": "基金平台",
            "productCode": "222222",
            "holdingShare": 10,
            "costAmount": 100,
            "latestPrice": 5,
        },
    ).json()

    response = test_client.post(
        f"/api/assets/{source['id']}/transactions/convert",
        json={
            "targetAssetId": target["id"],
            "transactionDate": "2026-07-12",
            "outAmount": 300,
            "outShare": 30,
            "outPrice": 10,
            "inAmount": 298,
            "inShare": 50,
            "inPrice": 5.96,
            "feeAmount": 2,
            "note": "基金转换",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["outTransaction"]["transactionType"] == "convert_out"
    assert body["inTransaction"]["transactionType"] == "convert_in"
    assert body["outTransaction"]["relatedTransactionId"] == body["inTransaction"]["id"]
    assert body["inTransaction"]["relatedTransactionId"] == body["outTransaction"]["id"]

    with Session(engine) as session:
        source_asset = session.get(Asset, source["id"])
        target_asset = session.get(Asset, target["id"])
        assert source_asset is not None
        assert target_asset is not None
        assert source_asset.holdingShare == Decimal("70.000000")
        assert source_asset.currentValue == Decimal("700.0000")
        assert target_asset.holdingShare == Decimal("60.000000")
        assert target_asset.costAmount == Decimal("398.0000")
        assert target_asset.currentValue == Decimal("348.0000")


def test_failed_price_update_writes_record_without_overwriting_last_valid_price(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "测试基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
        },
    ).json()

    with Session(engine) as session:
        updated, record, success = update_asset_price(session, asset["id"], adapter=FakeFailAdapter())
        assert success is False
        assert record.isValid is False
        assert record.dataStatus == "failed"
        assert record.errorMessage == "AKShare 数据暂不可用，请稍后重试，或使用手动补录价格。"
        assert "HTTPSConnectionPool" not in record.errorMessage
        assert updated.latestPrice == Decimal("2.000000")
        assert updated.currentValue == Decimal("200.0000")
        assert updated.dataStatus == "failed"
        assert updated.priceErrorMessage == "AKShare 数据暂不可用，请稍后重试，或使用手动补录价格。"


def test_failed_seed_price_history_uses_friendly_error_message(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "初始化失败基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
        },
    ).json()

    with Session(engine) as session:
        asset_model = session.get(Asset, asset["id"])
        count, record, success = seed_recent_price_history(session, asset_model, adapter=FakeFailAdapter(), limit=7)

    assert success is False
    assert count == 0
    assert record is not None
    assert record.errorMessage == "初始化最近 7 个交易日行情失败：AKShare 数据暂不可用，请稍后重试，或先手动补录价格。"
    assert "HTTPSConnectionPool" not in record.errorMessage


def test_legacy_html_price_error_is_sanitized_in_api_responses(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "equity",
            "name": "历史错误基金",
            "platform": "基金平台",
            "productCode": "005911",
            "holdingShare": 100,
            "costAmount": 200,
            "latestPrice": 2,
        },
    ).json()
    raw_error = "初始化最近 366 个交易日净值失败：<anonymous>:2: SyntaxError: Unexpected token '<' <!doctype html>"

    with Session(engine) as session:
        asset_model = session.get(Asset, asset["id"])
        asset_model.dataStatus = "failed"
        asset_model.priceErrorMessage = raw_error
        session.add(
            PriceRecord(
                id="price_legacy_html_error",
                ownerId="local_user",
                assetId=asset["id"],
                productCode="005911",
                priceDate=date(2026, 7, 10),
                price=Decimal("2.000000"),
                sourceType="akshare",
                fetchedAt=datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc),
                dataStatus="failed",
                isValid=False,
                errorMessage=raw_error,
            )
        )
        session.commit()

    assets_body = test_client.get("/api/assets?includeInactive=true").json()
    returned_asset = next(item for item in assets_body["items"] if item["id"] == asset["id"])
    assert returned_asset["priceErrorMessage"] == "初始化最近 366 个交易日行情失败：AKShare 数据暂不可用，请稍后重试，或先手动补录价格。"
    assert "SyntaxError" not in returned_asset["priceErrorMessage"]

    prices_body = test_client.get(f"/api/assets/{asset['id']}/prices").json()
    assert prices_body["items"][0]["errorMessage"] == "初始化最近 366 个交易日行情失败：AKShare 数据暂不可用，请稍后重试，或先手动补录价格。"
    assert "doctype" not in prices_body["items"][0]["errorMessage"]


def test_price_update_task_writes_task_log(client):
    test_client, engine = client

    response = test_client.post("/api/tasks/price-update/run")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["successCount"] == 0
    assert body["failedCount"] == 0
    with Session(engine) as session:
        logs = session.exec(select(TaskLog)).all()
        assert len(logs) == 2
        task_types = {log.taskType for log in logs}
        assert task_types == {"price_update", "alert_generate"}


def test_task_statuses_include_registered_background_jobs(client):
    test_client, _ = client

    response = test_client.get("/api/tasks/status")

    assert response.status_code == 200
    body = response.json()
    task_types = {item["taskType"] for item in body["items"]}
    assert task_types == {"price_update", "alert_generate", "daily_snapshot", "data_source_check", "auto_backup"}
    assert all(item["isEnabled"] is False for item in body["items"])


def test_alert_generation_persists_cash_alert(client):
    test_client, engine = client
    test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 100,
        },
    )

    response = test_client.post("/api/tasks/alert_generate/run")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    with Session(engine) as session:
        alerts = session.exec(select(AlertRecord)).all()
        assert any(alert.ruleCode == "cash_safety" for alert in alerts)
        cash_alert = next(alert for alert in alerts if alert.ruleCode == "cash_safety")
        assert cash_alert.currentValue is not None
        assert cash_alert.thresholdValue is not None
        assert cash_alert.reason


def test_strong_drawdown_does_not_create_normal_drawdown_alert(client):
    test_client, engine = client
    with Session(engine) as session:
        session.add(
            DailySnapshot(
                id="snapshot_high",
                ownerId="local_user",
                snapshotDate=date.today() - timedelta(days=1),
                totalAsset=Decimal("1000"),
                totalDebt=Decimal("0"),
                netAsset=Decimal("1000"),
                cashValue=Decimal("0"),
                fixedIncomeValue=Decimal("1000"),
                equityValue=Decimal("0"),
                debtValue=Decimal("0"),
                investmentValue=Decimal("1000"),
                dataStatus="normal",
            )
        )
        session.add(
            DailySnapshot(
                id="snapshot_low",
                ownerId="local_user",
                snapshotDate=date.today(),
                totalAsset=Decimal("800"),
                totalDebt=Decimal("0"),
                netAsset=Decimal("800"),
                cashValue=Decimal("0"),
                fixedIncomeValue=Decimal("800"),
                equityValue=Decimal("0"),
                debtValue=Decimal("0"),
                investmentValue=Decimal("800"),
                dataStatus="normal",
            )
        )
        session.commit()

    response = test_client.post("/api/tasks/alert_generate/run")

    assert response.status_code == 200
    with Session(engine) as session:
        rule_codes = {alert.ruleCode for alert in session.exec(select(AlertRecord)).all()}
        assert "portfolio_strong_drawdown" in rule_codes
        assert "portfolio_drawdown" not in rule_codes


def test_daily_snapshot_task_writes_snapshot_and_task_log(client):
    test_client, engine = client

    response = test_client.post("/api/tasks/daily_snapshot/run")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    with Session(engine) as session:
        snapshots = session.exec(select(DailySnapshot)).all()
        logs = session.exec(select(TaskLog).where(TaskLog.taskType == "daily_snapshot")).all()
        assert len(snapshots) == 1
        assert len(logs) == 1


def test_monthly_review_without_start_snapshot_marks_history_insufficient(client):
    test_client, engine = client
    with Session(engine) as session:
        session.add(
            DailySnapshot(
                id="snapshot_mid",
                ownerId="local_user",
                snapshotDate=date(2026, 7, 5),
                totalAsset=Decimal("1200"),
                totalDebt=Decimal("0"),
                netAsset=Decimal("1200"),
                cashValue=Decimal("200"),
                fixedIncomeValue=Decimal("500"),
                equityValue=Decimal("500"),
                debtValue=Decimal("0"),
                investmentValue=Decimal("1000"),
                dataStatus="normal",
            )
        )
        session.commit()

    response = test_client.post("/api/monthly-reviews/generate", json={"reviewMonth": "2026-07"})

    assert response.status_code == 200
    body = response.json()
    assert body["dataCompletenessStatus"] == "history_insufficient"
    assert body["startNetAsset"] is None
    assert body["netAssetChange"] is None
    assert body["investmentReturn"] is None
    assert "缺少 2026-07-01" in body["summaryText"]


def test_monthly_review_distinguishes_net_change_and_investment_return(client):
    test_client, engine = client
    with Session(engine) as session:
        session.add(
            DailySnapshot(
                id="snapshot_start",
                ownerId="local_user",
                snapshotDate=date(2026, 7, 1),
                totalAsset=Decimal("1000"),
                totalDebt=Decimal("0"),
                netAsset=Decimal("1000"),
                cashValue=Decimal("100"),
                fixedIncomeValue=Decimal("400"),
                equityValue=Decimal("500"),
                debtValue=Decimal("0"),
                investmentValue=Decimal("900"),
                dataStatus="normal",
            )
        )
        session.add(
            DailySnapshot(
                id="snapshot_end",
                ownerId="local_user",
                snapshotDate=date(2026, 7, 31),
                totalAsset=Decimal("1300"),
                totalDebt=Decimal("0"),
                netAsset=Decimal("1300"),
                cashValue=Decimal("200"),
                fixedIncomeValue=Decimal("500"),
                equityValue=Decimal("600"),
                debtValue=Decimal("0"),
                investmentValue=Decimal("1100"),
                dataStatus="normal",
            )
        )
        session.add(
            Transaction(
                id="transaction_contribution",
                ownerId="local_user",
                assetId="asset_unknown",
                transactionType="contribution",
                amount=Decimal("200"),
                transactionDate=date(2026, 7, 10),
            )
        )
        session.commit()

    response = test_client.post("/api/monthly-reviews/generate", json={"reviewMonth": "2026-07"})

    assert response.status_code == 200
    body = response.json()
    assert body["dataCompletenessStatus"] == "complete"
    assert Decimal(body["netAssetChange"]) == Decimal("300.0000")
    assert Decimal(body["newContribution"]) == Decimal("200.0000")
    assert Decimal(body["investmentReturn"]) == Decimal("100.0000")


def test_export_and_invalid_import_does_not_destroy_database(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 1000,
        },
    ).json()

    export_response = test_client.get("/api/export")
    assert export_response.status_code == 200
    exported = export_response.json()
    assert exported["dataVersion"] == "1.4.0"
    assert exported["ownerId"] == "local_user"
    assert "assets" in exported
    assert "token" not in str(exported).lower()

    exported["dataVersion"] = "0.0.0"
    import_response = test_client.post("/api/import", json={"confirmOverwrite": True, "data": exported})

    assert import_response.status_code == 400
    with Session(engine) as session:
        assert session.get(Asset, asset["id"]) is not None


def test_export_import_round_trip_overwrites_after_confirmation(client):
    test_client, engine = client
    asset = test_client.post(
        "/api/assets",
        json={
            "assetType": "cash",
            "name": "现金账户",
            "platform": "银行",
            "currentValue": 1000,
        },
    ).json()
    exported = test_client.get("/api/export").json()
    test_client.patch(f"/api/assets/{asset['id']}", json={"name": "被修改的名称"})

    response = test_client.post("/api/import", json={"confirmOverwrite": True, "data": exported})

    assert response.status_code == 200
    with Session(engine) as session:
        restored = session.get(Asset, asset["id"])
        assert restored.name == "现金账户"


def test_legacy_mislabeled_export_with_1_4_0_schema_remains_importable(client):
    test_client, _ = client
    exported = test_client.get("/api/export").json()
    exported["dataVersion"] = "1.0.0"
    response = test_client.post("/api/import", json={"confirmOverwrite": True, "data": exported})
    assert response.status_code == 200


def test_manual_backup_writes_backup_record(client):
    test_client, engine = client

    response = test_client.post("/api/backups/run")

    assert response.status_code == 200
    body = response.json()
    assert body["backupType"] == "manual"
    assert body["status"] == "success"
    with Session(engine) as session:
        backups = session.exec(select(Backup)).all()
        assert len(backups) == 1
        assert backups[0].filePath == backups[0].fileName
        assert not backups[0].filePath.startswith("/")
