import { useState, useRef, useCallback } from 'react';
import { HistoricalDataPoint, SystemInfoData } from '../types';

const INTERVAL_MS = 5000;

export const useHistoricalData = () => {
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [timeWindow, setTimeWindow] = useState<number>(5); // minutes
  const lastDataRef = useRef<SystemInfoData | null>(null);
  // Use a ref so addDataPoint always has the latest timeWindow in its closure
  const timeWindowRef = useRef<number>(timeWindow * 60 * 1000);
  timeWindowRef.current = timeWindow * 60 * 1000;

  const clearData = useCallback(() => setHistoricalData([]), []);

  const changeTimeWindow = useCallback((minutes: number) => {
    setTimeWindow(minutes);
    const maxPoints = Math.floor((minutes * 60 * 1000) / INTERVAL_MS);
    setHistoricalData(prev => prev.slice(-maxPoints));
  }, []);

  const addDataPoint = useCallback((data: SystemInfoData) => {
    const now = Date.now();
    const newPoint: HistoricalDataPoint = {
      timestamp: now,
      cpu_percent: data.cpu?.cpu_percent || [],
      memory_percent: data.memory?.percent || 0,
      network_bytes_sent: data.network?.io_counters?.bytes_sent || 0,
      network_bytes_recv: data.network?.io_counters?.bytes_recv || 0,
    };

    setHistoricalData(prev => {
      const updated = [...prev, newPoint];
      const windowMs = timeWindowRef.current;
      const maxPoints = Math.floor(windowMs / INTERVAL_MS);
      // Keep only points within the current time window
      const cutoff = now - windowMs;
      const filtered = updated.filter(d => d.timestamp >= cutoff);
      return filtered.length > maxPoints ? filtered.slice(-maxPoints) : filtered;
    });

    lastDataRef.current = data;
  }, []); // stable ref — no reactive deps needed

  const maxPoints = Math.floor((timeWindow * 60 * 1000) / INTERVAL_MS);

  return {
    historicalData,
    timeWindow,
    maxPoints,
    addDataPoint,
    clearData,
    changeTimeWindow,
  };
};
