from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import platform
import logging
import re
import pythoncom
import requests
import time

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

# Set up logging
logging.basicConfig(level=logging.ERROR)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Global offset for I/O counters reset
io_offsets = {
    'bytes_sent': 0,
    'bytes_recv': 0,
    'packets_sent': 0,
    'packets_recv': 0
}

# Global cache for IP info
ip_cache = {
    'data': None,
    'timestamp': 0
}
CACHE_DURATION = 300  # seconds

def detect_core_types(physical_cores, logical_processors, hardware_info=None):
    """Detect P-cores vs E-cores based on CPU architecture"""
    try:
        if physical_cores == logical_processors:
            # All cores are the same (older CPUs without hybrid cores)
            return {
                'p_cores': 0,
                'e_cores': physical_cores,
                'total_cores': physical_cores
            }

        # Calculate P-cores as the difference between logical and physical cores
        # Since P-cores support 2 threads each while E-cores support 1
        p_cores = logical_processors - physical_cores
        e_cores = physical_cores - p_cores

        # Verify against hardware info if available
        if hardware_info and 'processor' in hardware_info:
            processor_name = hardware_info['processor'].get('name', '').lower()
            manufacturer = hardware_info['processor'].get('manufacturer', '').lower()

            # Intel hybrid processors
            if any(arch in processor_name for arch in ['intel', 'core i']) or 'intel' in manufacturer:
                # Intel Raptor Lake/Meteor Lake/Arrow Lake have P+E cores
                if 'i5' in processor_name:
                    p_cores = min(p_cores, 6)  # i5 typically 6P+(4-8)E
                elif 'i7' in processor_name:
                    p_cores = min(p_cores, 8)  # i7 typically 8P+(4-8)E
                elif 'i9' in processor_name and physical_cores >= 16:
                    p_cores = min(p_cores, 8)  # i9 typically 8P+8E
                # Recalculate E-cores after capping P-cores
                e_cores = physical_cores - p_cores

            # AMD Ryzen 7000 series and newer have P+E cores
            elif 'amd' in manufacturer and any(arch in processor_name for arch in ['ryzen 7', 'ryzen 8', 'ryzen 9']):
                # AMD Ryzen 7000: 8 cores = 6P + 2E, 16 cores = 8P + 8E
                if physical_cores == 8:
                    p_cores = min(p_cores, 6)
                elif physical_cores == 16:
                    p_cores = min(p_cores, 8)
                e_cores = physical_cores - p_cores

            # Apple Silicon (M series and newer) - all cores are high-performance
            elif any(arch in processor_name for arch in ['apple m', 'apple silicon', 'm1', 'm2', 'm3', 'm4']):
                # Apple Silicon cores are all performance-oriented but can throttle
                p_cores = physical_cores  # All cores are P-type
                e_cores = 0

            # Qualcomm Snapdragon X Elite series
            elif 'qualcomm' in manufacturer or 'snapdragon' in processor_name:
                # Snapdragon X Elite: 12 cores = 8P + 4E
                if physical_cores == 12:
                    p_cores = min(p_cores, 8)
                e_cores = physical_cores - p_cores

        return {
            'p_cores': p_cores,
            'e_cores': e_cores,
            'total_cores': physical_cores
        }

    except Exception as e:
        logging.warning(f"Error in core type detection: {e}")
        # Fallback to equal distribution if detection fails
        return {
            'p_cores': 0,
            'e_cores': physical_cores,
            'total_cores': physical_cores
        }

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

