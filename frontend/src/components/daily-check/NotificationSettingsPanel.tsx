import { useState } from 'react';
import { Bell, Loader2, Plus, Send, Trash2 } from 'lucide-react';
import type {
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelType,
  NotificationSeverity,
} from '@/types';
import {
  useCreateNotificationChannel,
  useDeleteNotificationChannel,
  useNotificationChannels,
  useTestNotificationChannel,
  useUpdateNotificationChannel,
} from '@/hooks/useNotifications';

interface Props {
  clusters: { id: string; name: string }[];
}

const TYPE_LABEL: Record<NotificationChannelType, string> = {
  slack: 'Slack Webhook',
  email: 'Email (SMTP)',
  webhook: 'Generic Webhook',
  k8s_event: 'Kubernetes Event',
};

const SEVERITY_OPTIONS: { value: NotificationSeverity; label: string }[] = [
  { value: 'healthy', label: 'healthy 이상 (모두)' },
  { value: 'warning', label: 'warning 이상' },
  { value: 'critical', label: 'critical 만' },
];

export function NotificationSettingsPanel({ clusters }: Props) {
  const { data: channels = [], isLoading } = useNotificationChannels();
  const create = useCreateNotificationChannel();
  const update = useUpdateNotificationChannel();
  const remove = useDeleteNotificationChannel();
  const test = useTestNotificationChannel();

  const [draft, setDraft] = useState<NotificationChannelCreate>({
    name: '',
    type: 'slack',
    minSeverity: 'warning',
    enabled: true,
    clusterId: null,
    config: {},
  });

  const handleCreate = async () => {
    if (!draft.name.trim()) return;
    await create.mutateAsync(draft);
    setDraft({
      name: '',
      type: 'slack',
      minSeverity: 'warning',
      enabled: true,
      clusterId: null,
      config: {},
    });
  };

  return (
    <div className="space-y-4">
      {/* ── List ─────────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
          <Bell className="w-3.5 h-3.5" />
          {isLoading ? '불러오는 중...' : `${channels.length}개 채널 등록됨`}
        </div>
        {channels.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            아직 등록된 채널이 없습니다.
          </p>
        ) : (
          <ul className="space-y-2">
            {channels.map((ch) => (
              <ChannelRow
                key={ch.id}
                channel={ch}
                clusters={clusters}
                isTesting={test.isPending && test.variables === ch.id}
                isDeleting={remove.isPending && (remove.variables as string) === ch.id}
                onToggle={() =>
                  update.mutate({ id: ch.id, payload: { enabled: !ch.enabled } })
                }
                onChangeSeverity={(s) =>
                  update.mutate({ id: ch.id, payload: { minSeverity: s } })
                }
                onTest={() => test.mutate(ch.id)}
                onDelete={() => {
                  if (confirm(`"${ch.name}" 채널을 삭제할까요?`)) remove.mutate(ch.id);
                }}
              />
            ))}
          </ul>
        )}
      </div>

      {/* ── Add new ──────────────────────────────────────────────────── */}
      <div className="rounded-xl border border-dashed border-border p-3 space-y-2">
        <div className="text-xs font-semibold text-muted-foreground uppercase">
          새 채널 추가
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
          <input
            placeholder="이름 (예: ops-slack)"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
          />
          <select
            value={draft.type}
            onChange={(e) =>
              setDraft({
                ...draft,
                type: e.target.value as NotificationChannelType,
                config: {},
              })
            }
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
          >
            {(Object.keys(TYPE_LABEL) as NotificationChannelType[]).map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
          <select
            value={draft.clusterId ?? ''}
            onChange={(e) => setDraft({ ...draft, clusterId: e.target.value || null })}
            className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
          >
            <option value="">(전체 클러스터)</option>
            {clusters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <ChannelConfigEditor
          type={draft.type}
          config={draft.config ?? {}}
          onChange={(config) => setDraft({ ...draft, config })}
        />
        <div className="flex items-center justify-between">
          <select
            value={draft.minSeverity}
            onChange={(e) =>
              setDraft({ ...draft, minSeverity: e.target.value as NotificationSeverity })
            }
            className="px-3 py-1.5 bg-secondary border border-border rounded-lg text-xs"
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleCreate}
            disabled={create.isPending || !draft.name.trim()}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-xl bg-primary text-primary-foreground text-sm disabled:opacity-50"
          >
            {create.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            추가
          </button>
        </div>
      </div>
    </div>
  );
}

function ChannelRow({
  channel,
  clusters,
  isTesting,
  isDeleting,
  onToggle,
  onChangeSeverity,
  onTest,
  onDelete,
}: {
  channel: NotificationChannel;
  clusters: { id: string; name: string }[];
  isTesting: boolean;
  isDeleting: boolean;
  onToggle: () => void;
  onChangeSeverity: (s: NotificationSeverity) => void;
  onTest: () => void;
  onDelete: () => void;
}) {
  const scope = channel.clusterId
    ? clusters.find((c) => c.id === channel.clusterId)?.name ?? '특정 클러스터'
    : '전체';
  return (
    <li className="rounded-xl border border-border bg-card p-3 flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold truncate">{channel.name}</div>
        <div className="text-[11px] text-muted-foreground">
          {TYPE_LABEL[channel.type]} · {scope}
        </div>
      </div>
      <select
        value={channel.minSeverity}
        onChange={(e) => onChangeSeverity(e.target.value as NotificationSeverity)}
        className="px-2 py-1 bg-secondary border border-border rounded-xl text-xs"
      >
        {SEVERITY_OPTIONS.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      <button
        type="button"
        onClick={onToggle}
        className={`text-xs px-2 py-1 rounded-xl border ${
          channel.enabled
            ? 'border-status-healthy/40 text-status-healthy'
            : 'border-border text-muted-foreground'
        }`}
      >
        {channel.enabled ? 'on' : 'off'}
      </button>
      <button
        type="button"
        onClick={onTest}
        disabled={isTesting}
        className="p-1.5 rounded-xl border border-border"
        title="테스트 전송"
      >
        {isTesting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
      </button>
      <button
        type="button"
        onClick={onDelete}
        disabled={isDeleting}
        className="p-1.5 rounded-xl border border-status-critical/40 text-status-critical"
      >
        {isDeleting ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Trash2 className="w-3.5 h-3.5" />
        )}
      </button>
    </li>
  );
}

function ChannelConfigEditor({
  type,
  config,
  onChange,
}: {
  type: NotificationChannelType;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  config: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange: (c: Record<string, any>) => void;
}) {
  const set = (key: string, value: unknown) => onChange({ ...config, [key]: value });

  if (type === 'slack') {
    return (
      <input
        value={config.webhook_url ?? ''}
        onChange={(e) => set('webhook_url', e.target.value)}
        placeholder="Slack Incoming Webhook URL"
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
      />
    );
  }
  if (type === 'webhook') {
    return (
      <input
        value={config.url ?? ''}
        onChange={(e) => set('url', e.target.value)}
        placeholder="POST URL"
        className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
      />
    );
  }
  if (type === 'email') {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <input
          value={config.host ?? ''}
          onChange={(e) => set('host', e.target.value)}
          placeholder="SMTP host"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
        <input
          value={config.port ?? ''}
          onChange={(e) => set('port', Number(e.target.value))}
          placeholder="port (587)"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
        <input
          value={config.username ?? ''}
          onChange={(e) => set('username', e.target.value)}
          placeholder="username"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
        <input
          type="password"
          value={config.password ?? ''}
          onChange={(e) => set('password', e.target.value)}
          placeholder="password"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
        <input
          value={config.from ?? ''}
          onChange={(e) => set('from', e.target.value)}
          placeholder="from"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
        <input
          value={config.to ?? ''}
          onChange={(e) => set('to', e.target.value)}
          placeholder="to (콤마 구분)"
          className="px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
        />
      </div>
    );
  }
  // k8s_event
  return (
    <input
      value={config.namespace ?? ''}
      onChange={(e) => set('namespace', e.target.value)}
      placeholder="namespace (비우면 settings.mgmt_namespace)"
      className="w-full px-3 py-2 bg-secondary border border-border rounded-lg text-sm"
    />
  );
}
