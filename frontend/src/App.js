import React, { useState, useEffect } from 'react';
import SystemInfoCard from './components/SystemInfoCard';
import NetworkInfoCard from './components/NetworkInfoCard';
import HardwareInfoCard from './components/HardwareInfoCard';
import DynamicBackground from './components/DynamicBackground';
import TechStack from './components/TechStack';
import './App.css';

const App = () => {
  const [systemInfo, setSystemInfo] = useState(null);
  const [hardwareInfo, setHardwareInfo] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        // Fetch system and hardware info in parallel
        const [systemResponse, hardwareResponse] = await Promise.all([
          fetch('http://localhost:5000/api/system-info'),
          fetch('http://localhost:5000/api/hardware-info')
        ]);

        if (!systemResponse.ok) {
          throw new Error(`HTTP error! status: ${systemResponse.status}`);
        }
        if (!hardwareResponse.ok) {
          throw new Error(`HTTP error! status: ${hardwareResponse.status}`);
        }

        const systemData = await systemResponse.json();
        const hardwareData = await hardwareResponse.json();

        setSystemInfo(systemData);
        setHardwareInfo(hardwareData);
      } catch (e) {
        setError(e.message);
        console.error("Failed to fetch data:", e);
      }
    };

    fetchData();
    const intervalId = setInterval(fetchData, 1000);

    return () => clearInterval(intervalId);
  }, []);

  return (
    <div className="app-container">
      <DynamicBackground />
      <header className="app-header">
        <h1>System Monitor</h1>
      </header>
      <main className="main-content">
        {error && <p className="error-message">Error fetching data: {error}</p>}
        {systemInfo && hardwareInfo ? (
          <div className="info-cards">
            <SystemInfoCard data={systemInfo} hardwareData={hardwareInfo} />
            <NetworkInfoCard data={systemInfo.network} />
            <HardwareInfoCard data={hardwareInfo} />
          </div>
        ) : (
          !error && <p className="loading-message">Loading system information...</p>
        )}
      </main>
      <TechStack />
    </div>
  );
};

export default App;
