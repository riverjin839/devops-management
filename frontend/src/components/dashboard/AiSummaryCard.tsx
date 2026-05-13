import { useMemo } from 'react';
import { Sparkles, RefreshCw, AlertCircle, ArrowDownCircle, ArrowUpCircle, MinusCircle } from 'lucide-react';
import { MacCard } from '@/components/ui/MacCard';
import { StatusBadge } from '@/components/dashboard/StatusBadge';
import { useLatestDailyCheck, useDeepCheckReview, useRecomputeReview } from '@/hooks/useDeepCheck';
import { formatDateTime } from '@/lib/utils';
import type { Status } from '@/types';

interface Props {
  clusterId: string | null;
}

export function AiSummaryCard({ clusterId }: Props) {
  const { data: latest, isLoading: dailyLoading } = useLatestDailyCheck(clusterId ?? null);
  const dailyCheckLogId = latest?.id ?? null;
  const { data: review, isLoading: reviewLoading, isError, error } = useDeepCheckReview(dailyCheckLogId);
  const recompute = useRecomputeReview();

  const trend = review?.trendSummary;

  const trendBadges = useMemo(() => {
    if (!trend) return null;
    const badges: { icon: typeof ArrowDownCircle; label: string; tone: string }[] = [];
    if (trend.statusChanged) {
      const prev = trend.prevStatus ? statusLabel(trend.prevStatus) : '—';
      badges.push({ icon: ArrowUpCircle, label: `상태 변화: ${prev} → 현재`, tone: 'text-amber-400' });
    }
    if (trend.newErrors.length > 0) {
      badges.push({ icon: ArrowUpCircle, label: `새 에러 ${trend.newErrors.length}건`, tone: 'text-status-critical' });
    }
    if (trend.resolvedErrors.length > 0) {
      badges.push({ icon: ArrowDownCircle, label: `해소된 에러 ${trend.resolvedErrors.length}건`, tone: 'text-status-healthy' });
    }
    if (trend.readyNodesDelta !== 0) {
      const Icon = trend.readyNodesDelta > 0 ? ArrowDownCircle : ArrowUpCircle;
      const tone = trend.readyNodesDelta > 0 ? 'text-status-healthy' : 'text-status-warning';
      badges.push({
        icon: Icon,
        label: `Ready 노드 ${trend.readyNodesDelta > 0 ? '+' : ''}${trend.readyNodesDelta}`,
        tone,
      });
    }
    if (badges.length === 0 && trend.prevCheckedAt) {
      badges.push({ icon: MinusCircle, label: '직전 점검과 동일', tone: 'text-muted-foreground' });
    }
    return badges;
  }, [trend]);

  return (
    <MacCard title="AI 일일 점검 리뷰" bodyPadding="p-4">
      {!clusterId ? (
        <Empty message="클러스터를 선택하면 AI 리뷰가 표시됩니다." />
      ) : dailyLoading ? (
        <Empty message="일일 점검 결과를 불러오는 중..." />
      ) : !latest ? (
        <Empty message="아직 일일 점검 결과가 없습니다. 좌측에서 수동 실행을 해 보세요." />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" />
              <span>
                {formatDateTime(latest.checkedAt)} 점검 (
                {latest.scheduleType}
                ) · 노드 {latest.readyNodes}/{latest.totalNodes} Ready
              </span>
            </div>
            <button
              type="button"
              onClick={() => dailyCheckLogId && recompute.mutate(dailyCheckLogId)}
              disabled={!dailyCheckLogId || recompute.isPending}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-xl border border-border bg-card hover:bg-muted/40 disabled:opacity-50"
              title="AI 리뷰 다시 생성"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${recompute.isPending ? 'animate-spin' : ''}`} />
              <span>다시 분석</span>
            </button>
          </div>

          {reviewLoading || recompute.isPending ? (
            <Empty message="AI 가 점검 결과를 분석 중입니다… (Ollama 응답 대기)" />
          ) : isError ? (
            <ErrorBox message={(error as Error)?.message ?? '리뷰를 불러오지 못했습니다.'} />
          ) : review ? (
            <>
              {review.aiStatus !== 'ok' && (
                <div className="flex items-start gap-2 text-xs text-amber-500">
                  <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>
                    AI 가 오프라인이라 폴백 응답이 표시됩니다 ({review.aiStatus}). Ollama 상태를 확인하세요.
                  </span>
                </div>
              )}

              {trendBadges && trendBadges.length > 0 && (
                <div className="flex flex-wrap items-center gap-2">
                  {trendBadges.map((b, i) => {
                    const Icon = b.icon;
                    return (
                      <span
                        key={i}
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-xl border border-border bg-card text-xs ${b.tone}`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                        {b.label}
                      </span>
                    );
                  })}
                </div>
              )}

              <div className="rounded-xl border border-border bg-card p-3">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-muted-foreground">요약</span>
                  <StatusBadge status={latest.overallStatus as Status} size="sm" />
                </div>
                <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">
                  {review.aiSummary || '(AI 요약 없음)'}
                </p>
                {review.aiModel && (
                  <p className="mt-2 text-[10px] text-muted-foreground">model: {review.aiModel}</p>
                )}
              </div>

              {review.aiRemediation && review.aiRemediation.length > 0 && (
                <div className="rounded-xl border border-border bg-card p-3">
                  <span className="text-xs font-semibold text-muted-foreground">권장 조치</span>
                  <ol className="mt-2 space-y-2 text-sm">
                    {review.aiRemediation.map((step, idx) => (
                      <li key={idx} className="space-y-1">
                        <div className="font-medium">
                          {idx + 1}. {step.title}
                        </div>
                        {step.description && (
                          <div className="text-xs text-muted-foreground">{step.description}</div>
                        )}
                        {step.command && (
                          <pre className="mt-1 p-2 rounded bg-muted/50 text-xs overflow-x-auto">
                            <code>{step.command}</code>
                          </pre>
                        )}
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </>
          ) : (
            <Empty message="AI 리뷰를 가져오는 중..." />
          )}
        </div>
      )}
    </MacCard>
  );
}

function Empty({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground text-center py-4">{message}</p>;
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-status-critical/30 bg-status-critical/10 text-status-critical text-sm p-3 flex items-start gap-2">
      <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
      <span>{message}</span>
    </div>
  );
}

function statusLabel(s: Status): string {
  return { healthy: 'Healthy', warning: 'Warning', critical: 'Critical', pending: 'Pending' }[s];
}
