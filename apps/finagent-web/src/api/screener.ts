import apiClient from './index';
import { toCamelCase } from './utils';

// ============ API Interfaces ============

export interface ScreenerScreenRequest {
  strategy: string;
  market?: string;
  maxCandidates?: number;
  validate?: boolean;
  analyzeAfterScreen?: boolean;
}

export interface ScreenerCandidate {
  code: string;
  name: string;
  reason: string;
  score?: number;
  metadata?: Record<string, unknown>;
}

export interface ScreenerFailedItem {
  code: string;
  name: string;
  error: string;
}

export interface ScreenerResultResponse {
  taskId: string;
  strategy: string;
  status: string;
  candidates: ScreenerCandidate[];
  failed: ScreenerFailedItem[];
  totalAnalyzed: number;
  validationResults?: Record<string, unknown>;
}

export interface ScreenerStrategyResponse {
  name: string;
  displayName: string;
  description: string;
  category: string;
  defaultPriority: number;
}

export interface TaskAccepted {
  taskId: string;
  status: string;
  message: string;
}

// ============ Screener API ============

export interface BoardDataResponse {
  tradeDate: string;
  lhbCount: number;
  limitUpCount: number;
  previousLimitUpCount: number;
  conceptCount: number;
  chainLadder: Record<string, Record<string, unknown>[]>;
  concepts: Record<string, unknown>[];
  limitUpStocks: Record<string, unknown>[];
  lhbStocks: Record<string, unknown>[];
}

export const screenerApi = {
  /**
   * Create a screener task
   */
  screen: async (data: ScreenerScreenRequest): Promise<TaskAccepted> => {
    const requestData = {
      strategy: data.strategy,
      market: data.market || 'cn',
      max_candidates: data.maxCandidates || 10,
      data_validation: data.validate || false,
      analyze_after_screen: data.analyzeAfterScreen || false,
    };

    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/screener/screen',
      requestData
    );

    return toCamelCase<TaskAccepted>(response.data);
  },

  /**
   * Get screener result by task_id
   */
  getResult: async (taskId: string): Promise<ScreenerResultResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/screener/results/${taskId}`
    );
    return toCamelCase<ScreenerResultResponse>(response.data);
  },

  /**
   * List available screener strategies
   */
  listStrategies: async (): Promise<ScreenerStrategyResponse[]> => {
    const response = await apiClient.get<Record<string, unknown>[]>(
      '/api/v1/screener/strategies'
    );
    return (response.data as Record<string, unknown>[]).map((item) =>
      toCamelCase<ScreenerStrategyResponse>(item)
    );
  },

  /**
   * Get screener strategy details
   */
  getStrategy: async (name: string): Promise<ScreenerStrategyResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/screener/strategies/${name}`
    );
    return toCamelCase<ScreenerStrategyResponse>(response.data);
  },

  /**
   * Get board play strategy data (龙虎榜 + 连板天梯)
   */
  getBoardData: async (tradeDate?: string): Promise<BoardDataResponse> => {
    const params = tradeDate ? { trade_date: tradeDate } : {};
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/screener/board',
      { params }
    );
    return toCamelCase<BoardDataResponse>(response.data);
  },
};
