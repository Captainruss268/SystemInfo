from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import platform
import logging
import pythoncom
import time
from typing import Dict, List, Optional, Any
import subprocess
import glob

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

# Import our refactored modules
from config import Config, cache
from utils import (
    safe_execute, time_function, validate_temperature, validate_kelvin_temperature,
    process_cpu_name, extract_generation_from_cpu_name, get_mock_temperature,
    is_physical_wifi_adapter, extract_adapter_info, match_nvidia_memory,
    get_local_ipv6, get_basic_local_ip_info, fetch_ip_info
)

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Global state for I/O tracking
io_offsets = {
    'bytes_sent': 0,
    'bytes_recv': 0,
    'packets_sent': 0,
    'packets_recv': 0
}

def detect_core_types(physical_cores: int, logical_processors: int, hardware_info: Optional[Dict] = None) -> Dict[str, int]:
    """Simple core type detection"""
    try:
        if not hardware_info or 'processor' not in hardware_info:
            return {'p_cores': 0, 'e_cores': physical_cores, 'total_cores': physical_cores}

        processor_name = hardware_info['processor'].get('name', '').lower()
        if any(arch in processor_name for arch in ['apple m', 'apple silicon', 'm1', 'm2', 'm3', 'm4']):
            return {'p_cores': physical_cores, 'e_cores': 0, 'total_cores': physical_cores}

        # Simple fallback
        return {'p_cores': 0, 'e_cores': physical_cores, 'total_cores': physical_cores}
    except:
        return {'p_cores': 0, 'e_cores': physical_cores, 'total_cores': physical_cores}