def process_cpu_name(name, generation=None, manufacturer='Intel'):
    """Process CPU name: clean, format, and get codename"""
    if not name:
        return name, 'Unknown'

    # Clean name - remove generation prefixes and trademarks
    cleaned = re.sub(r'^\d+(?:st|nd|rd|th)\s+G(?:en|eneration)?\s+|[®™©®®™®©®™©®®™®©®™©]', '', name)

    # Remove registered/mark symbols
    cleaned = re.sub(r'\(R\)|\(TM\)', '', cleaned, flags=re.IGNORECASE)

    # Replace GenuineIntel with Intel
    final_name = cleaned.replace('GenuineIntel', 'Intel').strip()

    # Add hyphen for Intel i-series: i9 -> i9-
    if manufacturer == 'Intel' and 'Intel' in final_name:
        final_name = re.sub(r'\b(i\d+)([^-])', r'\1-\2', final_name)

    # Get codename if generation is available
    codename = 'Unknown'
    if generation and 'Intel' in manufacturer:
        gen_num = generation.split('th')[0] if 'th' in generation else None
        intel_codenames = {
            '13': 'Raptor Lake', '14': 'Meteor Lake', '15': 'Arrow Lake',
            '12': 'Broadwell', '11': 'Haswell', '10': 'Ivy Bridge',
            '9': 'Sandy Bridge', '7': 'Nehalem', '6': 'Core', '4': 'NetBurst'
        }
        codename = intel_codenames.get(gen_num, f'Gen {gen_num}' if gen_num else 'Unknown')

        # Add mobile suffix for laptop CPUs
        if any(term in cleaned.lower() for term in ['laptop', 'mobile', ' m ']):
            codename += ' (Mobile)'

    elif generation and 'AMD' in manufacturer:
        if any(series in name for series in ['Ryzen 9', 'Ryzen 8', 'Ryzen 7']):
            codename = 'Zen 4'
        else:
            codename = 'Zen Architecture'

    return final_name, codename

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
            except (PermissionError, FileNotFoundError, SystemError) as e:

                continue
        return disk_info
    except Exception as e:
        logging.error("Error getting disk info", exc_info=True)
        return None

def _normalize_ip_response(service_url, data):
    """Normalize IP response from different APIs"""
    if 'ipinfo.io' in service_url:
        return {
            'ip': data.get('ip'),
            'country': data.get('country'),
            'region': data.get('region'),
            'city': data.get('city')
        }
    elif 'ip-api.com' in service_url:
        return {
            'ip': data.get('query'),
            'country': data.get('country'),
            'region': data.get('regionName'),
            'city': data.get('city')
        }
    elif 'api.ipify.org' in service_url:
        return {
            'ip': data.get('ip'),
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown'
        }
    else:  # httpbin.org
        return {
            'ip': data.get('origin', '').split(',')[0].strip(),
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown'
        }

def fetch_ip_info_with_retry():
    """Fetch IP info with caching and exponential backoff"""
    global ip_cache

    # Simplified cache check
    if ip_cache['data'] and time.time() - ip_cache['timestamp'] < CACHE_DURATION:
        return ip_cache['data']

    services = [
        'https://ipinfo.io/json',
        'http://ip-api.com/json/?fields=query,country,regionName,city',
        'https://api.ipify.org/?format=json',
        'https://httpbin.org/ip'
    ]

    for service_url in services:
        for attempt in range(2):
            try:
                response = requests.get(service_url, timeout=5)
                if response.status_code == 200:
                    ip_cache['data'] = _normalize_ip_response(service_url, response.json())
                    ip_cache['timestamp'] = time.time()
                    return ip_cache['data']
                elif response.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.RequestException:
                time.sleep(2 ** attempt)

    logging.warning("All IP services failed, using local fallback")
    return get_basic_local_ip_info()

def get_basic_local_ip_info():
    """Get basic local IP information when external services fail"""
    try:
        local_ipv4 = None
        local_ipv6 = None

        # Get local IPv4 and IPv6 addresses
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name == 'AF_INET' and addr.address and not addr.address.startswith('127.'):
                    local_ipv4 = addr.address
                    break
                elif addr.family.name == 'AF_INET6' and addr.address and not addr.address.startswith('fe80') and not addr.address.startswith('::1'):
                    local_ipv6 = addr.address
                    break
            if local_ipv4 and local_ipv6:
                break

        return {
            'ip': local_ipv4 or '127.0.0.1',
            'local_ipv4': local_ipv4,
            'local_ipv6': local_ipv6,
            'country': 'Local Network',
            'region': 'Local Network',
            'city': 'Local Network',
            'source': 'local'
        }
    except Exception as e:
        logging.error(f"Could not get basic local IP info: {e}")
        return {
            'ip': '127.0.0.1',
            'local_ipv4': '127.0.0.1',
            'country': 'Local Network',
            'region': 'Local Network',
            'city': 'Local Network',
            'error': 'Could not determine local IP',
            'source': 'local'
        }

