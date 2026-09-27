export type HealthResponse = {
  status: "ok" | "degraded" | string;
  database: "ok" | "error" | string;
  dataVersion: string;
};

export type AssetType = "cash" | "fixed_income" | "equity" | "debt";
export type AssetStatus = "active" | "inactive" | "closed";

export type Asset = {
  id: string;
  ownerId: string;
  name: string;
  assetType: AssetType;
  subType?: string | null;
  platform: string;
  currency: string;
  currentValue: string;
  costAmount?: string | null;
  holdingCostPrice?: string | null;
  holdingGain?: string | null;
  cumulativeGain?: string | null;
  cumulativeNetBasis?: string | null;
  principalAmount?: string | null;
  productCode?: string | null;
  market?: string | null;
  holdingShare?: string | null;
  latestPrice?: string | null;
  priceDate?: string | null;
  dailyChangePct?: string | null;
  dailyIncomeAmount?: string | null;
  dataSourceType?: string | null;
  dataStatus: string;
  priceErrorMessage?: string | null;
  expectedReturnRate?: string | null;
  entryDate?: string | null;
  maturityDate?: string | null;
  liquidityLevel?: string | null;
  repaymentDate?: string | null;
  interestRate?: string | null;
  isDca: boolean;
  dcaAmount?: string | null;
  dcaFrequency?: string | null;
  dcaDay?: string | null;
  dcaNextDate?: string | null;
  targetTag?: string | null;
  note?: string | null;
  assetStatus: AssetStatus;
  createdAt: string;
  updatedAt: string;
};

export type AssetPayload = {
  [key: string]: unknown;
  name?: string;
  assetType?: AssetType;
  platform?: string;
  currentValue?: number | string;
};

export type DashboardSummary = {
  totalAsset: string;
  totalDebt: string;
  netAsset: string;
  cashValue: string;
  fixedIncomeValue: string;
  equityValue: string;
  debtValue: string;
  assetCount: number;
  activeAssetCount: number;
  cashCoverageMonths?: string | null;
  monthNetAssetChange?: string | null;
  portfolioDrawdownPct?: string | null;
  dataStatus: string;
  categorySummary: Array<{ assetType: AssetType; value: string; ratio: string; count: number }>;
};

export type Setting = {
  id: string;
  settingKey: string;
  settingName: string;
  settingValue: string;
  valueType: string;
  unit?: string | null;
  category: string;
  description?: string | null;
  isEditable: boolean;
};

export type AlertRule = {
  id: string;
  ruleCode: string;
  ruleName: string;
  category: string;
  metricKey: string;
  operator: string;
  thresholdValue: string;
  thresholdUnit?: string | null;
  alertLevel: string;
  checkFrequency: string;
  repeatIntervalDays?: number | null;
  isEnabled: boolean;
  isEditable: boolean;
};

export type DataSource = {
  id: string;
  sourceType: string;
  sourceName: string;
  priority: number;
  isEnabled: boolean;
  supportedMarkets?: string | null;
  healthStatus: string;
  lastSuccessAt?: string | null;
  lastFailedAt?: string | null;
  lastErrorMessage?: string | null;
};

export type TaskLog = {
  id: string;
  taskType: string;
  taskName: string;
  status: string;
  startedAt: string;
  finishedAt?: string | null;
  message?: string | null;
  errorMessage?: string | null;
};

export type TaskStatus = {
  taskType: string;
  taskName: string;
  isEnabled: boolean;
  lastRunAt?: string | null;
  nextRunAt?: string | null;
  lastStatus?: string | null;
  lastMessage?: string | null;
  errorMessage?: string | null;
};

export type TaskRunResponse = {
  taskLogId: string;
  taskType: string;
  status: string;
  message?: string | null;
  errorMessage?: string | null;
  successCount: number;
  failedCount: number;
};

export type BackupRecord = {
  id: string;
  ownerId: string;
  backupType: string;
  fileName: string;
  filePath: string;
  fileSizeBytes?: number | null;
  dataVersion: string;
  status: string;
  errorMessage?: string | null;
  createdAt: string;
};

export type AlertRecord = {
  id: string;
  alertLevel: string;
  title: string;
  reason: string;
  status: string;
  triggeredAt: string;
};

