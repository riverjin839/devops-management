import { useEffect, useMemo, useState } from 'react';
import { Loader2, Play, Save } from 'lucide-react';
import type {
  DeepCheckDefinition,
  DeepCheckDefinitionCreate,
  DeepCheckDefinitionUpdate,
  DeepCheckTestResult,
  DeepCheckTypeSchema,
} from '@/types';
import { StatusBadge } from '@/components/dashboard/StatusBadge';

interface Props {
  schemas: DeepCheckTypeSchema[];
  /** When null = create new; otherwise edit existing. */
  initial: DeepCheckDefinition | null;
  clusters: { id: string; name: string }[];
  isSaving: boolean;
  onSubmit: (payload: DeepCheckDefinitionCreate | DeepCheckDefinitionUpdate) => void;
  onCancel: () => void;
  // Test-now (only meaningful when editing). Receives chosen cluster id.
  onTest?: (clusterId: string) => Promise<DeepCheckTestResult>;
}

export function DeepCheckDefinitionForm({
  schemas,
  initial,
  clusters,
  isSaving,
  onSubmit,
  onCancel,
  onTest,
}: Props) {
  const isEdit = initial !== null;
  const [checkType, setCheckType] = useState<string>(
    initial?.checkType ?? schemas[0]?.checkType ?? '',
  );
  const schema = useMemo(
    () => schemas.find((s) => s.checkType === checkType),
    [schemas, checkType],
  );
  const [name, setName] = useState(initial?.name ?? schema?.label ?? '');
  const [description, setDescription] = useState(initial?.description ?? schema?.description ?? '');
  const [clusterId, setClusterId] = useState<string | ''>(initial?.clusterId ?? '');
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [sortOrder, setSortOrder] = useState(initial?.sortOrder ?? 0);
  const [thresholds, setThresholds] = useState<Record<string, unknown>>(
    initial?.thresholds ?? schema?.defaultThresholds ?? {},
  );
  const [params, setParams] = useState<Record<string, unknown>>(
    initial?.params ?? schema?.defaultParams ?? {},
  );

  // When switching check_type on a NEW definition, refill defaults.
  useEffect(() => {
    if (isEdit) return;
    if (!schema) return;
    setName(schema.label);
    setDescription(schema.description);
    setThresholds(schema.defaultThresholds);
    setParams(schema.defaultParams);
  }, [schema, isEdit]);

  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState<DeepCheckTestResult | null>(null);
  const [testCluster, setTestCluster] = useState<string>(
    clusterId || clusters[0]?.id || '',
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!checkType || !name.trim()) return;
    if (isEdit) {
      const payload: DeepCheckDefinitionUpdate = {
        name: name.trim(),
        description,
        enabled,
        sortOrder,
        thresholds,
        params,
      };
      onSubmit(payload);
    } else {
      const payload: DeepCheckDefinitionCreate = {
        checkType,
        clusterId: clusterId || null,
        name: name.trim(),
        description,
        enabled,
        sortOrder,
        thresholds,
        params,
      };
      onSubmit(payload);
    }
  };

  const handleTest = async () => {
    if (!onTest || !testCluster) return;
    setTestRunning(true);
    setTestResult(null);
    try {
      const res = await onTest(testCluster);
      setTestResult(res);
    } finally {
      setTestRunning(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label="Check Type">
          <select
            value={checkType}
            onChange={(e) => setCheckType(e.target.value)}
            disabled={isEdit}
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            {schemas.map((s) => (
              <option key={s.checkType} value={s.checkType}>
                {s.label} ({s.checkType})
              </option>
            ))}
          </select>
        </Field>
        <Field label="대상 클러스터">
          <select
            value={clusterId}
            onChange={(e) => setClusterId(e.target.value)}
            disabled={isEdit}
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          >
            <option value="">(전체 클러스터 적용)</option>
            {clusters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="이름" className="sm:col-span-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </Field>
        <Field label="설명" className="sm:col-span-2">
          <textarea
            value={description ?? ''}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </Field>
        <Field label="정렬 순서">
          <input
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(Number(e.target.value))}
            className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </Field>
        <Field label="활성화">
          <label className="inline-flex items-center gap-2 mt-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <span>{enabled ? '실행됨' : '비활성'}</span>
          </label>
        </Field>
      </div>

      {schema && (
        <ParamsEditor
          schema={schema}
          thresholds={thresholds}
          params={params}
          onThresholdsChange={setThresholds}
          onParamsChange={setParams}
        />
      )}

      <div className="flex flex-wrap items-center gap-2 justify-between pt-2 border-t border-border">
        <div className="flex items-center gap-2">
          {onTest && isEdit && (
            <>
              <select
                value={testCluster}
                onChange={(e) => setTestCluster(e.target.value)}
                className="form-input"
              >
                {clusters.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleTest}
                disabled={testRunning || !testCluster}
                className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl border border-border bg-card text-sm disabled:opacity-50"
              >
                {testRunning ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
                Test Now
              </button>
            </>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-xl border border-border bg-card text-sm"
          >
            취소
          </button>
          <button
            type="submit"
            disabled={isSaving || !checkType || !name.trim()}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-sm disabled:opacity-50"
          >
            {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            저장
          </button>
        </div>
      </div>

      {testResult && (
        <div className="rounded-xl border border-border bg-card p-3">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold">미리보기 결과</div>
            <StatusBadge status={testResult.status} size="sm" />
          </div>
          <p className="text-xs">{testResult.message}</p>
          <p className="mt-1 text-[10px] text-muted-foreground">
            응답시간 {testResult.responseTimeMs} ms · check_type = {testResult.checkType}
          </p>
          {testResult.details && (
            <pre className="mt-2 p-2 rounded bg-muted/50 text-[11px] overflow-x-auto max-h-60">
              <code>{JSON.stringify(testResult.details, null, 2)}</code>
            </pre>
          )}
        </div>
      )}
    </form>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block text-xs ${className ?? ''}`}>
      <span className="text-muted-foreground uppercase tracking-wide">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function ParamsEditor({
  schema,
  thresholds,
  params,
  onThresholdsChange,
  onParamsChange,
}: {
  schema: DeepCheckTypeSchema;
  thresholds: Record<string, unknown>;
  params: Record<string, unknown>;
  onThresholdsChange: (next: Record<string, unknown>) => void;
  onParamsChange: (next: Record<string, unknown>) => void;
}) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-semibold text-muted-foreground mb-1.5 uppercase">
          임계값 (thresholds)
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {Object.entries(schema.defaultThresholds).map(([key]) => (
            <Field key={key} label={key}>
              <input
                type="number"
                value={(thresholds[key] as number | undefined) ?? ''}
                onChange={(e) =>
                  onThresholdsChange({ ...thresholds, [key]: Number(e.target.value) })
                }
                className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </Field>
          ))}
        </div>
      </div>

      {schema.paramSchema.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-muted-foreground mb-1.5 uppercase">
            파라미터
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {schema.paramSchema.map((field) => (
              <Field key={field.name} label={field.label}>
                <ParamInput
                  field={field}
                  value={params[field.name]}
                  onChange={(value) => onParamsChange({ ...params, [field.name]: value })}
                />
              </Field>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ParamInput({
  field,
  value,
  onChange,
}: {
  field: { name: string; type: string; help?: string };
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (field.type === 'string[]') {
    const joined = Array.isArray(value) ? value.join(',') : '';
    return (
      <input
        value={joined}
        onChange={(e) => onChange(e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
        placeholder="콤마(,)로 구분"
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    );
  }
  if (field.type === 'number') {
    return (
      <input
        type="number"
        value={(value as number | undefined) ?? ''}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
      />
    );
  }
  if (field.type === 'boolean') {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  return (
    <input
      value={(value as string | undefined) ?? ''}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
    />
  );
}
