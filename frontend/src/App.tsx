import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import {
  api,
  type AlertRecord,
  type AlertRule,
  type Asset,
  type AssetPayload,
  type AssetType,
  type BenchmarkHistory,
  type BackupRecord,
  type ConversionPayload,
  type DashboardSummary,
  type DataSource,
  type HealthResponse,
  type MonthlyReview,
  type PriceRecord,
  type ScreenshotParseResult,
  type Setting,
  type TaskLog,
  type TaskStatus,
  type TransactionPayload,
  type TransactionRecord,
} from "./api/client";

type PageKey = "today" | "assets" | "alerts" | "reviews" | "settings";
type AssetTabKey = "all" | AssetType;
type ConnectionState =
  | { status: "checking" }
  | { status: "connected"; data: HealthResponse }
  | { status: "failed"; message: string };

type AssetSummaryItem = {
  label: string;
  value: string;
  isAmount?: boolean;
};

type AssetDraft = {
  name: string;
  assetType: AssetType;
  subType: string;
  platform: string;
  currentValue: string;
  costAmount: string;
  holdingCostPrice: string;
  holdingGain: string;
  cumulativeGain: string;
  principalAmount: string;
  productCode: string;
  market: string;
  holdingShare: string;
  latestPrice: string;
  priceDate: string;
  dailyChangePct: string;
  dailyIncomeAmount: string;
  dataSourceType: string;
  dataStatus: string;
  expectedReturnRate: string;
  entryDate: string;
  maturityDate: string;
  liquidityLevel: string;
  repaymentDate: string;
  interestRate: string;
  targetTag: string;
  note: string;
  isDca: boolean;
  dcaAmount: string;
  dcaFrequency: string;
  dcaDay: string;
  dcaNextDate: string;
};

type TransactionDraft = {
  mode: "buy" | "sell" | "convert";
  targetAssetId: string;
  transactionDate: string;
  amount: string;
  share: string;
  price: string;
  feeRate: string;
  tradeTiming: "before_15" | "after_15";
  inAmount: string;
  inShare: string;
  inPrice: string;
  feeAmount: string;
  note: string;
};

type TransactionImportDraft = {
  transactionType: "buy" | "sell";
  transactionDate: string;
  tradeTiming: "before_15" | "after_15";
  amount?: string;
  share?: string;
  feeAmount?: string;
  feeRate?: string;
  note?: string;
};

type AssetImportDraft = {
  assetType: AssetType;
  name: string;
  platform: string;
  productCode: string;
  currentValue: string;
  holdingShare: string;
  holdingCostPrice?: string;
  holdingGain?: string;
  cumulativeGain?: string;
  cumulativeNetBasis?: string;
  latestPrice?: string;
  priceDate?: string;
  market?: string;
};

type AppData = {
  dashboard?: DashboardSummary;
  assets: Asset[];
  alerts: AlertRecord[];
  reviews: MonthlyReview[];
  settings: Setting[];
  rules: AlertRule[];
  dataSources: DataSource[];
  taskStatuses: TaskStatus[];
  taskLogs: TaskLog[];
  backups: BackupRecord[];
};

const navItems: Array<{ key: PageKey; label: string }> = [
  { key: "today", label: "今日" },
  { key: "assets", label: "资产" },
  { key: "alerts", label: "提醒" },
  { key: "reviews", label: "复盘" },
  { key: "settings", label: "设置" },
];

const AMOUNT_VISIBLE_STORAGE_KEY = "asset_manager_amount_visible";
const MASKED_AMOUNT = "••••";

const assetTypeLabels: Record<AssetType, string> = {
  cash: "现金",
  fixed_income: "固收",
  equity: "权益",
  debt: "负债",
};

const assetTabs: Array<{ key: AssetTabKey; label: string }> = [
  { key: "all", label: "全部" },
  { key: "cash", label: "现金" },
  { key: "fixed_income", label: "固收" },
  { key: "equity", label: "权益" },
  { key: "debt", label: "负债" },
];

const platformOptions = ["支付宝", "微信理财通", "天天基金", "招商银行", "工商银行", "建设银行", "中国银行", "农业银行", "京东金融", "券商账户", "手动录入"];

const subtypeOptions: Record<AssetType, string[]> = {
  cash: ["活期现金", "货币基金", "现金管理", "备用金"],
  fixed_income: ["银行存款", "银行理财", "债券基金", "国债逆回购", "大额存单"],
  equity: ["混合基金", "股票基金", "指数基金", "债券基金", "黄金基金", "QDII", "ETF联接", "LOF", "A股股票", "港股股票", "美股股票", "股票账户"],
  debt: ["信用卡", "消费贷", "房贷", "车贷", "其他负债"],
};

const equityStockSubTypes = new Set(["A股股票", "港股股票", "美股股票"]);
const stockMarketOptions = ["CN_A_SH", "CN_A_SZ", "HK", "US", "北交所"];

const dcaFrequencyOptions = [
  { value: "daily", label: "每日" },
  { value: "weekly", label: "每周" },
  { value: "biweekly", label: "每两周" },
  { value: "monthly", label: "每月" },
];

const benchmarkOptions = [
  { value: "hs300", label: "沪深 300" },
  { value: "zz500", label: "中证 500" },
  { value: "sse", label: "上证指数" },
  { value: "szse", label: "深证成指" },
];

const weekDayOptions = [
  { value: "1", label: "周一" },
  { value: "2", label: "周二" },
  { value: "3", label: "周三" },
  { value: "4", label: "周四" },
  { value: "5", label: "周五" },
  { value: "6", label: "周六" },
  { value: "7", label: "周日" },
];

const monthDayOptions = Array.from({ length: 28 }, (_, index) => ({
  value: String(index + 1),
  label: `${index + 1} 日`,
}));

const emptyDraft: AssetDraft = {
  name: "",
  assetType: "cash",
  subType: "",
  platform: "",
  currentValue: "",
  costAmount: "",
  holdingCostPrice: "",
  holdingGain: "",
  cumulativeGain: "",
  principalAmount: "",
  productCode: "",
  market: "",
  holdingShare: "",
  latestPrice: "",
  priceDate: "",
  dailyChangePct: "",
  dailyIncomeAmount: "",
  dataSourceType: "",
  dataStatus: "",
  expectedReturnRate: "",
  entryDate: new Date().toISOString().slice(0, 10),
  maturityDate: "",
  liquidityLevel: "",
  repaymentDate: "",
  interestRate: "",
  targetTag: "",
  note: "",
  isDca: false,
  dcaAmount: "",
  dcaFrequency: "",
  dcaDay: "",
  dcaNextDate: "",
};

