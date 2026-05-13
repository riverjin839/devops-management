import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Play, RefreshCw, Settings as SettingsIcon, Loader2 } from 'lucide-react';
import { MacCard } from '@/components/ui/MacCard';
import { AiSummaryCard } from '@/components/dashboard/AiSummaryCard';
import { TrendChart, DiffPanel, DeepCheckGrid } from '@/components/daily-check';
import {
  useDailyCheckTrend,
  useLatestDailyCheck,
  useLatestDeepCheckResult,
  useRunDeepCheck,
} from '@/hooks/useDeepCheck';
import { useClusters } from '@/hooks/useCluster';

export function DailyCheckReviewPage() {
  const { clusterId = '' } = useParams<{ clusterId: string }>();
  const { data: clusters = [] } = useClusters();
  const cluster = clusters.find((c) => c.id === clusterId);
  const [days, setDays] = useState(7);

  const { data: latestDaily } = useLatestDailyCheck(clusterId);
  const { data: deepResult, isLoading: deepLoading } = useLatestDeepCheckResult(clusterId);
  const { data: trend = [], isLoading: trendLoading } = useDailyCheckTrend(clusterId, days);
  const runDeepCheck = useRunDeepCheck();

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 bg-card/85 backdrop-blur border-b border-border">
        <div className="max-w-[1600px] mx-auto px-5 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="w-4 h-4" /> Dashboard
            </Link>
            <div className="min-w-0">
              <h1 className="text-base font-semibold truncate">
                {cluster?.name ?? clusterId} · 일일 점검 리뷰
              </h1>
              {latestDaily && (
                <p className="text-[11px] text-muted-foreground truncate">
                  최근 점검:{' '}
                  {new Date(latestDaily.checkedAt).toLocaleString('ko-KR')} · 노드{' '}
                  {latestDaily.readyNodes}/{latestDaily.totalNodes} Ready
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/daily-check/settings"
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-border bg-card text-xs"
            >
              <SettingsIcon className="w-3.5 h-3.5" /> Deep Check 설정
            </Link>
            <button
              type="button"
              onClick={() => clusterId && runDeepCheck.mutate(clusterId)}
              disabled={!clusterId || runDeepCheck.isPending}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-xs disabled:opacity-50"
            >
              {runDeepCheck.isPending ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              Run Deep Check
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto px-5 py-5 space-y-4">
        <AiSummaryCard clusterId={clusterId} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <MacCard
            title="Daily Check Trend"
            bodyPadding="p-4"
            rootClassName="min-w-0"
          >
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-muted-foreground">
                선택 기간 내 에러/경고 수 추이
              </p>
              <div className="flex gap-1">
                {[3, 7, 14, 30].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDays(d)}
                    className={`px-2 py-1 rounded-xl text-[11px] border ${
                      days === d
                        ? 'border-primary text-primary'
                        : 'border-border text-muted-foreground'
                    }`}
                  >
                    {d}d
                  </button>
                ))}
              </div>
            </div>
            {trendLoading ? (
              <p className="text-sm text-muted-foreground text-center py-6">불러오는 중...</p>
            ) : (
              <TrendChart points={trend} />
            )}
          </MacCard>

          <MacCard title="Diff (직전 점검 대비)" bodyPadding="p-4" rootClassName="min-w-0">
            <DiffPanel trend={deepResult?.trendSummary ?? null} />
          </MacCard>
        </div>

        <MacCard
          title="Deep Check Results"
          bodyPadding="p-4"
          rootClassName="min-w-0"
        >
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs text-muted-foreground">
              {deepResult?.source === 'in_cluster'
                ? 'in_cluster (target cluster pushed)'
                : deepResult?.source === 'centralized'
                ? 'centralized (backend ran via kubeconfig)'
                : '실행 전'}
            </p>
            <button
              type="button"
              onClick={() => clusterId && runDeepCheck.mutate(clusterId)}
              disabled={!clusterId || runDeepCheck.isPending}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-xl border border-border bg-card text-[11px] disabled:opacity-50"
            >
              <RefreshCw className={`w-3 h-3 ${runDeepCheck.isPending ? 'animate-spin' : ''}`} />
              다시 실행
            </button>
          </div>
          {deepLoading ? (
            <p className="text-sm text-muted-foreground text-center py-6">불러오는 중...</p>
          ) : (
            <DeepCheckGrid
              results={deepResult?.results}
              errors={(deepResult?.errors as Array<{ check_type?: string; error?: string }>) ?? null}
            />
          )}
        </MacCard>
      </main>
    </div>
  );
}
