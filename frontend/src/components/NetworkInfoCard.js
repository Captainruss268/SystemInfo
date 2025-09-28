import React, { useState, useEffect } from 'react';
import './NetworkInfoCard.css';

const NetworkInfoCard = ({ data }) => {
  const [networkData, setNetworkData] = useState(data);

  useEffect(() => {
    setNetworkData(data);
  }, [data]);

  const refetchData = async () => {
    try {
      const response = await fetch('http://localhost:5000/api/system-info');
      const newData = await response.json();
      setNetworkData(newData.network);
    } catch (error) {
      console.error('Failed to refetch data:', error);
    }
  };
  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  if (!networkData) return null;

  return (
    <div className="network-info-card">
      <h2>Network Information</h2>

      <div className="network-section">
        <h3>Location</h3>
        {networkData.ip_info ? (
          <div className="location-info">
            {networkData.ip_info.error ? (
              <p>{networkData.ip_info.error}</p>
            ) : (
              <div className="location-details">
                {networkData.ip_info.city && (
                  <div className="location-item">
                    <span className="location-label">City:</span>
                    <span className="location-value">{networkData.ip_info.city}</span>
                  </div>
                )}
                {networkData.ip_info.region && (
                  <div className="location-item">
                    <span className="location-label">Province/State:</span>
                    <span className="location-value">{networkData.ip_info.region}</span>
                  </div>
                )}
                {networkData.ip_info.country && (
                  <div className="location-item">
                    <span className="location-label">Country:</span>
                    <span className="location-value">{networkData.ip_info.country}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <p>No location information available</p>
        )}
      </div>

      <div className="network-section">
        <h3>IP Address</h3>
        {networkData.ip_info ? (
          <div className="ip-info">
            {networkData.ip_info.error ? (
              <p>{networkData.ip_info.error}</p>
            ) : (
              <div className="ip-details">
                <div className="ip-item">
                  <span className="ip-label">IPv4 Address:</span>
                  <span className="ip-value">{networkData.ip_info.ip}</span>
                </div>
                {networkData.local_ipv6 && (
                  <div className="ip-item">
                    <span className="ip-label">IPv6 Address:</span>
                    <span className="ip-value">{networkData.local_ipv6}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <p>No IP information available</p>
        )}
      </div>

        <div className="network-section">
          <div className="io-header">
            <h3>Network I/O Statistics</h3>
            <button className="reset-button" onClick={async () => {
              try {
              const resetResponse = await fetch('http://localhost:5000/api/reset-io', { method: 'POST' });
                if (resetResponse.ok) {
                  refetchData(); // Update data without reload
                }
              } catch (error) {
                console.error('Failed to reset I/O:', error);
              }
            }}>
              Reset
            </button>
          </div>
          <div className="io-stats">
            <div className="stat-item">
              <span className="stat-label">Data Downloaded:</span>
              <span className="stat-value">{formatBytes(networkData.io_counters.bytes_recv)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Data Uploaded:</span>
              <span className="stat-value">{formatBytes(networkData.io_counters.bytes_sent)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Packets Sent:</span>
              <span className="stat-value">{networkData.io_counters.packets_sent}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Packets Received:</span>
              <span className="stat-value">{networkData.io_counters.packets_recv}</span>
            </div>
          </div>
        </div>
      

    </div>
  );
};

export default NetworkInfoCard;
