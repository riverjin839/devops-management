import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { dailyCheckApi, deepCheckApi } from '@/services/api';
import type { DailyCheckLog, DeepCheckReview } from '@/types';

const keys = {
  latestDaily: (clusterId: string) => ['daily-check', 'latest', clusterId] as const,
  review: (dailyCheckLogId: string) => ['deep-check', 'review', dailyCheckLogId] as const,
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
