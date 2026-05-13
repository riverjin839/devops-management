import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Plus } from 'lucide-react';
import { MacCard } from '@/components/ui/MacCard';
import {
  DeepCheckDefinitionForm,
  DeepCheckDefinitionList,
  NotificationSettingsPanel,
} from '@/components/daily-check';
import {
  useCheckTypes,
  useCreateDefinition,
  useDeepCheckDefinitions,
  useDeleteDefinition,
  useTestDefinition,
  useUpdateDefinition,
} from '@/hooks/useDeepCheck';
import { useClusters } from '@/hooks/useCluster';
import type {
  DeepCheckDefinition,
  DeepCheckDefinitionCreate,
  DeepCheckDefinitionUpdate,
} from '@/types';

export function DeepCheckSettingsPage() {
  const [scopeClusterId, setScopeClusterId] = useState<string>('');
  const { data: clusters = [] } = useClusters();
  const { data: schemas = [] } = useCheckTypes();
  const { data: definitions = [], isLoading } = useDeepCheckDefinitions(
    scopeClusterId || null,
  );
  const create = useCreateDefinition();
  const update = useUpdateDefinition();
  const remove = useDeleteDefinition();
  const test = useTestDefinition();

  const [editing, setEditing] = useState<DeepCheckDefinition | null>(null);
  const [showForm, setShowForm] = useState(false);

  const clusterNames = useMemo(
    () => Object.fromEntries(clusters.map((c) => [c.id, c.name] as const)),
    [clusters],
  );

  const handleSubmit = async (
    payload: DeepCheckDefinitionCreate | DeepCheckDefinitionUpdate,
  ) => {
    if (editing) {
      await update.mutateAsync({ id: editing.id, payload: payload as DeepCheckDefinitionUpdate });
    } else {
      await create.mutateAsync(payload as DeepCheckDefinitionCreate);
    }
    setShowForm(false);
    setEditing(null);
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-20 bg-card/85 backdrop-blur border-b border-border">
        <div className="max-w-[1400px] mx-auto px-5 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="w-4 h-4" /> Dashboard
            </Link>
            <h1 className="text-base font-semibold">Deep Check 설정</h1>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={scopeClusterId}
              onChange={(e) => setScopeClusterId(e.target.value)}
              className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
            >
              <option value="">전체 + 글로벌</option>
              {clusters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                setEditing(null);
                setShowForm(true);
              }}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-sm"
            >
              <Plus className="w-4 h-4" /> 추가
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-5 py-5 space-y-4">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MacCard title="등록된 Deep Check" bodyPadding="p-4" rootClassName="min-w-0">
          {isLoading ? (
            <p className="text-sm text-muted-foreground text-center py-6">불러오는 중...</p>
          ) : (
            <DeepCheckDefinitionList
              definitions={definitions}
              schemas={schemas}
              clusterNames={clusterNames}
              togglingId={update.isPending ? update.variables?.id ?? null : null}
              deletingId={remove.isPending ? (remove.variables as string) : null}
              onToggle={(def) =>
                update.mutate({ id: def.id, payload: { enabled: !def.enabled } })
              }
              onEdit={(def) => {
                setEditing(def);
                setShowForm(true);
              }}
              onDelete={(def) => {
                if (confirm(`"${def.name}" 정의를 삭제하시겠습니까?`)) remove.mutate(def.id);
              }}
            />
          )}
        </MacCard>

        <MacCard
          title={editing ? '편집' : showForm ? '새 Deep Check 추가' : '편집할 항목 선택'}
          bodyPadding="p-4"
          rootClassName="min-w-0"
        >
          {showForm ? (
            <DeepCheckDefinitionForm
              schemas={schemas}
              initial={editing}
              clusters={clusters.map((c) => ({ id: c.id, name: c.name }))}
              isSaving={create.isPending || update.isPending}
              onSubmit={handleSubmit}
              onCancel={() => {
                setShowForm(false);
                setEditing(null);
              }}
              onTest={
                editing
                  ? (clusterId) =>
                      test.mutateAsync({ id: editing.id, clusterId })
                  : undefined
              }
            />
          ) : (
            <p className="text-sm text-muted-foreground text-center py-8">
              왼쪽 목록에서 항목을 골라 편집하거나 "추가" 버튼으로 새 정의를 만드세요.
            </p>
          )}
        </MacCard>
        </div>

        <MacCard title="알림 채널" bodyPadding="p-4">
          <NotificationSettingsPanel
            clusters={clusters.map((c) => ({ id: c.id, name: c.name }))}
          />
        </MacCard>
      </main>
    </div>
  );
}
