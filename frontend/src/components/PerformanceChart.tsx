import React, { useEffect, useMemo } from 'react';
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

// Register Chart.js components
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
  // Prepare chart data
  const chartData = useMemo(() => {
    const labels = data.map(point =>
      new Date(point.timestamp).toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    );

    // Get CPU data (use average of all cores)
    const cpuData = data.map(point => {
      if (point.cpu_percent.length === 0) return 0;
      const avg = point.cpu_percent.reduce((a, b) => a + b, 0) / point.cpu_percent.length;
      return Math.round(avg * 100) / 100;
    });

    // Memory data
    const memoryData = data.map(point => Math.round(point.memory_percent * 100) / 100);

    // Network data (convert to MB/s)
    const networkData = data.map((point, index) => {
      if (index === 0) return 0;

      const prev = data[index - 1];
      const timeDiff = (point.timestamp - prev.timestamp) / 1000; // seconds
      const bytesPerSecond = (point.network_bytes_sent - prev.network_bytes_sent) / timeDiff;
      return Math.round(bytesPerSecond / (1024 * 1024) * 100) / 100; // MB/s
    });

    return {
      labels,
      datasets: [
        {
          label: 'CPU Usage (%)',
          data: cpuData,
          borderColor: '#00ffff',
          backgroundColor: 'rgba(0, 255, 255, 0.1)',
          tension: 0.4,
          fill: true,
        },
        {
          label: 'Memory Usage (%)',
          data: memoryData,
          borderColor: '#ff6b6b',
          backgroundColor: 'rgba(255, 107, 107, 0.1)',
          tension: 0.4,
          fill: true,
        },
        {
          label: 'Network (MB/s)',
          data: networkData,
          borderColor: '#4ecdc4',
          backgroundColor: 'rgba(78, 205, 196, 0.1)',
          yAxisID: 'y1',
          tension: 0.4,
          fill: false,
        },
      ],
    };
  }, [data]);

  // Chart options
  const options: ChartOptions<'line'> = {
    responsive: true,
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
    plugins: {
      title: {
        display: true,
        text: 'System Performance Over Time',
        font: {
          size: 20,
        },
      },
      legend: {
        position: 'top' as const,
      },
      tooltip: {
        mode: 'index' as const,
        intersect: false,
        callbacks: {
          title: (tooltipItems) => {
            return `Time: ${tooltipItems[0].label}`;
          },
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
      },
      y: {
        type: 'linear' as const,
        display: true,
        position: 'left' as const,
        title: {
          display: true,
          text: 'Usage (%)',
        },
      },
      y1: {
        type: 'linear' as const,
        display: true,
        position: 'right' as const,
        title: {
          display: true,
          text: 'Network (MB/s)',
        },
        grid: {
          drawOnChartArea: false,
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
    <div className="performance-chart">
      <Line data={chartData} options={options} />
    </div>
  );
};

export default PerformanceChart;
