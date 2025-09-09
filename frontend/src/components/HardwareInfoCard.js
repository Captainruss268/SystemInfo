import React from 'react';
import './HardwareInfoCard.css';

const HardwareInfoCard = ({ data }) => {
  if (!data) {
    return <div className="card hardware-info-card"><h2>Hardware Information</h2><p>No data available.</p></div>;
  }

  const { gpu, motherboard } = data;

  return (
    <div className="card hardware-info-card">
      <h2>Hardware Information</h2>
      <div className="hardware-section">
        <h3>GPU</h3>
        {gpu && gpu.length > 0 ? (
          <ul>
            {gpu.map((item, index) => (
              <li key={index}>
                <strong>{item.name}</strong>
                <br />
                <span>Driver: {item.driver_version}</span>
                <br />
                <span>Status: {item.status}</span>
                <br />
                <span>RAM: {(item.adapter_ram / (1024 ** 3)).toFixed(2)} GB</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>N/A</p>
        )}
      </div>
      <div className="hardware-section">
        <h3>Motherboard</h3>
        {motherboard ? (
          <ul>
            <li><strong>Manufacturer:</strong> {motherboard.manufacturer}</li>
            <li><strong>Product:</strong> {motherboard.product}</li>
            <li><strong>Serial:</strong> {motherboard.serial_number}</li>
          </ul>
        ) : (
          <p>N/A</p>
        )}
      </div>
    </div>
  );
};

export default HardwareInfoCard;
