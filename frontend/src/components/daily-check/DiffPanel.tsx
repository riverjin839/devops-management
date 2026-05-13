import { Plus, Minus } from 'lucide-react';
import type { TrendSummary } from '@/types';

interface Props {
  trend: TrendSummary | null | undefined;
}

export function DiffPanel({ trend }: Props) {
  if (!trend) {
    return <p className="text-sm text-muted-foreground">변화 정보 없음.</p>;
  }

  const sections: { label: string; items: string[]; tone: 'add' | 'remove' }[] = [
    { label: '새로 발생한 에러', items: trend.newErrors, tone: 'add' },
    { label: '해소된 에러', items: trend.resolvedErrors, tone: 'remove' },
    { label: '새로 발생한 경고', items: trend.newWarnings, tone: 'add' },
    { label: '해소된 경고', items: trend.resolvedWarnings, tone: 'remove' },
  ];

  return (
    <div className="space-y-3 text-sm">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span>
          직전 점검:{' '}
          {trend.prevCheckedAt
            ? new Date(trend.prevCheckedAt).toLocaleString('ko-KR')
            : '없음'}
        </span>
        {trend.statusChanged && (
          <span className="px-2 py-0.5 rounded-xl bg-amber-500/15 text-amber-500">
            상태 변화 발생 (이전: {trend.prevStatus ?? '—'})
          </span>
        )}
        {trend.readyNodesDelta !== 0 && (
          <span className="px-2 py-0.5 rounded-xl bg-card border border-border">
            Ready 노드 {trend.readyNodesDelta > 0 ? '+' : ''}
            {trend.readyNodesDelta}
          </span>
        )}
      </div>

      {sections.map((s) =>
        s.items.length === 0 ? null : (
          <div key={s.label} className="rounded-xl border border-border bg-card p-3">
            <div className="text-xs font-semibold text-muted-foreground mb-1.5 flex items-center gap-1.5">
              {s.tone === 'add' ? (
                <Plus className="w-3.5 h-3.5 text-status-critical" />
              ) : (
                <Minus className="w-3.5 h-3.5 text-status-healthy" />
              )}
              {s.label} ({s.items.length})
            </div>
            <ul className="space-y-1 text-xs">
              {s.items.map((it, i) => (
                <li
                  key={i}
                  className={`pl-3 border-l-2 ${
                    s.tone === 'add'
                      ? 'border-status-critical text-status-critical'
                      : 'border-status-healthy text-status-healthy'
                  }`}
                >
                  {it}
                </li>
              ))}
            </ul>
          </div>
        ),
      )}
    </div>
  );
}
