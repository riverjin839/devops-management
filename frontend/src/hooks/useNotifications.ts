import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { notificationsApi } from '@/services/api';
import type {
  NotificationChannel,
  NotificationChannelCreate,
  NotificationChannelUpdate,
  NotificationLog,
} from '@/types';

const keys = {
  channels: (clusterId?: string | null) =>
    ['notifications', 'channels', clusterId ?? 'all'] as const,
  log: (channelId?: string | null) => ['notifications', 'log', channelId ?? 'all'] as const,
};

export function useNotificationChannels(clusterId?: string | null) {
  return useQuery<NotificationChannel[]>({
    queryKey: keys.channels(clusterId),
    queryFn: async () => (await notificationsApi.listChannels(clusterId ?? undefined)).data,
  });
}

export function useCreateNotificationChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: NotificationChannelCreate) =>
      (await notificationsApi.createChannel(payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'channels'] }),
  });
}

export function useUpdateNotificationChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: NotificationChannelUpdate }) =>
      (await notificationsApi.updateChannel(id, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'channels'] }),
  });
}

export function useDeleteNotificationChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await notificationsApi.deleteChannel(id);
      return id;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'channels'] }),
  });
}

export function useTestNotificationChannel() {
  return useMutation<NotificationLog, Error, string>({
    mutationFn: async (id) => (await notificationsApi.testChannel(id)).data,
  });
}

export function useNotificationLogs(channelId?: string | null, limit = 50) {
  return useQuery<NotificationLog[]>({
    queryKey: [...keys.log(channelId), limit],
    queryFn: async () =>
      (await notificationsApi.listLogs(channelId ?? undefined, limit)).data,
  });
}
