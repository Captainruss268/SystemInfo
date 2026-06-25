from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import platform
import logging
import re
import time
from typing import Dict, List, Optional, Any
import subprocess
import glob
import requests

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

# =============================================================================
# Configuration
# =============================================================================
class Config:
    CACHE_DURATION = 300  # seconds
    MAX_TEMP_CELSIUS = 150
    MIN_TEMP_CELSIUS = 0
    MOCK_TEMP_BASE = 35
    MOCK_TEMP_RANGE = 30
    REQUEST_TIMEOUT = 5
    MAX_RETRIES = 2
    WIFI_SPEED_MAX = 10000000

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Global state
io_offsets = {
    'bytes_sent': 0,
    'bytes_recv': 0,
    'packets_sent': 0,
    'packets_recv': 0
}

ip_cache = {
    'data': None,
    'timestamp': 0
}


# =============================================================================
# CPU Architecture Detection
# =============================================================================
class CPUArchitectureDetector:
    """Handles detection of CPU core types (P-cores vs E-cores)"""

    @classmethod
    def detect_core_types(cls, physical_cores: int, logical_processors: int,
                          hardware_info: Optional[Dict] = None) -> Dict[str, int]:
        """Detect P-cores vs E-cores using physical vs logical processor counts"""
        try:
            if physical_cores == logical_processors or logical_processors == 2 * physical_cores:
                return cls._create_core_result(physical_cores, 0, physical_cores)

            # Hybrid: P-cores have 2 threads each, E-cores have 1 thread each
            #   logical = 2*p + e
            #   physical = p + e
            #   => p = logical - physical, e = 2*physical - logical
            p_cores = logical_processors - physical_cores
            e_cores = 2 * physical_cores - logical_processors

            if p_cores >= 0 and e_cores >= 0 and (p_cores + e_cores == physical_cores):
                return cls._create_core_result(p_cores, e_cores, physical_cores)

            return cls._create_core_result(physical_cores, 0, physical_cores)
        except Exception as e:
            logger.warning(f"Error in core type detection: {e}")
            return cls._create_fallback_result(physical_cores)

    @classmethod
    def _create_core_result(cls, p_cores: int, e_cores: int, total_cores: int) -> Dict[str, int]:
        return {'p_cores': p_cores, 'e_cores': e_cores, 'total_cores': total_cores}

    @classmethod
    def _create_fallback_result(cls, physical_cores: int) -> Dict[str, int]:
        return {'p_cores': 0, 'e_cores': physical_cores, 'total_cores': physical_cores}


