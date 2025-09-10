import React, { useState, useEffect, useRef } from 'react';
import SystemInfoCard from './components/SystemInfoCard';
import NetworkInfoCard from './components/NetworkInfoCard';
import HardwareInfoCard from './components/HardwareInfoCard';
import DynamicBackground from './components/DynamicBackground';
import TechStack from './components/TechStack';
import ThemeToggle from './components/ThemeToggle';
import PerformanceChart from './components/PerformanceChart';
import { ThemeProvider } from './context/ThemeContext';
import { useHistoricalData } from './hooks/useHistoricalData';
import { SystemInfoData, HardwareInfo } from './types';
import './App.css';

// Main app content component
const AppContent: React.FC = () => {
  const [systemInfo, setSystemInfo] = useState<SystemInfoData | null>(null);
  const [hardwareInfo, setHardwareInfo] = useState<HardwareInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { historicalData, addDataPoint, startTracking, clearData } = useHistoricalData();

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Clear previous errors when retrying
        setError(null);

        // Fetch system and hardware info in parallel with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        const [systemResponse, hardwareResponse] = await Promise.all([
          fetch('http://localhost:5000/api/system-info', {
            signal: controller.signal,
            headers: {
              'Cache-Control': 'no-cache'
            }
          }),
          fetch('http://localhost:5000/api/hardware-info', {
            signal: controller.signal,
            headers: {
              'Cache-Control': 'no-cache'
            }
          })
        ]);

        clearTimeout(timeoutId);

        if (!systemResponse.ok) {
          throw new Error(`System info: HTTP ${systemResponse.status}`);
        }
        if (!hardwareResponse.ok) {
          throw new Error(`Hardware info: HTTP ${hardwareResponse.status}`);
        }

        const systemData = await systemResponse.json();
        const hardwareData = await hardwareResponse.json();

        setSystemInfo(systemData);
        setHardwareInfo(hardwareData);

        // Add data point to historical tracking
        addDataPoint(systemData);
      } catch (e) {
        const error = e as Error;
        if (error.name === 'AbortError') {
          console.error("Request timed out");
          setError("Request timed out - server may be overloaded");
        } else {
          console.error("Failed to fetch data:", error);
          setError(error.message || "Failed to fetch system data");
        }
      }
    };

    fetchData();
    const intervalId = setInterval(fetchData, 5000); // Changed from 1000ms to 5000ms

    return () => clearInterval(intervalId);
  }, []);

  return (
    <div className="app-container">
      <DynamicBackground />
      <header className="app-header">
        <h1>System Monitor</h1>
        <ThemeToggle />
      </header>
      <nav className="section-nav">
        <button className="nav-link" onClick={() => document.querySelector('.network-info-card')?.scrollIntoView({ behavior: 'smooth' })}>Network</button>
        <button className="nav-link" onClick={() => document.querySelector('.system-info-card')?.scrollIntoView({ behavior: 'smooth' })}>System & CPU</button>
        <button className="nav-link" onClick={() => document.querySelector('.hardware-info-card')?.scrollIntoView({ behavior: 'smooth' })}>Hardware</button>
        <button className="nav-link" onClick={() => document.querySelector('.performance-chart-container')?.scrollIntoView({ behavior: 'smooth' })}>Performance</button>
      </nav>
      <main className="main-content">
        {error && <p className="error-message">Error fetching data: {error}</p>}
        {systemInfo && hardwareInfo ? (
          <>
            <div className="info-cards">
              <NetworkInfoCard data={systemInfo.network} />
              <SystemInfoCard data={systemInfo} hardwareData={hardwareInfo} />
              <HardwareInfoCard data={hardwareInfo} />
            </div>
            <div className="performance-chart-container">
              <PerformanceChart data={historicalData} />
            </div>
          </>
        ) : (
          !error && <p className="loading-message">Loading system information...</p>
        )}
      </main>
      <TechStack />
    </div>
  );
};

// Main App component with theme provider
const App: React.FC = () => {
  return (
    <ThemeProvider>
      <AppContent />
    </ThemeProvider>
  );
};

export default App;
