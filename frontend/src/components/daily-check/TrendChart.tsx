import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TrendPoint } from '@/types';

interface Props {
  points: TrendPoint[];
  height?: number;
}

export function TrendChart({ points, height = 220 }: Props) {
  if (!points.length) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">
        선택된 기간에 점검 결과가 없습니다.
      </p>
    );
  }

  const data = points.map((p) => ({
    ts: new Date(p.checkedAt).toLocaleString('ko-KR', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }),
    errors: p.errorCount,
    warnings: p.warningCount,
    ready: p.readyNodes,
    total: p.totalNodes,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="errorGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#ef4444" stopOpacity={0.5} />
            <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="warnGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.45} />
            <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis dataKey="ts" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
        <YAxis tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: 'hsl(var(--card))',
            border: '1px solid hsl(var(--border))',
            borderRadius: 12,
            fontSize: 12,
          }}
        />
        <Area
          type="monotone"
          dataKey="errors"
          name="에러"
          stroke="#ef4444"
          fill="url(#errorGrad)"
        />
        <Area
          type="monotone"
          dataKey="warnings"
          name="경고"
          stroke="#f59e0b"
          fill="url(#warnGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
