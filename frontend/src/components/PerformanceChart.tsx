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
}

const PerformanceChart: React.FC<PerformanceChartProps> = ({ data }) => {
  const networkChartData = useMemo(() => {
    const labels = data.map(point =>
      new Date(point.timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    );

    const networkData = data.map((point, index) => {
      if (index === 0) return 0;

      const prev = data[index - 1];
      const timeDiff = (point.timestamp - prev.timestamp) / 1000;
      if (timeDiff <= 0) return 0;
      const bytesSent = Math.max(0, point.network_bytes_sent - prev.network_bytes_sent);
      const bytesRecv = Math.max(0, point.network_bytes_recv - prev.network_bytes_recv);
      const bytesPerSecond = (bytesSent + bytesRecv) / timeDiff;
      return Math.round(bytesPerSecond / (1024 * 1024) * 100) / 100;
    });

    return {
      labels,
      datasets: [
        {
          label: 'Network (MB/s)',
          data: networkData,
          borderColor: '#4ecdc4',
          backgroundColor: 'rgba(78, 205, 196, 0.1)',
          tension: 0.4,
          fill: true,
        },
      ],
    };
  }, [data]);

  const networkOptions: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    clip: { left: 5, top: 5, right: 5, bottom: 5 },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    layout: {
      padding: {
        left: 5,
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
          title: (tooltipItems) => `Time: ${tooltipItems[0].label}`,
          label: (tooltipItem) => `${tooltipItem.dataset.label}: ${tooltipItem.parsed.y} MB/s`,
        },
      },
    },
    scales: {
      x: {
        display: true,
        title: {
          display: true,
          text: 'Time',
        },
        ticks: {
          maxTicksLimit: 8,
          font: { size: 10 },
          autoSkipPadding: 10,
          maxRotation: 30,
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

  if (data.length === 0) {
    return (
      <div className="chart-placeholder">
        <p>Collecting data... Chart will appear shortly.</p>
      </div>
    );
  }

  return (
    <div className="performance-chart card">
      <h2>Network Speed Over Time</h2>
      <Line data={networkChartData} options={networkOptions} />
    </div>
  );
};

export default PerformanceChart;