export type MonthlyReview = {
  id: string;
  ownerId: string;
  reviewMonth: string;
  startNetAsset?: string | null;
  endNetAsset: string;
  netAssetChange?: string | null;
  investmentReturn?: string | null;
  newContribution?: string | null;
  maxDrawdownPct?: string | null;
  summaryText: string;
  riskReviewText?: string | null;
  dcaReviewText?: string | null;
  nextMonthFocusText?: string | null;
  dataCompletenessStatus: string;
  generatedAt: string;
};

export type ListResponse<T> = { items: T[]; total: number };

export type PriceUpdateResult = {
  assetId: string;
  productCode?: string | null;
  success: boolean;
  priceRecord: {
    id: string;
    productCode: string;
    priceDate: string;
    price: string;
    dailyChangePct?: string | null;
    dailyIncomeAmount?: string | null;
    sourceType: string;
    fetchedAt: string;
    dataStatus: string;
    isValid: boolean;
    errorMessage?: string | null;
  };
};

export type PriceRecord = PriceUpdateResult["priceRecord"];

export type TransactionRecord = {
  id: string;
  ownerId: string;
  assetId: string;
  relatedAssetId?: string | null;
  relatedTransactionId?: string | null;
  transactionType: string;
  amount: string;
  share?: string | null;
  price?: string | null;
  feeAmount?: string | null;
  feeRate?: string | null;
  tradeTiming?: string | null;
  transactionDate: string;
  source: string;
  note?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type TransactionPayload = {
  transactionType: "buy" | "sell" | "cash_dividend";
  amount?: number;
  share?: number;
  price?: number;
  feeAmount?: number;
  feeRate?: number;
  tradeTiming?: "before_15" | "after_15";
  transactionDate: string;
  source?: string;
  note?: string;
};

export type ConversionPayload = {
  targetAssetId: string;
  transactionDate: string;
  outAmount: number;
  outShare?: number;
  outPrice?: number;
  inAmount?: number;
  inShare?: number;
  inPrice?: number;
  feeAmount?: number;
  feeRate?: number;
  tradeTiming?: "before_15" | "after_15";
  source?: string;
  note?: string;
};

export type ConversionResponse = {
  outTransaction: TransactionRecord;
  inTransaction: TransactionRecord;
};

export type FundBasicInfo = {
  productCode: string;
  assetType?: AssetType | null;
  subType?: string | null;
  name?: string | null;
  market: string;
  latestPrice?: string | null;
  priceDate?: string | null;
  dailyChangePct?: string | null;
  dailyIncomeAmount?: string | null;
  sourceType: string;
  dataStatus: string;
  errorMessage?: string | null;
};

export type BenchmarkPoint = {
  priceDate: string;
  close: string;
  dailyChangePct?: string | null;
};

export type BenchmarkHistory = {
  code: string;
  name: string;
  sourceType: string;
  dataStatus: string;
  errorMessage?: string | null;
  items: BenchmarkPoint[];
};

export type ScreenshotParseResult = {
  status: "parsed" | "needs_review" | string;
  message: string;
  draft: Record<string, unknown>;
  rawText?: string | null;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")).replace(/\/$/, "");

async function request<T>(path: string, options: RequestInit = {}, timeoutMs?: number): Promise<T> {
  const controller = timeoutMs ? new AbortController() : null;
  const timeoutId = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      ...options,
      signal: controller?.signal ?? options.signal,
    });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") {
      throw new Error("请求超时，请确认本地 OCR 服务或 PaddleOCR 模型已加载完成后重试。");
    }
    throw caught;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  if (!response.ok) {
    let detail = `API request failed with ${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch {
      // Keep the default message when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  dashboardSummary: () => request<DashboardSummary>("/api/dashboard/summary"),
  assets: (includeInactive = false) =>
    request<ListResponse<Asset>>(`/api/assets?includeInactive=${includeInactive ? "true" : "false"}`),
  createAsset: (payload: AssetPayload) =>
    request<Asset>("/api/assets", { method: "POST", body: JSON.stringify(payload) }),
  updateAsset: (id: string, payload: AssetPayload) =>
    request<Asset>(`/api/assets/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deactivateAsset: (id: string) => request<Asset>(`/api/assets/${id}/deactivate`, { method: "POST" }),
  deleteAsset: (id: string) => request<{ status: string; assetId: string }>(`/api/assets/${id}`, { method: "DELETE" }),
  updateAssetPrice: (id: string) => request<PriceUpdateResult>(`/api/assets/${id}/price/update`, { method: "POST" }),
  assetPrices: (id: string) => request<ListResponse<PriceRecord>>(`/api/assets/${id}/prices`),
  assetTransactions: (id: string) => request<ListResponse<TransactionRecord>>(`/api/assets/${id}/transactions`),
  createAssetTransaction: (id: string, payload: TransactionPayload) =>
    request<TransactionRecord>(`/api/assets/${id}/transactions`, { method: "POST", body: JSON.stringify(payload) }),
  updateAssetTransaction: (assetId: string, transactionId: string, payload: { amount: number | string }) =>
    request<TransactionRecord>(`/api/assets/${assetId}/transactions/${transactionId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  createAssetConversion: (id: string, payload: ConversionPayload) =>
    request<ConversionResponse>(`/api/assets/${id}/transactions/convert`, { method: "POST", body: JSON.stringify(payload) }),
  fundBasicInfo: (productCode: string, options?: { assetType?: AssetType; assetSubType?: string; market?: string }) => {
    const params = new URLSearchParams();
    if (options?.assetType) params.set("assetType", options.assetType);
    if (options?.assetSubType) params.set("assetSubType", options.assetSubType);
    if (options?.market) params.set("market", options.market);
    const query = params.toString();
    return request<FundBasicInfo>(`/api/funds/${encodeURIComponent(productCode)}/basic-info${query ? `?${query}` : ""}`);
  },
  benchmarkHistory: (code: string, startDate: string, endDate: string) =>
    request<BenchmarkHistory>(
      `/api/funds/benchmarks/${encodeURIComponent(code)}/history?startDate=${encodeURIComponent(startDate)}&endDate=${encodeURIComponent(endDate)}`,
    ),
  parseAssetScreenshot: (payload: { fileName: string; imageBase64: string }) =>
    request<ScreenshotParseResult>("/api/funds/screenshot/parse", { method: "POST", body: JSON.stringify(payload) }, 180000),
  manualPrice: (id: string, payload: { priceDate: string; price: number; currentValue?: number; dailyChangePct?: number; dailyIncomeAmount?: number }) =>
    request<PriceUpdateResult>(`/api/assets/${id}/price/manual`, { method: "POST", body: JSON.stringify(payload) }),
  runPriceUpdate: () =>
    request<{ taskLogId: string; status: string; successCount: number; failedCount: number }>(
      "/api/tasks/price-update/run",
      { method: "POST" },
    ),
  settings: () => request<ListResponse<Setting>>("/api/settings"),
  updateSetting: (key: string, settingValue: string) =>
    request<Setting>(`/api/settings/${key}`, { method: "PATCH", body: JSON.stringify({ settingValue }) }),
  alertRules: () => request<ListResponse<AlertRule>>("/api/alert-rules"),
  updateAlertRule: (ruleCode: string, payload: Partial<AlertRule>) =>
    request<AlertRule>(`/api/alert-rules/${ruleCode}`, { method: "PATCH", body: JSON.stringify(payload) }),
  dataSources: () => request<ListResponse<DataSource>>("/api/data-sources"),
  taskStatuses: () => request<ListResponse<TaskStatus>>("/api/tasks/status"),
  runTask: (taskType: string) =>
    request<TaskRunResponse>(`/api/tasks/${taskType}/run`, { method: "POST" }),
  taskLogs: () => request<ListResponse<TaskLog>>("/api/task-logs"),
  alerts: () => request<ListResponse<AlertRecord>>("/api/alerts"),
  monthlyReviews: () => request<ListResponse<MonthlyReview>>("/api/monthly-reviews"),
  generateMonthlyReview: (reviewMonth?: string) =>
    request<MonthlyReview>("/api/monthly-reviews/generate", {
      method: "POST",
      body: JSON.stringify({ reviewMonth: reviewMonth || undefined }),
    }),
  exportData: () => request<Record<string, unknown>>("/api/export"),
  importData: (data: Record<string, unknown>, confirmOverwrite: boolean) =>
    request<{ status: string; importedCounts: Record<string, number> }>("/api/import", {
      method: "POST",
      body: JSON.stringify({ data, confirmOverwrite }),
    }),
  backups: () => request<ListResponse<BackupRecord>>("/api/backups"),
  runBackup: () => request<BackupRecord>("/api/backups/run", { method: "POST" }),
};
