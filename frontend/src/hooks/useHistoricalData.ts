import { useState, useEffect, useRef } from 'react';
import { HistoricalDataPoint, SystemInfoData } from '../types';

const MAX_DATA_POINTS = 60; // Keep 1 hour of data (5 sec intervals)

export const useHistoricalData = () => {
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const lastDataRef = useRef<SystemInfoData | null>(null);

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

      // Keep only the last MAX_DATA_POINTS
      if (updated.length > MAX_DATA_POINTS) {
        return updated.slice(-MAX_DATA_POINTS);
      }

      return updated;
    });

    lastDataRef.current = data;
  };

  const startTracking = () => {
    if (intervalRef.current) return;

    intervalRef.current = setInterval(() => {
      if (lastDataRef.current) {
        addDataPoint(lastDataRef.current);
      }
    }, 5000); // Update every 5 seconds
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
    addDataPoint,
    startTracking,
    stopTracking,
    clearData: () => setHistoricalData([])
  };
};
