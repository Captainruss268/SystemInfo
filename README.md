# System Monitor Dashboard (Work in Progress)

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

## Prerequisites

- Python 3.8 or higher
- Node.js 14 or higher

## Installation & Setup

1. **Clone the repository**
```bash
git clone <your-repository-url>
cd system-info-app
```

2. **Install backend dependencies**
```bash
cd backend
pip install -r requirements.txt
```

3. **Install frontend dependencies**
```bash
cd ../frontend
npm install
```

## Running the Application

1. **Start the backend server**
```bash
cd backend
python app.py
```

2. **Start the frontend (in a new terminal)**
```bash
cd frontend
npm start
```

The application will be available at `http://localhost:3000`

## API Endpoints

- `/api/system-info` - Core system metrics and platform information
- `/api/hardware-info` - Detailed hardware specifications

## Project Status

🚧 **Work in Progress** - This full-stack system monitoring application has core functionality complete, with real-time data visualization and interactive charts. Ongoing improvements include enhancing the user interface and adding advanced features for better performance tracking.
