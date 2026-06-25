import React, { useState, useEffect } from 'react';
import SystemInfoCard from './components/SystemInfoCard';
import NetworkInfoCard from './components/NetworkInfoCard';
import HardwareInfoCard from './components/HardwareInfoCard';
import DynamicBackground from './components/DynamicBackground';
import TechStack from './components/TechStack';

import PerformanceChart from './components/PerformanceChart';
import SidebarNavigation from './components/SidebarNavigation';
import { ThemeProvider } from './context/ThemeContext';
import { useHistoricalData } from './hooks/useHistoricalData';
import { SystemInfoData, HardwareInfo } from './types';
import { API_BASE_URL } from './config';
import './App.css';

// Main app content component
const AppContent: React.FC = () => {
  const [systemInfo, setSystemInfo] = useState<SystemInfoData | null>(null);
  const [hardwareInfo, setHardwareInfo] = useState<HardwareInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { historicalData, addDataPoint, clearData, changeTimeWindow, timeWindow, maxPoints } = useHistoricalData();

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Clear previous errors when retrying
        setError(null);

        // Fetch system and hardware info in parallel with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000);

        const [systemResponse, hardwareResponse] = await Promise.all([
          fetch(`${API_BASE_URL}/api/system-info`, {
            signal: controller.signal,
            headers: { 'Cache-Control': 'no-cache' }
          }),
          fetch(`${API_BASE_URL}/api/hardware-info`, {
            signal: controller.signal,
            headers: { 'Cache-Control': 'no-cache' }
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
    const intervalId = setInterval(fetchData, 5000);

    return () => clearInterval(intervalId);
  }, [addDataPoint]);

  return (
    <div className="app-container">
      <SidebarNavigation />
      <DynamicBackground />
      <header className="app-header">
        <h1>System Monitor</h1>
      </header>
      <main className="main-content">
        {error && <p className="error-message">Error fetching data: {error}</p>}
        {systemInfo && hardwareInfo ? (
          <>
            <div className="info-cards">
              <SystemInfoCard data={systemInfo} hardwareData={hardwareInfo} />
              <HardwareInfoCard data={hardwareInfo} />
              <NetworkInfoCard data={systemInfo.network} />
            </div>
            <div className="performance-chart-container">
              <PerformanceChart
                data={historicalData}
                timeWindow={timeWindow}
                maxPoints={maxPoints}
                onClearData={clearData}
                onChangeTimeWindow={changeTimeWindow}
              />
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
