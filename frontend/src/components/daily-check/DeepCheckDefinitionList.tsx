import { Edit, Loader2, Trash2 } from 'lucide-react';
import type { DeepCheckDefinition, DeepCheckTypeSchema } from '@/types';

interface Props {
  definitions: DeepCheckDefinition[];
  schemas: DeepCheckTypeSchema[];
  clusterNames: Record<string, string>;
  togglingId: string | null;
  deletingId: string | null;
  onToggle: (def: DeepCheckDefinition) => void;
  onEdit: (def: DeepCheckDefinition) => void;
  onDelete: (def: DeepCheckDefinition) => void;
}

export function DeepCheckDefinitionList({
  definitions,
  schemas,
  clusterNames,
  togglingId,
  deletingId,
  onToggle,
  onEdit,
  onDelete,
}: Props) {
  if (definitions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-6">
        정의된 deep check 가 없습니다. 우상단 "추가" 버튼으로 만들어 보세요.
      </p>
    );
  }
  const schemaByType = new Map(schemas.map((s) => [s.checkType, s]));
  return (
    <ul className="space-y-2">
      {definitions.map((def) => {
        const schema = schemaByType.get(def.checkType);
        const scope = def.clusterId ? clusterNames[def.clusterId] ?? '특정 클러스터' : '전체';
        return (
          <li
            key={def.id}
            className="rounded-xl border border-border bg-card p-3 flex items-start gap-3"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm truncate">{def.name}</span>
                <span className="text-[10px] text-muted-foreground">
                  {def.checkType} · {scope}
                </span>
              </div>
              {def.description && (
                <p className="text-xs text-muted-foreground mt-0.5">{def.description}</p>
              )}
              {schema && (
                <p className="text-[11px] text-muted-foreground mt-1">
                  thresholds:{' '}
                  {def.thresholds
                    ? JSON.stringify(def.thresholds)
                    : JSON.stringify(schema.defaultThresholds)}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <button
                type="button"
                onClick={() => onToggle(def)}
                disabled={togglingId === def.id}
                className={`text-xs px-2 py-1 rounded-xl border ${
                  def.enabled
                    ? 'border-status-healthy/40 text-status-healthy'
                    : 'border-border text-muted-foreground'
                }`}
              >
                {togglingId === def.id ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : def.enabled ? (
                  'enabled'
                ) : (
                  'disabled'
                )}
              </button>
              <button
                type="button"
                onClick={() => onEdit(def)}
                className="p-1.5 rounded-xl border border-border hover:bg-muted/40"
                title="편집"
              >
                <Edit className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => onDelete(def)}
                disabled={deletingId === def.id}
                className="p-1.5 rounded-xl border border-status-critical/40 text-status-critical hover:bg-status-critical/10"
                title="삭제"
              >
                {deletingId === def.id ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
