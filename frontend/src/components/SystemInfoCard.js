import React from 'react';
import './SystemInfoCard.css';

const SystemInfoCard = ({ data, hardwareData }) => {
  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  if (!data || !hardwareData) return null;

  const { platform, cpu, memory, disk } = data;
  const processorName = hardwareData.processor?.name || platform.processor;
  const cores = hardwareData.processor?.cores || cpu.cpu_count_physical;
  const logicalProcessors = hardwareData.processor?.logical_processors || cpu.cpu_count_logical;
  const coreTypes = cpu.core_types || { p_cores: 0, e_cores: cores, total_cores: cores };

  return (
    <div className="card system-info-card">
      <h2>System Information</h2>
      
      <div className="info-grid">
        <div className="info-item">
          <h3>OS</h3>
          <p>{platform.system} {platform.release}</p>
        </div>
        
        <div className="info-item">
          <h3>Architecture</h3>
          <p>{platform.architecture}</p>
        </div>
        
        <div className="info-item">
          <h3>Processor</h3>
          <p>{processorName}</p>
        </div>

        <div className="info-item">
          <h3>CPU Cores</h3>
          <p>{logicalProcessors} logical, {cores} physical</p>
        </div>

        <div className="info-item memory-item">
          <h3>Memory Usage</h3>
          <div className="memory-info">
            <div className="memory-text">
              <p>Total: {formatBytes(memory.total)}</p>
              <p>Used: {formatBytes(memory.used)}</p>
            </div>
            <div className="circle-chart">
              <svg width="120" height="120" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="50" stroke="#ddd" strokeWidth="6" fill="none" />
                <circle
                  cx="60" cy="60" r="50" stroke="#4ecdc4" strokeWidth="6" fill="none"
                  strokeDasharray={`${2 * Math.PI * 50}`} strokeDashoffset={`${2 * Math.PI * 50 * (1 - memory.percent / 100)}`}
                  transform="rotate(-90 60 60)"
                />
                <text x="60" y="65" textAnchor="middle" fontSize="20" fill="#fff" fontWeight="bold">
                  {memory.percent.toFixed(1)}%
                </text>
              </svg>
            </div>
          </div>
        </div>

        <div className="cpu-temperature-item">
          <h3>CPU Temperature</h3>
          <div className="cpu-temperature-chart">
            {cpu.temperatures && cpu.temperatures.length > 0 ? (
              (() => {
                const temp = cpu.temperatures[0].current;
                const maxTemp = 100;
                const percent = Math.min((temp / maxTemp) * 100, 100);
                const circumference = 2 * Math.PI * 50;
                const strokeLength = circumference * (percent / 100);

                return (
                  <svg width="120" height="120" viewBox="0 0 120 120">
                    <circle cx="60" cy="60" r="50" stroke="#ddd" strokeWidth="6" fill="none" />
                    <circle
                      cx="60" cy="60" r="50" stroke="#ff6b35" strokeWidth="6" fill="none"
                      strokeDasharray={`${circumference}`}
                      strokeDashoffset={`${circumference - strokeLength}`}
                      transform="rotate(-90 60 60)"
                    />
                    <text x="60" y="65" textAnchor="middle" fontSize="20" fill="#fff" fontWeight="bold">
                      {temp.toFixed(0)}°C
                    </text>
                  </svg>
                );
              })()
            ) : (
              <div className="cpu-temp-placeholder">
                <svg width="120" height="120" viewBox="0 0 120 120">
                  <circle cx="60" cy="60" r="50" stroke="#ddd" strokeWidth="6" fill="none" />
                  <text x="60" y="65" textAnchor="middle" fontSize="20" fill="#fff" fontWeight="bold">
                    No Data
                  </text>
                </svg>
              </div>
            )}
          </div>
        </div>

        <div className="info-item cpu-usage-item">
          <h3>CPU Usage by Core</h3>
          {coreTypes.p_cores > 0 || coreTypes.e_cores > 0 ? (
            <div className="core-info-display">
              <p className="core-summary">
                {coreTypes.p_cores > 0 && `${coreTypes.p_cores} Performance Core${coreTypes.p_cores > 1 ? 's' : ''}`}
                {coreTypes.p_cores > 0 && coreTypes.e_cores > 0 && ', '}
                {coreTypes.e_cores > 0 && `${coreTypes.e_cores} Efficiency Core${coreTypes.e_cores > 1 ? 's' : ''}`}
              </p>
            </div>
          ) : null}
          <div className="cpu-cores">
            {cpu.cpu_percent.map((core, index) => {
              let label = 'Core';
              let coreNum = index + 1;
              let coreType = '';

              // Determine if this is a P-core or E-core
              if (coreTypes.p_cores > 0 && coreTypes.e_cores > 0) {
                // Hybrid CPU with both types (Intel/AMD Ryzen/Qualcomm)
                if (index < coreTypes.p_cores) {
                  coreType = 'P';
                  coreNum = index + 1;
                } else {
                  coreType = 'E';
                  coreNum = index - coreTypes.p_cores + 1;
                }
                label = `${coreType}-Core`;
              } else if (coreTypes.p_cores === cores && coreTypes.e_cores === 0) {
                // Apple Silicon or other unified-performance CPUs
                label = `P-Core`;
                coreNum = index + 1;
                coreType = 'P';
              } else {
                // Standard CPUs without hybrid architecture
                label = 'Core';
              }

              return (
                <div key={index} className={`cpu-core ${coreType === 'P' ? 'performance-core' : coreType === 'E' ? 'efficiency-core' : ''} ${core < 5 ? 'idle-core' : ''}`}>
                  <span>{label} {coreNum}</span>
                  <div className="progress-bar-container">
                    <div
                      className="progress-bar"
                      style={{ width: `${core}%` }}
                    >
                      {core.toFixed(1)}%
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="disk-info-section">
          <h3>Storage Information</h3>
          {disk && disk.length > 0 ? (
            <div className="disk-info">
              {disk.map((diskItem, index) => (
                <div key={index} className="disk-item">
                  <h4>Drive {diskItem.device.replace('/dev/', '').replace('\\', '')}</h4>
                  <div className="disk-details">
                    <div className="disk-text">
                      <p>Mount Point: {diskItem.mountpoint}</p>
                      <p>File System: {diskItem.fstype}</p>
                      <p>Total: {formatBytes(diskItem.total)}</p>
                      <p>Used: {formatBytes(diskItem.used)}</p>
                      <p>Free: {formatBytes(diskItem.free)}</p>
                    </div>
                    <div className="disk-usage-chart">
                      <svg width="120" height="120" viewBox="0 0 120 120">
                        <circle cx="60" cy="60" r="50" stroke="#ddd" strokeWidth="8" fill="none" />
                        <circle
                          cx="60" cy="60" r="50" stroke="#ff6b6b" strokeWidth="8" fill="none"
                          strokeDasharray={`${2 * Math.PI * 50}`} strokeDashoffset={`${2 * Math.PI * 50 * (1 - diskItem.percent / 100)}`}
                          transform="rotate(-90 60 60)"
                        />
                        <text x="60" y="65" textAnchor="middle" fontSize="18" fill="#fff" fontWeight="bold">
                          {diskItem.percent.toFixed(1)}%
                        </text>
                      </svg>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p>No storage information available</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default SystemInfoCard;
