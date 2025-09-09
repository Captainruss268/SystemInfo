from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import platform
import logging
import pythoncom

# Set up logging
logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

def get_cpu_info():
    """Get detailed CPU information"""
    try:
        cpu_info = {
            'cpu_count_physical': psutil.cpu_count(logical=False),
            'cpu_count_logical': psutil.cpu_count(logical=True),
            'cpu_percent': psutil.cpu_percent(interval=1, percpu=True)
        }
        # Get CPU frequency
        freq = psutil.cpu_freq()
        if freq:
            cpu_info['cpu_freq'] = {
                'current': freq.current,
                'min': freq.min,
                'max': freq.max
            }
        # Get CPU temperatures if available
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                cpu_info['temperatures'] = [
                    {'label': temp.label, 'current': temp.current}
                    for temp in temps['coretemp']
                ]
        return cpu_info
    except Exception as e:
        logging.error("Error getting CPU info: %s", e)
        return None

def get_memory_info():
    """Get detailed memory information"""
    try:
        memory = psutil.virtual_memory()
        return {
            'total': memory.total,
            'available': memory.available,
            'percent': memory.percent,
            'used': memory.used,
            'free': memory.free
        }
    except Exception as e:
        logging.error("Error getting memory info: %s", e)
        return None

def get_disk_info():
    """Get detailed disk information"""
    try:
        disk_info = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent
                })
            except (PermissionError, FileNotFoundError) as e:
                logging.warning("Could not access %s: %s", partition.mountpoint, e)
                continue
        return disk_info
    except Exception as e:
        logging.error("Error getting disk info: %s", e)
        return None

def get_network_info():
    """Get detailed network information"""
    try:
        net_io = psutil.net_io_counters()
        interfaces = {}
        for interface, addrs in psutil.net_if_addrs().items():
            interfaces[interface] = [
                {'type': addr.family.name, 'address': addr.address}
                for addr in addrs
            ]
        # Get active network connections
        connections = psutil.net_connections()
        connection_details = []
        for conn in connections:
            if conn.status == 'ESTABLISHED':  # Or all, but filter to established
                connection_details.append({
                    'local_address': f"{conn.laddr.ip if conn.laddr else ''}:{conn.laddr.port if conn.laddr else ''}",
                    'remote_address': f"{conn.raddr.ip if conn.raddr else ''}:{conn.raddr.port if conn.raddr else ''}" if conn.raddr else '',
                    'status': conn.status
                })
        return {
            'io_counters': net_io._asdict(),
            'interfaces': interfaces,
            'connections': connection_details
        }
    except Exception as e:
        logging.error(f"Error getting network info: {e}")
        return None

def get_hardware_info():
    """Get hardware information using WMI or other methods"""
    hardware_info = {'gpu': [], 'motherboard': {}, 'processor': {}}
    try:
        pythoncom.CoInitialize()
        import wmi
        wmi_instance = wmi.WMI()

        # Processor Info
        try:
            processor = wmi_instance.Win32_Processor()[0]
            name = processor.Name.strip()
            # Clean up name by removing extra trademarks and symbols
            import re
            name = re.sub(r'[®™©®®™®©®™©®®™®©®™©]', '', name)  # Remove registered, trademark, copyright symbols
            name = re.sub(r'\(R\)', '', name, flags=re.IGNORECASE)  # Remove (R)
            name = re.sub(r'\(TM\)', '', name, flags=re.IGNORECASE)  # Remove (TM)
            name = re.sub(r'\(C\)', '', name, flags=re.IGNORECASE)  # Remove (C)
            name = re.sub(r'\s+', ' ', name)  # Normalize spaces
            # Alternative: replace all non-alphanumeric and non-space with nothing
            import unicodedata
            name = ''.join(c for c in unicodedata.normalize('NFKD', name) if c.isalnum() or c in ' ')
            name = re.sub(r'\s+', ' ', name.strip())
            hardware_info['processor'] = {
                'name': name.strip(),
                'manufacturer': processor.Manufacturer,
                'cores': processor.NumberOfCores,
                'logical_processors': processor.NumberOfLogicalProcessors
            }
        except Exception as e:
            logging.error("Could not retrieve processor info via WMI: %s", e)

        # GPU Info
        try:
            for gpu in wmi_instance.Win32_VideoController():
                hardware_info['gpu'].append({
                    'name': gpu.Name,
                    'driver_version': gpu.DriverVersion,
                    'status': gpu.Status,
                    'adapter_ram': gpu.AdapterRAM
                })
        except Exception as e:
            logging.error("Could not retrieve GPU info via WMI: %s", e)

        # Motherboard Info
        try:
            board = wmi_instance.Win32_BaseBoard()[0]
            hardware_info['motherboard'] = {
                'manufacturer': board.Manufacturer,
                'product': board.Product,
                'serial_number': board.SerialNumber
            }
        except Exception as e:
            logging.error("Could not retrieve motherboard info via WMI: %s", e)

    except ImportError:
        logging.warning("WMI module not found. Hardware info will be limited.")
    except Exception as e:
        logging.error("An error occurred during WMI initialization or query: %s", e)

    return hardware_info

@app.route('/api/system-info', methods=['GET'])
def system_info():
    """Consolidated endpoint for system information"""
    data = {
        'cpu': get_cpu_info(),
        'memory': get_memory_info(),
        'disk': get_disk_info(),
        'network': get_network_info(),
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'architecture': platform.machine(),
            'processor': platform.processor()
        }
    }
    # Filter out None values if a function fails
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        return jsonify({'error': 'Could not retrieve system information'}), 500
    return jsonify(data)

@app.route('/api/hardware-info', methods=['GET'])
def hardware_info():
    """Endpoint for detailed hardware information"""
    info = get_hardware_info()
    return jsonify(info)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
