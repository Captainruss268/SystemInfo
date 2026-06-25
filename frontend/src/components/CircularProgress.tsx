import React from 'react';

interface CircularProgressProps {
  value: number;
  maxValue?: number;
  label?: string;
  strokeColor?: string;
  size?: number;
}

const CircularProgress: React.FC<CircularProgressProps> = ({
  value,
  maxValue = 100,
  label,
  strokeColor = '#4ecdc4',
  size = 120,
}) => {
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const percent = Math.min((value / maxValue) * 100, 100);
  const strokeLength = circumference * (percent / 100);

  return (
    <svg width={size} height={size} viewBox="0 0 120 120">
      <circle cx="60" cy="60" r={radius} stroke="#ddd" strokeWidth="6" fill="none" />
      <circle
        cx="60" cy="60" r={radius}
        stroke={strokeColor} strokeWidth="6" fill="none"
        strokeDasharray={`${circumference}`}
        strokeDashoffset={`${circumference - strokeLength}`}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="65" textAnchor="middle" fontSize="20" className="chart-text" fontWeight="bold">
        {label ?? `${percent.toFixed(1)}%`}
      </text>
    </svg>
  );
};

export default CircularProgress;