export function App() {
  const [activePage, setActivePage] = useState<PageKey>("today");
  const [connection, setConnection] = useState<ConnectionState>({ status: "checking" });
  const [data, setData] = useState<AppData>({
    assets: [],
    alerts: [],
    reviews: [],
    settings: [],
    rules: [],
    dataSources: [],
    taskStatuses: [],
    taskLogs: [],
    backups: [],
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [formMode, setFormMode] = useState<"closed" | "choose" | "create" | "edit">("closed");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [detailRequestId, setDetailRequestId] = useState<string | null>(null);
  const [draft, setDraft] = useState<AssetDraft>(emptyDraft);
  const [isAmountVisible, setIsAmountVisible] = useState(() => readAmountVisibilityPreference());

  const selectedAsset = data.assets.find((asset) => asset.id === selectedAssetId) ?? null;

  function toggleAmountVisibility() {
    setIsAmountVisible((current) => {
      const next = !current;
      window.localStorage.setItem(AMOUNT_VISIBLE_STORAGE_KEY, next ? "true" : "false");
      return next;
    });
  }

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [health, dashboard, assets, alerts, reviews, settings, rules, dataSources, taskStatuses, taskLogs, backups] =
        await Promise.all([
          api.health(),
          api.dashboardSummary(),
          api.assets(true),
          api.alerts(),
          api.monthlyReviews(),
          api.settings(),
          api.alertRules(),
          api.dataSources(),
          api.taskStatuses(),
          api.taskLogs(),
          api.backups(),
        ]);
      setConnection({ status: "connected", data: health });
      setData({
        dashboard,
        assets: assets.items,
        alerts: alerts.items,
        reviews: reviews.items,
        settings: settings.items,
        rules: rules.items,
        dataSources: dataSources.items,
        taskStatuses: taskStatuses.items,
        taskLogs: taskLogs.items,
        backups: backups.items,
      });
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "无法连接后端服务";
      setConnection({ status: "failed", message });
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  function startCreate(assetType?: AssetType) {
    setSelectedAssetId(null);
    setDraft({ ...emptyDraft, assetType: assetType ?? "cash" });
    setFormMode(assetType ? "create" : "choose");
    setActivePage("assets");
  }

  function startCreateWithDraft(assetType: AssetType, patch: Partial<AssetDraft>) {
    setSelectedAssetId(null);
    setDraft(applyAutoSubType({ ...emptyDraft, assetType, ...patch }));
    setFormMode("create");
    setActivePage("assets");
  }

  async function createAssetsFromDrafts(items: AssetImportDraft[]) {
    setError(null);
    try {
      for (const item of items) {
        const draftForPayload = applyAutoSubType({
          ...emptyDraft,
          ...item,
          assetType: item.assetType,
          platform: item.platform || "待确认平台",
        });
        await api.createAsset(draftToPayload(draftForPayload));
      }
      setFormMode("closed");
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "批量新增资产失败");
      throw caught;
    }
  }

  function startEdit(asset: Asset) {
    setSelectedAssetId(asset.id);
    setDraft(assetToDraft(asset));
    setFormMode("edit");
    setActivePage("assets");
  }

  async function saveAsset(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const payload = draftToPayload(draft);
      if (formMode === "edit" && selectedAsset) {
        const updatedAsset = await api.updateAsset(selectedAsset.id, payload);
        setDetailRequestId(updatedAsset.id);
      } else {
        await api.createAsset(payload);
      }
      setFormMode("closed");
      setDraft(emptyDraft);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存资产失败");
    }
  }

  async function lookupFundForDraft(productCode?: string) {
    const code = (productCode ?? draft.productCode).trim();
    if (!code) return;
    setError(null);
    try {
      const info = await api.fundBasicInfo(code, {
        assetType: draft.assetType,
        assetSubType: draft.subType || undefined,
        market: draft.market || undefined,
      });
      setDraft((current) => {
        const assetType = (info.assetType || current.assetType) as AssetType;
        const name = info.name ?? current.name;
        const previousInferred = inferAssetSubType(current.name, current.assetType);
        const inferredSubType = info.subType || inferAssetSubType(name, assetType);
        const shouldAutoFillSubType = !current.subType || current.subType === previousInferred;
        const nextDraft: AssetDraft = {
          ...current,
          assetType,
          productCode: info.productCode,
          name,
          subType: shouldAutoFillSubType ? inferredSubType : current.subType,
          market: info.market ?? current.market,
          dataSourceType: info.sourceType ?? current.dataSourceType,
          dataStatus: info.dataStatus ?? current.dataStatus,
        };
        if (assetType !== "cash") {
          nextDraft.latestPrice = info.latestPrice ?? current.latestPrice;
          nextDraft.priceDate = info.priceDate ?? current.priceDate;
          nextDraft.dailyChangePct = info.dailyChangePct ?? current.dailyChangePct;
        }
        return nextDraft;
      });
      if (info.errorMessage && info.dataStatus !== "valid") {
        setError(sanitizeTechnicalMessage(info.errorMessage));
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "产品信息查询失败");
    }
  }

  async function deactivateSelected() {
    if (!selectedAsset) return;
    await deactivateAsset(selectedAsset);
  }

  async function deactivateAsset(asset: Asset) {
    setError(null);
    try {
      await api.deactivateAsset(asset.id);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "停用资产失败");
    }
  }

  async function deleteAsset(asset: Asset) {
    const confirmed = window.confirm(`确定删除资产「${asset.name}」吗？删除后会同时移除该资产的交易记录、价格记录和提醒记录。`);
    if (!confirmed) return false;
    setError(null);
    try {
      await api.deleteAsset(asset.id);
      if (selectedAssetId === asset.id) {
        setSelectedAssetId(null);
      }
      await loadData();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除资产失败");
      return false;
    }
  }

  async function updateSelectedPrice() {
    if (!selectedAsset) return;
    setError(null);
    try {
      await api.updateAssetPrice(selectedAsset.id);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新行情失败");
      await loadData();
    }
  }

  async function runPriceUpdate() {
    setError(null);
    try {
      await api.runPriceUpdate();
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "行情更新失败");
      await loadData();
    }
  }

  async function manualPrice(assetId: string, payload: { priceDate: string; price: number; currentValue?: number; dailyChangePct?: number; dailyIncomeAmount?: number }) {
    setError(null);
    try {
      await api.manualPrice(assetId, payload);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "手动补录失败");
    }
  }

  async function createTransaction(assetId: string, payload: TransactionPayload) {
    setError(null);
    try {
      await api.createAssetTransaction(assetId, payload);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存交易记录失败");
      throw caught;
    }
  }

  async function createConversion(assetId: string, payload: ConversionPayload) {
    setError(null);
    try {
      await api.createAssetConversion(assetId, payload);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存转换记录失败");
      throw caught;
    }
  }

  async function runTask(taskType: string) {
    setError(null);
    try {
      await api.runTask(taskType);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "任务运行失败");
      await loadData();
    }
  }

  async function updateSetting(key: string, value: string) {
    setError(null);
    try {
      await api.updateSetting(key, value);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存设置失败");
    }
  }

  async function updateRule(rule: AlertRule, patch: Partial<AlertRule>) {
    setError(null);
    try {
      await api.updateAlertRule(rule.ruleCode, patch);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存规则失败");
    }
  }

  async function generateMonthlyReview() {
    setError(null);
    try {
      await api.generateMonthlyReview();
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成复盘失败");
    }
  }

  async function exportData() {
    setError(null);
    try {
      const payload = await api.exportData();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `asset-manager-export-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导出失败");
    }
  }

  async function importData(file: File) {
    setError(null);
    try {
      const text = await file.text();
      const payload = JSON.parse(text) as Record<string, unknown>;
      const confirmed = window.confirm("导入会覆盖当前 SQLite 中的资产、设置、提醒、快照、日志和备份记录。是否继续？");
      if (!confirmed) return;
      await api.importData(payload, true);
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入失败");
    }
  }

  async function runManualBackup() {
    setError(null);
    try {
      await api.runBackup();
      await loadData();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "手动备份失败");
    }
  }

  return (
    <main className="app-layout">
      <aside className="sidebar" aria-label="主导航">
        <div className="sidebar-panel">
          <div className="profile-header">
            <div className="brand-avatar" aria-hidden="true" />
            <div>
              <p className="caption">本地优先</p>
              <h1>资产管理</h1>
              <p className="availability">V1.5 数据闭环</p>
            </div>
          </div>

          <nav className="nav-list">
            {navItems.map((item) => (
              <button
                className={`nav-item ${activePage === item.key ? "is-active" : ""}`}
                key={item.key}
                onClick={() => setActivePage(item.key)}
                type="button"
              >
                <span className="nav-dot" aria-hidden="true" />
                {item.label}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <section className="main">
        <header className="topbar">
          <div>
            <p className="caption">{activePage === "assets" ? "资产分类" : "阶段 6"}</p>
            {activePage === "assets" ? null : <h2>{navItems.find((item) => item.key === activePage)?.label}</h2>}
          </div>
          <div className="search" aria-label="当前状态">
            <span className="search-dot" aria-hidden="true" />
            前端通过 API 读写 SQLite，页面刷新后数据仍保留
          </div>
          <StatusPill connection={connection} />
        </header>

        {error ? <div className="error-banner">{error}</div> : null}
        {isLoading ? <div className="dashboard-card">正在加载真实数据...</div> : null}

        {!isLoading && activePage === "today" ? (
          <TodayPage
            summary={data.dashboard}
            assets={data.assets}
            isAmountVisible={isAmountVisible}
            onCreate={() => startCreate()}
            onToggleAmountVisibility={toggleAmountVisibility}
          />
        ) : null}
        {!isLoading && activePage === "assets" ? (
          <AssetsPage
            assets={data.assets}
            selectedAsset={selectedAsset}
            isAmountVisible={isAmountVisible}
            formMode={formMode}
            draft={draft}
            onChooseType={(assetType) => startCreate(assetType)}
            onUseParsedDraft={startCreateWithDraft}
            onCreateParsedAssets={createAssetsFromDrafts}
            onStartCreate={() => startCreate()}
            onSelect={(asset) => {
              setSelectedAssetId(asset.id);
              setFormMode("closed");
            }}
            onEdit={startEdit}
            onCancelForm={() => setFormMode("closed")}
            onDraftChange={setDraft}
            onSave={saveAsset}
            onLookupFund={lookupFundForDraft}
            onDeactivate={deactivateSelected}
            onDeactivateAsset={deactivateAsset}
            onDeleteAsset={deleteAsset}
            onToggleAmountVisibility={toggleAmountVisibility}
            onUpdatePrice={updateSelectedPrice}
            onRunPriceUpdate={runPriceUpdate}
            onManualPrice={manualPrice}
            onCreateTransaction={createTransaction}
            onCreateConversion={createConversion}
            onDataChanged={loadData}
            taskStatuses={data.taskStatuses}
            detailRequestId={detailRequestId}
            onDetailRequestHandled={() => setDetailRequestId(null)}
          />
        ) : null}
        {!isLoading && activePage === "alerts" ? <AlertsPage alerts={data.alerts} /> : null}
        {!isLoading && activePage === "reviews" ? <ReviewsPage reviews={data.reviews} onGenerate={generateMonthlyReview} /> : null}
        {!isLoading && activePage === "settings" ? (
          <SettingsPage
            settings={data.settings}
            rules={data.rules}
            dataSources={data.dataSources}
            taskStatuses={data.taskStatuses}
            taskLogs={data.taskLogs}
            backups={data.backups}
            onSettingChange={updateSetting}
            onRuleChange={updateRule}
            onRunTask={runTask}
            onExportData={exportData}
            onImportData={importData}
            onRunBackup={runManualBackup}
          />
        ) : null}
      </section>
    </main>
  );
}

function TodayPage({
  summary,
  assets,
  isAmountVisible,
  onCreate,
  onToggleAmountVisibility,
}: {
  summary?: DashboardSummary;
  assets: Asset[];
  isAmountVisible: boolean;
  onCreate: () => void;
  onToggleAmountVisibility: () => void;
}) {
  if (!summary || assets.length === 0) {
    return (
      <div className="content-panel single-panel">
        <section className="dashboard-card empty-state">
          <p className="caption">今日</p>
          <h3>还没有资产记录</h3>
          <p className="body">新增第一笔资产后，这里会从后端汇总净资产、资产结构和现金覆盖月数。</p>
          <button className="primary-button" onClick={onCreate} type="button">
            新增资产
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="content-panel">
      <section className="dashboard-card metric-card">
        <div className="metric-card-header">
          <p className="caption">净资产</p>
          <AmountPrivacyToggle isVisible={isAmountVisible} onToggle={onToggleAmountVisibility} />
        </div>
        <div className="metric-number">{formatAmount(formatMoney(summary.netAsset), isAmountVisible)}</div>
        <p className="body">
          总资产 {formatAmount(formatMoney(summary.totalAsset), isAmountVisible)}，总负债 {formatAmount(formatMoney(summary.totalDebt), isAmountVisible)}
        </p>
      </section>
      <section className="dashboard-card">
        <div className="card-header">
          <h3>资产结构</h3>
          <span className="count-badge">{summary.activeAssetCount}</span>
        </div>
        <div className="stack-list">
          {summary.categorySummary.map((item) => (
            <div className="row-item" key={item.assetType}>
              <span>{assetTypeLabels[item.assetType]}</span>
              <strong>{formatAmount(formatMoney(item.value), isAmountVisible)}</strong>
            </div>
          ))}
        </div>
      </section>
      <section className="dashboard-card">
        <h3>现金覆盖</h3>
        <p className="body">
          {summary.cashCoverageMonths ? `${Number(summary.cashCoverageMonths).toFixed(1)} 个月` : "缺少月必要支出设置"}
        </p>
      </section>
    </div>
  );
}

function AssetsPage(props: {
  assets: Asset[];
  selectedAsset: Asset | null;
  isAmountVisible: boolean;
  formMode: "closed" | "choose" | "create" | "edit";
  draft: AssetDraft;
  onChooseType: (assetType: AssetType) => void;
  onUseParsedDraft: (assetType: AssetType, patch: Partial<AssetDraft>) => void;
  onCreateParsedAssets: (items: AssetImportDraft[]) => Promise<void>;
  onStartCreate: () => void;
  onSelect: (asset: Asset) => void;
  onEdit: (asset: Asset) => void;
  onCancelForm: () => void;
  onDraftChange: (draft: AssetDraft) => void;
  onSave: (event: FormEvent) => void;
  onLookupFund: (productCode?: string) => Promise<void>;
  onDeactivate: () => void;
  onDeactivateAsset: (asset: Asset) => void;
  onDeleteAsset: (asset: Asset) => Promise<boolean>;
  onToggleAmountVisibility: () => void;
  onUpdatePrice: () => void;
  onRunPriceUpdate: () => Promise<void>;
  onManualPrice: (assetId: string, payload: { priceDate: string; price: number; currentValue?: number; dailyChangePct?: number; dailyIncomeAmount?: number }) => void;
  onCreateTransaction: (assetId: string, payload: TransactionPayload) => Promise<void>;
  onCreateConversion: (assetId: string, payload: ConversionPayload) => Promise<void>;
  onDataChanged: () => Promise<void>;
  taskStatuses: TaskStatus[];
  detailRequestId: string | null;
  onDetailRequestHandled: () => void;
}) {
  const [activeTab, setActiveTab] = useState<AssetTabKey>("all");
  const [manualAsset, setManualAsset] = useState<Asset | null>(null);
  const [transactionAsset, setTransactionAsset] = useState<Asset | null>(null);
  const [detailAsset, setDetailAsset] = useState<Asset | null>(null);
  const [detailPrices, setDetailPrices] = useState<PriceRecord[]>([]);
  const [detailTransactions, setDetailTransactions] = useState<TransactionRecord[]>([]);
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [isUpdatingPrices, setIsUpdatingPrices] = useState(false);
  const visibleAssets = props.assets.filter((asset) => activeTab === "all" || asset.assetType === activeTab);
  const activeAssets = visibleAssets.filter((asset) => asset.assetStatus !== "inactive");
  const totalAssetValue = props.assets
    .filter((asset) => asset.assetType !== "debt" && asset.assetStatus !== "inactive")
    .reduce((sum, asset) => sum + Number(asset.currentValue ?? 0), 0);
  const tabSummary = buildAssetTabSummary(activeTab, activeAssets, totalAssetValue);
  const priceUpdateSummary = buildPriceUpdateSummary(props.assets, props.taskStatuses);

  useEffect(() => {
    if (!detailAsset) return;
    const refreshedAsset = props.assets.find((asset) => asset.id === detailAsset.id);
    if (refreshedAsset && refreshedAsset !== detailAsset) {
      setDetailAsset(refreshedAsset);
    }
  }, [props.assets, detailAsset]);

  useEffect(() => {
    if (!detailAsset) {
      setDetailPrices([]);
      setDetailTransactions([]);
      return;
    }
    let ignore = false;
    setIsDetailLoading(true);
    Promise.all([api.assetPrices(detailAsset.id), api.assetTransactions(detailAsset.id)])
      .then(([priceResponse, transactionResponse]) => {
        if (!ignore) {
          setDetailPrices(priceResponse.items);
          setDetailTransactions(transactionResponse.items);
        }
      })
      .catch(() => {
        if (!ignore) {
          setDetailPrices([]);
          setDetailTransactions([]);
        }
      })
      .finally(() => {
        if (!ignore) setIsDetailLoading(false);
      });
    return () => {
      ignore = true;
    };
  }, [detailAsset]);

  useEffect(() => {
    if (!props.detailRequestId || props.formMode !== "closed") return;
    const requestedAsset = props.assets.find((asset) => asset.id === props.detailRequestId);
    if (!requestedAsset) return;
    props.onSelect(requestedAsset);
    setDetailAsset(requestedAsset);
    props.onDetailRequestHandled();
  }, [props.detailRequestId, props.formMode, props.assets, props.onSelect, props.onDetailRequestHandled]);

  return (
    <div className="asset-workbench">
      <section className="asset-toolbar">
        <div className="asset-tabs" role="tablist" aria-label="资产分类">
          {assetTabs.map((tab) => (
            <button
              className={`asset-tab ${activeTab === tab.key ? "is-active" : ""}`}
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="asset-toolbar-actions">
          <AmountPrivacyToggle isVisible={props.isAmountVisible} onToggle={props.onToggleAmountVisibility} />
          <button className="primary-button compact" onClick={props.onStartCreate} type="button">
            新增资产
          </button>
        </div>
      </section>

      <section className="price-update-strip">
        <div className="price-update-title">
          <strong>AKShare 行情</strong>
          <span>{priceUpdateSummary.statusText}</span>
        </div>
        <div className="price-update-meta">
          <span>最近运行：{priceUpdateSummary.lastRunAt}</span>
          <span>最新价格日期：{priceUpdateSummary.latestPriceDate}</span>
          <span>最近结果：{priceUpdateSummary.lastResult}</span>
        </div>
        <button
          className="secondary-button compact"
          disabled={isUpdatingPrices}
          onClick={async () => {
            setIsUpdatingPrices(true);
            try {
              await props.onRunPriceUpdate();
            } finally {
              setIsUpdatingPrices(false);
            }
          }}
          type="button"
        >
          {isUpdatingPrices ? "更新中..." : "立即更新行情"}
        </button>
      </section>

      <section className="asset-summary-strip">
        {tabSummary.map((item) => (
          <div className="asset-summary-item" key={item.label}>
            <span>{item.label}</span>
            <strong>{item.isAmount ? formatAmount(item.value, props.isAmountVisible) : item.value}</strong>
          </div>
        ))}
      </section>

      <section className="dashboard-card asset-table-card">
        {visibleAssets.length === 0 ? (
          <EmptyBlock title="暂无资产" body="这里不会加载示例数据。新增资产后会直接写入 SQLite。" />
        ) : (
          <div className="table-wrap asset-table-wrap">
            <table className="asset-grid-table">
              <thead>
                <tr>
                  {assetColumns(activeTab).map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {visibleAssets.map((asset) => (
                  <tr className={asset.assetStatus === "inactive" ? "is-muted" : ""} key={asset.id}>
                    {assetCells(asset, activeTab, props.isAmountVisible, () => {
                      props.onSelect(asset);
                      setDetailAsset(asset);
                    }).map((cell, index) => (
                      <td key={index}>{cell}</td>
                    ))}
                    <td>
                      <div className="row-actions">
                        <button
                          className="text-button"
                          onClick={() => {
                            props.onSelect(asset);
                            setDetailAsset(asset);
                          }}
                          type="button"
                        >
                          详情
                        </button>
                        {canUsePriceRecords(asset) ? (
                          <button
                            className="text-button"
                            onClick={() => {
                              props.onSelect(asset);
                              setManualAsset(asset);
                            }}
                            type="button"
                          >
                            补录
                          </button>
                        ) : null}
                        <button className="text-button" onClick={() => props.onEdit(asset)} type="button">
                          编辑
                        </button>
                        <button
                          className="text-button danger-text"
                          disabled={asset.assetStatus === "inactive"}
                          onClick={() => props.onDeactivateAsset(asset)}
                          type="button"
                        >
                          停用
                        </button>
                        <button
                          className="text-button danger-text"
                          onClick={async () => {
                            const deleted = await props.onDeleteAsset(asset);
                            if (deleted && detailAsset?.id === asset.id) {
                              setDetailAsset(null);
                            }
                          }}
                          type="button"
                        >
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {props.formMode === "choose" ? (
        <ModalFrame title="新增资产" onClose={props.onCancelForm}>
          <CreateAssetEntry
            onChooseType={props.onChooseType}
            onUseParsedDraft={props.onUseParsedDraft}
            onCreateParsedAssets={props.onCreateParsedAssets}
          />
        </ModalFrame>
      ) : null}

      {props.formMode === "create" || props.formMode === "edit" ? (
        <DrawerFrame title={props.formMode === "edit" ? "编辑资产" : `新增${assetTypeLabels[props.draft.assetType]}`} onClose={props.onCancelForm}>
          <AssetForm
            draft={props.draft}
            mode={props.formMode}
            onChange={props.onDraftChange}
            onCancel={props.onCancelForm}
            onSave={props.onSave}
            onLookupFund={props.onLookupFund}
          />
        </DrawerFrame>
      ) : null}

      {manualAsset ? (
        <DrawerFrame title={`补录价格 · ${manualAsset.name}`} onClose={() => setManualAsset(null)}>
          <ManualPricePanel
            asset={manualAsset}
            onManualPrice={(assetId, payload) => {
              props.onManualPrice(assetId, payload);
              setManualAsset(null);
            }}
            onUpdatePrice={props.onUpdatePrice}
          />
        </DrawerFrame>
      ) : null}

      {transactionAsset ? (
        <DrawerFrame title={`记录交易 · ${transactionAsset.name}`} onClose={() => setTransactionAsset(null)}>
          <TransactionPanel
            asset={transactionAsset}
            assets={props.assets}
            onCreateTransaction={props.onCreateTransaction}
            onCreateConversion={props.onCreateConversion}
            onDone={() => {
              setTransactionAsset(null);
              setDetailAsset(transactionAsset);
            }}
          />
        </DrawerFrame>
      ) : null}

      {detailAsset ? (
        <ModalFrame title="持仓详情" onClose={() => setDetailAsset(null)} size="large">
          <AssetDetailPanel
            asset={detailAsset}
            isLoading={isDetailLoading}
            prices={detailPrices}
            transactions={detailTransactions}
            onEdit={() => {
              setDetailAsset(null);
              props.onEdit(detailAsset);
            }}
            onManual={() => {
              setDetailAsset(null);
              setManualAsset(detailAsset);
            }}
            onTransaction={() => {
              setDetailAsset(null);
              setTransactionAsset(detailAsset);
            }}
            onUpdateDcaAmount={async (transaction, amount) => {
              if (!detailAsset) return;
              await api.updateAssetTransaction(detailAsset.id, transaction.id, { amount });
              const [priceResponse, transactionResponse] = await Promise.all([
                api.assetPrices(detailAsset.id),
                api.assetTransactions(detailAsset.id),
              ]);
              setDetailPrices(priceResponse.items);
              setDetailTransactions(transactionResponse.items);
              await props.onDataChanged();
            }}
          />
        </ModalFrame>
      ) : null}
    </div>
  );
}

function AssetTypeChooser({ onChoose }: { onChoose: (assetType: AssetType) => void }) {
  return (
    <div>
      <div className="type-grid">
        {(Object.keys(assetTypeLabels) as AssetType[]).map((type) => (
          <button className="type-card" key={type} onClick={() => onChoose(type)} type="button">
            <strong>{assetTypeLabels[type]}</strong>
            <span>{typeDescription(type)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function CreateAssetEntry({
  onChooseType,
  onUseParsedDraft,
  onCreateParsedAssets,
}: {
  onChooseType: (assetType: AssetType) => void;
  onUseParsedDraft: (assetType: AssetType, patch: Partial<AssetDraft>) => void;
  onCreateParsedAssets: (items: AssetImportDraft[]) => Promise<void>;
}) {
  const [mode, setMode] = useState<"screenshot" | "manual">("screenshot");

  return (
    <div className="create-entry">
      <div className="mode-tabs" role="tablist" aria-label="录入方式">
        <button className={mode === "screenshot" ? "is-active" : ""} onClick={() => setMode("screenshot")} type="button">
          上传截图
        </button>
        <button className={mode === "manual" ? "is-active" : ""} onClick={() => setMode("manual")} type="button">
          手动录入
        </button>
      </div>
      {mode === "screenshot" ? (
        <ScreenshotAssetImporter onCreateParsedAssets={onCreateParsedAssets} onUseParsedDraft={onUseParsedDraft} />
      ) : (
        <AssetTypeChooser onChoose={onChooseType} />
      )}
    </div>
  );
}

function ScreenshotAssetImporter({
  onUseParsedDraft,
  onCreateParsedAssets,
}: {
  onUseParsedDraft: (assetType: AssetType, patch: Partial<AssetDraft>) => void;
  onCreateParsedAssets: (items: AssetImportDraft[]) => Promise<void>;
}) {
  const [result, setResult] = useState<ScreenshotParseResult | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [assetDrafts, setAssetDrafts] = useState<AssetImportDraft[]>([]);
  const [isAssetModalOpen, setIsAssetModalOpen] = useState(false);
  const [isSavingBatch, setIsSavingBatch] = useState(false);

  async function handleFile(file: File | null) {
    if (!file) return;
    setIsParsing(true);
    setError(null);
    setResult(null);
    try {
      const imageBase64 = await imageFileToOcrDataUrl(file);
      const nextResult = await api.parseAssetScreenshot({ fileName: file.name, imageBase64 });
      setResult(nextResult);
      const parsedAssets = normalizeAssetImportDrafts(nextResult.draft);
      setAssetDrafts(parsedAssets);
      if (parsedAssets.length > 0) {
        setIsAssetModalOpen(true);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "截图识别失败");
    } finally {
      setIsParsing(false);
    }
  }

  const hasDraft = result ? hasMeaningfulAssetDraft(result.draft) : false;

  function updateAssetDraft(index: number, patch: Partial<AssetImportDraft>) {
    setAssetDrafts((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  async function confirmAssetDrafts() {
    const invalidIndex = assetDrafts.findIndex((item) => !item.name || !item.platform || !item.currentValue || !item.holdingShare);
    const invalid = invalidIndex >= 0 ? assetDrafts[invalidIndex] : null;
    if (invalid) {
      const missing = [
        !invalid.name ? "名称" : "",
        !invalid.platform ? "平台" : "",
        !invalid.currentValue ? "当前金额" : "",
        !invalid.holdingShare ? "持有份额" : "",
      ].filter(Boolean);
      setError(`第 ${invalidIndex + 1} 条资产缺少：${missing.join("、")}。请在清单中补齐后再导入。`);
      return;
    }
    setIsSavingBatch(true);
    setError(null);
    try {
      await onCreateParsedAssets(assetDrafts);
      setAssetDrafts([]);
      setIsAssetModalOpen(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "批量新增资产失败");
    } finally {
      setIsSavingBatch(false);
    }
  }

  return (
    <div className="screenshot-importer">
      <div className="upload-panel">
        <strong>上传持仓截图</strong>
        <p>识别结果只用于预填权益资产表单，保存前需要你逐项确认。</p>
        <label className="primary-button file-button">
          选择截图
          <input
            accept="image/*"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              event.currentTarget.value = "";
              void handleFile(file);
            }}
            type="file"
          />
        </label>
      </div>
      {isParsing ? <div className="helper-box">正在压缩并识别截图，首次加载模型或长截图可能需要 1-2 分钟...</div> : null}
      {error ? <div className="error-banner compact-error">{error}</div> : null}
      {result ? (
        <div className="parse-result">
          <div className={`status-note ${result.status === "parsed" ? "is-ok" : "is-warn"}`}>
            {result.message}
          </div>
          {result.status !== "parsed" && result.rawText ? (
            <div className="helper-box">
              OCR 已返回文字，但暂未形成可导入资产清单。请展开下方“查看 OCR 原始文字”核对识别内容。
            </div>
          ) : null}
          {hasDraft ? (
            <>
              <KeyValuePreview data={result.draft} />
              {assetDrafts.length > 0 ? (
                <button className="primary-button" onClick={() => setIsAssetModalOpen(true)} type="button">
                  查看资产清单
                </button>
              ) : (
                <button
                  className="primary-button"
                  onClick={() => onUseParsedDraft("equity", normalizeDraftPatch(result.draft))}
                  type="button"
                >
                  使用识别结果继续确认
                </button>
              )}
            </>
          ) : (
            <>
              <div className="helper-box">
                未识别到可直接预填的资产字段。可以换一张更清晰的持仓页截图，或进入手动录入。
              </div>
              <button className="secondary-button" onClick={() => onUseParsedDraft("equity", { assetType: "equity" })} type="button">
                改为手动录入权益资产
              </button>
            </>
          )}
          {result.rawText ? <RawTextPreview text={result.rawText} /> : null}
        </div>
      ) : null}
      {assetDrafts.length > 0 && isAssetModalOpen ? (
        <ModalFrame title="确认批量资产" onClose={() => setIsAssetModalOpen(false)} size="large">
          <section className="transaction-import-modal">
            <p className="helper-note">识别结果不会自动入库，请确认每一项资产后再导入。</p>
            {error ? <div className="error-banner compact-error">{error}</div> : null}
            <div className="table-wrap import-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>名称</th>
                    <th>平台</th>
                    <th>代码</th>
                    <th>当前金额(元)</th>
                    <th>份额(份)</th>
                    <th>成本价(元/份)</th>
                    <th>持有收益(元)</th>
                    <th>累计收益(元)</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assetDrafts.map((item, index) => (
                    <tr key={`${item.productCode}-${index}`}>
                      <td><input className="table-input" value={item.name} onChange={(event) => updateAssetDraft(index, { name: event.target.value })} /></td>
                      <td><input className="table-input compact-input" value={item.platform} onChange={(event) => updateAssetDraft(index, { platform: event.target.value })} /></td>
                      <td><input className="table-input compact-input" value={item.productCode} onChange={(event) => updateAssetDraft(index, { productCode: event.target.value })} /></td>
                      <td><input className="table-input compact-input" value={item.currentValue} onChange={(event) => updateAssetDraft(index, { currentValue: event.target.value })} type="number" /></td>
                      <td><input className="table-input compact-input" value={item.holdingShare} onChange={(event) => updateAssetDraft(index, { holdingShare: event.target.value })} type="number" /></td>
                      <td><input className="table-input compact-input" value={item.holdingCostPrice ?? ""} onChange={(event) => updateAssetDraft(index, { holdingCostPrice: event.target.value })} type="number" /></td>
                      <td><input className="table-input compact-input" value={item.holdingGain ?? ""} onChange={(event) => updateAssetDraft(index, { holdingGain: event.target.value })} type="number" /></td>
                      <td><input className="table-input compact-input" value={item.cumulativeGain ?? ""} onChange={(event) => updateAssetDraft(index, { cumulativeGain: event.target.value })} type="number" /></td>
                      <td><button className="text-button danger-text" onClick={() => setAssetDrafts((current) => current.filter((_, itemIndex) => itemIndex !== index))} type="button">移除</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="form-actions">
              <button className="secondary-button" onClick={() => { setAssetDrafts([]); setIsAssetModalOpen(false); }} type="button">清空识别结果</button>
              <button className="primary-button" disabled={isSavingBatch} onClick={() => void confirmAssetDrafts()} type="button">
                {isSavingBatch ? "导入中..." : "确认导入资产"}
              </button>
            </div>
          </section>
        </ModalFrame>
      ) : null}
    </div>
  );
}

function KeyValuePreview({ data }: { data: Record<string, unknown> }) {
  const labels: Record<string, string> = {
    name: "名称",
    productCode: "基金代码",
    currentValue: "当前金额",
    holdingShare: "持有份额",
    holdingCostPrice: "持仓成本价",
    holdingGain: "持有收益",
    cumulativeGain: "累计收益",
    dailyIncomeAmount: "昨日收益",
    latestPrice: "最新净值",
    priceDate: "净值日期",
    market: "市场",
    dataStatus: "数据状态",
  };
  return (
    <div className="preview-grid">
      {Object.entries(data)
        .filter(([key]) => key in labels)
        .map(([key, value]) => (
          <div key={key}>
            <span>{labels[key]}</span>
            <strong>{String(value ?? "-")}</strong>
          </div>
        ))}
    </div>
  );
}

function RawTextPreview({ text }: { text: string }) {
  const preview = text.trim().slice(0, 800);
  if (!preview) return null;
  return (
    <details className="raw-text-preview">
      <summary>查看 OCR 原始文字</summary>
      <pre>{preview}{text.length > preview.length ? "\n..." : ""}</pre>
    </details>
  );
}

function ManualPricePanel({
  asset,
  onManualPrice,
  onUpdatePrice,
}: {
  asset: Asset;
  onManualPrice: (assetId: string, payload: { priceDate: string; price: number; currentValue?: number; dailyChangePct?: number; dailyIncomeAmount?: number }) => void;
  onUpdatePrice: () => void;
}) {
  const [manualDate, setManualDate] = useState(new Date().toISOString().slice(0, 10));
  const [manualPriceValue, setManualPriceValue] = useState("");
  const [manualCurrentValue, setManualCurrentValue] = useState(asset.currentValue ?? "");
  const [manualChangePct, setManualChangePct] = useState("");
  const [manualDailyIncome, setManualDailyIncome] = useState("");
  const isCash = asset.assetType === "cash";
  const priceLabel = isCash ? "年化收益率(%)" : asset.assetType === "fixed_income" ? "最新价格/净值" : isStockHoldingSubtype(asset.subType) ? "最新股价" : "最新净值/价格";
  const priceDateLabel = isCash ? "收益日期" : asset.assetType === "fixed_income" ? "价格/净值日期" : "价格日期";
  const changeLabel = isCash ? "收益率变化(百分点)" : "日涨跌幅";

  return (
    <form
      className="asset-form"
      onSubmit={(event) => {
        event.preventDefault();
        onManualPrice(asset.id, {
          priceDate: manualDate,
          price: Number(manualPriceValue),
          currentValue: manualCurrentValue ? Number(manualCurrentValue) : undefined,
          dailyChangePct: manualChangePct ? Number(manualChangePct) : undefined,
          dailyIncomeAmount: manualDailyIncome ? Number(manualDailyIncome) : undefined,
        });
        setManualPriceValue("");
        setManualChangePct("");
        setManualDailyIncome("");
      }}
    >
      <div className="detail-grid compact-detail">
        {isCash ? <div><dt>现金账户</dt><dd>{asset.name}</dd></div> : <div><dt>产品代码</dt><dd>{asset.productCode ?? "-"}</dd></div>}
        {isCash ? <div><dt>当前金额</dt><dd>{formatMoney(asset.currentValue)}</dd></div> : null}
        <div><dt>{priceLabel}</dt><dd>{isCash ? formatYieldRate(asset.latestPrice ?? asset.expectedReturnRate) : formatPrice(asset.latestPrice)}</dd></div>
        <div><dt>{priceDateLabel}</dt><dd>{asset.priceDate ?? "-"}</dd></div>
        <div><dt>数据状态</dt><dd>{asset.dataStatus}</dd></div>
      </div>
      {asset.priceErrorMessage ? <div className="error-banner">{sanitizeTechnicalMessage(asset.priceErrorMessage)}</div> : null}
      <div className="form-grid">
        <Field label={priceDateLabel} value={manualDate} onChange={setManualDate} type="date" required />
        <Field label={priceLabel} value={manualPriceValue} onChange={setManualPriceValue} type="number" required />
        {isCash ? <Field label="当前金额(元)" value={manualCurrentValue} onChange={setManualCurrentValue} type="number" /> : null}
        <Field label={changeLabel} value={manualChangePct} onChange={setManualChangePct} type="number" />
        <Field label="昨日收益金额" value={manualDailyIncome} onChange={setManualDailyIncome} type="number" />
      </div>
      <div className="form-actions">
        {asset.assetType === "equity" ? <button className="secondary-button" onClick={onUpdatePrice} type="button">AKShare 更新</button> : null}
        <button className="primary-button" type="submit">保存补录</button>
      </div>
    </form>
  );
}

function TransactionPanel({
  asset,
  assets,
  onCreateTransaction,
  onCreateConversion,
  onDone,
}: {
  asset: Asset;
  assets: Asset[];
  onCreateTransaction: (assetId: string, payload: TransactionPayload) => Promise<void>;
  onCreateConversion: (assetId: string, payload: ConversionPayload) => Promise<void>;
  onDone: () => void;
}) {
  const targetAssets = assets.filter((item) => item.id !== asset.id && item.assetStatus !== "inactive");
  const [draft, setDraft] = useState<TransactionDraft>({
    mode: "buy",
    targetAssetId: targetAssets[0]?.id ?? "",
    transactionDate: new Date().toISOString().slice(0, 10),
    amount: "",
    share: "",
    price: "",
    feeRate: "",
    tradeTiming: "before_15",
    inAmount: "",
    inShare: "",
    inPrice: "",
    feeAmount: "",
    note: "",
  });
  const [ocrMessage, setOcrMessage] = useState<string | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [importDrafts, setImportDrafts] = useState<TransactionImportDraft[]>([]);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const set = <K extends keyof TransactionDraft>(field: K, value: TransactionDraft[K]) =>
    setDraft((current) => ({ ...current, [field]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (draft.mode === "convert") {
      await onCreateConversion(asset.id, {
        targetAssetId: draft.targetAssetId,
        transactionDate: draft.transactionDate,
        outAmount: Number(draft.amount),
        outShare: optionalNumberValue(draft.share),
        outPrice: optionalNumberValue(draft.price),
        inAmount: optionalNumberValue(draft.inAmount),
        inShare: optionalNumberValue(draft.inShare),
        inPrice: optionalNumberValue(draft.inPrice),
        feeAmount: optionalNumberValue(draft.feeAmount),
        feeRate: optionalNumberValue(draft.feeRate),
        tradeTiming: draft.tradeTiming,
        source: "manual",
        note: optional(draft.note),
      });
      onDone();
      return;
    }
    await onCreateTransaction(asset.id, {
      transactionType: draft.mode,
      amount: optionalNumberValue(draft.amount),
      share: optionalNumberValue(draft.share),
      feeAmount: optionalNumberValue(draft.feeAmount),
      feeRate: optionalNumberValue(draft.feeRate),
      tradeTiming: draft.tradeTiming,
      transactionDate: draft.transactionDate,
      source: "manual",
      note: optional(draft.note),
    });
    onDone();
  }

  async function parseScreenshot(file: File) {
    setIsParsing(true);
    setOcrMessage(null);
    try {
      const imageBase64 = await imageFileToOcrDataUrl(file);
      const result = await api.parseAssetScreenshot({ fileName: file.name, imageBase64 });
      const parsedTransactions = normalizeTransactionImportDrafts(result.draft, draft);
      if (parsedTransactions.length > 0) {
        setImportDrafts(parsedTransactions);
        setIsImportModalOpen(true);
      } else {
        const patch = normalizeTransactionDraftPatch(result.draft);
        setDraft((current) => ({ ...current, ...patch }));
      }
      setOcrMessage(result.message);
    } catch (caught) {
      setOcrMessage(caught instanceof Error ? caught.message : "OCR 识别失败");
    } finally {
      setIsParsing(false);
    }
  }

  async function confirmImportDrafts() {
    const invalid = importDrafts.find((item) => !item.transactionDate || (item.transactionType === "buy" && !item.amount) || (item.transactionType === "sell" && !item.amount && !item.share));
    if (invalid) {
      setOcrMessage("请先补全交易日期，以及买入金额或卖出金额/份额，再确认导入。");
      return;
    }
    for (const item of importDrafts) {
      await onCreateTransaction(asset.id, {
        transactionType: item.transactionType,
        amount: optionalNumberValue(item.amount ?? ""),
        share: optionalNumberValue(item.share ?? ""),
        feeAmount: optionalNumberValue(item.feeAmount ?? ""),
        feeRate: optionalNumberValue(item.feeRate ?? ""),
        tradeTiming: item.tradeTiming,
        transactionDate: item.transactionDate,
        source: "ocr",
        note: item.note,
      });
    }
    setImportDrafts([]);
    setIsImportModalOpen(false);
    onDone();
  }

  function updateImportDraft(index: number, patch: Partial<TransactionImportDraft>) {
    setImportDrafts((current) => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)));
  }

  return (
    <>
    <form className="asset-form" onSubmit={submit}>
      <div className="segmented-control">
        {[
          ["buy", "买入"],
          ["sell", "卖出"],
          ["convert", "转换"],
        ].map(([key, label]) => (
          <button
            className={draft.mode === key ? "is-active" : ""}
            key={key}
            onClick={() => set("mode", key as TransactionDraft["mode"])}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>

      <label className="secondary-button file-button compact transaction-ocr-button">
        {isParsing ? "识别中..." : "上传截图识别"}
        <input
          accept="image/*"
          disabled={isParsing}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void parseScreenshot(file);
            event.target.value = "";
          }}
          type="file"
        />
      </label>
      {ocrMessage ? <div className="helper-note">{ocrMessage}</div> : null}
      {importDrafts.length > 0 ? (
        <div className="import-preview compact-import-preview">
          <div>
            <strong>已识别 {importDrafts.length} 条交易</strong>
            <p className="helper-note">请在独立确认清单中核对日期、方向和金额后再导入。</p>
          </div>
          <button className="secondary-button compact" onClick={() => setIsImportModalOpen(true)} type="button">查看清单</button>
        </div>
      ) : null}

      <div className="detail-grid compact-detail">
        <div><dt>资产</dt><dd>{asset.name}</dd></div>
        <div><dt>当前份额</dt><dd>{formatQuantity(asset.holdingShare)}</dd></div>
        <div><dt>当前金额</dt><dd>{formatMoney(asset.currentValue)}</dd></div>
        <div><dt>当前成本价</dt><dd>{formatPrice(getHoldingCostPrice(asset))}</dd></div>
      </div>

      <div className="form-grid">
        <Field label="交易日期" value={draft.transactionDate} onChange={(value) => set("transactionDate", value)} type="date" required />
        <label className="field">
          <span>交易时间</span>
          <select value={draft.tradeTiming} onChange={(event) => set("tradeTiming", event.target.value as TransactionDraft["tradeTiming"])}>
            <option value="before_15">15 点前</option>
            <option value="after_15">15 点后</option>
          </select>
        </label>
        {draft.mode === "convert" ? (
          <label className="field">
            <span>转入资产</span>
            <select value={draft.targetAssetId} onChange={(event) => set("targetAssetId", event.target.value)} required>
              {targetAssets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {assetTypeLabels[item.assetType]}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {draft.mode === "buy" ? (
          <Field label="买入金额" value={draft.amount} onChange={(value) => set("amount", value)} type="number" required />
        ) : null}
        {draft.mode === "sell" ? (
          <>
            <Field label="卖出份额" value={draft.share} onChange={(value) => set("share", value)} type="number" />
            <Field label="卖出金额" value={draft.amount} onChange={(value) => set("amount", value)} type="number" />
          </>
        ) : null}
        {draft.mode === "convert" ? (
          <>
            <Field label="转出金额" value={draft.amount} onChange={(value) => set("amount", value)} type="number" required />
            <Field label="转出份额" value={draft.share} onChange={(value) => set("share", value)} type="number" />
            <Field label="转出价格" value={draft.price} onChange={(value) => set("price", value)} type="number" />
          </>
        ) : null}
        {draft.mode === "convert" ? (
          <>
            <Field label="转入金额" value={draft.inAmount} onChange={(value) => set("inAmount", value)} type="number" />
            <Field label="转入份额" value={draft.inShare} onChange={(value) => set("inShare", value)} type="number" />
            <Field label="转入价格" value={draft.inPrice} onChange={(value) => set("inPrice", value)} type="number" />
          </>
        ) : null}
        <Field label="费用" value={draft.feeAmount} onChange={(value) => set("feeAmount", value)} type="number" />
        <Field label="费率 %" value={draft.feeRate} onChange={(value) => set("feeRate", value)} type="number" />
        <label className="field field-full">
          <span>备注</span>
          <textarea value={draft.note} onChange={(event) => set("note", event.target.value)} maxLength={500} />
        </label>
      </div>

      {draft.mode === "convert" && targetAssets.length === 0 ? (
        <div className="error-banner">没有可作为转入目标的其他资产，请先新增目标资产。</div>
      ) : null}
      <p className="body compact-body">
        这里仅记录已经发生的资金流水，用于持仓、收益和复盘计算；不提供交易建议或操作指令。
      </p>
      <div className="form-actions">
        <button className="primary-button" disabled={draft.mode === "convert" && targetAssets.length === 0} type="submit">
          保存交易记录
        </button>
      </div>
    </form>
    {importDrafts.length > 0 && isImportModalOpen ? (
      <ModalFrame title="确认批量交易记录" onClose={() => setIsImportModalOpen(false)} size="large">
        <section className="transaction-import-modal">
          <div className="section-title-row">
            <div>
              <h3>待确认交易清单</h3>
              <p className="helper-note">OCR 只做预填，保存前请逐条核对；确认后会写入当前资产的交易记录。</p>
            </div>
            <span className="count-badge">{importDrafts.length}</span>
          </div>
          <div className="table-wrap import-table-wrap">
            <table className="import-table">
              <thead><tr><th>方向</th><th>日期</th><th>时间</th><th>金额</th><th>份额</th><th>费用</th><th>费率%</th><th>操作</th></tr></thead>
              <tbody>
                {importDrafts.map((item, index) => (
                  <tr key={index}>
                    <td>
                      <select value={item.transactionType} onChange={(event) => updateImportDraft(index, { transactionType: event.target.value as "buy" | "sell" })}>
                        <option value="buy">买入</option>
                        <option value="sell">卖出</option>
                      </select>
                    </td>
                    <td><input className="table-input compact-input" value={item.transactionDate} onChange={(event) => updateImportDraft(index, { transactionDate: event.target.value })} type="date" /></td>
                    <td>
                      <select value={item.tradeTiming} onChange={(event) => updateImportDraft(index, { tradeTiming: event.target.value as "before_15" | "after_15" })}>
                        <option value="before_15">15点前</option>
                        <option value="after_15">15点后</option>
                      </select>
                    </td>
                    <td><input className="table-input compact-input" value={item.amount ?? ""} onChange={(event) => updateImportDraft(index, { amount: event.target.value })} type="number" /></td>
                    <td><input className="table-input compact-input" value={item.share ?? ""} onChange={(event) => updateImportDraft(index, { share: event.target.value })} type="number" /></td>
                    <td><input className="table-input compact-input" value={item.feeAmount ?? ""} onChange={(event) => updateImportDraft(index, { feeAmount: event.target.value })} type="number" /></td>
                    <td><input className="table-input compact-input" value={item.feeRate ?? ""} onChange={(event) => updateImportDraft(index, { feeRate: event.target.value })} type="number" /></td>
                    <td><button className="text-button danger-text" onClick={() => setImportDrafts((current) => current.filter((_, itemIndex) => itemIndex !== index))} type="button">移除</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-actions">
            <button className="secondary-button" onClick={() => { setImportDrafts([]); setIsImportModalOpen(false); }} type="button">清空识别结果</button>
            <button className="primary-button" onClick={() => void confirmImportDrafts()} type="button">确认导入</button>
          </div>
        </section>
      </ModalFrame>
    ) : null}
    </>
  );
}

function AssetDetailPanel({
  asset,
  prices,
  transactions,
  isLoading,
  onEdit,
  onManual,
  onTransaction,
  onUpdateDcaAmount,
}: {
  asset: Asset;
  prices: PriceRecord[];
  transactions: TransactionRecord[];
  isLoading: boolean;
  onEdit: () => void;
  onManual: () => void;
  onTransaction: () => void;
  onUpdateDcaAmount: (transaction: TransactionRecord, amount: number) => Promise<void>;
}) {
  const value = Number(asset.currentValue ?? 0);
  const cost = Number(asset.costAmount ?? asset.principalAmount ?? 0);
  const holdingGain = getHoldingGain(asset);
  const holdingCostBase = getHoldingCostBase(asset);
  const holdingGainRate = holdingCostBase > 0 && holdingGain !== null ? (holdingGain / holdingCostBase) * 100 : null;
  const cumulativeGain = getCumulativeGain(asset, transactions);
  const cumulativeGainBase = getCumulativeGainBase(asset, transactions);
  const cumulativeGainRate = cumulativeGainBase > 0 && cumulativeGain !== null ? (cumulativeGain / cumulativeGainBase) * 100 : null;
  const yesterdayIncome = estimateDailyIncome(asset, prices);
  const cashAsset = asset.assetType === "cash";
  const stockHolding = asset.assetType === "equity" && isStockHoldingSubtype(asset.subType);
  const stockAccount = asset.assetType === "equity" && isStockAccountSubtype(asset.subType);
  const shareLabel = stockHolding ? "持有股数(股)" : "份额(份)";
  const costPriceLabel = stockHolding ? "持仓成本价(元/股)" : "持仓成本价(元/份)";
  const latestPriceLabel = cashAsset ? "年化收益率(%)" : stockHolding ? "最新股价(元/股)" : "最新价格(元/份)";
  const [activeDetailTab, setActiveDetailTab] = useState<"income" | "rate" | "performance" | "estimate" | "records">("income");
  const [editingDca, setEditingDca] = useState<TransactionRecord | null>(null);
  const [dcaAmountDraft, setDcaAmountDraft] = useState("");
  const [dcaEditError, setDcaEditError] = useState<string | null>(null);
  const [isSavingDca, setIsSavingDca] = useState(false);

  async function saveDcaAmount() {
    if (!editingDca) return;
    const amount = Number(dcaAmountDraft);
    if (!Number.isFinite(amount) || amount <= 0) {
      setDcaEditError("定投金额必须大于 0");
      return;
    }
    setIsSavingDca(true);
    setDcaEditError(null);
    try {
      await onUpdateDcaAmount(editingDca, amount);
      setEditingDca(null);
      setDcaAmountDraft("");
    } catch (caught) {
      setDcaEditError(caught instanceof Error ? caught.message : "定投金额保存失败");
    } finally {
      setIsSavingDca(false);
    }
  }

  return (
    <div className="holding-detail">
      <section className="holding-hero">
        <div>
          <h3>{asset.name}</h3>
          <p className="body compact-body">
            {[asset.productCode, asset.subType ?? assetTypeLabels[asset.assetType], asset.platform].filter(Boolean).join(" · ")}
          </p>
        </div>
        <span className="tag">{asset.assetStatus}</span>
      </section>

      <section className="holding-amount">
        <span>{asset.assetType === "debt" ? "待还金额" : "金额 / 市值"}（元）</span>
        <strong>{formatMoney(value)}</strong>
      </section>

      <section className="holding-metrics">
        {cashAsset ? (
          <>
            <MetricBlock label="昨日收益(元)" value={formatSignedMoney(yesterdayIncome.value)} subValue={yesterdayIncome.source} />
            <MetricBlock label="年化收益率" value={formatYieldRate(asset.latestPrice ?? asset.expectedReturnRate)} subValue={asset.priceDate ?? "未补录"} />
            <MetricBlock label="累计收益(元)" value={formatSignedMoney(cumulativeGain)} subValue="来自补录/交易记录" />
          </>
        ) : (
          <>
            <MetricBlock
              label="昨日收益(元)"
              value={formatSignedMoney(yesterdayIncome.value)}
              subValue={`${formatPct(asset.dailyChangePct)} · ${yesterdayIncome.source}`}
            />
            <MetricBlock label="持有收益(元)" value={formatSignedMoney(holdingGain)} subValue={formatNullablePct(holdingGainRate)} />
            <MetricBlock label="累计收益(元)" value={formatSignedMoney(cumulativeGain)} subValue={formatNullablePct(cumulativeGainRate)} />
          </>
        )}
      </section>

      <section className="detail-section">
        <div className="section-title-row">
          <h3>持仓信息</h3>
          <div className="form-actions">
            <button className="secondary-button compact" onClick={onTransaction} type="button">记录交易</button>
            <button className="secondary-button compact" onClick={onEdit} type="button">编辑</button>
          </div>
        </div>
        <dl className="detail-grid compact-detail">
          <div><dt>类型</dt><dd>{assetTypeLabels[asset.assetType]}</dd></div>
          <div><dt>平台</dt><dd>{asset.platform}</dd></div>
          <div><dt>录入日期</dt><dd>{asset.entryDate ?? asset.createdAt.slice(0, 10)}</dd></div>
          {stockAccount || cashAsset ? null : <div><dt>{shareLabel}</dt><dd>{formatQuantity(asset.holdingShare)}</dd></div>}
          {stockAccount || cashAsset ? null : <div><dt>{costPriceLabel}</dt><dd>{formatPrice(getHoldingCostPrice(asset))}</dd></div>}
          {cashAsset ? null : <div><dt>累计投入本金(元)</dt><dd>{asset.costAmount ? formatMoney(asset.costAmount) : "-"}</dd></div>}
          {stockAccount ? null : <div>
            <dt>{latestPriceLabel}</dt>
            <dd className="inline-value-action">
              {cashAsset ? formatYieldRate(asset.latestPrice ?? asset.expectedReturnRate) : formatPrice(asset.latestPrice)}
              {canUsePriceRecords(asset) ? <button className="text-button mini-text-button" onClick={onManual} type="button">补录</button> : null}
            </dd>
          </div>}
          {stockAccount ? null : <div><dt>{cashAsset ? "收益日期" : "价格日期"}</dt><dd>{asset.priceDate ?? "-"}</dd></div>}
        </dl>
        <p className="helper-note">
          来源 {asset.dataSourceType ?? "-"} · 状态 {asset.dataStatus}
          {asset.priceErrorMessage ? ` · ${sanitizeTechnicalMessage(asset.priceErrorMessage)}` : ""} · 更新 {formatDateTime(asset.updatedAt)}
        </p>
        {asset.priceErrorMessage ? <div className="error-banner">{sanitizeTechnicalMessage(asset.priceErrorMessage)}</div> : null}
      </section>

      <section className="detail-section">
        <div className="detail-tabs" aria-label="详情分区">
          {[
            ["income", "收益走势"],
            ["rate", "收益率走势"],
            ["performance", "业绩走势"],
            ["estimate", "净值估算"],
            ["records", "数据记录"],
          ].map(([key, label]) => (
            <button
              className={activeDetailTab === key ? "is-active" : ""}
              key={key}
              onClick={() => setActiveDetailTab(key as "income" | "rate" | "performance" | "estimate" | "records")}
              type="button"
            >
              {label}
            </button>
          ))}
        </div>
        {isLoading ? (
          <div className="empty-block compact-empty">正在读取真实价格记录...</div>
        ) : renderDetailTab(activeDetailTab, asset, prices, transactions)}
      </section>

      <section className="detail-section">
        <h3>交易记录</h3>
        {transactions.length === 0 ? (
          <EmptyBlock title="暂无交易记录" body="当前没有 transactions 记录；这里不会展示示例交易。" />
        ) : (
          <>
            <Table
              headers={["日期", "类型", "金额", "份额", "价格", "来源", "备注", "操作"]}
              rows={transactions.map((transaction) => [
                transaction.transactionDate,
                transactionTypeLabel(transaction.transactionType),
                formatMoney(transaction.amount),
                formatQuantity(transaction.share),
                formatPrice(transaction.price),
                transaction.source,
                transaction.note ?? "-",
                transaction.transactionType === "dca" ? (
                  <button
                    className="text-button mini-text-button"
                    onClick={() => {
                      setEditingDca(transaction);
                      setDcaAmountDraft(String(Number(transaction.amount ?? 0)));
                      setDcaEditError(null);
                    }}
                    type="button"
                  >
                    修改金额
                  </button>
                ) : (
                  "-"
                ),
              ])}
            />
            {editingDca ? (
              <div className="inline-edit-panel">
                <div>
                  <strong>修改定投金额</strong>
                  <p className="helper-note">
                    {editingDca.transactionDate} 的定投记录会按原成交价格重新计算份额，并同步更新持仓金额、份额和成本。
                  </p>
                </div>
                <label className="field compact-field">
                  定投金额(元)
                  <input
                    className="table-input compact-input"
                    min="0.01"
                    onChange={(event) => setDcaAmountDraft(event.target.value)}
                    step="0.01"
                    type="number"
                    value={dcaAmountDraft}
                  />
                </label>
                <div className="form-actions">
                  <button className="primary-button compact" disabled={isSavingDca} onClick={() => void saveDcaAmount()} type="button">
                    {isSavingDca ? "保存中..." : "保存"}
                  </button>
                  <button
                    className="secondary-button compact"
                    disabled={isSavingDca}
                    onClick={() => {
                      setEditingDca(null);
                      setDcaAmountDraft("");
                      setDcaEditError(null);
                    }}
                    type="button"
                  >
                    取消
                  </button>
                </div>
                {dcaEditError ? <div className="error-banner compact-error">{dcaEditError}</div> : null}
              </div>
            ) : null}
          </>
        )}
      </section>

    </div>
  );
}

function MetricBlock({ label, value, subValue }: { label: string; value: string; subValue: string }) {
  const isPositive = value.startsWith("+");
  const isNegative = value.startsWith("-");
  return (
    <div className="metric-block">
      <span>{label}</span>
      <strong className={isPositive ? "positive-value" : isNegative ? "negative-value" : ""}>{value}</strong>
      <small className={isPositive ? "positive-value" : isNegative ? "negative-value" : ""}>{subValue}</small>
    </div>
  );
}

function AmountPrivacyToggle({ isVisible, onToggle }: { isVisible: boolean; onToggle: () => void }) {
  return (
    <button
      aria-label={isVisible ? "隐藏金额" : "显示金额"}
      className="amount-privacy-button"
      onClick={onToggle}
      title={isVisible ? "隐藏金额" : "显示金额"}
      type="button"
    >
      <span className="amount-eye-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" focusable="false">
          <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
          <circle cx="12" cy="12" r="3" />
          {!isVisible ? <path className="eye-slash" d="M4 20 20 4" /> : null}
        </svg>
      </span>
      <span>{isVisible ? "隐藏金额" : "显示金额"}</span>
    </button>
  );
}

function MaskedAmount() {
  return <span className="masked-amount">{MASKED_AMOUNT}</span>;
}

function SignedValue({
  value,
  formatter,
}: {
  value: number | null | undefined;
  formatter: (value: number | null | undefined) => string;
}) {
  const className =
    value !== null && value !== undefined && !Number.isNaN(value)
      ? value > 0
        ? "positive-value"
        : value < 0
          ? "negative-value"
          : ""
      : "";
  return <span className={className}>{formatter(value)}</span>;
}

function renderDetailTab(
  tab: "income" | "rate" | "performance" | "estimate" | "records",
  asset: Asset,
  prices: PriceRecord[],
  transactions: TransactionRecord[],
) {
  if (prices.length === 0 && tab !== "records") {
    return <EmptyBlock title="暂无历史价格记录" body="没有 price_records 时不绘制走势；更新行情或手动补录后，这里会展示真实记录。" />;
  }
  if (tab === "income") {
    return <PriceSparkline asset={asset} mode="income" prices={prices} transactions={transactions} />;
  }
  if (tab === "rate") {
    return <PriceSparkline asset={asset} mode="rate" prices={prices} transactions={transactions} />;
  }
  if (tab === "performance") {
    return <PriceSparkline asset={asset} mode="performance" prices={prices} transactions={transactions} />;
  }
  if (tab === "estimate") {
    const latest = prices.find((price) => price.isValid);
    const cashAsset = asset.assetType === "cash";
    return (
      <>
        <div className="estimate-grid">
          <div><span>{cashAsset ? "年化收益率(%)" : "最新净值 / 价格(元/份)"}</span><strong>{cashAsset ? formatYieldRate(latest?.price ?? asset.latestPrice ?? asset.expectedReturnRate) : formatPrice(latest?.price ?? asset.latestPrice)}</strong></div>
          <div><span>{cashAsset ? "收益日期" : "价格日期"}</span><strong>{latest?.priceDate ?? asset.priceDate ?? "-"}</strong></div>
          <div><span>{cashAsset ? "收益率变化(百分点)" : "涨跌幅(%)"}</span><strong><SignedValue value={toNumberOrNull(latest?.dailyChangePct ?? asset.dailyChangePct)} formatter={formatPct} /></strong></div>
          <div><span>昨日收益(元)</span><strong><SignedValue value={toNumberOrNull(latest?.dailyIncomeAmount ?? asset.dailyIncomeAmount)} formatter={formatSignedMoney} /></strong></div>
          <div><span>{cashAsset ? "当前金额(元)" : "估算市值(元)"}</span><strong>{formatMoney(asset.currentValue)}</strong></div>
        </div>
        <p className="helper-note">
          来源 {latest?.sourceType ?? asset.dataSourceType ?? "-"} · 状态 {latest?.dataStatus ?? asset.dataStatus} · 更新 {formatDateTime(latest?.fetchedAt ?? asset.updatedAt)}
        </p>
      </>
    );
  }
  const cashAsset = asset.assetType === "cash";
  return prices.length === 0 ? (
    <EmptyBlock title="暂无数据记录" body="当前没有 price_records 记录。" />
  ) : (
    <Table
      headers={cashAsset ? ["日期", "年化收益率(%)", "收益率变化", "昨日收益(元)"] : ["日期", "净值(元/份)", "涨跌幅(%)", "昨日收益(元)"]}
      rows={prices.map((price) => [
        <div className="table-cell-stack">
          <strong>{price.priceDate}</strong>
          <span>{price.sourceType} · {price.isValid ? price.dataStatus : sanitizeTechnicalMessage(price.errorMessage) || price.dataStatus} · {formatDateTime(price.fetchedAt)}</span>
        </div>,
        cashAsset ? formatYieldRate(price.price) : formatPrice(price.price),
        <SignedValue value={toNumberOrNull(price.dailyChangePct)} formatter={formatPct} />,
        <SignedValue value={toNumberOrNull(price.dailyIncomeAmount)} formatter={formatSignedMoney} />,
      ])}
    />
  );
}

function PriceSparkline({
  asset,
  prices,
  transactions,
  mode,
}: {
  asset: Asset;
  prices: PriceRecord[];
  transactions: TransactionRecord[];
  mode: "income" | "rate" | "performance";
}) {
  const [rangeKey, setRangeKey] = useState<"1m" | "3m" | "6m" | "1y" | "all">("1y");
  const [benchmarkCode, setBenchmarkCode] = useState("hs300");
  const [benchmarkHistory, setBenchmarkHistory] = useState<BenchmarkHistory | null>(null);
  const [benchmarkError, setBenchmarkError] = useState<string | null>(null);
  const allOrdered = [...prices]
    .filter((price) => price.isValid)
    .sort((left, right) => left.priceDate.localeCompare(right.priceDate));
  const rangePrices = filterPricesByRange(allOrdered, rangeKey);
  const chartPrices = mode === "performance" ? rangePrices : trimPricesBeforeEntryDate(rangePrices, asset);
  const benchmarkStartDate = chartPrices[0]?.priceDate ?? "";
  const benchmarkEndDate = chartPrices[chartPrices.length - 1]?.priceDate ?? "";

  useEffect(() => {
    if (mode !== "performance" || chartPrices.length < 2) {
      setBenchmarkHistory(null);
      setBenchmarkError(null);
      return;
    }
    let isActive = true;
    setBenchmarkError(null);
    setBenchmarkHistory(null);
    void api
      .benchmarkHistory(benchmarkCode, benchmarkStartDate, benchmarkEndDate)
      .then((history) => {
        if (!isActive) return;
        setBenchmarkHistory(history);
        setBenchmarkError(history.dataStatus === "failed" ? history.errorMessage ?? "基准数据暂不可用" : null);
      })
      .catch((caught) => {
        if (!isActive) return;
        setBenchmarkHistory(null);
        setBenchmarkError(caught instanceof Error ? caught.message : "基准数据暂不可用");
      });
    return () => {
      isActive = false;
    };
  }, [benchmarkCode, benchmarkEndDate, benchmarkStartDate, chartPrices.length, mode]);

  if (chartPrices.length < 2) {
    return (
      <div className="price-chart">
        <ChartRangeTabs value={rangeKey} onChange={setRangeKey} />
        <EmptyBlock
          title={mode === "performance" ? "价格记录不足" : "缺少可计算的持仓区间"}
          body={
            mode === "performance"
              ? "至少需要两条有效价格记录才能形成趋势；最近一年需要先通过 AKShare 更新补齐交易日净值。"
              : "近一年净值和涨跌幅会保留在数据记录中，但收益和收益率只从资产录入日期之后开始计算。"
          }
        />
      </div>
    );
  }
  const trendSeries = mode === "performance" ? null : buildIncomeTrendSeries(asset, chartPrices, transactions, mode);
  const holdingValues = trendSeries?.holding ?? [];
  const cumulativeValues = trendSeries?.cumulative ?? [];
  const values = mode === "performance" ? buildTrendValues(asset, chartPrices, transactions, mode) : mode === "income" ? cumulativeValues : holdingValues;
  const benchmarkValues = mode === "performance" && benchmarkHistory?.dataStatus === "normal" ? buildBenchmarkTrendValues(benchmarkHistory, benchmarkStartDate, benchmarkEndDate) : [];
  const latestValue = values[values.length - 1] ?? null;
  const previousValue = values.length > 1 ? values[values.length - 2] : null;
  const latestBenchmarkValue = benchmarkValues[benchmarkValues.length - 1]?.value ?? null;
  const dailyIncome = estimateDailyIncome(asset, prices);
  const chartTitle = mode === "income" ? "收益走势" : mode === "rate" ? "收益率走势" : "业绩走势";
  const chartUnitFormatter = mode === "income" ? formatSignedMoney : formatNullablePct;
  const allChartValues = [
    ...values,
    ...benchmarkValues.map((item) => item.value),
  ];
  const chartDomain = buildChartDomain(allChartValues);
  const { min, max } = chartDomain;
  const valueRange = max - min || 1;
  const plot = { left: 72, right: 740, top: 18, bottom: 220 };
  const startTime = new Date(`${chartPrices[0].priceDate}T00:00:00`).getTime();
  const endTime = new Date(`${chartPrices[chartPrices.length - 1].priceDate}T00:00:00`).getTime();
  const timeRange = endTime - startTime || 1;
  const yTicks = buildChartTicks(min, max);
  const xTicks = buildDateTicks(chartPrices);
  const yForValue = (value: number) => plot.bottom - ((value - min) / valueRange) * (plot.bottom - plot.top);
  const xForDate = (priceDate: string) =>
    plot.left + ((new Date(`${priceDate}T00:00:00`).getTime() - startTime) / timeRange) * (plot.right - plot.left);
  const points = values
    .map((value, index) => {
      const x = xForDate(chartPrices[index].priceDate);
      const y = yForValue(value);
      return `${x},${y}`;
    })
    .join(" ");
  const benchmarkPoints = benchmarkValues
    .map((item) => `${xForDate(item.priceDate)},${yForValue(item.value)}`)
    .join(" ");
  return (
    <div className="price-chart" aria-label="真实价格走势">
      {mode === "performance" ? (
        <div className="chart-toolbar">
          <label className="field compact-field">
            比较基准
            <select value={benchmarkCode} onChange={(event) => setBenchmarkCode(event.target.value)}>
              {benchmarkOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <span className="helper-note chart-status-note" title={benchmarkError ?? undefined}>
            {benchmarkError ? "基准暂不可用：AKShare 指数接口连接失败" : `来源 AKShare · ${benchmarkHistory?.name ?? "加载中"}`}
          </span>
        </div>
      ) : null}
      <div className="chart-stats">
        <div>
          <span>{mode === "income" ? "累计收益(元)" : mode === "rate" ? "持有收益率(%)" : "本基金(%)"}</span>
          <strong><SignedValue value={latestValue} formatter={chartUnitFormatter} /></strong>
        </div>
        <div>
          <span>{mode === "performance" ? benchmarkHistory?.name ?? "比较基准(%)" : mode === "rate" ? "上一交易日变化(%)" : "上一交易日累计变化(元)"}</span>
          <strong><SignedValue value={mode === "performance" ? latestBenchmarkValue : latestValue !== null && previousValue !== null ? latestValue - previousValue : null} formatter={chartUnitFormatter} /></strong>
        </div>
        <div>
          <span>{mode === "income" ? `日收益(元 · ${chartPrices[chartPrices.length - 1]?.priceDate.slice(5)})` : "上一交易日变化(%)"}</span>
          <strong>
            <SignedValue
              value={mode === "income" ? dailyIncome.value : latestValue !== null && previousValue !== null ? latestValue - previousValue : null}
              formatter={mode === "income" ? formatSignedMoney : formatNullablePct}
            />
          </strong>
        </div>
      </div>
      <svg viewBox="0 0 760 260" role="img">
        <line className="chart-axis-line" x1={plot.left} x2={plot.left} y1={plot.top} y2={plot.bottom} />
        <line className="chart-axis-line" x1={plot.left} x2={plot.right} y1={plot.bottom} y2={plot.bottom} />
        {yTicks.map((tick) => {
          const y = yForValue(tick);
          return (
            <g key={`y-${tick}`}>
              <line className="chart-grid-line" x1={plot.left} x2={plot.right} y1={y} y2={y} />
              <text className="chart-axis-text" x={plot.left - 8} y={y + 4}>{formatChartTick(tick, mode)}</text>
            </g>
          );
        })}
        {xTicks.map((tick) => {
          const x = xForDate(tick);
          return (
            <g key={`x-${tick}`}>
              <line className="chart-tick-line" x1={x} x2={x} y1={plot.bottom} y2={plot.bottom + 6} />
              <text className="chart-axis-text chart-x-text" x={x} y={plot.bottom + 24}>{tick.slice(5)}</text>
            </g>
          );
        })}
        {chartDomain.showZeroLine ? (
          <line className="chart-zero-line" x1={plot.left} x2={plot.right} y1={yForValue(0)} y2={yForValue(0)} />
        ) : null}
        <polyline className={mode === "income" ? "chart-cumulative-line" : "chart-product-line"} points={points} />
        {benchmarkPoints ? <polyline className="chart-benchmark-line" points={benchmarkPoints} /> : null}
        {mode === "performance" ? null : transactionMarkers(chartPrices, transactions, values, yForValue).map((marker) => (
          <g className={`transaction-marker ${marker.markerClass}`} key={`${marker.label}-${marker.x}`}>
            <circle cx={marker.x} cy={marker.y} r="5.5" />
            <text x={marker.x} y={Math.max(16, marker.y - 12)}>{marker.label}</text>
          </g>
        ))}
      </svg>
      <ChartRangeTabs value={rangeKey} onChange={setRangeKey} />
      <div className="chart-legend">
        <span>{chartTitle}基于真实 price_records 计算</span>
        {mode === "performance" ? <span>业绩走势按当前区间的产品净值重新归零，比较基准来自 AKShare 指数历史</span> : mode === "income" ? <span>收益走势只展示累计收益；手动累计收益作为当前锚点</span> : <span>收益率走势只展示持有收益率；手动校正值作为当前锚点</span>}
      </div>
      <div className="price-chart-axis">
        <span>{chartPrices[0]?.priceDate}</span>
        <span>{chartPrices[chartPrices.length - 1]?.priceDate}</span>
      </div>
    </div>
  );
}

function buildTrendValues(
  asset: Asset,
  prices: PriceRecord[],
  transactions: TransactionRecord[],
  mode: "income" | "rate" | "performance",
) {
  if (mode === "performance") {
    const firstPrice = Number(prices[0]?.price ?? 0);
    return prices.map((price) => (firstPrice > 0 ? ((Number(price.price) - firstPrice) / firstPrice) * 100 : 0));
  }
  return [];
}

function buildIncomeTrendSeries(
  asset: Asset,
  prices: PriceRecord[],
  transactions: TransactionRecord[],
  mode: "income" | "rate",
) {
  const entryDate = assetEntryDate(asset);
  const priceDates = prices.map((price) => price.priceDate);
  const state = buildEntryTrendState(asset, transactions, entryDate, priceDates);
  const transactionEvents = buildTransactionEvents(transactions, priceDates)
    .filter((event) => event.effectiveDate >= entryDate)
    .sort((left, right) => left.effectiveDate.localeCompare(right.effectiveDate));
  let cursor = 0;
  const holding: number[] = [];
  const cumulative: number[] = [];

  prices.forEach((price) => {
    while (cursor < transactionEvents.length && transactionEvents[cursor].effectiveDate <= price.priceDate) {
      applyTransactionToTrendState(state, transactionEvents[cursor].transaction);
      cursor += 1;
    }
    const marketValue = state.share * Number(price.price);
    const holdingIncome = marketValue - state.holdingCostBasis;
    const cumulativeIncome = marketValue - state.cumulativeNetBasis;
    if (mode === "rate") {
      holding.push(state.holdingCostBasis > 0 ? (holdingIncome / state.holdingCostBasis) * 100 : 0);
      cumulative.push(state.cumulativeNetBasis > 0 ? (cumulativeIncome / state.cumulativeNetBasis) * 100 : 0);
      return;
    }
    holding.push(holdingIncome);
    cumulative.push(cumulativeIncome);
  });

  return { holding, cumulative };
}

function buildBenchmarkTrendValues(history: BenchmarkHistory, startDate: string, endDate: string) {
  const ordered = [...history.items]
    .filter((item) => item.priceDate >= startDate && item.priceDate <= endDate)
    .sort((left, right) => left.priceDate.localeCompare(right.priceDate));
  const firstClose = Number(ordered[0]?.close ?? 0);
  if (firstClose <= 0) return [];
  return ordered.map((item) => ({
    priceDate: item.priceDate,
    value: ((Number(item.close) - firstClose) / firstClose) * 100,
  }));
}

function buildEntryTrendState(asset: Asset, transactions: TransactionRecord[], entryDate: string, priceDates: string[]) {
  const state = {
    share: Number(asset.holdingShare ?? 0),
    holdingCostBasis: getHoldingCostBaseForTrend(asset),
    cumulativeNetBasis: getCumulativeNetBasisForTrend(asset, transactions),
  };
  for (const transaction of transactions) {
    const effectiveDate = transactionEffectiveDate(transaction, priceDates);
    if (transaction.transactionDate < entryDate || (effectiveDate && effectiveDate < entryDate)) continue;
    reverseTransactionFromTrendState(state, transaction);
  }
  return {
    share: Math.max(state.share, 0),
    holdingCostBasis: Math.max(state.holdingCostBasis, 0),
    cumulativeNetBasis: Math.max(state.cumulativeNetBasis, 0),
  };
}

function buildEntryPosition(asset: Asset, transactions: TransactionRecord[], entryDate: string, priceDates: string[]) {
  let share = Number(asset.holdingShare ?? 0);
  let costBasis = getHoldingCostBaseForTrend(asset);
  for (const transaction of transactions) {
    const effectiveDate = transactionEffectiveDate(transaction, priceDates);
    if (transaction.transactionDate < entryDate || (effectiveDate && effectiveDate < entryDate)) continue;
    const type = transaction.transactionType;
    const transactionShare = Number(transaction.share ?? 0);
    const amount = Number(transaction.amount ?? 0) + Number(transaction.feeAmount ?? 0);
    if (["buy", "convert_in", "deposit", "contribution", "dca"].includes(type)) {
      share -= transactionShare;
      costBasis -= amount;
    }
    if (["sell", "convert_out", "withdraw", "redeem"].includes(type)) {
      share += transactionShare;
      costBasis += amount;
    }
  }
  return { share: Math.max(share, 0), costBasis: Math.max(costBasis, 0) };
}

function buildTransactionEvents(transactions: TransactionRecord[], priceDates: string[]) {
  return transactions
    .map((transaction) => {
      const effectiveDate = transactionEffectiveDate(transaction, priceDates);
      return effectiveDate ? { effectiveDate, transaction } : null;
    })
    .filter((event): event is { effectiveDate: string; transaction: TransactionRecord } => event !== null);
}

function transactionEffectiveDate(transaction: TransactionRecord, priceDates: string[]) {
  if (["buy", "convert_in", "dca"].includes(transaction.transactionType)) {
    return priceDates.find((priceDate) => priceDate >= transaction.transactionDate) ?? null;
  }
  return transaction.transactionDate;
}

function applyTransactionToTrendState(
  state: { share: number; holdingCostBasis: number; cumulativeNetBasis: number },
  transaction: TransactionRecord,
) {
  const type = transaction.transactionType;
  const share = Number(transaction.share ?? 0);
  const amount = Number(transaction.amount ?? 0) + Number(transaction.feeAmount ?? 0);
  if (["buy", "convert_in", "deposit", "contribution", "dca"].includes(type)) {
    state.share += share;
    state.holdingCostBasis += amount;
    state.cumulativeNetBasis += amount;
  }
  if (["sell", "convert_out", "withdraw", "redeem"].includes(type)) {
    const averageCost = state.share > 0 ? state.holdingCostBasis / state.share : 0;
    state.share = Math.max(state.share - share, 0);
    state.holdingCostBasis = Math.max(state.holdingCostBasis - averageCost * share, 0);
    state.cumulativeNetBasis = Math.max(state.cumulativeNetBasis - Number(transaction.amount ?? 0), 0);
  }
  if (["dividend", "cash_dividend", "bonus"].includes(type)) {
    state.cumulativeNetBasis = Math.max(state.cumulativeNetBasis - Number(transaction.amount ?? 0), 0);
  }
}

function reverseTransactionFromTrendState(
  state: { share: number; holdingCostBasis: number; cumulativeNetBasis: number },
  transaction: TransactionRecord,
) {
  const type = transaction.transactionType;
  const share = Number(transaction.share ?? 0);
  const amount = Number(transaction.amount ?? 0) + Number(transaction.feeAmount ?? 0);
  if (["buy", "convert_in", "deposit", "contribution", "dca"].includes(type)) {
    state.share -= share;
    state.holdingCostBasis -= amount;
    state.cumulativeNetBasis -= amount;
  }
  if (["sell", "convert_out", "withdraw", "redeem"].includes(type)) {
    state.share += share;
    state.holdingCostBasis += Number(transaction.amount ?? 0);
    state.cumulativeNetBasis += Number(transaction.amount ?? 0);
  }
  if (["dividend", "cash_dividend", "bonus"].includes(type)) {
    state.cumulativeNetBasis += Number(transaction.amount ?? 0);
  }
}

function trimPricesBeforeEntryDate(prices: PriceRecord[], asset: Asset) {
  const entryDate = assetEntryDate(asset);
  return prices.filter((price) => price.priceDate >= entryDate);
}

function assetEntryDate(asset: Asset) {
  return asset.entryDate ?? asset.createdAt.slice(0, 10);
}

function ChartRangeTabs({
  value,
  onChange,
}: {
  value: "1m" | "3m" | "6m" | "1y" | "all";
  onChange: (value: "1m" | "3m" | "6m" | "1y" | "all") => void;
}) {
  return (
    <div className="chart-range-tabs" aria-label="走势时间范围">
      {[
        ["1m", "近1月"],
        ["3m", "近3月"],
        ["6m", "近6月"],
        ["1y", "近1年"],
        ["all", "记账以来"],
      ].map(([key, label]) => (
        <button className={value === key ? "is-active" : ""} key={key} onClick={() => onChange(key as "1m" | "3m" | "6m" | "1y" | "all")} type="button">
          {label}
        </button>
      ))}
    </div>
  );
}

function filterPricesByRange(prices: PriceRecord[], range: "1m" | "3m" | "6m" | "1y" | "all") {
  if (range === "all" || prices.length === 0) return prices;
  const days = range === "1m" ? 31 : range === "3m" ? 93 : range === "6m" ? 186 : 366;
  const latest = new Date(`${prices[prices.length - 1].priceDate}T00:00:00`);
  const cutoff = new Date(latest);
  cutoff.setDate(cutoff.getDate() - days);
  return prices.filter((price) => new Date(`${price.priceDate}T00:00:00`) >= cutoff);
}

function buildChartDomain(values: number[]) {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (finiteValues.length === 0) {
    return { min: -1, max: 1, showZeroLine: true };
  }
  const rawMin = Math.min(...finiteValues);
  const rawMax = Math.max(...finiteValues);
  if (rawMin === rawMax) {
    const padding = Math.max(Math.abs(rawMin) * 0.08, 1);
    const min = rawMin - padding;
    const max = rawMax + padding;
    return { min, max, showZeroLine: min <= 0 && max >= 0 };
  }
  const range = rawMax - rawMin;
  const magnitude = Math.max(Math.abs(rawMin), Math.abs(rawMax), 1);
  const padding = Math.max(range * 0.12, magnitude * 0.006);
  const min = rawMin - padding;
  const max = rawMax + padding;
  return { min, max, showZeroLine: min <= 0 && max >= 0 };
}

function buildChartTicks(min: number, max: number) {
  if (min === max) return [min];
  const mid = (min + max) / 2;
  return [max, mid, min];
}

function buildDateTicks(prices: PriceRecord[]) {
  if (prices.length <= 2) return prices.map((price) => price.priceDate);
  const midIndex = Math.floor((prices.length - 1) / 2);
  return [prices[0].priceDate, prices[midIndex].priceDate, prices[prices.length - 1].priceDate];
}

function formatChartTick(value: number, mode: "income" | "rate" | "performance") {
  if (mode === "income") {
    const abs = Math.abs(value);
    if (abs >= 10000) return `${(value / 10000).toFixed(1)}万`;
    return value.toFixed(0);
  }
  return `${value.toFixed(0)}%`;
}

function transactionMarkers(
  prices: PriceRecord[],
  transactions: TransactionRecord[],
  values: number[],
  yForValue: (value: number) => number,
) {
  if (prices.length < 2 || transactions.length === 0) return [];
  const plotLeft = 72;
  const plotRight = 740;
  const start = new Date(`${prices[0].priceDate}T00:00:00`).getTime();
  const end = new Date(`${prices[prices.length - 1].priceDate}T00:00:00`).getTime();
  const span = end - start || 1;
  return transactions
    .map((transaction) => {
      const time = new Date(`${transaction.transactionDate}T00:00:00`).getTime();
      if (time < start || time > end) return null;
      const nearestIndex = nearestPriceIndex(prices, transaction.transactionDate);
      return {
        x: plotLeft + ((time - start) / span) * (plotRight - plotLeft),
        y: yForValue(values[nearestIndex] ?? 0),
        label: transactionTypeLabel(transaction.transactionType),
        markerClass: transactionMarkerClass(transaction.transactionType),
      };
    })
    .filter((marker): marker is { x: number; y: number; label: string; markerClass: string } => marker !== null);
}

function transactionMarkerClass(transactionType: string) {
  if (["buy", "convert_in", "deposit", "transfer_in", "contribution", "dca", "add"].includes(transactionType)) {
    return "is-buy";
  }
  if (["sell", "convert_out", "redeem", "withdraw", "transfer_out", "reduce", "clear"].includes(transactionType)) {
    return "is-sell";
  }
  return "is-other";
}

function nearestPriceIndex(prices: PriceRecord[], transactionDate: string) {
  const target = new Date(`${transactionDate}T00:00:00`).getTime();
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  prices.forEach((price, index) => {
    const distance = Math.abs(new Date(`${price.priceDate}T00:00:00`).getTime() - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function transactionTypeLabel(type: string) {
  const labels: Record<string, string> = {
    buy: "买入",
    sell: "卖出",
    convert_in: "转换转入",
    convert_out: "转换转出",
    clear: "清仓",
    rebalance: "调仓",
    deposit: "存入",
    withdraw: "取出",
    contribution: "投入",
    dca: "定投",
    dividend: "现金分红",
    cash_dividend: "现金分红",
    bonus: "分红",
  };
  return labels[type] ?? type;
}

function buildPriceUpdateSummary(assets: Asset[], taskStatuses: TaskStatus[]) {
  const priceTask = taskStatuses.find((task) => task.taskType === "price_update" || task.taskType === "price-update");
  const equityAssets = assets.filter((asset) => asset.assetType === "equity" && asset.assetStatus !== "inactive");
  const priceDates = equityAssets
    .map((asset) => asset.priceDate)
    .filter((value): value is string => Boolean(value))
    .sort();
  const latestPriceDate = priceDates.length > 0 ? priceDates[priceDates.length - 1] : undefined;
  const abnormalCount = equityAssets.filter((asset) => asset.dataStatus === "failed" || asset.dataStatus === "stale").length;
  const validCount = equityAssets.filter((asset) => asset.latestPrice && asset.priceDate).length;

  return {
    statusText:
      equityAssets.length === 0
        ? "暂无权益资产"
        : abnormalCount > 0
          ? `${abnormalCount} 项行情异常`
          : `${validCount}/${equityAssets.length} 项有价格`,
    lastRunAt: formatDateTime(priceTask?.lastRunAt),
    latestPriceDate: latestPriceDate ?? "-",
    lastResult: priceTask?.lastStatus ?? priceTask?.lastMessage ?? "-",
  };
}

function ModalFrame({
  title,
  children,
  onClose,
  size = "normal",
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  size?: "normal" | "large";
}) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className={`modal-panel ${size === "large" ? "modal-panel-large" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="card-header">
          <h3>{title}</h3>
          <button className="secondary-button compact" onClick={onClose} type="button">关闭</button>
        </div>
        {children}
      </section>
    </div>
  );
}

function DrawerFrame({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="drawer-panel" role="dialog" aria-modal="true" aria-label={title}>
        <div className="card-header">
          <h3>{title}</h3>
          <button className="secondary-button compact" onClick={onClose} type="button">关闭</button>
        </div>
        {children}
      </aside>
    </div>
  );
}

function buildAssetTabSummary(tab: AssetTabKey, assets: Asset[], totalAssetValue: number): AssetSummaryItem[] {
  const value = assets.reduce((sum, asset) => sum + Number(asset.currentValue ?? 0), 0);
  const ratio = totalAssetValue > 0 ? `${((value / totalAssetValue) * 100).toFixed(1)}%` : "-";
  const inactiveCount = assets.filter((asset) => asset.assetStatus === "inactive").length;
  if (tab === "equity") {
    const cost = assets.reduce((sum, asset) => sum + getHoldingCostBase(asset), 0);
    const gain = assets.reduce((sum, asset) => sum + (getHoldingGain(asset) ?? 0), 0);
    const gainRate = cost > 0 ? `${((gain / cost) * 100).toFixed(2)}%` : "-";
    const abnormal = assets.filter((asset) => asset.dataStatus !== "normal" && asset.dataStatus !== "manual").length;
    return [
      { label: "当前市值", value: formatMoney(value), isAmount: true },
      { label: "占比", value: ratio },
      { label: "持有收益率", value: gainRate },
      { label: "数据状态", value: abnormal === 0 ? "正常" : `${abnormal} 项异常` },
    ];
  }
  if (tab === "fixed_income") {
    const maturityAmount = assets
      .filter((asset) => daysUntil(asset.maturityDate) !== null && Number(daysUntil(asset.maturityDate)) <= 30 && Number(daysUntil(asset.maturityDate)) >= 0)
      .reduce((sum, asset) => sum + Number(asset.currentValue ?? 0), 0);
    const cost = assets.reduce((sum, asset) => sum + getHoldingCostBase(asset), 0);
    const gain = assets.reduce((sum, asset) => sum + (getHoldingGain(asset) ?? 0), 0);
    const gainRate = cost > 0 ? `${((gain / cost) * 100).toFixed(2)}%` : "-";
    return [
      { label: "当前金额", value: formatMoney(value), isAmount: true },
      { label: "占比", value: ratio },
      { label: "持有收益率", value: gainRate },
      { label: "30 天内到期金额", value: formatMoney(maturityAmount), isAmount: true },
    ];
  }
  if (tab === "cash") {
    const latestYieldValues = assets.map((asset) => Number(asset.latestPrice ?? asset.expectedReturnRate)).filter((value) => Number.isFinite(value));
    const avgYield = latestYieldValues.length > 0 ? `${(latestYieldValues.reduce((sum, value) => sum + value, 0) / latestYieldValues.length).toFixed(2)}%` : "-";
    const dailyIncome = assets.reduce((sum, asset) => sum + Number(asset.dailyIncomeAmount ?? 0), 0);
    return [
      { label: "当前金额", value: formatMoney(value), isAmount: true },
      { label: "占比", value: ratio },
      { label: "平均年化", value: avgYield },
      { label: "昨日收益", value: formatSignedMoney(dailyIncome), isAmount: true },
    ];
  }
  if (tab === "debt") {
    const highInterest = assets.filter((asset) => Number(asset.interestRate ?? 0) >= 8).length;
    return [
      { label: "待还金额", value: formatMoney(value), isAmount: true },
      { label: "负债项", value: String(assets.length) },
      { label: "高息负债", value: String(highInterest) },
      { label: "30 天内还款", value: String(assets.filter((asset) => isWithinDays(asset.repaymentDate, 30)).length) },
    ];
  }
  return [
    { label: "资产项", value: String(assets.length) },
    { label: "资产金额", value: formatMoney(value), isAmount: true },
    { label: "权益占比", value: categoryRatio(assets, "equity", totalAssetValue) },
    { label: "异常数据", value: String(assets.filter((asset) => asset.dataStatus === "failed" || asset.dataStatus === "abnormal").length) },
  ];
}

function assetColumns(tab: AssetTabKey) {
  if (tab === "cash") return ["资产名称", "平台", "当前金额(元)", "年化收益率(%)", "昨日收益(元)", "收益日期", "数据状态"];
  if (tab === "fixed_income") return ["资产名称", "细分类", "平台", "当前金额(元)", "持有收益(元)", "收益率(%)", "份额(份)", "最新净值", "预期年化(%)", "到期日"];
  if (tab === "equity") return ["资产名称", "细分类", "平台", "市值(元)", "收益/亏损(元)", "收益率(%)", "最新价格/净值", "价格日期", "数据状态"];
  if (tab === "debt") return ["资产名称", "平台", "待还金额(元)", "年化利率(%)", "还款日", "状态"];
  return ["资产名称", "类型/细分类", "平台", "当前金额/市值(元)", "收益/亏损(元)", "收益率(%)", "最新价格(元/份)", "价格日期", "数据状态"];
}

function assetCells(asset: Asset, tab: AssetTabKey, isAmountVisible: boolean, onNameClick: () => void): ReactNode[] {
  const name = (
    <button className="asset-name-button" onClick={onNameClick} type="button">
      {asset.name}
    </button>
  );
  const gainValue = getHoldingGain(asset);
  const gain = isAmountVisible ? <SignedValue value={gainValue} formatter={formatSignedMoney} /> : <MaskedAmount />;
  const gainRateValue = getHoldingGainRate(asset);
  const gainRate = <SignedValue value={gainRateValue} formatter={formatNullablePct} />;
  if (tab === "cash") {
    return [
      name,
      asset.platform,
      formatAmount(formatMoney(asset.currentValue), isAmountVisible),
      formatYieldRate(asset.latestPrice ?? asset.expectedReturnRate),
      isAmountVisible ? <SignedValue value={toNumberOrNull(asset.dailyIncomeAmount)} formatter={formatSignedMoney} /> : <MaskedAmount />,
      asset.priceDate ?? "-",
      dataStatusLabel(asset),
    ];
  }
  if (tab === "fixed_income") {
    return [
      name,
      asset.subType ?? "-",
      asset.platform,
      formatAmount(formatMoney(asset.currentValue), isAmountVisible),
      gain,
      gainRate,
      formatQuantity(asset.holdingShare),
      formatPrice(asset.latestPrice),
      asset.expectedReturnRate ? `${asset.expectedReturnRate}%` : "-",
      asset.maturityDate ?? "-",
    ];
  }
  if (tab === "equity") return [name, asset.subType ?? "-", asset.platform, formatAmount(formatMoney(asset.currentValue), isAmountVisible), gain, gainRate, isStockAccountSubtype(asset.subType) ? "-" : formatPrice(asset.latestPrice), asset.priceDate ?? "-", dataStatusLabel(asset)];
  if (tab === "debt") {
    return [name, asset.platform, formatAmount(formatMoney(asset.currentValue), isAmountVisible), asset.interestRate ? `${asset.interestRate}%` : "-", asset.repaymentDate ?? "-", asset.assetStatus];
  }
  return [
    name,
    `${assetTypeLabels[asset.assetType]}${asset.subType ? ` / ${asset.subType}` : ""}`,
    asset.platform,
    formatAmount(formatMoney(asset.currentValue), isAmountVisible),
    gain,
    gainRate,
    formatPrice(asset.latestPrice),
    asset.priceDate ?? "-",
    dataStatusLabel(asset),
  ];
}

function getHoldingGainRate(asset: Asset) {
  const holdingCostBase = getHoldingCostBase(asset);
  if (holdingCostBase <= 0 || asset.assetType === "cash" || asset.assetType === "debt") return null;
  const gain = getHoldingGain(asset);
  if (gain === null) return null;
  return (gain / holdingCostBase) * 100;
}

function getHoldingGain(asset: Asset) {
  const value = Number(asset.currentValue ?? 0);
  const holdingCostBase = getHoldingCostBase(asset);
  if (holdingCostBase > 0 && asset.assetType !== "cash" && asset.assetType !== "debt") {
    return value - holdingCostBase;
  }
  const cost = Number(asset.costAmount ?? asset.principalAmount ?? 0);
  if (cost <= 0 || asset.assetType === "cash" || asset.assetType === "debt") return null;
  return value - cost;
}

function getCumulativeGain(asset: Asset, transactions: TransactionRecord[] = []) {
  const basis = manualNumber(asset.cumulativeNetBasis);
  if (basis !== null) {
    return Number(asset.currentValue ?? 0) - basis;
  }
  const transactionValue = getTransactionBasedCumulativeGain(asset, transactions);
  if (transactionValue !== null) return transactionValue;
  if (asset.cumulativeGain !== null && asset.cumulativeGain !== undefined && asset.cumulativeGain !== "") {
    return Number(asset.cumulativeGain);
  }
  const cost = Number(asset.costAmount ?? asset.principalAmount ?? 0);
  const value = Number(asset.currentValue ?? 0);
  if (cost <= 0 || asset.assetType === "cash" || asset.assetType === "debt") return null;
  return value - cost;
}

function getCumulativeGainBase(asset: Asset, transactions: TransactionRecord[] = []) {
  const basis = manualNumber(asset.cumulativeNetBasis);
  if (basis !== null) return basis;
  const invested = sumTransactions(transactions, INVEST_TRANSACTION_TYPES);
  if (invested > 0) return invested;
  return Number(asset.costAmount ?? asset.principalAmount ?? 0);
}

function getTransactionBasedCumulativeGain(asset: Asset, transactions: TransactionRecord[]) {
  if (asset.assetType === "cash" || asset.assetType === "debt" || transactions.length === 0) return null;
  const invested = sumTransactions(transactions, INVEST_TRANSACTION_TYPES);
  if (invested <= 0) return null;
  const redeemed = sumTransactions(transactions, REDEEM_TRANSACTION_TYPES);
  const dividends = sumTransactions(transactions, DIVIDEND_TRANSACTION_TYPES);
  return Number(asset.currentValue ?? 0) - invested + redeemed + dividends;
}

const INVEST_TRANSACTION_TYPES = new Set(["buy", "convert_in", "deposit", "transfer_in", "contribution", "dca", "add"]);
const REDEEM_TRANSACTION_TYPES = new Set(["sell", "convert_out", "redeem", "withdraw", "transfer_out", "reduce", "clear"]);
const DIVIDEND_TRANSACTION_TYPES = new Set(["dividend", "cash_dividend", "bonus"]);

function sumTransactions(transactions: TransactionRecord[], types: Set<string>) {
  return transactions
    .filter((transaction) => types.has(transaction.transactionType))
    .reduce((sum, transaction) => sum + Number(transaction.amount ?? 0), 0);
}

function getHoldingCostBase(asset: Asset) {
  const costPrice = getHoldingCostPrice(asset);
  const share = Number(asset.holdingShare ?? 0);
  if (costPrice !== null && share > 0) return costPrice * share;
  return Number(asset.costAmount ?? asset.principalAmount ?? 0);
}

function getHoldingCostBaseForTrend(asset: Asset) {
  return getHoldingCostBase(asset);
}

function getCumulativeNetBasisForTrend(asset: Asset, transactions: TransactionRecord[] = []) {
  const storedBasis = manualNumber(asset.cumulativeNetBasis);
  if (storedBasis !== null) {
    return storedBasis;
  }
  const manualCumulativeGain = manualNumber(asset.cumulativeGain);
  if (manualCumulativeGain !== null) {
    return Math.max(Number(asset.currentValue ?? 0) - manualCumulativeGain, 0);
  }
  const invested = sumTransactions(transactions, INVEST_TRANSACTION_TYPES);
  const redeemed = sumTransactions(transactions, REDEEM_TRANSACTION_TYPES);
  const dividends = sumTransactions(transactions, DIVIDEND_TRANSACTION_TYPES);
  if (transactions.length > 0 && (invested > 0 || redeemed > 0 || dividends > 0)) {
    return Math.max(invested - redeemed - dividends, 0);
  }
  return Number(asset.costAmount ?? asset.principalAmount ?? 0);
}

function manualNumber(value: string | null | undefined) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getHoldingCostPrice(asset: Asset) {
  if (asset.holdingCostPrice !== null && asset.holdingCostPrice !== undefined && asset.holdingCostPrice !== "") {
    return Number(asset.holdingCostPrice);
  }
  const cost = Number(asset.costAmount ?? 0);
  const share = Number(asset.holdingShare ?? 0);
  if (cost > 0 && share > 0) return cost / share;
  return null;
}

function dataStatusLabel(asset: Asset) {
  if (asset.priceErrorMessage) return `${asset.dataStatus} · ${sanitizeTechnicalMessage(asset.priceErrorMessage)}`;
  return asset.dataStatus;
}

function sanitizeTechnicalMessage(message?: string | null) {
  if (!message) return "";
  const technicalPatterns = [
    /HTTPS?ConnectionPool/i,
    /Max retries exceeded/i,
    /ProxyError/i,
    /RemoteDisconnected/i,
    /Traceback/i,
    /urllib3/i,
    /requests/i,
    /httpx/i,
    /akshare response/i,
    /host=.*port=/i,
    /Caused by/i,
    /SyntaxError/i,
    /Unexpected token/i,
    /<!doctype html>/i,
    /<html/i,
    /<anonymous>/i,
    /\/api\//i,
  ];
  if (technicalPatterns.some((pattern) => pattern.test(message))) {
    const seedMatch = message.match(/初始化最近\s*(\d+)\s*个交易日/);
    if (seedMatch) {
      return `初始化最近 ${seedMatch[1]} 个交易日行情失败：AKShare 数据暂不可用，请稍后重试，或先手动补录价格。`;
    }
    return "AKShare 数据暂不可用，请稍后重试，或使用手动补录价格。";
  }
  return message;
}

function applyAutoSubType<T extends Partial<AssetDraft>>(draft: T): T {
  if (draft.subType || !draft.name) return draft;
  const assetType = draft.assetType ?? "equity";
  const inferred = inferAssetSubType(draft.name, assetType);
  return inferred ? { ...draft, subType: inferred } : draft;
}

function inferAssetSubType(name: string | undefined, assetType: AssetType) {
  const text = name ?? "";
  if (!text) return "";
  if (assetType === "cash") {
    if (/货币|余额宝|零钱通/.test(text)) return "货币基金";
    if (/活期|现金/.test(text)) return "活期现金";
    return "";
  }
  if (assetType === "fixed_income") {
    if (/大额存单/.test(text)) return "大额存单";
    if (/存款/.test(text)) return "银行存款";
    if (/理财/.test(text)) return "银行理财";
    if (/债/.test(text)) return "债券基金";
    return "";
  }
  if (assetType === "debt") {
    if (/信用卡/.test(text)) return "信用卡";
    if (/房贷/.test(text)) return "房贷";
    if (/车贷/.test(text)) return "车贷";
    if (/贷|借款/.test(text)) return "消费贷";
    return "";
  }
  if (/股票账户|证券账户|券商账户/.test(text)) return "股票账户";
  if (/港股|HK|H股/i.test(text)) return "港股股票";
  if (/美股|US|纳斯达克|纽交所|NASDAQ|NYSE/i.test(text)) return "美股股票";
  if (/A股|沪市|深市|上证|深证/.test(text)) return "A股股票";
  if (/黄金/.test(text)) return "黄金基金";
  if (/QDII|纳指|标普|海外|全球|美元/i.test(text)) return "QDII";
  if (/ETF联接|联接/.test(text)) return "ETF联接";
  if (/LOF/i.test(text)) return "LOF";
  if (/指数|沪深|中证|创业板|科创|红利/.test(text)) return "指数基金";
  if (/债/.test(text)) return "债券基金";
  if (/股票/.test(text)) return "股票基金";
  if (/混合/.test(text)) return "混合基金";
  if (/货币/.test(text)) return "货币基金";
  return "";
}

function isStockHoldingSubtype(value: string | null | undefined) {
  return equityStockSubTypes.has(value ?? "");
}

function isStockAccountSubtype(value: string | null | undefined) {
  return value === "股票账户";
}

function isStockHoldingDraft(draft: Pick<AssetDraft, "assetType" | "subType">) {
  return draft.assetType === "equity" && isStockHoldingSubtype(draft.subType);
}

function isStockAccountDraft(draft: Pick<AssetDraft, "assetType" | "subType">) {
  return draft.assetType === "equity" && isStockAccountSubtype(draft.subType);
}

function canUsePriceRecords(asset: Asset) {
  return asset.assetType === "cash" || asset.assetType === "fixed_income" || (asset.assetType === "equity" && !isStockAccountSubtype(asset.subType));
}

function categoryRatio(assets: Asset[], type: AssetType, totalAssetValue: number) {
  const value = assets.filter((asset) => asset.assetType === type).reduce((sum, asset) => sum + Number(asset.currentValue ?? 0), 0);
  return totalAssetValue > 0 ? `${((value / totalAssetValue) * 100).toFixed(1)}%` : "-";
}

function isWithinDays(value: string | null | undefined, days: number) {
  const diff = daysUntil(value);
  return diff !== null && diff >= 0 && diff <= days;
}

function daysUntil(value: string | null | undefined) {
  if (!value) return null;
  const target = new Date(`${value}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((target.getTime() - today.getTime()) / 86400000);
}

function AssetForm({
  draft,
  mode,
  onChange,
  onCancel,
  onSave,
  onLookupFund,
}: {
  draft: AssetDraft;
  mode: "create" | "edit";
  onChange: (draft: AssetDraft) => void;
  onCancel: () => void;
  onSave: (event: FormEvent) => void;
  onLookupFund: (productCode?: string) => Promise<void>;
}) {
  const set = (key: keyof AssetDraft, value: string | boolean) => onChange({ ...draft, [key]: value });
  const setInvestmentMetric = (key: keyof AssetDraft, value: string) => onChange(applyInvestmentMetricDerivation({ ...draft, [key]: value }, key));
  const setName = (value: string) => {
    const previousInferred = inferAssetSubType(draft.name, draft.assetType);
    const nextInferred = inferAssetSubType(value, draft.assetType);
    onChange({
      ...draft,
      name: value,
      subType: !draft.subType || draft.subType === previousInferred ? nextInferred : draft.subType,
    });
  };
  const setDcaFrequency = (value: string) => {
    const nextDraft = { ...draft, dcaFrequency: value };
    if (value === "daily") {
      nextDraft.dcaDay = "";
    } else if (!nextDraft.dcaDay) {
      nextDraft.dcaDay = value === "monthly" ? "1" : "1";
    }
    onChange(nextDraft);
  };
  const stockHolding = isStockHoldingDraft(draft);
  const stockAccount = isStockAccountDraft(draft);
  const equityCodeLabel = stockAccount ? "证券账户号" : stockHolding ? "股票代码" : "基金代码";
  const equityMarketLabel = stockAccount ? "账户市场" : stockHolding ? "交易市场" : "市场";
  const equityShareLabel = stockHolding ? "持有股数(股)" : "持有份额(份)";
  const equityCostPriceLabel = stockHolding ? "持仓成本价(元/股)" : "持仓成本价(元/份)";
  const equityLatestPriceLabel = stockHolding ? "最新股价(元/股)" : "最新净值/价格(元/份)";
  const equityPriceDateLabel = stockHolding ? "股价日期" : "净值日期";
  const codeLookupLabel =
    draft.assetType === "cash" ? "产品/账户代码" :
      draft.assetType === "fixed_income" ? "产品代码" :
        draft.assetType === "debt" ? "贷款/账单代码" :
          equityCodeLabel;
  const lookupByCode = () => {
    if (draft.productCode.trim()) void onLookupFund(draft.productCode);
  };

  return (
    <form className="asset-form" onSubmit={onSave}>
      <div className="card-header">
        <h3>{mode === "edit" ? "编辑资产" : `新增${assetTypeLabels[draft.assetType]}`}</h3>
        <span className="tag">{assetTypeLabels[draft.assetType]}</span>
      </div>
      <div className="form-grid">
        <Field label="名称" value={draft.name} onChange={setName} required />
        <Field label="平台" value={draft.platform} onChange={(value) => set("platform", value)} suggestions={platformOptions} required />
        <Field label={draft.assetType === "debt" ? "待还余额(元)" : "当前金额(元)"} value={draft.currentValue} onChange={(value) => draft.assetType === "equity" || draft.assetType === "fixed_income" ? setInvestmentMetric("currentValue", value) : set("currentValue", value)} type="number" required />
        <Field label="录入日期" value={draft.entryDate} onChange={(value) => set("entryDate", value)} type="date" />
        <Field label="细分类" value={draft.subType} onChange={(value) => set("subType", value)} suggestions={subtypeOptions[draft.assetType]} />
        {draft.assetType === "cash" ? (
          <>
            <div className="field-with-action">
              <Field
                label={codeLookupLabel}
                value={draft.productCode}
                onBlur={lookupByCode}
                onChange={(value) => set("productCode", value)}
              />
              <button className="secondary-button compact" disabled={!draft.productCode.trim()} onClick={lookupByCode} type="button">
                按代码填充
              </button>
            </div>
            <Field label="年化收益率(%)" value={draft.expectedReturnRate} onChange={(value) => set("expectedReturnRate", value)} type="number" />
            <Field label="昨日收益(元)" value={draft.dailyIncomeAmount} onChange={(value) => set("dailyIncomeAmount", value)} type="number" />
            <Field label="收益日期" value={draft.priceDate} onChange={(value) => set("priceDate", value)} type="date" />
          </>
        ) : null}
        {draft.assetType === "fixed_income" ? (
          <>
            <div className="field-with-action">
              <Field
                label={codeLookupLabel}
                value={draft.productCode}
                onBlur={lookupByCode}
                onChange={(value) => set("productCode", value)}
              />
              <button className="secondary-button compact" disabled={!draft.productCode.trim()} onClick={lookupByCode} type="button">
                按代码填充
              </button>
            </div>
            <Field label="本金(元)" value={draft.principalAmount} onChange={(value) => set("principalAmount", value)} type="number" />
            <Field label="持有份额(份)" value={draft.holdingShare} onChange={(value) => setInvestmentMetric("holdingShare", value)} type="number" />
            <Field label="累计投入本金(元)" value={draft.costAmount} onChange={(value) => setInvestmentMetric("costAmount", value)} type="number" />
            <Field label="持仓成本价(元/份)" value={draft.holdingCostPrice} onChange={(value) => setInvestmentMetric("holdingCostPrice", value)} type="number" />
            <Field label="持有收益(元)" value={draft.holdingGain} onChange={(value) => setInvestmentMetric("holdingGain", value)} type="number" />
            <Field label="累计收益校正(元)" value={draft.cumulativeGain} onChange={(value) => set("cumulativeGain", value)} type="number" />
            <Field label="最新净值/价格(元/份)" value={draft.latestPrice} onChange={(value) => setInvestmentMetric("latestPrice", value)} type="number" />
            <Field label="净值日期" value={draft.priceDate} onChange={(value) => set("priceDate", value)} type="date" />
            {stockAccount ? null : <Field label="日涨跌幅(%)" value={draft.dailyChangePct} onChange={(value) => set("dailyChangePct", value)} type="number" />}
            <Field label="预期年化(%)" value={draft.expectedReturnRate} onChange={(value) => set("expectedReturnRate", value)} type="number" />
            <Field label="到期日" value={draft.maturityDate} onChange={(value) => set("maturityDate", value)} type="date" />
            <Field label="流动性" value={draft.liquidityLevel} onChange={(value) => set("liquidityLevel", value)} />
          </>
        ) : null}
        {draft.assetType === "equity" ? (
          <>
            <div className="field-with-action">
              <Field
                label={equityCodeLabel}
                value={draft.productCode}
                onBlur={() => {
                  const minCodeLength = stockHolding ? 4 : 6;
                  if (!stockAccount && draft.productCode.trim().length >= minCodeLength) void onLookupFund(draft.productCode);
                }}
                onChange={(value) => set("productCode", value)}
              />
              {!stockAccount ? <button className="secondary-button compact" onClick={() => void onLookupFund(draft.productCode)} type="button">
                按代码填充
              </button> : null}
            </div>
            <Field label={equityMarketLabel} value={draft.market} onChange={(value) => set("market", value)} suggestions={stockHolding || stockAccount ? stockMarketOptions : undefined} />
            {stockAccount ? null : <Field label={equityShareLabel} value={draft.holdingShare} onChange={(value) => setInvestmentMetric("holdingShare", value)} type="number" required />}
            <Field label={stockAccount ? "持仓成本/投入本金(元)" : "累计投入本金(元)"} value={draft.costAmount} onChange={(value) => setInvestmentMetric("costAmount", value)} type="number" />
            {stockAccount ? null : <Field label={equityCostPriceLabel} value={draft.holdingCostPrice} onChange={(value) => setInvestmentMetric("holdingCostPrice", value)} type="number" />}
            <Field label="持有收益(元)" value={draft.holdingGain} onChange={(value) => setInvestmentMetric("holdingGain", value)} type="number" />
            <Field label="累计收益校正(元)" value={draft.cumulativeGain} onChange={(value) => set("cumulativeGain", value)} type="number" />
            {stockAccount ? null : <Field label={equityLatestPriceLabel} value={draft.latestPrice} onChange={(value) => setInvestmentMetric("latestPrice", value)} type="number" />}
            {stockAccount ? null : <Field label={equityPriceDateLabel} value={draft.priceDate} onChange={(value) => set("priceDate", value)} type="date" />}
            <Field label="日涨跌幅(%)" value={draft.dailyChangePct} onChange={(value) => set("dailyChangePct", value)} type="number" />
            <Field label="数据源" value={draft.dataSourceType} onChange={(value) => set("dataSourceType", value)} />
            {!stockHolding && !stockAccount ? <label className="checkbox-row">
              <input
                checked={draft.isDca}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    isDca: event.target.checked,
                    dcaFrequency: event.target.checked && !draft.dcaFrequency ? "daily" : draft.dcaFrequency,
                    dcaDay: event.target.checked ? draft.dcaDay : "",
                  })
                }
                type="checkbox"
              />
              定投资产
            </label> : null}
            {!stockHolding && !stockAccount && draft.isDca ? (
              <>
            <Field label="定投金额(元)" value={draft.dcaAmount} onChange={(value) => set("dcaAmount", value)} type="number" />
                <SelectField label="定投频率" value={draft.dcaFrequency} onChange={setDcaFrequency} options={dcaFrequencyOptions} />
                {draft.dcaFrequency === "weekly" || draft.dcaFrequency === "biweekly" ? (
                  <SelectField label="定投日期" value={draft.dcaDay} onChange={(value) => set("dcaDay", value)} options={weekDayOptions} />
                ) : null}
                {draft.dcaFrequency === "monthly" ? (
                  <SelectField label="定投日期" value={draft.dcaDay} onChange={(value) => set("dcaDay", value)} options={monthDayOptions} />
                ) : null}
                <Field label="下次定投日" value={draft.dcaNextDate} onChange={(value) => set("dcaNextDate", value)} type="date" />
              </>
            ) : null}
          </>
        ) : null}
        {draft.assetType === "debt" ? (
          <>
            <div className="field-with-action">
              <Field
                label={codeLookupLabel}
                value={draft.productCode}
                onBlur={lookupByCode}
                onChange={(value) => set("productCode", value)}
              />
              <button className="secondary-button compact" disabled={!draft.productCode.trim()} onClick={lookupByCode} type="button">
                按代码填充
              </button>
            </div>
            <Field label="还款日" value={draft.repaymentDate} onChange={(value) => set("repaymentDate", value)} type="date" />
            <Field label="年化利率(%)" value={draft.interestRate} onChange={(value) => set("interestRate", value)} type="number" />
          </>
        ) : null}
        <Field label="目标标签" value={draft.targetTag} onChange={(value) => set("targetTag", value)} />
        <label className="field full-field">
          备注
          <textarea value={draft.note} onChange={(event) => set("note", event.target.value)} />
        </label>
      </div>
      <div className="form-actions">
        <button className="secondary-button" onClick={onCancel} type="button">取消</button>
        <button className="primary-button" type="submit">保存资产</button>
      </div>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  onBlur,
  suggestions,
  type = "text",
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  suggestions?: string[];
  type?: string;
  required?: boolean;
}) {
  const listId = suggestions && suggestions.length > 0 ? `field-options-${label}` : undefined;
  return (
    <label className="field">
      {label}
      <input list={listId} required={required} type={type} value={value} onBlur={onBlur} onChange={(event) => onChange(event.target.value)} />
      {listId ? (
        <datalist id={listId}>
          {suggestions?.map((option) => <option key={option} value={option} />)}
        </datalist>
      ) : null}
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="field">
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">请选择</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function AssetDetail({
  asset,
  onEdit,
  onDeactivate,
  onUpdatePrice,
  onManualPrice,
}: {
  asset: Asset | null;
  onEdit: (asset: Asset) => void;
  onDeactivate: () => void;
  onUpdatePrice: () => void;
  onManualPrice: (assetId: string, payload: { priceDate: string; price: number; currentValue?: number; dailyChangePct?: number; dailyIncomeAmount?: number }) => void;
}) {
  const [manualDate, setManualDate] = useState(new Date().toISOString().slice(0, 10));
  const [manualPriceValue, setManualPriceValue] = useState("");
  const [manualChangePct, setManualChangePct] = useState("");
  const [manualDailyIncome, setManualDailyIncome] = useState("");

  if (!asset) {
    return <EmptyBlock title="选择一项资产" body="点击左侧资产查看详情，或新增第一项真实资产。" />;
  }
  const canUpdatePrice = canUsePriceRecords(asset);
  const priceLabel = asset.assetType === "fixed_income" ? "最新价格/净值" : isStockHoldingSubtype(asset.subType) ? "最新股价" : "最新净值/价格";
  const priceDateLabel = asset.assetType === "fixed_income" ? "价格/净值日期" : "价格日期";
  return (
    <div>
      <div className="card-header">
        <h3>{asset.name}</h3>
        <span className="tag">{assetTypeLabels[asset.assetType]}</span>
      </div>
      <dl className="detail-grid">
        <div><dt>平台</dt><dd>{asset.platform}</dd></div>
        <div><dt>金额</dt><dd>{formatMoney(asset.currentValue)}</dd></div>
        <div><dt>状态</dt><dd>{asset.assetStatus}</dd></div>
        <div><dt>Owner</dt><dd>{asset.ownerId}</dd></div>
        {asset.productCode ? <div><dt>产品代码</dt><dd>{asset.productCode}</dd></div> : null}
        {asset.holdingShare ? <div><dt>份额</dt><dd>{formatQuantity(asset.holdingShare)}</dd></div> : null}
        {asset.latestPrice ? <div><dt>{priceLabel}</dt><dd>{formatPrice(asset.latestPrice)}</dd></div> : null}
        {asset.priceDate ? <div><dt>{priceDateLabel}</dt><dd>{asset.priceDate}</dd></div> : null}
        <div><dt>数据源</dt><dd>{asset.dataSourceType ?? "-"}</dd></div>
        <div><dt>数据状态</dt><dd>{asset.dataStatus}</dd></div>
        {asset.dailyChangePct ? <div><dt>日涨跌幅</dt><dd>{asset.dailyChangePct}%</dd></div> : null}
        {asset.repaymentDate ? <div><dt>还款日</dt><dd>{asset.repaymentDate}</dd></div> : null}
        {asset.maturityDate ? <div><dt>到期日</dt><dd>{asset.maturityDate}</dd></div> : null}
      </dl>
      {asset.priceErrorMessage ? <div className="error-banner">{sanitizeTechnicalMessage(asset.priceErrorMessage)}</div> : null}
      {canUpdatePrice ? (
        <form
          className="manual-price-box"
          onSubmit={(event) => {
            event.preventDefault();
            onManualPrice(asset.id, {
              priceDate: manualDate,
              price: Number(manualPriceValue),
              dailyChangePct: manualChangePct ? Number(manualChangePct) : undefined,
              dailyIncomeAmount: manualDailyIncome ? Number(manualDailyIncome) : undefined,
            });
            setManualPriceValue("");
            setManualChangePct("");
            setManualDailyIncome("");
          }}
        >
          <h3>手动补录价格</h3>
          <div className="form-grid">
            <Field label={priceDateLabel} value={manualDate} onChange={setManualDate} type="date" required />
            <Field label={priceLabel} value={manualPriceValue} onChange={setManualPriceValue} type="number" required />
            <Field label="日涨跌幅" value={manualChangePct} onChange={setManualChangePct} type="number" />
            <Field label="昨日收益金额" value={manualDailyIncome} onChange={setManualDailyIncome} type="number" />
          </div>
          <div className="form-actions">
            {asset.assetType === "equity" ? <button className="secondary-button" onClick={onUpdatePrice} type="button">AKShare 更新</button> : null}
            <button className="primary-button" type="submit">保存补录</button>
          </div>
        </form>
      ) : null}
      <div className="form-actions">
        <button className="secondary-button" onClick={() => onEdit(asset)} type="button">编辑</button>
        <button className="danger-button" disabled={asset.assetStatus === "inactive"} onClick={onDeactivate} type="button">
          停用
        </button>
      </div>
    </div>
  );
}

function AlertsPage({ alerts }: { alerts: AlertRecord[] }) {
  return (
    <div className="content-panel single-panel">
      <section className="dashboard-card">
        <h3>提醒</h3>
        {alerts.length === 0 ? (
          <EmptyBlock title="暂无提醒记录" body="提醒必须由后端任务生成并保存为 alert_records；本阶段不在页面临时生成提醒。" />
        ) : (
          <Table headers={["标题", "级别", "状态", "触发时间"]} rows={alerts.map((item) => [item.title, item.alertLevel, item.status, item.triggeredAt])} />
        )}
      </section>
    </div>
  );
}

function ReviewsPage({ reviews, onGenerate }: { reviews: MonthlyReview[]; onGenerate: () => void }) {
  return (
    <div className="content-panel single-panel">
      <section className="dashboard-card">
        <div className="card-header">
          <h3>复盘</h3>
          <button className="primary-button compact" onClick={onGenerate} type="button">生成本月复盘</button>
        </div>
        {reviews.length === 0 ? (
          <EmptyBlock title="暂无月度复盘" body="没有月初快照时不伪造月初数据；可先运行每日快照，再生成真实复盘。" />
        ) : (
          <Table
            headers={["月份", "完整性", "月末净资产", "净资产变化", "投资收益", "生成时间"]}
            rows={reviews.map((item) => [
              item.reviewMonth,
              item.dataCompletenessStatus,
              formatMoney(item.endNetAsset),
              item.netAssetChange ?? "-",
              item.investmentReturn ?? "-",
              item.generatedAt,
            ])}
          />
        )}
      </section>
      {reviews[0] ? (
        <section className="dashboard-card">
          <h3>{reviews[0].reviewMonth} 复盘详情</h3>
          <p className="body">{reviews[0].summaryText}</p>
          <p className="body">{reviews[0].riskReviewText ?? ""}</p>
          <p className="body">{reviews[0].dcaReviewText ?? ""}</p>
          <p className="body">{reviews[0].nextMonthFocusText ?? ""}</p>
        </section>
      ) : null}
    </div>
  );
}

function SettingsPage({
  settings,
  rules,
  dataSources,
  taskStatuses,
  taskLogs,
  backups,
  onSettingChange,
  onRuleChange,
  onRunTask,
  onExportData,
  onImportData,
  onRunBackup,
}: {
  settings: Setting[];
  rules: AlertRule[];
  dataSources: DataSource[];
  taskStatuses: TaskStatus[];
  taskLogs: TaskLog[];
  backups: BackupRecord[];
  onSettingChange: (key: string, value: string) => void;
  onRuleChange: (rule: AlertRule, patch: Partial<AlertRule>) => void;
  onRunTask: (taskType: string) => void;
  onExportData: () => void;
  onImportData: (file: File) => void;
  onRunBackup: () => void;
}) {
  return (
    <div className="settings-grid">
      <section className="dashboard-card">
        <h3>设置</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>名称</th><th>值</th><th>单位</th><th>说明</th></tr></thead>
            <tbody>
              {settings.map((item) => (
                <tr key={item.id}>
                  <td>{item.settingName}</td>
                  <td>
                    <input
                      className="table-input"
                      disabled={!item.isEditable}
                      defaultValue={item.settingValue}
                      onBlur={(event) => {
                        if (event.target.value !== item.settingValue) onSettingChange(item.settingKey, event.target.value);
                      }}
                    />
                  </td>
                  <td>{item.unit ?? "-"}</td>
                  <td>{item.description ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="dashboard-card">
        <h3>提醒规则</h3>
        <div className="table-wrap">
          <table>
            <thead><tr><th>规则</th><th>启用</th><th>阈值</th><th>级别</th><th>间隔</th></tr></thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.ruleName}</td>
                  <td><input checked={rule.isEnabled} onChange={(event) => onRuleChange(rule, { isEnabled: event.target.checked })} type="checkbox" /></td>
                  <td><input className="table-input compact-input" defaultValue={rule.thresholdValue} onBlur={(event) => event.target.value !== rule.thresholdValue && onRuleChange(rule, { thresholdValue: event.target.value })} /></td>
                  <td>
                    <select defaultValue={rule.alertLevel} onChange={(event) => onRuleChange(rule, { alertLevel: event.target.value })}>
                      <option value="strong">strong</option>
                      <option value="must">must</option>
                      <option value="attention">attention</option>
                      <option value="review">review</option>
                    </select>
                  </td>
                  <td><input className="table-input compact-input" defaultValue={rule.repeatIntervalDays ?? ""} onBlur={(event) => onRuleChange(rule, { repeatIntervalDays: Number(event.target.value || 0) })} type="number" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="dashboard-card">
        <h3>数据源状态</h3>
        <Table headers={["名称", "类型", "启用", "健康状态"]} rows={dataSources.map((item) => [item.sourceName, item.sourceType, item.isEnabled ? "是" : "否", item.healthStatus])} />
      </section>
      <section className="dashboard-card">
        <div className="card-header">
          <h3>导入导出与备份</h3>
          <button className="primary-button compact" onClick={onRunBackup} type="button">手动备份</button>
        </div>
        <div className="form-actions">
          <button className="secondary-button" onClick={onExportData} type="button">导出 JSON</button>
          <label className="secondary-button file-button">
            导入 JSON
            <input
              accept="application/json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onImportData(file);
                event.target.value = "";
              }}
              type="file"
            />
          </label>
        </div>
        {backups.length === 0 ? (
          <EmptyBlock title="暂无备份" body="点击手动备份或等待自动备份任务后，会写入 backups 表。" />
        ) : (
          <Table
            headers={["类型", "文件", "大小", "状态", "时间"]}
            rows={backups.map((item) => [
              item.backupType,
              item.fileName,
              item.fileSizeBytes ?? "-",
              item.status,
              item.createdAt,
            ])}
          />
        )}
      </section>
      <section className="dashboard-card">
        <h3>任务状态</h3>
        {taskStatuses.length === 0 ? (
          <EmptyBlock title="暂无任务状态" body="后端启动后会注册本地 APScheduler 任务。" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>任务名称</th><th>启用状态</th><th>上次运行</th><th>下次运行</th><th>最近结果</th><th>操作</th></tr></thead>
              <tbody>
                {taskStatuses.map((item) => (
                  <tr key={item.taskType}>
                    <td>{item.taskName}</td>
                    <td>{item.isEnabled ? "启用" : "停用"}</td>
                    <td>{formatDateTime(item.lastRunAt)}</td>
                    <td>{formatDateTime(item.nextRunAt)}</td>
                    <td>{sanitizeTechnicalMessage(item.errorMessage) || item.lastMessage || item.lastStatus || "-"}</td>
                    <td>
                      <button className="secondary-button compact" onClick={() => onRunTask(item.taskType)} type="button">
                        立即运行
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="dashboard-card">
        <h3>任务日志</h3>
        {taskLogs.length === 0 ? (
          <EmptyBlock title="暂无任务日志" body="后台任务运行后会写入 task_logs。" />
        ) : (
          <Table headers={["任务", "状态", "开始时间", "消息"]} rows={taskLogs.map((item) => [item.taskName, item.status, item.startedAt, item.message || sanitizeTechnicalMessage(item.errorMessage) || "-"])} />
        )}
      </section>
    </div>
  );
}

function StatusPill({ connection }: { connection: ConnectionState }) {
  const label =
    connection.status === "connected" ? "后端在线" : connection.status === "failed" ? "后端离线" : "检测中";
  return <div className={`status-pill status-${connection.status}`}>{label}</div>;
}

function EmptyBlock({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-block">
      <div className="empty-mark small" aria-hidden="true">0</div>
      <h3>{title}</h3>
      <p className="body">{body}</p>
    </div>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: Array<Array<ReactNode>> }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function assetToDraft(asset: Asset): AssetDraft {
  return {
    ...emptyDraft,
    name: asset.name,
    assetType: asset.assetType,
    subType: asset.subType ?? "",
    platform: asset.platform,
    currentValue: asset.currentValue ?? "",
    costAmount: asset.costAmount ?? "",
    holdingCostPrice: asset.holdingCostPrice ?? "",
    holdingGain: asset.holdingGain ?? "",
    cumulativeGain: asset.cumulativeGain ?? "",
    principalAmount: asset.principalAmount ?? "",
    productCode: asset.productCode ?? "",
    market: asset.market ?? "",
    holdingShare: asset.holdingShare ?? "",
    latestPrice: asset.latestPrice ?? "",
    priceDate: asset.priceDate ?? "",
    dailyChangePct: asset.dailyChangePct ?? "",
    dailyIncomeAmount: asset.dailyIncomeAmount ?? "",
    dataSourceType: asset.dataSourceType ?? "",
    dataStatus: asset.dataStatus ?? "",
    expectedReturnRate: asset.expectedReturnRate ?? "",
    entryDate: asset.entryDate ?? asset.createdAt.slice(0, 10),
    maturityDate: asset.maturityDate ?? "",
    liquidityLevel: asset.liquidityLevel ?? "",
    repaymentDate: asset.repaymentDate ?? "",
    interestRate: asset.interestRate ?? "",
    targetTag: asset.targetTag ?? "",
    note: asset.note ?? "",
    isDca: asset.isDca,
    dcaAmount: asset.dcaAmount ?? "",
    dcaFrequency: asset.dcaFrequency ?? "",
    dcaDay: asset.dcaDay ?? "",
    dcaNextDate: asset.dcaNextDate ?? "",
  };
}

function draftToPayload(draft: AssetDraft): AssetPayload {
  const payload: AssetPayload = {
    assetType: draft.assetType,
    name: draft.name,
    platform: draft.platform,
    subType: optional(draft.subType),
    currentValue: numberValue(draft.currentValue),
    entryDate: optional(draft.entryDate),
    targetTag: optional(draft.targetTag),
    note: optional(draft.note),
  };
  if (draft.assetType === "cash") {
    payload.latestPrice = optionalNumber(draft.expectedReturnRate || draft.latestPrice);
    payload.expectedReturnRate = optionalNumber(draft.expectedReturnRate);
    payload.priceDate = optional(draft.priceDate);
    payload.dailyIncomeAmount = optionalNumber(draft.dailyIncomeAmount);
    payload.dataSourceType = optional(draft.dataSourceType);
    payload.dataStatus = optional(draft.dataStatus);
  }
  if (draft.assetType === "fixed_income") {
    const fixedIncomeCost = nullableNumber(draft.costAmount);
    payload.productCode = optional(draft.productCode);
    payload.principalAmount = optionalNumber(draft.principalAmount);
    payload.costAmount = fixedIncomeCost ?? optionalNumber(draft.principalAmount);
    payload.holdingShare = optionalNumber(draft.holdingShare);
    payload.holdingCostPrice = nullableNumber(draft.holdingCostPrice);
    payload.holdingGain = nullableNumber(draft.holdingGain);
    payload.cumulativeGain = nullableNumber(draft.cumulativeGain);
    payload.latestPrice = optionalNumber(draft.latestPrice);
    payload.priceDate = optional(draft.priceDate);
    payload.dailyChangePct = optionalNumber(draft.dailyChangePct);
    payload.expectedReturnRate = optionalNumber(draft.expectedReturnRate);
    payload.maturityDate = optional(draft.maturityDate);
    payload.liquidityLevel = optional(draft.liquidityLevel);
  }
  if (draft.assetType === "equity") {
    const stockAccount = isStockAccountDraft(draft);
    payload.productCode = optional(draft.productCode);
    payload.market = optional(draft.market);
    payload.holdingShare = stockAccount ? optionalNumber(draft.holdingShare) : numberValue(draft.holdingShare);
    payload.costAmount = nullableNumber(draft.costAmount);
    payload.holdingCostPrice = stockAccount ? undefined : nullableNumber(draft.holdingCostPrice);
    payload.holdingGain = nullableNumber(draft.holdingGain);
    payload.cumulativeGain = nullableNumber(draft.cumulativeGain);
    payload.latestPrice = stockAccount ? undefined : optionalNumber(draft.latestPrice);
    payload.priceDate = stockAccount ? undefined : optional(draft.priceDate);
    payload.dailyChangePct = stockAccount ? undefined : optionalNumber(draft.dailyChangePct);
    payload.dataSourceType = optional(draft.dataSourceType);
    payload.dataStatus = optional(draft.dataStatus);
    payload.isDca = stockAccount || isStockHoldingDraft(draft) ? false : draft.isDca;
    if (!stockAccount && !isStockHoldingDraft(draft) && draft.isDca) {
      payload.dcaAmount = optionalNumber(draft.dcaAmount);
      payload.dcaFrequency = optional(draft.dcaFrequency);
      payload.dcaDay = draft.dcaFrequency === "daily" ? undefined : optional(draft.dcaDay);
      payload.dcaNextDate = optional(draft.dcaNextDate);
    }
  }
  if (draft.assetType === "debt") {
    payload.repaymentDate = optional(draft.repaymentDate);
    payload.interestRate = optionalNumber(draft.interestRate);
  }
  return payload;
}

function applyInvestmentMetricDerivation(draft: AssetDraft, changedKey: keyof AssetDraft): AssetDraft {
  if (draft.assetType !== "equity" && draft.assetType !== "fixed_income") return draft;
  const currentValue = parseDraftNumber(draft.currentValue);
  const share = parseDraftNumber(draft.holdingShare);
  const latestPrice = parseDraftNumber(draft.latestPrice);
  const holdingGain = parseDraftNumber(draft.holdingGain);
  const holdingCostPrice = parseDraftNumber(draft.holdingCostPrice);
  const costAmount = parseDraftNumber(draft.costAmount);
  const next = { ...draft };

  if ((changedKey === "latestPrice" || changedKey === "holdingShare") && latestPrice !== null && share !== null && share > 0) {
    next.currentValue = formatDraftNumber(latestPrice * share, 2);
  }

  if (changedKey === "holdingGain" && currentValue !== null && holdingGain !== null) {
    const holdingCost = currentValue - holdingGain;
    if (holdingCost >= 0) {
      next.costAmount = formatDraftNumber(holdingCost, 2);
      if (share !== null && share > 0) {
        next.holdingCostPrice = formatDraftNumber(holdingCost / share, 4);
      }
    }
    return next;
  }

  if (changedKey === "holdingCostPrice" && currentValue !== null && holdingCostPrice !== null && share !== null && share > 0) {
    const holdingCost = holdingCostPrice * share;
    next.costAmount = formatDraftNumber(holdingCost, 2);
    next.holdingGain = formatDraftNumber(currentValue - holdingCost, 2);
    return next;
  }

  if (changedKey === "costAmount" && currentValue !== null && costAmount !== null) {
    if (share !== null && share > 0) {
      next.holdingCostPrice = formatDraftNumber(costAmount / share, 4);
    }
    next.holdingGain = formatDraftNumber(currentValue - costAmount, 2);
    return next;
  }

  if ((changedKey === "currentValue" || changedKey === "holdingShare" || changedKey === "latestPrice") && parseDraftNumber(next.currentValue) !== null) {
    const nextCurrentValue = parseDraftNumber(next.currentValue);
    const derivedCost = holdingCostPrice !== null && share !== null && share > 0 ? holdingCostPrice * share : costAmount;
    if (derivedCost !== null && nextCurrentValue !== null) {
      next.costAmount = formatDraftNumber(derivedCost, 2);
      next.holdingGain = formatDraftNumber(nextCurrentValue - derivedCost, 2);
    } else if (holdingGain !== null && nextCurrentValue !== null) {
      const holdingCost = nextCurrentValue - holdingGain;
      next.costAmount = formatDraftNumber(holdingCost, 2);
      if (share !== null && share > 0) {
        next.holdingCostPrice = formatDraftNumber(holdingCost / share, 4);
      }
    }
  }
  return next;
}

function parseDraftNumber(value: string | undefined) {
  if (value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatDraftNumber(value: number, digits: number) {
  if (!Number.isFinite(value)) return "";
  return value.toFixed(digits);
}

function normalizeDraftPatch(raw: Record<string, unknown>): Partial<AssetDraft> {
  const patch: Partial<AssetDraft> = {};
  const stringFields: Array<keyof AssetDraft> = [
    "name",
    "assetType",
    "subType",
    "platform",
    "currentValue",
    "costAmount",
    "holdingCostPrice",
    "holdingGain",
    "cumulativeGain",
    "principalAmount",
    "productCode",
    "market",
    "holdingShare",
    "latestPrice",
    "priceDate",
    "dailyChangePct",
    "dailyIncomeAmount",
    "dataSourceType",
    "dataStatus",
    "expectedReturnRate",
    "entryDate",
    "maturityDate",
    "liquidityLevel",
    "repaymentDate",
    "interestRate",
    "targetTag",
    "note",
    "dcaAmount",
    "dcaFrequency",
    "dcaDay",
    "dcaNextDate",
  ];
  for (const field of stringFields) {
    const value = raw[field];
    if (value !== undefined && value !== null) {
      patch[field] = String(value) as never;
    }
  }
  if (typeof raw.isDca === "boolean") {
    patch.isDca = raw.isDca;
  }
  return applyAutoSubType(patch);
}

function normalizeAssetImportDrafts(raw: Record<string, unknown>): AssetImportDraft[] {
  const value = raw.assets;
  const records = Array.isArray(value) ? value : [];
  const normalized = records
    .map((item): AssetImportDraft | null => {
      if (!item || typeof item !== "object") return null;
      const record = normalizeDraftPatch(item as Record<string, unknown>);
      if (!record.productCode && !record.name) return null;
      return {
        assetType: "equity",
        name: record.name ?? "",
        platform: record.platform ?? "待确认平台",
        productCode: record.productCode ?? "",
        currentValue: record.currentValue ?? "",
        holdingShare: record.holdingShare ?? "",
        holdingCostPrice: record.holdingCostPrice,
        holdingGain: record.holdingGain,
        cumulativeGain: record.cumulativeGain,
        latestPrice: record.latestPrice,
        priceDate: record.priceDate,
        market: record.market ?? "CN_FUND",
      };
    })
    .filter((item): item is AssetImportDraft => item !== null);
  if (normalized.length > 0) return normalized;

  const single = normalizeDraftPatch(raw);
  const hasAssetField = Boolean(single.name || single.productCode || single.currentValue || single.holdingShare || single.holdingGain || single.cumulativeGain);
  if (!hasAssetField) return [];
  return [
    {
      assetType: "equity",
      name: single.name ?? "",
      platform: single.platform ?? "待确认平台",
      productCode: single.productCode ?? "",
      currentValue: single.currentValue ?? "",
      holdingShare: single.holdingShare ?? "",
      holdingCostPrice: single.holdingCostPrice,
      holdingGain: single.holdingGain,
      cumulativeGain: single.cumulativeGain,
      latestPrice: single.latestPrice,
      priceDate: single.priceDate,
      market: single.market ?? "CN_FUND",
    },
  ];
}

function hasMeaningfulAssetDraft(raw: Record<string, unknown>) {
  return normalizeAssetImportDrafts(raw).length > 0 || ["name", "productCode", "currentValue", "holdingShare", "holdingGain", "cumulativeGain", "latestPrice", "priceDate"].some((key) => {
    const value = raw[key];
    return value !== undefined && value !== null && value !== "";
  });
}

function normalizeTransactionDraftPatch(raw: Record<string, unknown>): Partial<TransactionDraft> {
  const patch: Partial<TransactionDraft> = {};
  const transactionType = raw.transactionType;
  if (transactionType === "buy" || transactionType === "sell") {
    patch.mode = transactionType;
  }
  const stringFields: Array<keyof TransactionDraft> = [
    "targetAssetId",
    "transactionDate",
    "amount",
    "share",
    "price",
    "feeRate",
    "inAmount",
    "inShare",
    "inPrice",
    "feeAmount",
    "note",
  ];
  for (const field of stringFields) {
    const value = raw[field];
    if (value !== undefined && value !== null) {
      patch[field] = String(value) as never;
    }
  }
  if (raw.tradeTiming === "before_15" || raw.tradeTiming === "after_15") {
    patch.tradeTiming = raw.tradeTiming;
  }
  return patch;
}

function normalizeTransactionImportDrafts(raw: Record<string, unknown>, fallback: TransactionDraft): TransactionImportDraft[] {
  const value = raw.transactions;
  const records = Array.isArray(value) ? value : [];
  const parsed = records
    .map((item): TransactionImportDraft | null => {
      if (!item || typeof item !== "object") return null;
      const record = item as Record<string, unknown>;
      const transactionType = record.transactionType === "sell" ? "sell" : record.transactionType === "buy" ? "buy" : null;
      const transactionDate = typeof record.transactionDate === "string" ? record.transactionDate : fallback.transactionDate;
      if (!transactionType) return null;
      return {
        transactionType,
        transactionDate,
        tradeTiming: record.tradeTiming === "after_15" ? "after_15" : "before_15",
        amount: record.amount === undefined || record.amount === null ? undefined : String(record.amount),
        share: record.share === undefined || record.share === null ? undefined : String(record.share),
        feeAmount: record.feeAmount === undefined || record.feeAmount === null ? undefined : String(record.feeAmount),
        feeRate: record.feeRate === undefined || record.feeRate === null ? undefined : String(record.feeRate),
        note: record.note === undefined || record.note === null ? undefined : String(record.note),
      };
    })
    .filter((item): item is TransactionImportDraft => item !== null);
  if (parsed.length > 0) return parsed;

  const transactionType = raw.transactionType === "sell" ? "sell" : raw.transactionType === "buy" ? "buy" : null;
  if (!transactionType) return [];
  const amount = raw.amount === undefined || raw.amount === null ? undefined : String(raw.amount);
  const share = raw.share === undefined || raw.share === null ? undefined : String(raw.share);
  if (transactionType === "buy" && !amount) return [];
  if (transactionType === "sell" && !amount && !share) return [];
  return [
    {
      transactionType,
      transactionDate: typeof raw.transactionDate === "string" ? raw.transactionDate : fallback.transactionDate,
      tradeTiming: raw.tradeTiming === "after_15" ? "after_15" : "before_15",
      amount,
      share,
      feeAmount: raw.feeAmount === undefined || raw.feeAmount === null ? undefined : String(raw.feeAmount),
      feeRate: raw.feeRate === undefined || raw.feeRate === null ? undefined : String(raw.feeRate),
      note: raw.note === undefined || raw.note === null ? undefined : String(raw.note),
    },
  ];
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error("读取截图文件失败"));
    reader.readAsDataURL(file);
  });
}

async function imageFileToOcrDataUrl(file: File): Promise<string> {
  const dataUrl = await readFileAsDataUrl(file);
  const image = await loadImage(dataUrl);
  const maxWidth = 1600;
  const maxHeight = 2600;
  const ratio = Math.min(1, maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
  const width = Math.max(1, Math.round(image.naturalWidth * ratio));
  const height = Math.max(1, Math.round(image.naturalHeight * ratio));
  if (ratio === 1 && file.size <= 900 * 1024) return dataUrl;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return dataUrl;
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.86);
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("截图图片加载失败，请换一张清晰截图重试。"));
    image.src = src;
  });
}

function typeDescription(type: AssetType) {
  return {
    cash: "银行活期、余额宝、现金管理",
    fixed_income: "定期、理财、债基、存单",
    equity: "基金、ETF、股票",
    debt: "信用卡、贷款、分期",
  }[type];
}

function formatMoney(value?: string | number | null) {
  const number = Number(value ?? 0);
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number);
}

function formatAmount(value: ReactNode, isVisible: boolean): ReactNode {
  return isVisible ? value : <MaskedAmount />;
}

function formatPrice(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return number.toFixed(4);
}

function formatQuantity(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return number.toFixed(2);
}

function formatDateTime(value?: string | null) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

function formatSignedMoney(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const formatted = formatMoney(Math.abs(value));
  if (value > 0) return `+${formatted}`;
  if (value < 0) return `-${formatted}`;
  return formatted;
}

function formatPct(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function formatYieldRate(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${number.toFixed(2)}%`;
}

function formatNullablePct(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function toNumberOrNull(value?: string | number | null) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isNaN(number) ? null : number;
}

function readAmountVisibilityPreference() {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(AMOUNT_VISIBLE_STORAGE_KEY) === "true";
}

function estimateDailyIncome(asset: Asset, prices: PriceRecord[] = []) {
  const latestManualIncome = [...prices]
    .filter((price) => price.isValid && price.dailyIncomeAmount !== null && price.dailyIncomeAmount !== undefined)
    .sort((left, right) => {
      const leftTime = new Date(`${left.priceDate}T00:00:00`).getTime();
      const rightTime = new Date(`${right.priceDate}T00:00:00`).getTime();
      if (leftTime !== rightTime) return leftTime - rightTime;
      return new Date(left.fetchedAt).getTime() - new Date(right.fetchedAt).getTime();
    })
    .pop();
  if (latestManualIncome?.dailyIncomeAmount !== null && latestManualIncome?.dailyIncomeAmount !== undefined) {
    return { value: Number(latestManualIncome.dailyIncomeAmount), source: "平台/手动" };
  }
  if (asset.dailyIncomeAmount !== null && asset.dailyIncomeAmount !== undefined) {
    return { value: Number(asset.dailyIncomeAmount), source: "平台/手动" };
  }

  const share = Number(asset.holdingShare ?? 0);
  if (asset.assetType !== "equity" || Number.isNaN(share) || share <= 0) return { value: null, source: "缺少份额" };

  const validPrices = [...prices]
    .filter((price) => price.isValid && price.price)
    .sort((left, right) => {
      const leftTime = new Date(`${left.priceDate}T00:00:00`).getTime();
      const rightTime = new Date(`${right.priceDate}T00:00:00`).getTime();
      if (leftTime !== rightTime) return leftTime - rightTime;
      return new Date(left.fetchedAt).getTime() - new Date(right.fetchedAt).getTime();
    });
  const latest = validPrices[validPrices.length - 1];
  const previous = [...validPrices].reverse().find((price) => latest && price.priceDate < latest.priceDate);
  if (latest && previous) {
    const latestRecordPrice = Number(latest.price);
    const previousRecordPrice = Number(previous.price);
    if (!Number.isNaN(latestRecordPrice) && !Number.isNaN(previousRecordPrice)) {
      return { value: (latestRecordPrice - previousRecordPrice) * share, source: "净值差" };
    }
  }

  const change = Number(asset.dailyChangePct);
  const latestPrice = Number(asset.latestPrice ?? 0);
  if (!Number.isNaN(change) && !Number.isNaN(latestPrice) && latestPrice > 0 && change > -100) {
    const previousPrice = latestPrice / (1 + change / 100);
    return { value: (latestPrice - previousPrice) * share, source: "涨幅反推" };
  }

  return { value: null, source: "缺少数据" };
}

function optional(value: string) {
  return value.trim() ? value.trim() : undefined;
}

function numberValue(value: string) {
  return Number(value || 0);
}

function optionalNumber(value: string) {
  return value === "" ? undefined : Number(value);
}

function nullableNumber(value: string) {
  return value.trim() === "" ? null : Number(value);
}

function optionalNumberValue(value: string) {
  return value.trim() === "" ? undefined : Number(value);
}
