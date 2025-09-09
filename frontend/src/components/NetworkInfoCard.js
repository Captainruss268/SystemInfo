import React from 'react';
import './NetworkInfoCard.css';

const NetworkInfoCard = ({ data }) => {
  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  if (!data) return null;

  return (
    <div className="network-info-card">
      <h2>Network Information</h2>
      
      <div className="network-section">
        <h3>Network Interfaces</h3>
        {Object.keys(data.interfaces).length > 0 ? (
          Object.entries(data.interfaces).map(([interfaceName, addresses]) => (
            <div key={interfaceName} className="interface-card">
              <h4>{interfaceName}</h4>
              {addresses.map((addr, index) => (
                <div key={index} className="address-item">
                  <span className="address-type">{addr.type}: </span>
                  <span className="address-value">{addr.address}</span>
                  {addr.netmask && <span> (Netmask: {addr.netmask})</span>}
                </div>
              ))}
            </div>
          ))
        ) : (
          <p>No network interfaces found</p>
        )}
      </div>
      
      <div className="network-section">
        <h3>Network I/O Statistics</h3>
        <div className="io-stats">
          <div className="stat-item">
            <span className="stat-label">Bytes Sent:</span>
            <span className="stat-value">{formatBytes(data.io_counters.bytes_sent)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Bytes Received:</span>
            <span className="stat-value">{formatBytes(data.io_counters.bytes_recv)}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Packets Sent:</span>
            <span className="stat-value">{data.io_counters.packets_sent}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Packets Received:</span>
            <span className="stat-value">{data.io_counters.packets_recv}</span>
          </div>
        </div>
      </div>
      
      <div className="network-section">
        <h3>Active Connections</h3>
        {data.connections && data.connections.length > 0 ? (
          <div className="connections-list">
            {data.connections.slice(0, 10).map((conn, index) => (
              <div key={index} className="connection-item">
                <div className="connection-details">
                  <span className="connection-address">{conn.local_address}</span>
                  <span className="connection-type">→</span>
                  <span className="connection-address">{conn.remote_address || 'N/A'}</span>
                </div>
                <div className="connection-status">{conn.status}</div>
              </div>
            ))}
            {data.connections.length > 10 && (
              <p className="more-connections">... and {data.connections.length - 10} more connections</p>
            )}
          </div>
        ) : (
          <p>No active network connections found</p>
        )}
      </div>
    </div>
  );
};

export default NetworkInfoCard;