# =============================================================================
# Temperature Detection
# =============================================================================
class TemperatureDetector:
    """Handles temperature detection across different platforms"""

    SENSOR_CONFIGS = {
        'Linux': {
            'thermal_zones_path': '/sys/class/thermal/thermal_zone*/temp',
            'lm_sensors_cmd': ['sensors'],
            'temp_conversion_factor': 1000.0
        },
        'Windows': {
            'temp_range_kelvin': (273, 423),
            'conversion_factor': 273.15
        },
        'Darwin': {
            'sysctl_patterns': ['cpu_temp', 'cpu.temperature']
        }
    }

    @classmethod
    def get_cpu_temperatures(cls) -> List[Dict[str, Any]]:
        """Get CPU temperatures using platform-specific methods"""
        current_platform = platform.system()

        # Try psutil first (cross-platform)
        temperatures = cls._try_psutil_sensors()
        if temperatures:
            return temperatures

        # Platform-specific methods
        if current_platform == "Linux":
            temperatures = cls._get_linux_temperatures()
        elif current_platform == "Windows":
            temperatures = cls._get_windows_temperatures()
        elif current_platform == "Darwin":
            temperatures = cls._get_macos_temperatures()

        if temperatures:
            return temperatures

        # Fallback to mock data
        return cls._get_mock_temperatures()

    @classmethod
    def _try_psutil_sensors(cls) -> List[Dict[str, Any]]:
        """Try to get temperatures using psutil sensors"""
        try:
            if not hasattr(psutil, "sensors_temperatures"):
                return []

            temps = psutil.sensors_temperatures()
            if not temps:
                return []

            # Check all available sensor types
            temperatures = []
            for sensor_name, sensor_list in temps.items():
                for temp_sensor in sensor_list:
                    if hasattr(temp_sensor, 'current'):
                        temp_value = temp_sensor.current
                        if -50 < temp_value < 200:
                            temperatures.append({
                                'label': getattr(temp_sensor, 'label', f'{sensor_name}_sensor'),
                                'current': temp_value
                            })

            return temperatures
        except Exception as e:
            logger.warning(f"Failed to get psutil temperatures: {e}")
            return []

    @classmethod
    def _get_linux_temperatures(cls) -> List[Dict[str, Any]]:
        """Get temperatures on Linux systems"""
        temperatures = []
        try:
            thermal_zones = glob.glob(cls.SENSOR_CONFIGS['Linux']['thermal_zones_path'])
            for zone_file in thermal_zones:
                try:
                    with open(zone_file, 'r') as f:
                        temp_millicelsius = int(f.read().strip())
                        temp_celsius = temp_millicelsius / cls.SENSOR_CONFIGS['Linux']['temp_conversion_factor']
                        if cls._is_valid_temperature(temp_celsius):
                            temperatures.append({
                                'label': f'Zone {zone_file.split("/")[-2]}',
                                'current': temp_celsius
                            })
                except (OSError, ValueError):
                    continue
        except Exception as e:
            logger.warning(f"Failed to get Linux thermal zone temperatures: {e}")

        if not temperatures:
            temperatures.extend(cls._get_linux_lm_sensors())

        return temperatures

    @classmethod
    def _get_linux_lm_sensors(cls) -> List[Dict[str, Any]]:
        """Get temperatures using lm-sensors on Linux"""
        temperatures = []
        try:
            result = subprocess.run(
                cls.SENSOR_CONFIGS['Linux']['lm_sensors_cmd'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '°C' in line and ('temp' in line.lower() or 'core' in line.lower()):
                        temp_value = cls._parse_lm_sensor_line(line)
                        if temp_value and cls._is_valid_temperature(temp_value):
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
            import pythoncom
            import wmi
            pythoncom.CoInitialize()

            wmi_instance = wmi.WMI()
            wmi_cpu = wmi_instance.Win32_TemperatureProbe()
            for probe in wmi_cpu:
                if hasattr(probe, 'CurrentReading') and probe.CurrentReading:
                    temp_kelvin = probe.CurrentReading
                    if cls.SENSOR_CONFIGS['Windows']['temp_range_kelvin'][0] <= temp_kelvin <= cls.SENSOR_CONFIGS['Windows']['temp_range_kelvin'][1]:
                        temp_celsius = temp_kelvin - cls.SENSOR_CONFIGS['Windows']['conversion_factor']
                        temperatures.append({
                            'label': getattr(probe, 'Name', 'CPU Temperature'),
                            'current': temp_celsius
                        })

            # Try thermal zone method as fallback
            if not temperatures:
                wmi_instance_thermal = wmi.WMI(namespace="root\\wmi")
                temp_probes = wmi_instance_thermal.MSAcpi_ThermalZoneTemperature()
                for i, probe in enumerate(temp_probes):
                    if hasattr(probe, 'CurrentTemperature'):
                        temp_deci_kelvin = probe.CurrentTemperature
                        temp_celsius = (temp_deci_kelvin / 10.0) - 273.15
                        if cls._is_valid_temperature(temp_celsius):
                            temperatures.append({
                                'label': getattr(probe, 'InstanceName', f'Thermal Zone {i}').replace('_TZ', ' TZ'),
                                'current': temp_celsius
                            })
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to get Windows temperatures: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

        return temperatures

    @classmethod
    def _get_macos_temperatures(cls) -> List[Dict[str, Any]]:
        """Get temperatures on macOS systems"""
        temperatures = []
        try:
            result = subprocess.run(['sysctl', '-a'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if any(pattern in line for pattern in cls.SENSOR_CONFIGS['Darwin']['sysctl_patterns']):
                    temp_value = cls._parse_sysctl_line(line)
                    if temp_value and cls._is_valid_temperature(temp_value):
                        temperatures.append({'label': 'CPU Temperature', 'current': temp_value})
        except Exception as e:
            logger.warning(f"Failed to get macOS temperatures: {e}")
        return temperatures

    @classmethod
    def _get_mock_temperatures(cls) -> List[Dict[str, Any]]:
        """Generate mock temperature data when no sensors are available"""
        import random
        mock_temp = Config.MOCK_TEMP_BASE + random.uniform(0, Config.MOCK_TEMP_RANGE)
        return [{'label': 'CPU Core (Mock)', 'current': mock_temp}]

    @classmethod
    def _is_valid_temperature(cls, temp: float) -> bool:
        return Config.MIN_TEMP_CELSIUS <= temp <= Config.MAX_TEMP_CELSIUS

    @staticmethod
    def _parse_lm_sensor_line(line: str) -> Optional[float]:
        """Parse temperature from lm-sensors output line"""
        try:
            parts = line.split(':')
            if len(parts) >= 2:
                temp_part = parts[1].strip()
                if '+' in temp_part:
                    return float(temp_part.split('+')[-1].strip().replace('°C', '').strip())
        except (ValueError, IndexError):
            pass
        return None

    @staticmethod
    def _parse_sysctl_line(line: str) -> Optional[float]:
        """Parse temperature from sysctl output line"""
        try:
            return float(line.split(':')[-1].strip())
        except (ValueError, IndexError):
            return None


# =============================================================================
# System Information Collector
# =============================================================================
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
            freq = psutil.cpu_freq()
            if freq:
                cpu_info['cpu_freq'] = {
                    'current': freq.current,
                    'min': freq.min,
                    'max': freq.max
                }
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
            for partition in psutil.disk_partitions(all=True):
                if not partition.mountpoint:
                    continue
                try:
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
                except (PermissionError, FileNotFoundError, OSError):
                    continue

            if not disk_info:
                disk_info = SystemInfoCollector._get_wmi_disk_usage()

            return disk_info
        except Exception as e:
            logger.error(f"Error getting disk info: {e}")
            return None

    @staticmethod
    def _get_wmi_disk_usage() -> List[Dict[str, Any]]:
        """Get disk usage using WMI on Windows"""
        disk_info = []
        try:
            import pythoncom
            import wmi
            pythoncom.CoInitialize()
            wmi_instance = wmi.WMI()

            for logical_disk in wmi_instance.Win32_LogicalDisk():
                try:
                    if logical_disk.Size:
                        drive_letter = logical_disk.Name
                        if drive_letter and len(drive_letter) == 2 and drive_letter[1] == ':':
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
                except Exception:
                    continue
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to get disk info via WMI: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

        # Fallback to psutil with common drive letters
        if not disk_info and platform.system() == "Windows":
            for drive in ['C:', 'D:', 'E:', 'F:']:
                try:
                    usage = psutil.disk_usage(drive + '\\')
                    disk_info.append({
                        'device': drive,
                        'mountpoint': drive + '\\',
                        'fstype': 'NTFS',
                        'total': usage.total,
                        'used': usage.used,
                        'free': usage.free,
                        'percent': usage.percent
                    })
                except Exception:
                    continue

        return disk_info


# =============================================================================
# CPU Name Processing
# =============================================================================
# Intel generation to codename mapping
INTEL_CODENAMES = {
    '4': 'Haswell', '5': 'Broadwell', '6': 'Skylake',
    '7': 'Kaby Lake', '8': 'Coffee Lake', '9': 'Coffee Lake Refresh',
    '10': 'Comet Lake', '11': 'Rocket Lake', '12': 'Alder Lake',
    '13': 'Raptor Lake', '14': 'Meteor Lake', '15': 'Arrow Lake'
}

# Trademark/registered symbol cleanup pattern (compiled once for performance)
TRADEMARK_REGEX = re.compile(r'[®™©]')


def process_cpu_name(name: Optional[str], generation: Optional[str] = None,
                     manufacturer: str = 'Intel') -> tuple:
    """Process CPU name: clean, format, and get codename"""
    if not name:
        return name, 'Unknown'

    # Remove trademarks and generation prefixes
    cleaned = TRADEMARK_REGEX.sub('', name)
    cleaned = re.sub(r'^\d+(?:st|nd|rd|th)\s+G(?:en|eneration)?\s+', '', cleaned)
    cleaned = re.sub(r'\([Rr]\)|\([Tt][Mm]\)', '', cleaned)

    # Replace GenuineIntel with Intel
    final_name = cleaned.replace('GenuineIntel', 'Intel').strip()

    # Add hyphen for Intel i-series: i9 -> i9-
    if manufacturer == 'Intel' and 'Intel' in final_name:
        final_name = re.sub(r'\b(i\d+)([^-])', r'\1-\2', final_name)

    # Get codename
    codename = _get_cpu_codename(generation, manufacturer, cleaned)

    return final_name, codename


def _get_cpu_codename(generation: Optional[str], manufacturer: str, cleaned_name: str) -> str:
    """Extract CPU codename from generation and manufacturer info"""
    if not generation or 'Intel' not in manufacturer:
        if generation and 'AMD' in manufacturer and any(s in cleaned_name for s in ['Ryzen 9', 'Ryzen 8', 'Ryzen 7']):
            return 'Zen 4'
        return 'Unknown'

    gen_match = re.search(r'(\d+)(?:th|st|nd|rd)', generation)
    if not gen_match:
        return 'Unknown'

    gen_num = gen_match.group(1)
    codename = INTEL_CODENAMES.get(gen_num, f'Gen {gen_num}')

    # Add mobile suffix for laptop CPUs
    if any(term in cleaned_name.lower() for term in ['laptop', 'mobile', ' m ']):
        codename += ' (Mobile)'

    return codename


# =============================================================================
# Network Utilities
# =============================================================================
class NetworkUtils:
    """Handles network-related operations and caching"""

    IP_SERVICES = [
        'https://ipinfo.io/json',
        'http://ip-api.com/json/?fields=query,country,regionName,city',
        'https://api.ipify.org/?format=json',
        'https://httpbin.org/ip'
    ]

    @staticmethod
    def normalize_ip_response(service_url: str, data: Dict[str, Any]) -> Dict[str, str]:
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
            return {'ip': data.get('ip'), 'country': 'Unknown', 'region': 'Unknown', 'city': 'Unknown'}
        elif 'httpbin.org' in service_url:
            return {
                'ip': data.get('origin', '').split(',')[0].strip(),
                'country': 'Unknown', 'region': 'Unknown', 'city': 'Unknown'
            }
        return {'ip': 'Unknown', 'country': 'Unknown', 'region': 'Unknown', 'city': 'Unknown'}

    @staticmethod
    def fetch_ip_info_with_retry() -> Dict[str, Any]:
        """Fetch IP info with caching and exponential backoff"""
        global ip_cache

        if ip_cache['data'] and time.time() - ip_cache['timestamp'] < Config.CACHE_DURATION:
            return ip_cache['data']

        for service_url in NetworkUtils.IP_SERVICES:
            for attempt in range(Config.MAX_RETRIES):
                try:
                    response = requests.get(service_url, timeout=Config.REQUEST_TIMEOUT)
                    if response.status_code == 200:
                        ip_data = NetworkUtils.normalize_ip_response(service_url, response.json())
                        ip_cache['data'] = ip_data
                        ip_cache['timestamp'] = time.time()
                        return ip_data
                    elif response.status_code == 429:
                        time.sleep(2 ** attempt)
                        continue
                except requests.exceptions.RequestException:
                    time.sleep(2 ** attempt)

        logger.warning("All IP services failed, using local fallback")
        return NetworkUtils.get_basic_local_ip_info()

    @staticmethod
    def get_basic_local_ip_info() -> Dict[str, Any]:
        """Get basic local IP information when external services fail"""
        try:
            local_ipv4 = None
            local_ipv6 = None

            for addrs in psutil.net_if_addrs().values():
                for addr in addrs:
                    family = getattr(addr.family, 'name', '')
                    if family == 'AF_INET' and addr.address and not addr.address.startswith('127.'):
                        local_ipv4 = addr.address
                    elif family == 'AF_INET6' and addr.address and not addr.address.startswith('fe80') and not addr.address.startswith('::1'):
                        local_ipv6 = addr.address

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
            logger.error(f"Could not get basic local IP info: {e}")
            return {
                'ip': '127.0.0.1', 'local_ipv4': '127.0.0.1',
                'country': 'Local Network', 'region': 'Local Network',
                'city': 'Local Network', 'error': 'Could not determine local IP', 'source': 'local'
            }

    @staticmethod
    def get_network_info() -> Optional[Dict[str, Any]]:
        """Get detailed network information"""
        try:
            net_io = psutil.net_io_counters(pernic=False)
            ip_info = NetworkUtils.fetch_ip_info_with_retry()
            local_ipv6 = None

            if not ip_info or ip_info.get('error') or (ip_info.get('ip') and ':' not in ip_info.get('ip', '')):
                local_ipv6 = NetworkUtils._get_local_ipv6()

            # Apply offsets for reset functionality
            net_io_dict = net_io._asdict()
            for key in io_offsets:
                net_io_dict[key] = max(0, net_io_dict[key] - io_offsets[key])

            return {'io_counters': net_io_dict, 'ip_info': ip_info, 'local_ipv6': local_ipv6}
        except Exception as e:
            logger.error(f"Error getting network info: {e}")
            return None

    @staticmethod
    def _get_local_ipv6() -> Optional[str]:
        """Get local IPv6 address"""
        try:
            for addrs in psutil.net_if_addrs().values():
                for addr in addrs:
                    family = getattr(addr.family, 'name', '')
                    if family == 'AF_INET6' and addr.address and not addr.address.startswith('fe80'):
                        return addr.address
        except Exception:
            pass
        return None


# =============================================================================
# Hardware Detection
# =============================================================================
class HardwareDetector:
    """Handles hardware detection and information gathering"""

    WIFI_KEYWORDS = {'WIFI', 'WIRELESS', '802.11', 'WLAN', 'AX', 'BE', 'AC',
                     'BROADCOM', 'ATHEROS', 'REALTEK', 'INTEL', 'QUALCOMM', 'MEDIATEK', 'RALINK'}
    ETHERNET_KEYWORDS = {'ETHERNET', 'GBE', 'PCIE GBE', 'LAN', 'ETHERNET CONTROLLER'}

    # Cache WMI instance to avoid repeated initialization
    _wmi_instance = None

    @classmethod
    def _get_wmi(cls):
        """Get or create cached WMI instance"""
        if cls._wmi_instance is None:
            import pythoncom
            import wmi
            try:
                pythoncom.CoInitialize()
                cls._wmi_instance = wmi.WMI()
            except Exception:
                pass
        return cls._wmi_instance

    @classmethod
    def get_hardware_info(cls) -> Dict[str, Any]:
        """Get comprehensive hardware information"""
        hardware_info = {'gpu': [], 'motherboard': {}, 'processor': {}, 'wifi_adapters': []}

        try:
            wmi_instance = cls._get_wmi()
            if wmi_instance is None:
                return hardware_info

            hardware_info['processor'] = cls._get_processor_info(wmi_instance)
            hardware_info['gpu'] = cls._get_gpu_info(wmi_instance)
            hardware_info['motherboard'] = cls._get_motherboard_info(wmi_instance)
            hardware_info['wifi_adapters'] = cls._get_wifi_adapters(wmi_instance)

        except ImportError:
            logger.warning("WMI module not found. Hardware info will be limited.")
        except Exception as e:
            logger.error(f"Error during hardware detection: {e}")

        return hardware_info

    @classmethod
    def _get_processor_info(cls, wmi_instance) -> Dict[str, Any]:
        """Get processor information"""
        try:
            processor = wmi_instance.Win32_Processor()[0]
            cpu_name = processor.Name.strip()

            generation_match = re.search(r'(\d+)(?:th|st|nd|rd)\s*Gen', cpu_name)
            generation = generation_match.group(1) + 'th Gen' if generation_match else None

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
            logger.error(f"Could not retrieve processor info: {e}")
            return {}

    @classmethod
    def _get_gpu_info(cls, wmi_instance) -> List[Dict[str, Any]]:
        """Get GPU information"""
        gpu_info = []
        try:
            nvidia_memory = get_nvidia_gpu_memory()
            for gpu in wmi_instance.Win32_VideoController():
                adapter_ram = gpu.AdapterRAM

                if (gpu.Name and 'NVIDIA' in gpu.Name.upper() and
                    (adapter_ram is None or adapter_ram <= 0) and nvidia_memory):
                    adapter_ram = cls._match_nvidia_memory(gpu.Name, nvidia_memory)

                gpu_info.append({
                    'name': gpu.Name,
                    'driver_version': gpu.DriverVersion,
                    'status': gpu.Status,
                    'adapter_ram': adapter_ram
                })
        except Exception as e:
            logger.error(f"Could not retrieve GPU info: {e}")
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
            logger.error(f"Could not retrieve motherboard info: {e}")
            return {}

    @classmethod
    def _get_wifi_adapters(cls, wmi_instance) -> List[Dict[str, Any]]:
        """Get WiFi adapter information"""
        wifi_adapters = []
        try:
            for adapter in wmi_instance.Win32_NetworkAdapter():
                if cls._is_physical_wifi_adapter(adapter):
                    adapter_info = cls._extract_adapter_info(adapter)
                    if adapter_info:
                        wifi_adapters.append(adapter_info)
        except Exception as e:
            logger.error(f"Could not retrieve wifi adapter info: {e}")
        return wifi_adapters

    @staticmethod
    def _is_physical_wifi_adapter(adapter) -> bool:
        """Check if adapter is a physical WiFi adapter"""
        # Check if physical and enabled
        is_physical = bool(adapter.PhysicalAdapter) if adapter.PhysicalAdapter is not None else False
        is_enabled = bool(adapter.NetEnabled) if adapter.NetEnabled is not None else False

        if not (is_physical and is_enabled):
            return False

        adapter_name = adapter.Name or adapter.Description or 'Unknown'
        adapter_name_upper = adapter_name.upper()

        # Check if it's WiFi (not Ethernet)
        is_ethernet = any(kw in adapter_name_upper for kw in HardwareDetector.ETHERNET_KEYWORDS)
        is_wifi = (any(kw in adapter_name_upper for kw in HardwareDetector.WIFI_KEYWORDS)
                   and not is_ethernet and adapter.MACAddress)

        return is_wifi

    @staticmethod
    def _extract_adapter_info(adapter) -> Optional[Dict[str, Any]]:
        """Extract information from a WiFi adapter"""
        try:
            speed_value = None
            if adapter.Speed is not None:
                try:
                    speed_val = int(adapter.Speed)
                    if 0 < speed_val < Config.WIFI_SPEED_MAX:
                        speed_value = speed_val
                except (ValueError, TypeError):
                    pass

            return {
                'name': adapter.Name or adapter.Description or 'Unknown',
                'manufacturer': adapter.Manufacturer,
                'device_id': adapter.DeviceID,
                'mac_address': adapter.MACAddress,
                'speed': speed_value,
                'status': adapter.Status
            }
        except Exception:
            return None

    @staticmethod
    def _match_nvidia_memory(gpu_name: str, nvidia_memory: Dict[str, int]) -> Optional[int]:
        """Match GPU name with NVIDIA memory info"""
        if not nvidia_memory:
            return None

        gpu_name_upper = gpu_name.upper()
        for nv_name, nv_memory in nvidia_memory.items():
            nv_name_upper = nv_name.upper()
            if (('GEFORCE' in gpu_name_upper and 'GEFORCE' in nv_name_upper) or
                ('RTX' in gpu_name_upper and 'RTX' in nv_name_upper) or
                any(word in gpu_name_upper for word in nv_name_upper.split() if len(word) > 3)):
                return nv_memory
        return None


# =============================================================================
# NVIDIA GPU Memory
# =============================================================================
def get_nvidia_gpu_memory() -> Optional[Dict[str, int]]:
    """Get NVIDIA GPU memory information using NVML"""
    if not NVML_AVAILABLE:
        return None

    try:
        pynvml.nvmlInit()
    except Exception:
        return None

    try:
        device_count = pynvml.nvmlDeviceGetCount()
        gpu_memory_info = {}
        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            name = pynvml.nvmlDeviceGetName(handle)

            if isinstance(name, bytes):
                name = name.decode('utf-8')
            elif hasattr(name, '__str__'):
                name = str(name)

            gpu_memory_info[name] = info.total

        pynvml.nvmlShutdown()
        return gpu_memory_info
    except Exception as e:
        logger.warning(f"Error getting NVIDIA GPU memory: {e}")
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        return None


# =============================================================================
# API Routes
# =============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": time.time()})


@app.route('/api/system-info', methods=['GET'])
def system_info():
    """Consolidated endpoint for system information"""
    hardware_data = HardwareDetector.get_hardware_info()

    cpu_info = SystemInfoCollector.get_cpu_info()
    if cpu_info:
        physical_cores = cpu_info.get('cpu_count_physical', 0)
        logical_processors = cpu_info.get('cpu_count_logical', 0)
        cpu_info['core_types'] = CPUArchitectureDetector.detect_core_types(physical_cores, logical_processors, hardware_data)

    data = {
        'cpu': cpu_info,
        'memory': SystemInfoCollector.get_memory_info(),
        'disk': SystemInfoCollector.get_disk_info(),
        'network': NetworkUtils.get_network_info(),
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'windows_version': _get_windows_version(),
            'architecture': platform.machine(),
            'processor': platform.processor()
        }
    }

    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        return jsonify({'error': 'Could not retrieve system information'}), 500
    return jsonify(data)


def _get_windows_version() -> str:
    """Determine Windows version from platform version string"""
    try:
        ver_parts = platform.version().split('.')
        if ver_parts and int(ver_parts[-1]) >= 22000:
            return 'Windows 11'
    except (ValueError, IndexError):
        pass
    return 'Windows 10'


@app.route('/api/hardware-info', methods=['GET'])
def hardware_info():
    """Endpoint for detailed hardware information"""
    return jsonify(HardwareDetector.get_hardware_info())


@app.route('/api/reset-io', methods=['POST'])
def reset_io():
    """Reset I/O counters"""
    global io_offsets
    try:
        current_io = psutil.net_io_counters(pernic=False)
        io_offsets['bytes_sent'] = current_io.bytes_sent
        io_offsets['bytes_recv'] = current_io.bytes_recv
        io_offsets['packets_sent'] = current_io.packets_sent
        io_offsets['packets_recv'] = current_io.packets_recv
        return jsonify({'status': 'I/O counters reset'})
    except Exception as e:
        logger.error(f"Error resetting I/O: {e}")
        return jsonify({'error': 'Failed to reset I/O counters'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)