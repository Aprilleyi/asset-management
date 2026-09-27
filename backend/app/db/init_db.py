from sqlmodel import Session, select

from app.core.config import settings
from app.models import AlertRule, DataSource, SchemaMigration, Setting


DEFAULT_SETTINGS = [
    ("monthly_required_expense", "月必要支出", "12000", "number", "元", "基础参数", "计算现金覆盖月数"),
    ("cash_safety_months", "现金安全月数", "3", "number", "月", "提醒阈值", "现金不足提醒阈值"),
    ("cash_idle_months", "现金闲置月数", "6", "number", "月", "提醒阈值", "现金闲置提醒阈值"),
    ("equity_ratio_upper_limit", "权益仓位上限", "40", "number", "%", "提醒阈值", "权益偏高提醒阈值"),
    ("max_drawdown_warning", "回撤提醒线", "10", "number", "%", "提醒阈值", "普通回撤提醒"),
    ("max_drawdown_strong", "强风险线", "15", "number", "%", "提醒阈值", "强风险提醒"),
    ("maturity_reminder_days", "到期提前提醒", "7", "number", "天", "提醒阈值", "固收到期提醒"),
    ("repayment_reminder_days", "还款提前提醒", "7", "number", "天", "提醒阈值", "负债还款提醒"),
    ("high_interest_debt_rate", "高息负债线", "8", "number", "%", "提醒阈值", "高息负债提醒"),
    ("price_delay_days", "行情延迟天数", "2", "number", "天", "提醒阈值", "数据延迟提醒"),
    ("price_update_time_1", "第一次行情更新时间", "20:30", "time", "时间", "任务配置", "本地后台任务"),
    ("price_update_time_2", "第二次行情更新时间", "22:30", "time", "时间", "任务配置", "本地后台任务"),
    ("daily_snapshot_time", "每日快照时间", "23:30", "time", "时间", "任务配置", "每日资产快照任务"),
    ("backup_retention_days", "自动备份保留天数", "30", "number", "天", "数据管理", "备份滚动保留"),
]


DEFAULT_ALERT_RULES = [
    ("cash_safety", "现金安全线提醒", "现金", "cashCoverageMonths", "<", "3", "月", "must", "每日"),
    ("cash_idle", "现金闲置提醒", "现金", "cashCoverageMonths", ">", "6", "月", "attention", "每日"),
    ("equity_ratio_high", "权益仓位偏高", "权益", "equityRatio", ">", "40", "%", "attention", "每日"),
    ("portfolio_drawdown", "投资组合回撤提醒", "权益", "portfolioDrawdownPct", ">", "10", "%", "must", "跟随行情"),
    ("portfolio_strong_drawdown", "投资组合强风险提醒", "权益", "portfolioDrawdownPct", ">", "15", "%", "strong", "跟随行情"),
    ("fixed_income_maturity", "固收到期提醒", "固收", "daysToMaturity", "<=", "7", "天", "must", "每日"),
    ("debt_repayment", "负债还款提醒", "负债", "daysToRepayment", "<=", "7", "天", "must", "每日"),
    ("high_interest_debt", "高息负债提醒", "负债", "interestRate", ">", "8", "%", "must", "每日"),
    ("price_data_delay", "行情数据延迟", "数据", "priceDelayDays", ">", "2", "天", "review", "跟随行情"),
    ("price_data_abnormal", "行情数据异常", "数据", "dataStatus", "=", "abnormal", None, "attention", "跟随行情"),
    ("dca_monthly_review", "定投效果复盘", "复盘", "isDca", "=", "true", None, "review", "每月"),
]


def seed_defaults(session: Session) -> None:
    """Populate initial lookup rows during an explicit migration, never on Web startup."""
    _ensure_schema_migration(session)
    _ensure_stage_2_migration(session)
    _ensure_stage_4_migration(session)
    _ensure_stage_5_migration(session)
    _ensure_stage_6_migration(session)
    _ensure_settings(session)
    _ensure_alert_rules(session)
    _ensure_data_sources(session)