def get_network_info():
    """Get detailed network information"""
    try:
        net_io = psutil.net_io_counters()
        # Fetch IP and location info with caching and retry
        ip_info = fetch_ip_info_with_retry()
        local_ipv6 = None
        # Get IPv6 from local interfaces if available (if IP fetch failed or got IPv4)
        if not ip_info or ip_info.get('error') or (ip_info.get('ip') and ':' not in ip_info.get('ip', '')):
            try:
                for interface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.family.name == 'AF_INET6' and addr.address and not addr.address.startswith('fe80'):
                            local_ipv6 = addr.address
                            break
                    if local_ipv6:
                        break
            except Exception as e:
                logging.warning(f"Could not get local IPv6: {e}")
        # Apply offsets for reset
        net_io_dict = net_io._asdict()
        for key in io_offsets:
            net_io_dict[key] = max(0, net_io_dict[key] - io_offsets[key])
        return {
            'io_counters': net_io_dict,
            'ip_info': ip_info,
            'local_ipv6': local_ipv6
        }
    except Exception as e:
        logging.error(f"Error getting network info: {e}")
        return None

def get_nvidia_gpu_memory():
    """Get NVIDIA GPU memory information using NVML"""
    if not NVML_AVAILABLE:
        return None

    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()

        gpu_memory_info = {}
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)
            # Handle different versions of nvidia-ml-py
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            elif hasattr(name, '__str__'):
                name = str(name)
            gpu_memory_info[name] = info.total  # total memory in bytes

        pynvml.nvmlShutdown()
        return gpu_memory_info
    except Exception as e:
        logging.error(f"Error getting NVIDIA GPU memory: {e}")
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
            cpu_name = processor.Name.strip()

            # Extract generation first
            generation_match = re.search(r'(\d+)(?:th|th\s+Gen|st|st\s+Gen|nd|nd\s+Gen|rd|rd\s+Gen)', cpu_name)
            generation = None
            if generation_match:
                generation = generation_match.group(1) + 'th Gen'

            manufacturer = processor.Manufacturer or 'Intel'
            formatted_name, codename = process_cpu_name(cpu_name.strip(), generation, manufacturer)

            hardware_info['processor'] = {
                'name': formatted_name,
                'manufacturer': format_cpu_name(manufacturer),
                'cores': processor.NumberOfCores,
                'logical_processors': processor.NumberOfLogicalProcessors,
                'generation': generation,
                'codename': codename
            }
        except Exception as e:
            logging.error("Could not retrieve processor info via WMI: %s", e)

        # GPU Info
        try:
            # Get NVIDIA GPU memory info if available
            nvidia_memory = get_nvidia_gpu_memory()

            for gpu in wmi_instance.Win32_VideoController():
                adapter_ram = gpu.AdapterRAM

                # If this is an NVIDIA GPU and adapter_ram is invalid (negative or zero), use NVML data
                if (gpu.Name and 'NVIDIA' in gpu.Name.upper() and
                    (adapter_ram is None or adapter_ram <= 0) and
                    nvidia_memory is not None):
                    # Try to find matching NVIDIA GPU name and get memory
                    for nv_name, nv_memory in nvidia_memory.items():
                        # Simple name matching - check if key parts match
                        if ('GEFORCE' in gpu.Name.upper() and 'GEFORCE' in nv_name.upper()) or \
                           ('RTX' in gpu.Name.upper() and 'RTX' in nv_name.upper()) or \
                           any(word in gpu.Name.upper() for word in nv_name.upper().split() if len(word) > 3):
                            adapter_ram = nv_memory
                            break

                hardware_info['gpu'].append({
                    'name': gpu.Name,
                    'driver_version': gpu.DriverVersion,
                    'status': gpu.Status,
                    'adapter_ram': adapter_ram
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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/api/system-info', methods=['GET'])
def system_info():
    """Consolidated endpoint for system information"""
    # Get hardware info for CPU core detection
    hardware_data = get_hardware_info()

    # Get CPU info
    cpu_info = get_cpu_info()
    if cpu_info:
        # Detect core types using hardware info
        physical_cores = cpu_info.get('cpu_count_physical', 0)
        logical_processors = cpu_info.get('cpu_count_logical', 0)
        core_types = detect_core_types(physical_cores, logical_processors, hardware_data)
        cpu_info['core_types'] = core_types

    data = {
        'cpu': cpu_info,
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

@app.route('/api/reset-io', methods=['POST'])
def reset_io():
    """Reset I/O counters"""
    global io_offsets
    try:
        current_io = psutil.net_io_counters()
        io_offsets['bytes_sent'] = current_io.bytes_sent
        io_offsets['bytes_recv'] = current_io.bytes_recv
        io_offsets['packets_sent'] = current_io.packets_sent
        io_offsets['packets_recv'] = current_io.packets_recv
        return jsonify({'status': 'I/O counters reset'})
    except Exception as e:
        logging.error(f"Error resetting I/O: {e}")
        return jsonify({'error': 'Failed to reset I/O counters'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
