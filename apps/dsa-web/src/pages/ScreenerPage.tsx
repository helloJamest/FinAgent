import type React from 'react';
import { useState, useCallback, useEffect } from 'react';
import { Filter, Loader2, XCircle, CheckCircle2, ChevronDown } from 'lucide-react';
import { screenerApi } from '../api/screener';
import type { ScreenerCandidate, ScreenerFailedItem, ScreenerStrategyResponse } from '../api/screener';
import { Card, Badge, EmptyState } from '../components/common';

const INPUT_CLASS =
  'h-10 w-full rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground transition-all focus:border-cyan/50 focus:outline-none focus:ring-1 focus:ring-cyan/50';

const SCREENER_PAGE = 'min-h-screen bg-gradient-to-b from-base via-base to-base/95';

const MARKET_OPTIONS = [
  { value: 'cn', label: 'A股' },
  { value: 'hk', label: '港股' },
  { value: 'us', label: '美股' },
];

const ScreenerPage: React.FC = () => {
  const [strategies, setStrategies] = useState<ScreenerStrategyResponse[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState('');
  const [market, setMarket] = useState('cn');
  const [maxCandidates, setMaxCandidates] = useState(10);
  const [validate, setValidate] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [failed, setFailed] = useState<ScreenerFailedItem[]>([]);
  const [totalAnalyzed, setTotalAnalyzed] = useState(0);
  const [strategyOpen, setStrategyOpen] = useState(false);

  // Load strategies on mount
  useEffect(() => {
    const loadStrategies = async () => {
      try {
        const list = await screenerApi.listStrategies();
        setStrategies(list);
        if (list.length > 0 && !selectedStrategy) {
          setSelectedStrategy(list[0].name);
        }
      } catch (err) {
        console.error('Failed to load screener strategies:', err);
      }
    };
    loadStrategies();
  }, []);

  const handleScreen = useCallback(async () => {
    if (!selectedStrategy) return;
    setIsLoading(true);
    setIsPolling(true);
    setError(null);
    setCandidates([]);
    setFailed([]);
    setTotalAnalyzed(0);

    try {
      // Start screening task
      const accepted = await screenerApi.screen({
        strategy: selectedStrategy,
        market,
        maxCandidates,
        validate,
      });

      // Poll for results
      const pollInterval = setInterval(async () => {
        try {
          const result = await screenerApi.getResult(accepted.taskId || 'pending');
          if (result.status === 'completed' || result.candidates.length > 0 || result.failed.length > 0) {
            clearInterval(pollInterval);
            setCandidates(result.candidates);
            setFailed(result.failed);
            setTotalAnalyzed(result.totalAnalyzed);
            setIsPolling(false);
          }
        } catch {
          // Still running, keep polling
        }
      }, 2000);

      // Timeout after 5 minutes
      setTimeout(() => {
        clearInterval(pollInterval);
        setIsPolling(false);
        setIsLoading(false);
      }, 5 * 60 * 1000);

    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '筛选任务启动失败';
      setError(message);
      setIsLoading(false);
      setIsPolling(false);
    }
  }, [selectedStrategy, market, maxCandidates, validate]);

  const handleReset = () => {
    setCandidates([]);
    setFailed([]);
    setTotalAnalyzed(0);
    setError(null);
  };

  const selectedStrategyInfo = strategies.find((s) => s.name === selectedStrategy);

  return (
    <div className={SCREENER_PAGE}>
      <div className="mx-auto max-w-5xl px-4 py-8">
        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground">选股</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            通过策略配置、LLM 筛选、数据验证的三阶段流程，自动筛选符合条件的股票
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-500/20 bg-red-500/5 p-4">
            <div className="text-sm font-medium text-red-400">{error}</div>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left Panel: Controls */}
          <div className="lg:col-span-1">
            <Card className="p-4">
              <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
                <Filter className="h-4 w-4" />
                筛选配置
              </h2>

              {/* Strategy Selector */}
              <div className="mb-4">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  选股策略
                </label>
                <div className="relative">
                  <button
                    type="button"
                    className={`${INPUT_CLASS} flex items-center justify-between pr-8`}
                    onClick={() => setStrategyOpen(!strategyOpen)}
                  >
                    <span className="truncate">
                      {selectedStrategyInfo?.displayName || '请选择策略'}
                    </span>
                    <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${strategyOpen ? 'rotate-180' : ''}`} />
                  </button>
                  {strategyOpen && (
                    <div className="absolute z-10 mt-1 w-full rounded-xl border border-white/10 bg-surface/95 p-1 shadow-lg backdrop-blur">
                      {strategies.map((s) => (
                        <button
                          key={s.name}
                          type="button"
                          className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors hover:bg-white/10 ${
                            s.name === selectedStrategy ? 'bg-white/10 text-foreground' : 'text-muted-foreground'
                          }`}
                          onClick={() => {
                            setSelectedStrategy(s.name);
                            setStrategyOpen(false);
                          }}
                        >
                          <div className="font-medium">{s.displayName}</div>
                          <div className="truncate text-xs opacity-70">{s.description}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {selectedStrategyInfo && (
                  <p className="mt-1 text-xs text-muted-foreground">{selectedStrategyInfo.description}</p>
                )}
              </div>

              {/* Market Selector */}
              <div className="mb-4">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  市场
                </label>
                <div className="flex gap-2">
                  {MARKET_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-all ${
                        market === opt.value
                          ? 'border-cyan/50 bg-cyan/10 text-foreground'
                          : 'border-white/10 text-muted-foreground hover:border-white/20'
                      }`}
                      onClick={() => setMarket(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Max Candidates */}
              <div className="mb-4">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  最大候选数: {maxCandidates}
                </label>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={maxCandidates}
                  onChange={(e) => setMaxCandidates(Number(e.target.value))}
                  className="w-full accent-cyan"
                />
              </div>

              {/* Validate Toggle */}
              <div className="mb-6 flex items-center justify-between rounded-lg border border-white/10 p-3">
                <div>
                  <div className="text-sm text-foreground">数据验证</div>
                  <div className="text-xs text-muted-foreground">使用真实市场数据验证候选</div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={validate}
                  className={`relative h-6 w-11 rounded-full transition-colors ${validate ? 'bg-cyan' : 'bg-white/10'}`}
                  onClick={() => setValidate(!validate)}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${validate ? 'translate-x-5' : ''}`}
                  />
                </button>
              </div>

              {/* Action Buttons */}
              <button
                type="button"
                disabled={isLoading || !selectedStrategy}
                onClick={handleScreen}
                className="btn-primary w-full"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    筛选中...
                  </>
                ) : (
                  <>
                    <Filter className="h-4 w-4" />
                    开始筛选
                  </>
                )}
              </button>

              {candidates.length > 0 && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="btn-ghost mt-2 w-full text-sm"
                >
                  清除结果
                </button>
              )}
            </Card>
          </div>

          {/* Right Panel: Results */}
          <div className="lg:col-span-2">
            {isLoading && !isPolling && (
              <Card className="flex items-center justify-center p-12">
                <div className="text-center">
                  <Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan" />
                  <p className="mt-4 text-sm text-muted-foreground">正在初始化筛选任务...</p>
                </div>
              </Card>
            )}

            {isPolling && (
              <Card className="flex items-center justify-center p-12">
                <div className="text-center">
                  <Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan" />
                  <p className="mt-4 text-sm text-muted-foreground">LLM 正在分析市场数据，请稍候...</p>
                  <p className="mt-1 text-xs text-muted-foreground/60">这可能需要 1-3 分钟</p>
                </div>
              </Card>
            )}

            {!isLoading && !isPolling && candidates.length === 0 && totalAnalyzed === 0 && (
              <Card className="p-12">
                <EmptyState
                  icon={<Filter className="h-12 w-12 text-muted-foreground/50" />}
                  title="选择策略开始筛选"
                  description="配置筛选条件后点击「开始筛选」，系统将自动为您寻找符合条件的股票"
                />
              </Card>
            )}

            {!isLoading && !isPolling && candidates.length === 0 && totalAnalyzed > 0 && (
              <Card className="p-8">
                <div className="text-center">
                  <XCircle className="mx-auto h-12 w-12 text-muted-foreground/50" />
                  <h3 className="mt-4 text-lg font-semibold text-foreground">未找到符合条件的股票</h3>
                  <p className="mt-2 text-sm text-muted-foreground">
                    尝试调整策略或放宽筛选条件
                  </p>
                </div>
              </Card>
            )}

            {candidates.length > 0 && (
              <div className="space-y-3">
                {/* Summary Bar */}
                <div className="flex items-center gap-4">
                  <Badge variant="success" glow>
                    <CheckCircle2 className="h-3 w-3" />
                    通过 {candidates.length} 只
                  </Badge>
                  {failed.length > 0 && (
                    <Badge variant="default">失败 {failed.length} 只</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    共分析 {totalAnalyzed} 只
                  </span>
                </div>

                {/* Candidate Cards */}
                {candidates.map((candidate, index) => (
                  <Card key={candidate.code} className="p-4 transition-all hover:border-cyan/30">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-gradient text-xs font-bold text-[hsl(var(--primary-foreground))]">
                          {index + 1}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold text-foreground">
                              {candidate.code}
                            </span>
                            <span className="text-sm text-foreground">{candidate.name}</span>
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">{candidate.reason}</p>
                        </div>
                      </div>
                      {candidate.score != null && (
                        <div className="text-right">
                          <div className="text-lg font-bold text-foreground">{candidate.score}</div>
                          <div className="text-xs text-muted-foreground">评分</div>
                        </div>
                      )}
                    </div>
                  </Card>
                ))}

                {/* Failed Items */}
                {failed.length > 0 && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm text-muted-foreground">
                      查看失败项 ({failed.length})
                    </summary>
                    <div className="mt-2 space-y-2">
                      {failed.map((item) => (
                        <div key={item.code} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs text-foreground">{item.code}</span>
                            <span className="text-xs text-foreground">{item.name}</span>
                          </div>
                          <p className="mt-1 text-xs text-red-400">{item.error}</p>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScreenerPage;
