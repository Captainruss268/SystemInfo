# System Monitor Dashboard

A real-time web application that monitors and displays your computer's system information, featuring live updates and visual data representations.

## Features

- **Real-time monitoring** of CPU, memory, disk, and network usage
- **Interactive memory chart** with circular progress indicators
- **Hardware information** including processor details, GPU specs, and motherboard info
- **Network statistics** showing interfaces, IP info, and I/O counters
- **Dark/Light theme** toggle
- **Sidebar navigation** with smooth scrolling to each section
- **Modern interface** with responsive design and smooth animations

## Technology Stack

### Backend
- Python with Flask web framework
- psutil for system monitoring
- WMI for Windows hardware information
- pynvml for NVIDIA GPU memory detection

### Frontend
- React 18 with TypeScript
- Chart.js for performance graphs
- tsparticles for animated background
- Custom SVG circular progress components

## Quick Start

### One-Click Setup (Windows)

**Double-click `start.bat`**.

The script automatically:
1. ✅ Checks for Python and Node.js (installs via winget if missing)
2. ✅ Installs backend Python dependencies
3. ✅ Starts the backend server on port 5000
4. ✅ Installs frontend npm packages
5. ✅ Starts the frontend dev server on port 3000
6. ✅ Opens the dashboard in your browser

> If Python or Node.js aren't installed, the script will handle installation automatically.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/system-info` | GET | Core system metrics (CPU, memory, disk, network, platform) |
| `/api/hardware-info` | GET | Detailed hardware specifications (GPU, motherboard, processor, WiFi) |
| `/api/health` | GET | Health check with server timestamp |
| `/api/reset-io` | POST | Reset network I/O counters to zero |

## Project Status

✅ **Stable** — All core features complete:
- Real-time system monitoring with 5-second refresh
- CPU, memory, disk, and network visualization
- Hardware detection (GPU, motherboard, WiFi adapters)
- Hybrid CPU core detection (P-cores vs E-cores)
- Historical performance tracking with configurable time windows
- Dark/Light theme support
- Animated particle background
- Responsive sidebar navigation
