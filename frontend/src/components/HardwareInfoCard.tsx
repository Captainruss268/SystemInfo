import React from 'react';
import './HardwareInfoCard.css';
import { HardwareInfo } from '../types';

interface HardwareInfoCardProps {
  data: HardwareInfo | null;
}

const HardwareInfoCard: React.FC<HardwareInfoCardProps> = ({ data }) => {
  if (!data) {
    return <div className="card hardware-info-card"><h2>Hardware Information</h2><p>No data available.</p></div>;
  }

  const { gpu, motherboard, processor } = data;

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
                <span>RAM: {item.adapter_ram > 0 ? `${(item.adapter_ram / (1024 ** 3)).toFixed(2)} GB` : 'N/A'}</span>
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
      <div className="hardware-section">
        <h3>Processor</h3>
        {processor && Object.keys(processor).length > 0 ? (
          <ul>
            <li><strong>Name:</strong> {processor.name}</li>
            <li><strong>Manufacturer:</strong> {processor.manufacturer}</li>
            {processor.generation && <li><strong>Generation:</strong> {processor.generation}</li>}
            {processor.codename && processor.codename !== 'Unknown' && <li><strong>Codename:</strong> {processor.codename}</li>}
            <li><strong>Cores:</strong> {processor.cores}</li>
            <li><strong>Logical Processors:</strong> {processor.logical_processors}</li>
          </ul>
        ) : (
          <p>N/A</p>
        )}
      </div>
    </div>
  );
};

export default HardwareInfoCard;
