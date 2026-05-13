import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dailyCheckApi, deepCheckApi } from '@/services/api';
import type {
  DailyCheckLog,
  DeepCheckDefinition,
  DeepCheckDefinitionCreate,
  DeepCheckDefinitionUpdate,
  DeepCheckReview,
  DeepCheckTestResult,
  DeepCheckTypeSchema,
  TrendPoint,
} from '@/types';

const keys = {
  latestDaily: (clusterId: string) => ['daily-check', 'latest', clusterId] as const,
  review: (dailyCheckLogId: string) => ['deep-check', 'review', dailyCheckLogId] as const,
  latestResult: (clusterId: string) => ['deep-check', 'latest-result', clusterId] as const,
  checkTypes: ['deep-check', 'check-types'] as const,
  definitions: (clusterId?: string | null) => ['deep-check', 'definitions', clusterId ?? 'all'] as const,
  trend: (clusterId: string, days: number) => ['deep-check', 'trend', clusterId, days] as const,
};

/** Latest DailyCheckLog for a cluster (404 → returns undefined). */
export function useLatestDailyCheck(clusterId: string | null | undefined) {
  return useQuery<DailyCheckLog | undefined>({
    queryKey: keys.latestDaily(clusterId ?? ''),
    enabled: Boolean(clusterId),
    queryFn: async () => {
      if (!clusterId) return undefined;
      try {
        const { data } = await dailyCheckApi.getLatest(clusterId);
        return data;
      } catch (err) {
        if ((err as { response?: { status?: number } })?.response?.status === 404) {
          return undefined;
        }
        throw err;
      }
    },
    staleTime: 30_000,
  });
}

/** AI review for a daily-check log. Computes inline on first request. */
export function useDeepCheckReview(dailyCheckLogId: string | null | undefined) {
  return useQuery<DeepCheckReview | undefined>({
    queryKey: keys.review(dailyCheckLogId ?? ''),
    enabled: Boolean(dailyCheckLogId),
    queryFn: async () => {
      if (!dailyCheckLogId) return undefined;
      const { data } = await deepCheckApi.getReview(dailyCheckLogId);
      return data;
    },
    staleTime: 60_000,
  });
}

export function useRecomputeReview() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (dailyCheckLogId: string) => {
      const { data } = await deepCheckApi.recomputeReview(dailyCheckLogId);
      return data;
    },
    onSuccess: (data) => {
      qc.setQueryData(keys.review(data.dailyCheckLogId), data);
    },
  });
}

// ── Deep check execution + result ───────────────────────────────────────

export function useLatestDeepCheckResult(clusterId: string | null | undefined) {
  return useQuery<DeepCheckReview | null>({
    queryKey: keys.latestResult(clusterId ?? ''),
    enabled: Boolean(clusterId),
    queryFn: async () => {
      if (!clusterId) return null;
      const { data } = await deepCheckApi.getLatestResult(clusterId);
      return data ?? null;
    },
    staleTime: 30_000,
  });
}

export function useRunDeepCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (clusterId: string) => {
      const { data } = await deepCheckApi.runDeepCheck(clusterId);
      return { clusterId, data };
    },
    onSuccess: ({ clusterId, data }) => {
      qc.setQueryData(keys.latestResult(clusterId), data);
      qc.invalidateQueries({ queryKey: keys.review(data.dailyCheckLogId) });
    },
  });
}

// ── Trend ───────────────────────────────────────────────────────────────

export function useDailyCheckTrend(clusterId: string | null | undefined, days = 7) {
  return useQuery<TrendPoint[]>({
    queryKey: keys.trend(clusterId ?? '', days),
    enabled: Boolean(clusterId),
    queryFn: async () => {
      if (!clusterId) return [];
      const { data } = await deepCheckApi.getTrend(clusterId, days);
      return data;
    },
    staleTime: 60_000,
  });
}

// ── Check-type catalog + definitions CRUD ──────────────────────────────

export function useCheckTypes() {
  return useQuery<DeepCheckTypeSchema[]>({
    queryKey: keys.checkTypes,
    queryFn: async () => (await deepCheckApi.getCheckTypes()).data,
    staleTime: 1000 * 60 * 30,
  });
}

export function useDeepCheckDefinitions(clusterId?: string | null) {
  return useQuery<DeepCheckDefinition[]>({
    queryKey: keys.definitions(clusterId),
    queryFn: async () => (await deepCheckApi.listDefinitions(clusterId ?? undefined)).data,
  });
}

export function useCreateDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: DeepCheckDefinitionCreate) =>
      (await deepCheckApi.createDefinition(payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deep-check', 'definitions'] });
    },
  });
}

export function useUpdateDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: DeepCheckDefinitionUpdate }) =>
      (await deepCheckApi.updateDefinition(id, payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deep-check', 'definitions'] });
    },
  });
}

export function useDeleteDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await deepCheckApi.deleteDefinition(id);
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deep-check', 'definitions'] });
    },
  });
}

export function useTestDefinition() {
  return useMutation<DeepCheckTestResult, Error, { id: string; clusterId: string }>({
    mutationFn: async ({ id, clusterId }) =>
      (await deepCheckApi.testDefinition(id, clusterId)).data,
  });
}
