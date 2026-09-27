"""Frozen SQLite 1.4.0 schema captured from the current database, without data."""

import sqlite3

from alembic import op
from sqlmodel import Session

from app.db.init_db import seed_defaults


revision = "baseline_1_4_0"
down_revision = None
branch_labels = None
depends_on = None

BASELINE_SQL = r"""CREATE TABLE schema_migrations (
	id VARCHAR NOT NULL,
	version VARCHAR NOT NULL,
	description VARCHAR,
	"appliedAt" DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX ix_schema_migrations_version ON schema_migrations (version);
CREATE TABLE settings (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"settingKey" VARCHAR NOT NULL,
	"settingName" VARCHAR NOT NULL,
	"settingValue" VARCHAR NOT NULL,
	"valueType" VARCHAR NOT NULL,
	unit VARCHAR,
	category VARCHAR NOT NULL,
	description TEXT,
	"isEditable" BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_settings_ownerId" ON settings ("ownerId");
CREATE INDEX "ix_settings_settingKey" ON settings ("settingKey");
CREATE TABLE alert_rules (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"ruleCode" VARCHAR NOT NULL,
	"ruleName" VARCHAR NOT NULL,
	category VARCHAR NOT NULL,
	description TEXT,
	"metricKey" VARCHAR NOT NULL,
	operator VARCHAR NOT NULL,
	"thresholdValue" VARCHAR NOT NULL,
	"thresholdUnit" VARCHAR,
	"alertLevel" VARCHAR NOT NULL,
	"checkFrequency" VARCHAR NOT NULL,
	"repeatIntervalDays" INTEGER,
	"isEnabled" BOOLEAN NOT NULL,
	"isEditable" BOOLEAN NOT NULL,
	"isBuiltIn" BOOLEAN NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_alert_rules_ruleCode" ON alert_rules ("ruleCode");
CREATE INDEX "ix_alert_rules_ownerId" ON alert_rules ("ownerId");
CREATE TABLE assets (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	"assetType" VARCHAR NOT NULL,
	"subType" VARCHAR,
	platform VARCHAR NOT NULL,
	currency VARCHAR NOT NULL,
	"currentValue" NUMERIC(18, 4) NOT NULL,
	"costAmount" NUMERIC(18, 4),
	"principalAmount" NUMERIC(18, 4),
	"productCode" VARCHAR,
	market VARCHAR,
	"holdingShare" NUMERIC(18, 6),
	"latestPrice" NUMERIC(18, 6),
	"priceDate" DATE,
	"dailyChangePct" NUMERIC(10, 4),
	"expectedReturnRate" NUMERIC(10, 4),
	"startDate" DATE,
	"maturityDate" DATE,
	"liquidityLevel" VARCHAR,
	"repaymentDate" DATE,
	"interestRate" NUMERIC(10, 4),
	"isDca" BOOLEAN NOT NULL,
	"dcaAmount" NUMERIC(18, 4),
	"dcaFrequency" VARCHAR,
	"dcaDay" VARCHAR,
	"dcaNextDate" DATE,
	"dcaStatus" VARCHAR,
	"targetTag" VARCHAR,
	note TEXT,
	"assetStatus" VARCHAR NOT NULL, dataSourceType VARCHAR, dataStatus VARCHAR NOT NULL DEFAULT 'missing', priceErrorMessage TEXT, holdingGain NUMERIC(18, 4), holdingCostPrice NUMERIC(18, 6), cumulativeGain NUMERIC(18, 4), dailyIncomeAmount NUMERIC(18, 4), entryDate DATE, cumulativeNetBasis NUMERIC(18, 4),
	PRIMARY KEY (id)
);
CREATE INDEX "ix_assets_ownerId" ON assets ("ownerId");
CREATE INDEX "ix_assets_assetType" ON assets ("assetType");
CREATE INDEX "ix_assets_productCode" ON assets ("productCode");
CREATE TABLE transactions (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"assetId" VARCHAR NOT NULL,
	"transactionType" VARCHAR NOT NULL,
	amount NUMERIC(18, 4) NOT NULL,
	share NUMERIC(18, 6),
	price NUMERIC(18, 6),
	"transactionDate" DATE NOT NULL,
	source VARCHAR NOT NULL,
	note TEXT, relatedAssetId VARCHAR, relatedTransactionId VARCHAR, feeAmount NUMERIC(18, 4), feeRate NUMERIC(10, 6), tradeTiming VARCHAR,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_transactions_assetId" ON transactions ("assetId");
CREATE INDEX "ix_transactions_ownerId" ON transactions ("ownerId");
CREATE TABLE price_records (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	id VARCHAR NOT NULL,
	"assetId" VARCHAR,
	"productCode" VARCHAR NOT NULL,
	market VARCHAR,
	"priceDate" DATE NOT NULL,
	price NUMERIC(18, 6) NOT NULL,
	"accumulatedNetValue" NUMERIC(18, 6),
	"dailyChangePct" NUMERIC(10, 4),
	"sourceType" VARCHAR NOT NULL,
	"sourceName" VARCHAR,
	"fetchedAt" DATETIME NOT NULL,
	"dataStatus" VARCHAR NOT NULL,
	"isValid" BOOLEAN NOT NULL,
	"errorMessage" TEXT, dailyIncomeAmount NUMERIC(18, 4),
	PRIMARY KEY (id)
);
CREATE INDEX "ix_price_records_ownerId" ON price_records ("ownerId");
CREATE INDEX "ix_price_records_assetId" ON price_records ("assetId");
CREATE INDEX "ix_price_records_productCode" ON price_records ("productCode");
CREATE INDEX "ix_price_records_priceDate" ON price_records ("priceDate");
CREATE TABLE alert_records (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"ruleId" VARCHAR NOT NULL,
	"ruleCode" VARCHAR NOT NULL,
	"alertLevel" VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	description TEXT,
	"targetAssetId" VARCHAR,
	"targetAssetName" VARCHAR,
	"currentValue" VARCHAR,
	"thresholdValue" VARCHAR,
	unit VARCHAR,
	reason TEXT NOT NULL,
	"aiExplanation" TEXT,
	status VARCHAR NOT NULL,
	"triggeredAt" DATETIME NOT NULL,
	"priceDate" DATE,
	"dataSourceType" VARCHAR,
	"dataStatus" VARCHAR,
	"resolvedAt" DATETIME,
	"userActionNote" TEXT,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_alert_records_ruleCode" ON alert_records ("ruleCode");
CREATE INDEX "ix_alert_records_ruleId" ON alert_records ("ruleId");
CREATE INDEX "ix_alert_records_targetAssetId" ON alert_records ("targetAssetId");
CREATE INDEX "ix_alert_records_ownerId" ON alert_records ("ownerId");
CREATE TABLE daily_snapshots (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	id VARCHAR NOT NULL,
	"snapshotDate" DATE NOT NULL,
	"totalAsset" NUMERIC(18, 4) NOT NULL,
	"totalDebt" NUMERIC(18, 4) NOT NULL,
	"netAsset" NUMERIC(18, 4) NOT NULL,
	"cashValue" NUMERIC(18, 4) NOT NULL,
	"fixedIncomeValue" NUMERIC(18, 4) NOT NULL,
	"equityValue" NUMERIC(18, 4) NOT NULL,
	"debtValue" NUMERIC(18, 4) NOT NULL,
	"investmentValue" NUMERIC(18, 4),
	"cashRatio" NUMERIC(10, 4),
	"fixedIncomeRatio" NUMERIC(10, 4),
	"equityRatio" NUMERIC(10, 4),
	"debtRatio" NUMERIC(10, 4),
	"portfolioDrawdownPct" NUMERIC(10, 4),
	"dataStatus" VARCHAR NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_daily_snapshots_ownerId" ON daily_snapshots ("ownerId");
CREATE INDEX "ix_daily_snapshots_snapshotDate" ON daily_snapshots ("snapshotDate");
CREATE TABLE monthly_reviews (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"reviewMonth" VARCHAR NOT NULL,
	"startSnapshotId" VARCHAR,
	"endSnapshotId" VARCHAR,
	"startNetAsset" NUMERIC(18, 4),
	"endNetAsset" NUMERIC(18, 4) NOT NULL,
	"netAssetChange" NUMERIC(18, 4),
	"investmentReturn" NUMERIC(18, 4),
	"newContribution" NUMERIC(18, 4),
	"maxDrawdownPct" NUMERIC(10, 4),
	"summaryText" TEXT NOT NULL,
	"riskReviewText" TEXT,
	"dcaReviewText" TEXT,
	"nextMonthFocusText" TEXT,
	"dataCompletenessStatus" VARCHAR NOT NULL,
	"generatedAt" DATETIME NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_monthly_reviews_reviewMonth" ON monthly_reviews ("reviewMonth");
CREATE INDEX "ix_monthly_reviews_ownerId" ON monthly_reviews ("ownerId");
CREATE TABLE data_sources (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	"updatedAt" DATETIME NOT NULL,
	id VARCHAR NOT NULL,
	"sourceType" VARCHAR NOT NULL,
	"sourceName" VARCHAR NOT NULL,
	priority INTEGER NOT NULL,
	"isEnabled" BOOLEAN NOT NULL,
	"baseUrl" VARCHAR,
	"tokenEnvKey" VARCHAR,
	"supportedMarkets" TEXT,
	"lastSuccessAt" DATETIME,
	"lastFailedAt" DATETIME,
	"lastErrorMessage" TEXT,
	"healthStatus" VARCHAR NOT NULL,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_data_sources_ownerId" ON data_sources ("ownerId");
CREATE INDEX "ix_data_sources_sourceType" ON data_sources ("sourceType");
CREATE TABLE task_logs (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	id VARCHAR NOT NULL,
	"taskType" VARCHAR NOT NULL,
	"taskName" VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	"startedAt" DATETIME NOT NULL,
	"finishedAt" DATETIME,
	"durationMs" INTEGER,
	"successCount" INTEGER,
	"failedCount" INTEGER,
	"skippedCount" INTEGER,
	message TEXT,
	"errorMessage" TEXT,
	"nextRunAt" DATETIME,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_task_logs_ownerId" ON task_logs ("ownerId");
CREATE INDEX "ix_task_logs_taskType" ON task_logs ("taskType");
CREATE TABLE backups (
	"createdAt" DATETIME NOT NULL,
	"ownerId" VARCHAR NOT NULL,
	id VARCHAR NOT NULL,
	"backupType" VARCHAR NOT NULL,
	"fileName" VARCHAR NOT NULL,
	"filePath" VARCHAR NOT NULL,
	"fileSizeBytes" INTEGER,
	"dataVersion" VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	"errorMessage" TEXT,
	PRIMARY KEY (id)
);
CREATE INDEX "ix_backups_ownerId" ON backups ("ownerId");
"""


def upgrade() -> None:
    statement = ""
    for line in BASELINE_SQL.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            op.execute(statement)
            statement = ""
    if statement.strip():
        raise RuntimeError("Incomplete baseline SQL statement")
    with Session(op.get_bind()) as session:
        seed_defaults(session)
        session.commit()


def downgrade() -> None:
    raise RuntimeError("Baseline downgrade is destructive; restore a verified backup instead")
