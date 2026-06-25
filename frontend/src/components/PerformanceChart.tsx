import React, { useMemo } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ChartOptions,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { HistoricalDataPoint } from '../types';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
);

interface PerformanceChartProps {
  data: HistoricalDataPoint[];
  timeWindow: number;
  maxPoints: number;
  onClearData: () => void;
  onChangeTimeWindow: (minutes: number) => void;
}

const PerformanceChart: React.FC<PerformanceChartProps> = ({
  data,
  timeWindow,
  maxPoints,
  onClearData,
  onChangeTimeWindow,
}) => {
  const maxSeconds = timeWindow * 60;

  const networkChartData = useMemo(() => {
    const points: { x: number; y: number }[] = [];

    if (data.length <= 1) {
      return {
        datasets: [
          {
            label: 'Network (MB/s)',
            data: points,
            borderColor: '#4ecdc4',
            backgroundColor: 'rgba(78, 205, 196, 0.1)',
            tension: 0.4,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: '#4ecdc4',
            spanGaps: false,
          },
        ],
      };
    }

    const windowMs = timeWindow * 60 * 1000;
    const newestTime = data[data.length - 1].timestamp;
    const windowStart = newestTime - windowMs;
    const filtered = data.filter(d => d.timestamp >= windowStart);

    for (let i = 1; i < filtered.length; i++) {
      const prev = filtered[i - 1];
      const curr = filtered[i];
      const timeDiff = (curr.timestamp - prev.timestamp) / 1000;
      let mbps = 0;
      if (timeDiff > 0) {
        const bytesSent = Math.max(0, curr.network_bytes_sent - prev.network_bytes_sent);
        const bytesRecv = Math.max(0, curr.network_bytes_recv - prev.network_bytes_recv);
        const bytesPerSecond = (bytesSent + bytesRecv) / timeDiff;
        mbps = Math.round(bytesPerSecond / (1024 * 1024) * 100) / 100;
      }
      const secondsAgo = Math.round((newestTime - curr.timestamp) / 1000);
      points.push({ x: secondsAgo, y: mbps });
    }

    return {
      datasets: [
        {
          label: 'Network (MB/s)',
          data: points,
          borderColor: '#4ecdc4',
          backgroundColor: 'rgba(78, 205, 196, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: '#4ecdc4',
          spanGaps: false,
        },
      ],
    };
  }, [data, timeWindow]);

  const networkOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    clip: { left: 0, top: 5, right: 5, bottom: 5 },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    layout: {
      padding: {
        left: 0,
        right: 15,
        top: 5,
        bottom: 5,
      },
    },
    plugins: {
      title: {
        display: false,
      },
      legend: {
        position: 'top' as const,
        labels: {
          boxWidth: 12,
          padding: 10,
          font: { size: 11 },
        },
      },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
        callbacks: {
          title: (tooltipItems) => `Time: ${Math.round(tooltipItems[0].parsed.x as number)}s`,
          label: (tooltipItem) => `${tooltipItem.dataset.label}: ${tooltipItem.parsed.y} MB/s`,
        },
      },
    },
    scales: {
      x: {
        type: 'linear',
        display: true,
        min: 0,
        max: maxSeconds,
        beginAtZero: true,
        title: {
          display: true,
          text: 'Seconds ago',
        },
        ticks: {
          font: { size: 10 },
          maxRotation: 0,
          maxTicksLimit: 6,
          callback: (value) => `${Math.round(value as number)}s`,
        },
        grid: {
          display: true,
        },
      },
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
        min: 0,
        title: {
          display: true,
          text: 'Speed (MB/s)',
        },
        ticks: {
          font: { size: 10 },
        },
      },
    },
  };

  return (
    <div className="performance-chart card">
      <div className="chart-header">
        <h2>Network Speed Over Time</h2>
        <div className="chart-controls">
          <div className="time-window-buttons">
            <button
              className={`time-btn ${timeWindow === 1 ? 'active' : ''}`}
              onClick={() => onChangeTimeWindow(1)}
            >
              1 min
            </button>
            <button
              className={`time-btn ${timeWindow === 5 ? 'active' : ''}`}
              onClick={() => onChangeTimeWindow(5)}
            >
              5 min
            </button>
          </div>
          <button className="reset-btn" onClick={onClearData}>
            Reset
          </button>
        </div>
      </div>
      {data.length === 0 ? (
        <div className="chart-placeholder">
          <p>Collecting data... Chart will appear shortly.</p>
        </div>
      ) : (
        <Line data={networkChartData} options={networkOptions} />
      )}
    </div>
  );
};

export default PerformanceChart;