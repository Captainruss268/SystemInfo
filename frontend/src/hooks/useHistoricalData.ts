import { useState, useEffect, useRef, useCallback } from 'react';
import { HistoricalDataPoint, SystemInfoData } from '../types';

const INTERVAL_MS = 1000;

export const useHistoricalData = () => {
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [timeWindow, setTimeWindow] = useState<number>(5); // minutes
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastDataRef = useRef<SystemInfoData | null>(null);

  const clearData = useCallback(() => setHistoricalData([]), []);

  const changeTimeWindow = useCallback((minutes: number) => {
    setTimeWindow(minutes);
    const maxPoints = Math.floor((minutes * 60 * 1000) / INTERVAL_MS);
    setHistoricalData(prev => prev.slice(-maxPoints));
  }, []);

  const addDataPoint = (data: SystemInfoData) => {
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
      const maxPoints = Math.floor(timeWindowRef.current / (INTERVAL_MS / 1000));
      if (updated.length > maxPoints) {
        return updated.slice(-maxPoints);
      }
      return updated;
    });

    lastDataRef.current = data;
  };

  // Use a ref so the addDataPoint closure always has the latest timeWindow
  const timeWindowRef = useRef(timeWindow * 60 * 1000);
  useEffect(() => { timeWindowRef.current = timeWindow * 60 * 1000; }, [timeWindow]);

  const maxPoints = Math.floor((timeWindow * 60 * 1000) / INTERVAL_MS);

  const startTracking = () => {
    if (intervalRef.current) return;
    intervalRef.current = setInterval(() => {
      if (lastDataRef.current) {
        addDataPoint(lastDataRef.current);
      }
    }, INTERVAL_MS);
  };

  const stopTracking = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, []);

  return {
    historicalData,
    timeWindow,
    maxPoints,
    addDataPoint,
    startTracking,
    stopTracking,
    clearData,
    changeTimeWindow,
  };
};