def _ensure_schema_migration(session: Session) -> None:
    migration_id = "migration_1_0_0"
    existing = session.get(SchemaMigration, migration_id)
    if existing:
        return
    session.add(
        SchemaMigration(
            id=migration_id,
            version="1.0.0",
            description="Initial V1.5 local background-task schema",
        )
    )

def _ensure_stage_2_migration(session: Session) -> None:
    migration_id = "migration_1_1_0_stage_2_api"
    if session.get(SchemaMigration, migration_id):
        return
    session.add(
        SchemaMigration(
            id=migration_id,
            version="1.1.0",
            description="Stage 2 basic API layer and validation",
        )
    )


def _ensure_stage_4_migration(session: Session) -> None:
    migration_id = "migration_1_2_0_stage_4_prices"
    if session.get(SchemaMigration, migration_id):
        return
    session.add(
        SchemaMigration(
            id=migration_id,
            version="1.2.0",
            description="Stage 4 price data source integration and manual price records",
        )
    )


def _ensure_stage_5_migration(session: Session) -> None:
    migration_id = "migration_1_3_0_stage_5_tasks_alerts"
    if session.get(SchemaMigration, migration_id):
        return
    session.add(
        SchemaMigration(
            id=migration_id,
            version="1.3.0",
            description="Stage 5 background tasks, retries, snapshots, backups, and persisted alerts",
        )
    )


def _ensure_stage_6_migration(session: Session) -> None:
    migration_id = "migration_1_4_0_stage_6_reviews_import_export_backups"
    if session.get(SchemaMigration, migration_id):
        return
    session.add(
        SchemaMigration(
            id=migration_id,
            version="1.4.0",
            description="Stage 6 monthly reviews, full JSON import/export, and manual backups",
        )
    )


def _ensure_settings(session: Session) -> None:
    for key, name, value, value_type, unit, category, description in DEFAULT_SETTINGS:
        setting_id = f"setting_{key}"
        if session.get(Setting, setting_id):
            continue
        session.add(
            Setting(
                id=setting_id,
                ownerId=settings.default_owner_id,
                settingKey=key,
                settingName=name,
                settingValue=value,
                valueType=value_type,
                unit=unit,
                category=category,
                description=description,
                isEditable=True,
            )
        )


def _ensure_alert_rules(session: Session) -> None:
    for code, name, category, metric, operator, threshold, unit, level, frequency in DEFAULT_ALERT_RULES:
        rule_id = f"rule_{code}"
        if session.get(AlertRule, rule_id):
            continue
        session.add(
            AlertRule(
                id=rule_id,
                ownerId=settings.default_owner_id,
                ruleCode=code,
                ruleName=name,
                category=category,
                description=f"内置规则：{name}",
                metricKey=metric,
                operator=operator,
                thresholdValue=threshold,
                thresholdUnit=unit,
                alertLevel=level,
                checkFrequency=frequency,
                repeatIntervalDays=1,
                isEnabled=True,
                isEditable=True,
                isBuiltIn=True,
            )
        )


def _ensure_data_sources(session: Session) -> None:
    existing = session.exec(select(DataSource)).first()
    if existing:
        return
    session.add(
        DataSource(
            id="ds_akshare",
            ownerId=settings.default_owner_id,
            sourceType="akshare",
            sourceName="AKShare",
            priority=1,
            isEnabled=True,
            supportedMarkets="CN_FUND,CN_ETF,CN_STOCK",
            healthStatus="unconfigured",
        )
    )
    session.add(
        DataSource(
            id="ds_manual",
            ownerId=settings.default_owner_id,
            sourceType="manual",
            sourceName="手动补录",
            priority=99,
            isEnabled=True,
            supportedMarkets="cash,fixed_income,equity,debt",
            healthStatus="normal",
        )
    )
