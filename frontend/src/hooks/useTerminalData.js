import { useQuery } from "@tanstack/react-query";
import { fetchChartSuite, fetchCoreSnapshot, fetchDetailSnapshot, fetchExpiryExposureMap, fetchJson, fetchPriceHistory, normalizeOverlay } from "../lib/api";

export function useTerminalData({ symbol, bucket, overlayFilters, chartNames = [], language = "en", includePriceHistory = false, includeExpiryMap = false }) {
  const symbolsQuery = useQuery({
    queryKey: ["symbols"],
    queryFn: ({ signal }) => fetchJson("/api/v1/symbols", { signal }),
    staleTime: 60_000,
    refetchInterval: 60_000,
  });

  const symbols = Array.isArray(symbolsQuery.data) ? symbolsQuery.data : [];
  const activeSymbol = symbols.includes(symbol) || !symbols.length ? symbol : symbols[0];
  const coreQuery = useQuery({
    queryKey: [
      "terminal-snapshot",
      activeSymbol,
      bucket,
      language,
      overlayFilters.flowType,
      overlayFilters.flowSide,
      overlayFilters.flowExpiration,
      overlayFilters.minPremium,
      overlayFilters.minVolume,
      overlayFilters.window,
      overlayFilters.timeframe,
    ],
    queryFn: ({ signal }) => fetchCoreSnapshot({ symbol: activeSymbol, bucket, overlayFilters, language, signal }),
    enabled: Boolean(activeSymbol),
    staleTime: 2_000,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    retry: 2,
    placeholderData: (previous) => previous,
  });

  const detailQuery = useQuery({
    queryKey: ["terminal-details", activeSymbol, bucket, language],
    queryFn: ({ signal }) => fetchDetailSnapshot({ symbol: activeSymbol, bucket, language, signal }),
    enabled: Boolean(activeSymbol) && coreQuery.status === "success",
    staleTime: 8_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 1,
    placeholderData: (previous) => previous,
  });

  const chartsQuery = useQuery({
    queryKey: [
      "terminal-charts",
      activeSymbol,
      bucket,
      overlayFilters.window,
      overlayFilters.metric,
      overlayFilters.series,
      overlayFilters.profileExpiry,
      overlayFilters.profileSide,
      overlayFilters.profileMode,
      language,
      chartNames,
    ],
    queryFn: ({ signal }) => fetchChartSuite({
      symbol: activeSymbol,
      bucket,
      chartNames,
      window: overlayFilters.window,
      metric: overlayFilters.metric,
      series: overlayFilters.series,
      profileExpiry: overlayFilters.profileExpiry,
      profileSide: overlayFilters.profileSide,
      profileMode: overlayFilters.profileMode,
      language,
      signal,
    }),
    enabled: Boolean(activeSymbol) && chartNames.length > 0 && coreQuery.status === "success",
    staleTime: 10_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 1,
    placeholderData: (previous) => previous,
  });

  const priceQuery = useQuery({
    queryKey: ["terminal-price-history", activeSymbol, overlayFilters.historyDays, overlayFilters.interval],
    queryFn: ({ signal }) => fetchPriceHistory({ symbol: activeSymbol, days: overlayFilters.historyDays, interval: overlayFilters.interval, signal }),
    enabled: Boolean(activeSymbol) && includePriceHistory,
    staleTime: 5_000,
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
    retry: 1,
    placeholderData: (previous) => previous,
  });

  const expiryMapQuery = useQuery({
    queryKey: ["terminal-expiry-map", activeSymbol, overlayFilters.expiryMapMetric, overlayFilters.expiryMapExpiries, overlayFilters.expiryMapStrikes],
    queryFn: ({ signal }) => fetchExpiryExposureMap({
      symbol: activeSymbol,
      metric: overlayFilters.expiryMapMetric,
      expiries: overlayFilters.expiryMapExpiries,
      strikes: overlayFilters.expiryMapStrikes,
      signal,
    }),
    enabled: Boolean(activeSymbol) && includeExpiryMap && coreQuery.status === "success",
    staleTime: 10_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 1,
    placeholderData: (previous) => previous,
  });

  const data = { ...(coreQuery.data || {}), ...(detailQuery.data || {}), charts: chartsQuery.data?.charts || {} };
  return {
    symbols,
    activeSymbol,
    ...data,
    overlay: normalizeOverlay(data.overlay),
    status: coreQuery.status,
    priceHistory: priceQuery.data,
    priceHistoryStatus: priceQuery.status,
    expiryMap: expiryMapQuery.data,
    expiryMapStatus: expiryMapQuery.status,
    isFetching: coreQuery.isFetching || detailQuery.isFetching || chartsQuery.isFetching || priceQuery.isFetching || expiryMapQuery.isFetching,
    isStale: coreQuery.isStale || detailQuery.isStale,
    error: coreQuery.error,
    chartsStatus: chartsQuery.status,
    chartErrors: chartsQuery.data?.errors || {},
    refresh: () => Promise.all([coreQuery.refetch(), detailQuery.refetch(), chartsQuery.refetch(), priceQuery.refetch(), expiryMapQuery.refetch()]),
  };
}
