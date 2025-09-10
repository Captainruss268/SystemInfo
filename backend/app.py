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

def get_intel_codename(generation, name):
    """Get Intel CPU microarchitecture code name"""
    # Intel desktop microarchitectures
    desktop_codenames = {
        '1': 'P6',
        '2': 'Pentium Pro',
        '3': 'P6',
        '4': 'NetBurst',
        '5': 'NetBurst',
        '6': 'Core',
        '7': 'Nehalem',
        '8': 'Nehalem',
        '9': 'Sandy Bridge',
        '10': 'Ivy Bridge',
        '11': 'Haswell',
        '12': 'Broadwell',
        '13': 'Raptor Lake',
        '14': 'Meteor Lake',
        '15': 'Arrow Lake'
    }

    # Extract generation number (remove 'th Gen')
    gen_num = generation.split('th')[0] if generation else None

    # Safely handle the case where gen_num might be None
    if gen_num:
        codename = desktop_codenames.get(gen_num, f'Gen {gen_num}')
    else:
        codename = 'Unknown'

    # Add mobile suffix if it's a laptop CPU
    if name and ('Laptop' in name or 'M' in name.split()[-1] or 'Mobile' in name):
        codename += ' (Mobile)'

    return codename

def get_amd_codename(generation, name):
    """Get AMD CPU microarchitecture code name"""
    # AMD microarchitectures by generation/series
    zen_codenames = {
        'Ryzen 2': 'Pinnacle Ridge',
        'Ryzen 3': 'Matisse',
        'Ryzen 4': 'Renior',
        'Ryzen 5': 'Vermeer/Lucienne',
        'Ryzen 6': 'Raphael',
        'Ryzen 7': 'Phoenix',
        'Ryzen 8': 'Raphael',
        'Ryzen 9': 'Zen 4'
    }

    # Try to match AMD Ryzen series
    for series, codename in zen_codenames.items():
        if series in name:
            return codename

    # Fallback for generation-based
    return f'Zen Architecture (Gen {generation})' if generation else 'Zen Architecture'

def clean_cpu_name(name):
    """Clean CPU name by removing generation from the beginning"""
    if not name:
        return name

    # Patterns to remove: "13th Gen ", "12nd Gen ", etc.
    patterns = [
        r'^\d+(?:st|nd|rd|th)\s+Gen\s+',  # "13th Gen "
        r'^\d+(?:st|nd|rd|th)-Generation\s+',  # "13th-Generation "
        r'^\d+(?:st|nd|rd|th)\s+',  # "13th "
        r'^\d+(?:st|nd|rd|th)-Gen\s+',  # "13th-Gen "
    ]

    for pattern in patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    return name.strip()

def format_cpu_name(name):
    """Format CPU name for better display"""
    if not name:
        return name

    # Replace GenuineIntel with just Intel
    name = name.replace('GenuineIntel', 'Intel')

    # Handle Intel and AMD CPU naming
    if 'Intel' in name:
        # Add hyphen for Intel i-series: i9 -> i9-
        name = re.sub(r'\b(i\d+)([^-])', r'\1-\2', name)
    elif 'AMD' in name:
        # AMD typically doesn't need hyphen formatting, but clean up if needed
        pass

    return name

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

def fetch_ip_info_with_retry():
    """Fetch IP info with caching and exponential backoff, multiple services"""
    global ip_cache

    # Check cache validity
    current_time = time.time()
    if ip_cache['data'] and (current_time - ip_cache['timestamp']) < CACHE_DURATION:
        return ip_cache['data']

    # Fallback IP services in order of preference
    services = [
        'https://ipinfo.io/json',
        'http://ip-api.com/json/?fields=query,country,regionName,city',
        'https://api.ipify.org/?format=json',
        'https://httpbin.org/ip'
    ]

    timeout = 5
    backoff_factor = 2

    for service_url in services:
        max_retries = 2  # Less retries per service since we have fallbacks

        for attempt in range(max_retries):
            try:
                response = requests.get(service_url, timeout=timeout)
                if response.status_code == 200:
                    data = response.json()

                    # Normalize different API response formats
                    if 'ipinfo.io' in service_url:
                        ip_info = {
                            'ip': data.get('ip'),
                            'country': data.get('country'),
                            'region': data.get('region'),
                            'city': data.get('city')
                        }
                    elif 'ip-api.com' in service_url:
                        ip_info = {
                            'ip': data.get('query'),
                            'country': data.get('country'),
                            'region': data.get('regionName'),
                            'city': data.get('city')
                        }
                    elif 'api.ipify.org' in service_url:
                        ip_info = {
                            'ip': data.get('ip'),
                            'country': 'Unknown',
                            'region': 'Unknown',
                            'city': 'Unknown'
                        }
                    elif 'httpbin.org' in service_url:
                        ip_info = {
                            'ip': data.get('origin', '').split(',')[0].strip(),  # Handle multiple IPs
                            'country': 'Unknown',
                            'region': 'Unknown',
                            'city': 'Unknown'
                        }

                    # Cache successful result
                    ip_cache['data'] = ip_info
                    ip_cache['timestamp'] = current_time
                    return ip_info

                elif response.status_code == 429:
                    # Rate limited - wait and try next service
                    wait_time = backoff_factor ** attempt
                    logging.warning(f"Rate limited (429) for {service_url}. Waiting {wait_time} seconds before next attempt")
                    time.sleep(wait_time)

                    # If this was the last attempt for this service, continue to next service
                    if attempt == max_retries - 1:
                        break
                    else:
                        continue
                else:
                    # Other HTTP error - try next service immediately
                    break

            except requests.exceptions.RequestException as e:
                wait_time = backoff_factor ** attempt
                logging.warning(f"Request failed for {service_url}: {e}. Waiting {wait_time} seconds")
                time.sleep(wait_time)

                if attempt == max_retries - 1:
                    break
                else:
                    continue

    # All services failed - return basic local info
    logging.warning("All IP services failed, falling back to local interface info")
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

            # Clean up name by removing extra trademarks and symbols
            cpu_name = re.sub(r'[®™©®®™®©®™©®®™®©®™©]', '', cpu_name)  # Remove registered, trademark, copyright symbols
            cpu_name = re.sub(r'\(R\)', '', cpu_name, flags=re.IGNORECASE)  # Remove (R)
            cpu_name = re.sub(r'\(TM\)', '', cpu_name, flags=re.IGNORECASE)  # Remove (TM)

            # Clean CPU name by removing generation prefix
            cleaned_name = clean_cpu_name(cpu_name.strip())

            # Format the CPU name
            formatted_name = format_cpu_name(cleaned_name)

            # Get codename
            manufacturer = processor.Manufacturer or 'Intel'
            codename = 'Unknown'
            if 'Intel' in manufacturer.upper() and generation:
                codename = get_intel_codename(generation, formatted_name)
            elif 'AMD' in manufacturer.upper() and generation:
                codename = get_amd_codename(generation, formatted_name)

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