# Temperature Detection Module
class TemperatureDetector:
    """Handles temperature detection across different platforms"""

    @classmethod
    @safe_execute(default_return=[])
    def get_cpu_temperatures(cls) -> List[Dict[str, Any]]:
        """Get CPU temperatures using platform-specific methods"""
        current_platform = platform.system()
        logger.info(f"Detecting CPU temperatures on platform: {current_platform}")

        # Try psutil first (cross-platform)
        temperatures = cls._try_psutil_sensors()
        if temperatures:
            logger.info(f"Found {len(temperatures)} temperature sensors via psutil")
            return temperatures

        # Platform-specific methods
        if current_platform == "Linux":
            temperatures = cls._get_linux_temperatures()
            if temperatures:
                logger.info(f"Found {len(temperatures)} temperature sensors via Linux methods")
                return temperatures
        elif current_platform == "Windows":
            temperatures = cls._get_windows_temperatures()
            if temperatures:
                logger.info(f"Found {len(temperatures)} temperature sensors via Windows WMI")
                return temperatures
        elif current_platform == "Darwin":
            temperatures = cls._get_macos_temperatures()
            if temperatures:
                logger.info(f"Found {len(temperatures)} temperature sensors via macOS")
                return temperatures

        # Fallback to mock data - always provide something
        logger.info("No real temperature sensors found, using mock data")
        return [get_mock_temperature()]

    @classmethod
    def _try_psutil_sensors(cls) -> List[Dict[str, Any]]:
        """Try to get temperatures using psutil sensors"""
        try:
            if not hasattr(psutil, "sensors_temperatures"):
                logger.warning("psutil.sensors_temperatures not available")
                return []

            temps = psutil.sensors_temperatures()
            if not temps:
                logger.warning("No temperature sensors found by psutil")
                return []

            temperatures = []

            # Check all available sensor types
            for sensor_name in Config.SENSOR_NAMES:
                if sensor_name in temps:
                    logger.info(f"Found temperature sensor: {sensor_name}")
                    for temp_sensor in temps[sensor_name]:
                        if hasattr(temp_sensor, 'current'):
                            temp_value = temp_sensor.current
                            # Less strict temperature validation
                            if -50 < temp_value < 200:  # Reasonable CPU temp range
                                temperatures.append({
                                    'label': getattr(temp_sensor, 'label', f'{sensor_name}_sensor'),
                                    'current': temp_value
                                })

            if temperatures:
                logger.info(f"Successfully retrieved {len(temperatures)} temperature readings")
                return temperatures
            else:
                logger.warning("No valid temperature readings found in sensors")

        except Exception as e:
            logger.warning(f"Failed to get psutil temperatures: {e}")

        return []

    @classmethod
    def _get_linux_temperatures(cls) -> List[Dict[str, Any]]:
        """Get temperatures on Linux systems"""
        temperatures = []

        # Try thermal zones
        try:
            thermal_zones = glob.glob(Config.SENSOR_CONFIGS['Linux']['thermal_zones_path'])
            for zone_file in thermal_zones:
                try:
                    with open(zone_file, 'r') as f:
                        temp_millicelsius = int(f.read().strip())
                        temp_celsius = temp_millicelsius / Config.SENSOR_CONFIGS['Linux']['temp_conversion_factor']

                        if validate_temperature(temp_celsius):
                            temperatures.append({
                                'label': f'Zone {zone_file.split("/")[-2]}',
                                'current': temp_celsius
                            })
                except (OSError, ValueError):
                    continue
        except Exception as e:
            logger.warning(f"Failed to get Linux thermal zone temperatures: {e}")

        # Try lm-sensors
        if not temperatures:
            temperatures.extend(cls._get_linux_lm_sensors())

        return temperatures

    @classmethod
    def _get_linux_lm_sensors(cls) -> List[Dict[str, Any]]:
        """Get temperatures using lm-sensors on Linux"""
        temperatures = []
        try:
            result = subprocess.run(
                Config.SENSOR_CONFIGS['Linux']['lm_sensors_cmd'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '°C' in line and ('temp' in line.lower() or 'core' in line.lower()):
                        temp_value = parse_lm_sensor_line(line)
                        if temp_value and validate_temperature(temp_value):
                            temperatures.append({
                                'label': line.split(':')[0].strip(),
                                'current': temp_value
                            })
        except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        return temperatures

    @classmethod
    def _get_windows_temperatures(cls) -> List[Dict[str, Any]]:
        """Get temperatures on Windows systems using WMI"""
        temperatures = []
        try:
            pythoncom.CoInitialize()
            import wmi

            # First, try the existing method
            try:
                wmi_instance = wmi.WMI()
                wmi_cpu = wmi_instance.Win32_TemperatureProbe()
                for probe in wmi_cpu:
                    if hasattr(probe, 'CurrentReading'):
                        temp_kelvin = probe.CurrentReading
                        if temp_kelvin and validate_kelvin_temperature(temp_kelvin):
                            temp_celsius = temp_kelvin - Config.SENSOR_CONFIGS['Windows']['conversion_factor']
                            temperatures.append({
                                'label': getattr(probe, 'Name', 'CPU Temperature'),
                                'current': temp_celsius
                            })
            except Exception as e:
                logger.warning(f"Failed to get Windows temperatures with Win32_TemperatureProbe: {e}")

            # If the first method fails or returns no data, try the thermal zone method
            if not temperatures:
                try:
                    wmi_instance_thermal = wmi.WMI(namespace="root\\wmi")
                    temp_probes = wmi_instance_thermal.MSAcpi_ThermalZoneTemperature()
                    for i, probe in enumerate(temp_probes):
                        if hasattr(probe, 'CurrentTemperature'):
                            temp_deci_kelvin = probe.CurrentTemperature
                            temp_celsius = (temp_deci_kelvin / 10.0) - 273.15
                            if validate_temperature(temp_celsius):
                                temperatures.append({
                                    'label': getattr(probe, 'InstanceName', f'Thermal Zone {i}').replace('_TZ', ' TZ'),
                                    'current': temp_celsius
                                })
                except Exception as e:
                    logger.warning(f"Failed to get Windows temperatures with MSAcpi_ThermalZoneTemperature: {e}")

        except Exception as e:
            logger.warning(f"Failed to get Windows temperatures: {e}")

        return temperatures

    @classmethod
    def _get_macos_temperatures(cls) -> List[Dict[str, Any]]:
        """Get temperatures on macOS systems"""
        temperatures = []
        try:
            result = subprocess.run(['sysctl', '-a'], capture_output=True, text=True)

            for line in result.stdout.split('\n'):
                if any(pattern in line for pattern in Config.SENSOR_CONFIGS['Darwin']['sysctl_patterns']):
                    temp_value = parse_sysctl_line(line)
                    if temp_value and validate_temperature(temp_value):
                        temperatures.append({
                            'label': 'CPU Temperature',
                            'current': temp_value
                        })
        except Exception as e:
            logger.warning(f"Failed to get macOS temperatures: {e}")

        return temperatures

# System Information Collector
class SystemInfoCollector:
    """Collects and organizes system information"""

    @staticmethod
    def get_cpu_info() -> Optional[Dict[str, Any]]:
        """Get comprehensive CPU information"""
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

            # Get temperatures
            cpu_info['temperatures'] = TemperatureDetector.get_cpu_temperatures()

            return cpu_info

        except Exception as e:
            logger.error(f"Error getting CPU info: {e}")
            return None

    @staticmethod
    def get_memory_info() -> Optional[Dict[str, Any]]:
        """Get memory information"""
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
            logger.error(f"Error getting memory info: {e}")
            return None

    @staticmethod
    def get_disk_info() -> Optional[List[Dict[str, Any]]]:
        """Get disk information"""
        try:
            disk_info = []
            partitions = psutil.disk_partitions(all=True)
            logger.info(f"Found {len(partitions)} disk partitions")

            for partition in partitions:
                try:
                    # Skip partitions without mountpoints
                    if not partition.mountpoint:
                        continue

                    logger.info(f"Processing partition: {partition.device} -> {partition.mountpoint}")

                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info.append({
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype or 'Unknown',
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent
                    })
                    logger.info(f"Added disk info for {partition.mountpoint}: {usage.percent}% used")

                except (PermissionError, FileNotFoundError, OSError) as e:
                    logger.warning(f"Could not get usage for {partition.mountpoint}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error processing partition {partition.mountpoint}: {e}")
                    continue

            # If no disk info was collected, try to get basic disk usage for common drives
            if not disk_info:
                logger.info("No disk partitions found, trying common drive letters")
                disk_info.extend(SystemInfoCollector._get_common_disk_usage())

            logger.info(f"Returning {len(disk_info)} disk information entries")
            return disk_info

        except Exception as e:
            logger.error(f"Error getting disk info: {e}")
            return None

    @staticmethod
    def _get_common_disk_usage() -> List[Dict[str, Any]]:
        """Get disk usage for common drive letters when normal detection fails"""
        disk_info = []

        # Try to get disk usage using WMI instead of psutil for Windows
        try:
            pythoncom.CoInitialize()
            import wmi
            wmi_instance = wmi.WMI()

            # Get logical disk information from WMI
            for logical_disk in wmi_instance.Win32_LogicalDisk():
                try:
                    if logical_disk.Size:  # Only process drives with valid size
                        drive_letter = logical_disk.Name
                        if drive_letter and len(drive_letter) == 2 and drive_letter[1] == ':':
                            # Calculate usage percentage
                            used_bytes = int(logical_disk.Size) - int(logical_disk.FreeSpace)
                            total_bytes = int(logical_disk.Size)
                            free_bytes = int(logical_disk.FreeSpace)
                            percent_used = (used_bytes / total_bytes * 100) if total_bytes > 0 else 0

                            disk_info.append({
                                'device': drive_letter,
                                'mountpoint': drive_letter + '\\',
                                'fstype': logical_disk.FileSystem or 'Unknown',
                                'total': total_bytes,
                                'used': used_bytes,
                                'free': free_bytes,
                                'percent': round(percent_used, 1)
                            })
                            logger.info(f"Added WMI drive {drive_letter}: {percent_used}% used")
                except Exception as e:
                    logger.warning(f"Error processing WMI logical disk {logical_disk.Name}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to get disk info via WMI: {e}")

        # If WMI fails, try psutil with error handling
        if not disk_info:
            common_drives = ['C:', 'D:', 'E:', 'F:']
            for drive in common_drives:
                try:
                    # Try different path formats
                    for path_format in [drive, drive + ':\\', drive + '/']:
                        try:
                            usage = psutil.disk_usage(path_format)
                            disk_info.append({
                                'device': drive,
                                'mountpoint': drive + '\\',
                                'fstype': 'NTFS',  # Common filesystem type on Windows
                                'total': usage.total,
                                'used': usage.used,
                                'free': usage.free,
                                'percent': usage.percent
                            })
                            logger.info(f"Added psutil drive {drive}: {usage.percent}% used")
                            break  # Success, break inner loop
                        except:
                            continue  # Try next format

                except Exception as e:
                    logger.warning(f"Could not get disk usage for drive {drive}: {e}")
                    continue

        return disk_info

# Backward compatibility function
def get_cpu_info() -> Optional[Dict[str, Any]]:
    """Legacy function for backward compatibility"""
    return SystemInfoCollector.get_cpu_info()



# Network Utilities
class NetworkUtils:
    """Handles network-related operations and caching"""

    @staticmethod
    @safe_execute(default_return=None)
    def get_network_info() -> Optional[Dict[str, Any]]:
        """Get detailed network information"""
        try:
            net_io = psutil.net_io_counters()
            ip_info = fetch_ip_info()
            local_ipv6 = None

            # Get IPv6 from local interfaces if needed
            if not ip_info or ip_info.get('error') or (ip_info.get('ip') and ':' not in ip_info.get('ip', '')):
                local_ipv6 = get_local_ipv6()

            # Apply offsets for reset functionality
            net_io_dict = net_io._asdict()
            for key in io_offsets:
                net_io_dict[key] = max(0, net_io_dict[key] - io_offsets[key])

            return {
                'io_counters': net_io_dict,
                'ip_info': ip_info,
                'local_ipv6': local_ipv6
            }
        except Exception as e:
            logger.error(f"Error getting network info: {e}")
            return None

# Hardware Detection Module
class HardwareDetector:
    """Handles hardware detection and information gathering"""

    @staticmethod
    @safe_execute(default_return={'gpu': [], 'motherboard': {}, 'processor': {}, 'wifi_adapters': []})
    def get_hardware_info() -> Dict[str, Any]:
        """Get comprehensive hardware information"""
        hardware_info = {
            'gpu': [],
            'motherboard': {},
            'processor': {},
            'wifi_adapters': []
        }

        try:
            pythoncom.CoInitialize()
            import wmi
            wmi_instance = wmi.WMI()

            # Get processor info
            hardware_info['processor'] = HardwareDetector._get_processor_info(wmi_instance)

            # Get GPU info
            hardware_info['gpu'] = HardwareDetector._get_gpu_info(wmi_instance)

            # Get motherboard info
            hardware_info['motherboard'] = HardwareDetector._get_motherboard_info(wmi_instance)

            # Get WiFi adapter info
            hardware_info['wifi_adapters'] = HardwareDetector._get_wifi_adapters(wmi_instance)

        except ImportError:
            logger.warning("WMI module not found. Hardware info will be limited.")
        except Exception as e:
            logger.error(f"An error occurred during WMI initialization or query: {e}")

        return hardware_info

    @classmethod
    def _get_processor_info(cls, wmi_instance) -> Dict[str, Any]:
        """Get processor information"""
        try:
            processor = wmi_instance.Win32_Processor()[0]
            cpu_name = processor.Name.strip()

            # Extract generation using utility function
            generation = extract_generation_from_cpu_name(cpu_name)

            manufacturer = processor.Manufacturer or 'Intel'
            formatted_name, codename = process_cpu_name(cpu_name, generation, manufacturer)

            return {
                'name': formatted_name,
                'manufacturer': manufacturer,
                'cores': processor.NumberOfCores,
                'logical_processors': processor.NumberOfLogicalProcessors,
                'generation': generation,
                'codename': codename
            }
        except Exception as e:
            logger.error(f"Could not retrieve processor info via WMI: {e}")
            return {}

    @classmethod
    def _get_gpu_info(cls, wmi_instance) -> List[Dict[str, Any]]:
        """Get GPU information"""
        gpu_info = []

        try:
            # Get NVIDIA GPU memory info if available
            nvidia_memory = get_nvidia_gpu_memory()

            for gpu in wmi_instance.Win32_VideoController():
                adapter_ram = gpu.AdapterRAM

                # Use NVML data for NVIDIA GPUs if WMI data is invalid
                if (gpu.Name and 'NVIDIA' in gpu.Name.upper() and
                    (adapter_ram is None or adapter_ram <= 0) and nvidia_memory):
                    adapter_ram = match_nvidia_memory(gpu.Name, nvidia_memory)

                gpu_info.append({
                    'name': gpu.Name,
                    'driver_version': gpu.DriverVersion,
                    'status': gpu.Status,
                    'adapter_ram': adapter_ram
                })
        except Exception as e:
            logger.error(f"Could not retrieve GPU info via WMI: {e}")

        return gpu_info

    @classmethod
    def _get_motherboard_info(cls, wmi_instance) -> Dict[str, Any]:
        """Get motherboard information"""
        try:
            board = wmi_instance.Win32_BaseBoard()[0]
            return {
                'manufacturer': board.Manufacturer,
                'product': board.Product,
                'serial_number': board.SerialNumber
            }
        except Exception as e:
            logger.error(f"Could not retrieve motherboard info via WMI: {e}")
            return {}

    @classmethod
    def _get_wifi_adapters(cls, wmi_instance) -> List[Dict[str, Any]]:
        """Get WiFi adapter information"""
        wifi_adapters = []

        try:
            for adapter in wmi_instance.Win32_NetworkAdapter():
                if is_physical_wifi_adapter(adapter):
                    adapter_info = extract_adapter_info(adapter)
                    if adapter_info:
                        wifi_adapters.append(adapter_info)
        except Exception as e:
            logger.error(f"Could not retrieve wifi adapter info via WMI: {e}")

        return wifi_adapters

# Legacy compatibility functions
def get_memory_info() -> Optional[Dict[str, Any]]:
    """Legacy function for backward compatibility"""
    return SystemInfoCollector.get_memory_info()

def get_disk_info() -> Optional[List[Dict[str, Any]]]:
    """Legacy function for backward compatibility"""
    return SystemInfoCollector.get_disk_info()

def get_network_info() -> Optional[Dict[str, Any]]:
    """Legacy function for backward compatibility"""
    return NetworkUtils.get_network_info()

def get_hardware_info() -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return HardwareDetector.get_hardware_info()

@safe_execute(default_return=None)
def get_nvidia_gpu_memory() -> Optional[Dict[str, int]]:
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
        logger.error(f"Error getting NVIDIA GPU memory: {e}")
        return None




@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": time.time()})

@app.route('/api/system-info', methods=['GET'])
@time_function
def system_info():
    """Consolidated endpoint for system information"""
    try:
        # Use parallel data collection for better performance
        hardware_data = get_hardware_info()
        cpu_info = get_cpu_info()
        memory_info = get_memory_info()
        disk_info = get_disk_info()
        network_info = get_network_info()

        # Add core types to CPU info if available
        if cpu_info and hardware_data:
            physical_cores = cpu_info.get('cpu_count_physical', 0)
            logical_processors = cpu_info.get('cpu_count_logical', 0)
            core_types = detect_core_types(physical_cores, logical_processors, hardware_data)
            cpu_info['core_types'] = core_types

        # Build response data
        data = {
            'cpu': cpu_info,
            'memory': memory_info,
            'disk': disk_info,
            'network': network_info,
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

    except Exception as e:
        logger.error(f"Error in system_info endpoint: {e}")
        return jsonify({'error': 'Internal server error'}), 500

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
