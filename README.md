# System Monitor Dashboard

A real-time web application that monitors and displays your computer's system information, featuring live updates and visual data representations.

## Features

- **Real-time monitoring** of CPU, memory, disk, and network usage
- **Interactive memory chart** with circular progress indicator
- **Hardware information** including processor details, GPU specs, and motherboard info
- **Network statistics** showing interfaces and active connections
- **Modern interface** with responsive design and smooth animations

## Technology Stack

### Backend
- Python with Flask web framework
- psutil for system monitoring
- WMI for Windows hardware information

### Frontend
- React.js for user interface
- Custom SVG charts
- CSS for styling

## Quick Start (Windows)

**Double-click `start.bat`** — it will automatically:

1. ✅ Check/install Python dependencies (via pip)
2. ✅ Check/install Node.js (via winget if missing)
3. ✅ Install frontend dependencies (npm install)
4. ✅ Start the backend server (port 5000)
5. ✅ Start the frontend dev server (port 3000)
6. ✅ Open the dashboard in your browser

> **One-click setup** — no manual steps required. If Python or Node.js aren't installed, the script will guide you.

## Manual Setup

### Prerequisites

- Python 3.8 or higher
- Node.js 14 or higher

### Installation & Running

1. **Clone the repository**
```bash
git clone <your-repository-url>
cd SystemInfo
```

2. **Install backend dependencies**
```bash
pip install -r backend/requirements.txt
```

3. **Install frontend dependencies**
```bash
cd frontend
npm install --legacy-peer-deps --ignore-scripts
cd ..
```

4. **Start the backend** (Terminal 1)
```bash
cd backend
python app.py
```

5. **Start the frontend** (Terminal 2)
```bash
cd frontend
npm start
```

6. Open **http://localhost:3000** in your browser

## API Endpoints

- `GET /api/system-info` — Core system metrics and platform information
- `GET /api/hardware-info` — Detailed hardware specifications
- `GET /api/health` — Health check
- `POST /api/reset-io` — Reset network IO counters

## Troubleshooting

### "node is not recognized" during npm install
The `@tsparticles/engine` package has a postinstall script that requires `node` on PATH. The `--ignore-scripts` flag bypasses this. If you see this error, run:
```bash
cd frontend
npm install --legacy-peer-deps --ignore-scripts
```

### Port already in use
- Backend: Change the port in `backend/app.py` (look for `port=5000`)
- Frontend: The `frontend/.env` file can set `PORT=3001` or similar

## Project Status

🚧 **Work in Progress** — Core functionality is complete with real-time data visualization and interactive charts.