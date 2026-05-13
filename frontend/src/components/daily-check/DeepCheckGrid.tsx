import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { MacCard } from '@/components/ui/MacCard';
import { StatusBadge } from '@/components/dashboard/StatusBadge';
import type { Status } from '@/types';

interface DeepResult {
  name?: string;
  label?: string;
  status: string;
  message: string;
  responseTimeMs?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  details?: Record<string, any> | null;
}

interface Props {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  results: Record<string, any> | null | undefined;
  errors?: Array<{ check_type?: string; error?: string }> | null;
}

export function DeepCheckGrid({ results, errors }: Props) {
  const rows = results ? Object.entries(results) : [];
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-4">
        아직 deep check 결과가 없습니다. 우측 "Run Deep Check" 버튼으로 즉시 실행하세요.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {rows.map(([checkType, raw]) => (
        <DeepCheckTile key={checkType} checkType={checkType} result={raw as DeepResult} />
      ))}
      {errors && errors.length > 0 && (
        <div className="rounded-xl border border-status-critical/30 bg-status-critical/10 p-3 col-span-full">
          <div className="text-xs font-semibold text-status-critical mb-1">실행 실패한 체크</div>
          <ul className="text-xs space-y-1">
            {errors.map((e, i) => (
              <li key={i}>
                <b>{e.check_type ?? 'unknown'}</b>: {e.error ?? ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DeepCheckTile({ checkType, result }: { checkType: string; result: DeepResult }) {
  const [expanded, setExpanded] = useState(false);
  const status = (result.status as Status) ?? 'pending';
  return (
    <MacCard rootClassName="min-w-0" bodyPadding="p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-sm font-semibold truncate">
            {result.name || result.label || checkType}
          </div>
          <div className="text-[10px] text-muted-foreground">{checkType}</div>
        </div>
        <StatusBadge status={status} size="sm" />
      </div>
      <p className="mt-2 text-xs text-muted-foreground break-words">{result.message}</p>
      {result.details && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 inline-flex items-center gap-1 text-[11px] text-primary hover:underline"
        >
          {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          상세
        </button>
      )}
      {expanded && result.details && (
        <pre className="mt-2 p-2 rounded bg-muted/50 text-[11px] overflow-x-auto max-h-72">
          <code>{JSON.stringify(result.details, null, 2)}</code>
        </pre>
      )}
    </MacCard>
  );
}
