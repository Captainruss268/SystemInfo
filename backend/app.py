from flask import Flask, jsonify
from flask_cors import CORS
import psutil
import platform
import logging
import re
import pythoncom
import requests
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from functools import lru_cache
import subprocess
import glob

try:
    import pynvml
    NVML_AVAILABLE = True
except ImportError:
    NVML_AVAILABLE = False

# Configuration constants
class Config:
    CACHE_DURATION = 300  # seconds
    MAX_TEMP_CELSIUS = 150
    MIN_TEMP_CELSIUS = 0
    MOCK_TEMP_BASE = 35
    MOCK_TEMP_RANGE = 30
    REQUEST_TIMEOUT = 5
    MAX_RETRIES = 2
    WMI_TEMP_KELVIN_MIN = 273
    WMI_TEMP_KELVIN_MAX = 423
    WIFI_SPEED_MAX = 10000000

# Set up logging
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.logger.setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Global state (consider moving to a class)
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

# CPU Architecture Detection
class CPUArchitectureDetector:
    """Handles detection of CPU core types (P-cores vs E-cores)"""

    # CPU architecture patterns
    CPU_PATTERNS = {
        'intel': {
            'i3': lambda cores: (cores, 0),  # All P-cores
            'i5': lambda cores: (6, cores - 6),
            'i7': lambda cores: (8, cores - 8) if cores != 24 else (8, 16),
            'i9': lambda cores: (8, cores - 8) if cores != 24 else (8, 16),
        },
        'amd': {
            'ryzen_7000_8core': lambda cores: (6, 2),
            'ryzen_7000_16core': lambda cores: (8, 8),
        },
        'apple': {
            'silicon': lambda cores: (cores, 0),  # All P-cores
        },
        'qualcomm': {
            'snapdragon_x': lambda cores: (8, 4) if cores == 12 else (0, cores),
        }
    }

    @classmethod
    def detect_core_types(cls, physical_cores: int, logical_processors: int, hardware_info: Optional[Dict] = None) -> Dict[str, int]:
        """Detect P-cores vs E-cores based on CPU architecture"""
        try:
            if physical_cores == logical_processors:
                return cls._create_core_result(0, physical_cores, physical_cores)

            if not hardware_info or 'processor' not in hardware_info:
                return cls._calculate_fallback_cores(physical_cores, logical_processors)

            processor_name = hardware_info['processor'].get('name', '').lower()
            manufacturer = hardware_info['processor'].get('manufacturer', '').lower()

            return cls._detect_by_manufacturer(processor_name, manufacturer, physical_cores, logical_processors)

        except Exception as e:
            logger.warning(f"Error in core type detection: {e}")
            return cls._create_fallback_result(physical_cores)

    @classmethod
    def _detect_by_manufacturer(cls, processor_name: str, manufacturer: str, physical_cores: int, logical_processors: int) -> Dict[str, int]:
        """Detect core types based on manufacturer and model"""

        # Intel detection
        if cls._is_intel_cpu(processor_name, manufacturer):
            return cls._detect_intel_cores(processor_name, physical_cores)

        # AMD detection
        if cls._is_amd_cpu(manufacturer, processor_name):
            return cls._detect_amd_cores(physical_cores)

        # Apple Silicon detection
        if cls._is_apple_silicon(processor_name):
            return cls._create_core_result(physical_cores, 0, physical_cores)

        # Qualcomm detection
        if cls._is_qualcomm_cpu(manufacturer, processor_name):
            return cls._detect_qualcomm_cores(physical_cores)

        # Fallback calculation
        return cls._calculate_fallback_cores(physical_cores, logical_processors)

    @classmethod
    def _is_intel_cpu(cls, processor_name: str, manufacturer: str) -> bool:
        return any(arch in processor_name for arch in ['intel', 'core i']) or 'intel' in manufacturer

    @classmethod
    def _is_amd_cpu(cls, manufacturer: str, processor_name: str) -> bool:
        return 'amd' in manufacturer and any(arch in processor_name for arch in ['ryzen 7', 'ryzen 8', 'ryzen 9'])

    @classmethod
    def _is_apple_silicon(cls, processor_name: str) -> bool:
        return any(arch in processor_name for arch in ['apple m', 'apple silicon', 'm1', 'm2', 'm3', 'm4'])

    @classmethod
    def _is_qualcomm_cpu(cls, manufacturer: str, processor_name: str) -> bool:
        return 'qualcomm' in manufacturer or 'snapdragon' in processor_name

    @classmethod
    def _detect_intel_cores(cls, processor_name: str, physical_cores: int) -> Dict[str, int]:
        """Detect Intel CPU core configuration"""
        intel_patterns = cls.CPU_PATTERNS['intel']

        if 'i3' in processor_name:
            p_cores, e_cores = intel_patterns['i3'](physical_cores)
        elif 'i5' in processor_name:
            p_cores, e_cores = intel_patterns['i5'](physical_cores)
        elif 'i7' in processor_name or 'i9' in processor_name:
            p_cores, e_cores = intel_patterns['i7'](physical_cores)
        else:
            # Generic Intel fallback
            p_cores = min(8, physical_cores) if physical_cores > 4 else physical_cores
            e_cores = max(0, physical_cores - p_cores)

        return cls._validate_and_create_result(p_cores, e_cores, physical_cores)

    @classmethod
    def _detect_amd_cores(cls, physical_cores: int) -> Dict[str, int]:
        """Detect AMD CPU core configuration"""
        amd_patterns = cls.CPU_PATTERNS['amd']

        if physical_cores == 8:
            p_cores, e_cores = amd_patterns['ryzen_7000_8core'](physical_cores)
        elif physical_cores == 16:
            p_cores, e_cores = amd_patterns['ryzen_7000_16core'](physical_cores)
        else:
            # Generic AMD fallback
            p_cores = physical_cores // 2 + 1
            e_cores = physical_cores - p_cores

        return cls._validate_and_create_result(p_cores, e_cores, physical_cores)

    @classmethod
    def _detect_qualcomm_cores(cls, physical_cores: int) -> Dict[str, int]:
        """Detect Qualcomm CPU core configuration"""
        qualcomm_patterns = cls.CPU_PATTERNS['qualcomm']
        p_cores, e_cores = qualcomm_patterns['snapdragon_x'](physical_cores)
        return cls._validate_and_create_result(p_cores, e_cores, physical_cores)

    @classmethod
    def _calculate_fallback_cores(cls, physical_cores: int, logical_processors: int) -> Dict[str, int]:
        """Calculate core types using logical vs physical processor count"""
        calc_p_cores = logical_processors - physical_cores
        calc_e_cores = physical_cores - calc_p_cores

        if calc_p_cores >= 0 and calc_e_cores >= 0 and (calc_p_cores + calc_e_cores == physical_cores):
            return cls._create_core_result(calc_p_cores, calc_e_cores, physical_cores)

        return cls._create_fallback_result(physical_cores)

    @classmethod
    def _validate_and_create_result(cls, p_cores: int, e_cores: int, physical_cores: int) -> Dict[str, int]:
        """Validate core calculation and create result"""
        if p_cores + e_cores != physical_cores:
            logger.warning(f"Core calculation mismatch: {p_cores}P + {e_cores}E != {physical_cores} total")
            return cls._create_fallback_result(physical_cores)

        return cls._create_core_result(p_cores, e_cores, physical_cores)

    @classmethod
    def _create_core_result(cls, p_cores: int, e_cores: int, total_cores: int) -> Dict[str, int]:
        return {
            'p_cores': p_cores,
            'e_cores': e_cores,
            'total_cores': total_cores
        }

    @classmethod
    def _create_fallback_result(cls, physical_cores: int) -> Dict[str, int]:
        return {
            'p_cores': 0,
            'e_cores': physical_cores,
            'total_cores': physical_cores
        }

# Backward compatibility function
def detect_core_types(physical_cores: int, logical_processors: int, hardware_info: Optional[Dict] = None) -> Dict[str, int]:
    """Legacy function for backward compatibility"""
    return CPUArchitectureDetector.detect_core_types(physical_cores, logical_processors, hardware_info)

# Temperature Detection Module
class TemperatureDetector:
    """Handles temperature detection across different platforms"""

    # Platform-specific sensor configurations
    SENSOR_CONFIGS = {
        'Linux': {
            'psutil_sensors': ['coretemp', 'cpu_thermal', 'k10temp', 'acpi_thermal', 'thermal_zone0'],
            'thermal_zones_path': '/sys/class/thermal/thermal_zone*/temp',
            'lm_sensors_cmd': ['sensors'],
            'temp_conversion_factor': 1000.0  # Convert from millicelsius
        },
        'Windows': {
            'wmi_class': 'Win32_TemperatureProbe',
            'temp_range_kelvin': (273, 423),
            'conversion_factor': 273.15  # Convert from Kelvin to Celsius
        },
        'Darwin': {
            'sysctl_patterns': ['cpu_temp', 'cpu.temperature']
        }
    }

    @classmethod
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
        return cls._get_mock_temperatures()

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

            # Expanded list of sensor names to check
            sensor_names = [
                'coretemp', 'cpu_thermal', 'k10temp', 'acpi_thermal', 'thermal_zone0',
                'cpu_0', 'cpu_1', 'cpu_2', 'cpu_3', 'cpu_4', 'cpu_5', 'cpu_6', 'cpu_7',
                'cpu', 'thermal', 'hwmon', 'sensors', 'temperatures'
            ]

            temperatures = []

            # Check all available sensor types
            for sensor_name in sensor_names:
                if sensor_name in temps:
                    logger.info(f"Found temperature sensor: {sensor_name}")
                    for temp_sensor in temps[sensor_name]:
                        if hasattr(temp_sensor, 'current'):
                            temp_value = temp_sensor.current
                            # Less strict temperature validation
                            if temp_value > -50 and temp_value < 200:  # Reasonable CPU temp range
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
                cls.SENSOR_CONFIGS['Linux']['lm_sensors_cmd'],
                capture_output=True,
                text=True,
                timeout=5
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
            pythoncom.CoInitialize()
            import wmi
            
            # First, try the existing method
            try:
                wmi_instance = wmi.WMI()
                wmi_cpu = wmi_instance.Win32_TemperatureProbe()
                for probe in wmi_cpu:
                    if hasattr(probe, 'CurrentReading'):
                        temp_kelvin = probe.CurrentReading
                        if temp_kelvin and cls._is_valid_kelvin_temperature(temp_kelvin):
                            temp_celsius = temp_kelvin - cls.SENSOR_CONFIGS['Windows']['conversion_factor']
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
                            if cls._is_valid_temperature(temp_celsius):
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
                if any(pattern in line for pattern in cls.SENSOR_CONFIGS['Darwin']['sysctl_patterns']):
                    temp_value = cls._parse_sysctl_line(line)
                    if temp_value and cls._is_valid_temperature(temp_value):
                        temperatures.append({
                            'label': 'CPU Temperature',
                            'current': temp_value
                        })
        except Exception as e:
            logger.warning(f"Failed to get macOS temperatures: {e}")

        return temperatures

    @classmethod
    def _get_mock_temperatures(cls) -> List[Dict[str, Any]]:
        """Generate mock temperature data when no sensors are available"""
        import random
        mock_temp = Config.MOCK_TEMP_BASE + random.uniform(0, Config.MOCK_TEMP_RANGE)
        logger.info(f"Using mock temperature data (no real sensors detected): {mock_temp}°C")
        return [{
            'label': 'CPU Core (Mock)',
            'current': mock_temp
        }]

    @classmethod
    def _is_valid_temperature(cls, temp: float) -> bool:
        """Check if temperature is in valid range"""
        return Config.MIN_TEMP_CELSIUS <= temp <= Config.MAX_TEMP_CELSIUS

    @classmethod
    def _is_valid_kelvin_temperature(cls, temp_kelvin: float) -> bool:
        """Check if Kelvin temperature is in valid range"""
        return (cls.SENSOR_CONFIGS['Windows']['temp_range_kelvin'][0] <= temp_kelvin <=
                cls.SENSOR_CONFIGS['Windows']['temp_range_kelvin'][1])

    @classmethod
    def _parse_lm_sensor_line(cls, line: str) -> Optional[float]:
        """Parse temperature from lm-sensors output line"""
        try:
            parts = line.split(':')
            if len(parts) >= 2:
                temp_part = parts[1].strip()
                if '+' in temp_part:
                    temp_str = temp_part.split('+')[-1].strip()
                    return float(temp_str.replace('°C', '').strip())
        except (ValueError, IndexError):
            pass
        return None

    @classmethod
    def _parse_sysctl_line(cls, line: str) -> Optional[float]:
        """Parse temperature from sysctl output line"""
        try:
            temp_str = line.split(':')[-1].strip()
            return float(temp_str)
        except (ValueError, IndexError):
            pass
        return None

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

# Network Utilities
class NetworkUtils:
    """Handles network-related operations and caching"""

    # IP service endpoints
    IP_SERVICES = [
        'https://ipinfo.io/json',
        'http://ip-api.com/json/?fields=query,country,regionName,city',
        'https://api.ipify.org/?format=json',
        'https://httpbin.org/ip'
    ]

    @staticmethod
    def normalize_ip_response(service_url: str, data: Dict[str, Any]) -> Dict[str, str]:
        """Normalize IP response from different APIs"""
        service_mappings = {
            'ipinfo.io': lambda d: {
                'ip': d.get('ip'),
                'country': d.get('country'),
                'region': d.get('region'),
                'city': d.get('city')
            },
            'ip-api.com': lambda d: {
                'ip': d.get('query'),
                'country': d.get('country'),
                'region': d.get('regionName'),
                'city': d.get('city')
            },
            'api.ipify.org': lambda d: {
                'ip': d.get('ip'),
                'country': 'Unknown',
                'region': 'Unknown',
                'city': 'Unknown'
            },
            'httpbin.org': lambda d: {
                'ip': d.get('origin', '').split(',')[0].strip(),
                'country': 'Unknown',
                'region': 'Unknown',
                'city': 'Unknown'
            }
        }

        for service, mapping_func in service_mappings.items():
            if service in service_url:
                return mapping_func(data)

        return {
            'ip': 'Unknown',
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown'
        }

    @staticmethod
    def fetch_ip_info_with_retry() -> Dict[str, Any]:
        """Fetch IP info with caching and exponential backoff"""
        global ip_cache

        # Check cache first
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
                    elif response.status_code == 429:  # Rate limited
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
            logger.error(f"Could not get basic local IP info: {e}")
            return {
                'ip': '127.0.0.1',
                'local_ipv4': '127.0.0.1',
                'country': 'Local Network',
                'region': 'Local Network',
                'city': 'Local Network',
                'error': 'Could not determine local IP',
                'source': 'local'
            }

    @staticmethod
    def get_network_info() -> Optional[Dict[str, Any]]:
        """Get detailed network information"""
        try:
            net_io = psutil.net_io_counters()
            ip_info = NetworkUtils.fetch_ip_info_with_retry()
            local_ipv6 = None

            # Get IPv6 from local interfaces if needed
            if not ip_info or ip_info.get('error') or (ip_info.get('ip') and ':' not in ip_info.get('ip', '')):
                local_ipv6 = NetworkUtils._get_local_ipv6()

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

    @staticmethod
    def _get_local_ipv6() -> Optional[str]:
        """Get local IPv6 address"""
        try:
            for interface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family.name == 'AF_INET6' and addr.address and not addr.address.startswith('fe80'):
                        return addr.address
        except Exception as e:
            logger.warning(f"Could not get local IPv6: {e}")
        return None

# Hardware Detection Module
class HardwareDetector:
    """Handles hardware detection and information gathering"""

    # WiFi adapter keywords
    WIFI_KEYWORDS = [
        'WIFI', 'WIRELESS', '802.11', 'WLAN', 'AX', 'BE', 'AC',
        'BROADCOM', 'ATHEROS', 'REALTEK', 'INTEL', 'QUALCOMM', 'MEDIATEK',
        'RALIINK', 'RALINK'
    ]

    ETHERNET_KEYWORDS = [
        'ETHERNET', 'GBE', 'PCIE GBE', 'LAN', 'ETHERNET CONTROLLER'
    ]

    @staticmethod
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

    @staticmethod
    def _get_processor_info(wmi_instance) -> Dict[str, Any]:
        """Get processor information"""
        try:
            processor = wmi_instance.Win32_Processor()[0]
            cpu_name = processor.Name.strip()

            # Extract generation
            generation_match = re.search(r'(\d+)(?:th|th\s+Gen|st|st\s+Gen|nd|nd\s+Gen|rd|rd\s+Gen)', cpu_name)
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
            logger.error(f"Could not retrieve processor info via WMI: {e}")
            return {}

    @staticmethod
    def _get_gpu_info(wmi_instance) -> List[Dict[str, Any]]:
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
                    adapter_ram = HardwareDetector._match_nvidia_memory(gpu.Name, nvidia_memory)

                gpu_info.append({
                    'name': gpu.Name,
                    'driver_version': gpu.DriverVersion,
                    'status': gpu.Status,
                    'adapter_ram': adapter_ram
                })
        except Exception as e:
            logger.error(f"Could not retrieve GPU info via WMI: {e}")

        return gpu_info

    @staticmethod
    def _get_motherboard_info(wmi_instance) -> Dict[str, Any]:
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

    @staticmethod
    def _get_wifi_adapters(wmi_instance) -> List[Dict[str, Any]]:
        """Get WiFi adapter information"""
        wifi_adapters = []

        try:
            for adapter in wmi_instance.Win32_NetworkAdapter():
                if HardwareDetector._is_physical_wifi_adapter(adapter):
                    adapter_info = HardwareDetector._extract_adapter_info(adapter)
                    if adapter_info:
                        wifi_adapters.append(adapter_info)
        except Exception as e:
            logger.error(f"Could not retrieve wifi adapter info via WMI: {e}")

        return wifi_adapters

    @staticmethod
    def _is_physical_wifi_adapter(adapter) -> bool:
        """Check if adapter is a physical WiFi adapter"""
        # Check if physical
        is_physical = False
        if adapter.PhysicalAdapter is not None:
            if isinstance(adapter.PhysicalAdapter, bool):
                is_physical = adapter.PhysicalAdapter
            elif isinstance(adapter.PhysicalAdapter, (int, str)):
                is_physical = str(adapter.PhysicalAdapter).lower() in ('1', 'true', 'yes')

        # Check if enabled
        is_enabled = False
        if adapter.NetEnabled is not None:
            if isinstance(adapter.NetEnabled, bool):
                is_enabled = adapter.NetEnabled
            elif isinstance(adapter.NetEnabled, (int, str)):
                is_enabled = str(adapter.NetEnabled).lower() in ('1', 'true', 'yes')

        if not (is_physical and is_enabled):
            return False

        adapter_name = adapter.Name or adapter.Description or 'Unknown'

        # Check if it's WiFi (not Ethernet)
        is_ethernet = any(keyword in adapter_name.upper() for keyword in HardwareDetector.ETHERNET_KEYWORDS)
        is_wifi = (any(keyword in adapter_name.upper() for keyword in HardwareDetector.WIFI_KEYWORDS)
                  and not is_ethernet and adapter.MACAddress)

        return is_wifi

    @staticmethod
    def _extract_adapter_info(adapter) -> Optional[Dict[str, Any]]:
        """Extract information from a WiFi adapter"""
        try:
            adapter_name = adapter.Name or adapter.Description or 'Unknown'

            # Parse speed safely
            speed_value = None
            if adapter.Speed is not None:
                try:
                    speed_val = int(adapter.Speed)
                    if 0 < speed_val < Config.WIFI_SPEED_MAX:
                        speed_value = speed_val
                except (ValueError, TypeError):
                    pass

            return {
                'name': adapter_name,
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

            # Simple name matching
            if (('GEFORCE' in gpu_name_upper and 'GEFORCE' in nv_name_upper) or
                ('RTX' in gpu_name_upper and 'RTX' in nv_name_upper) or
                any(word in gpu_name_upper for word in nv_name_upper.split() if len(word) > 3)):
                return nv_memory

        return None

# Backward compatibility functions
def get_memory_info() -> Optional[Dict[str, Any]]:
    """Legacy function for backward compatibility"""
    return SystemInfoCollector.get_memory_info()

def get_disk_info() -> Optional[List[Dict[str, Any]]]:
    """Legacy function for backward compatibility"""
    return SystemInfoCollector.get_disk_info()

def _normalize_ip_response(service_url: str, data: Dict[str, Any]) -> Dict[str, str]:
    """Legacy function for backward compatibility"""
    return NetworkUtils.normalize_ip_response(service_url, data)

def fetch_ip_info_with_retry() -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return NetworkUtils.fetch_ip_info_with_retry()

def get_basic_local_ip_info() -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return NetworkUtils.get_basic_local_ip_info()

def get_network_info() -> Optional[Dict[str, Any]]:
    """Legacy function for backward compatibility"""
    return NetworkUtils.get_network_info()

def get_hardware_info() -> Dict[str, Any]:
    """Legacy function for backward compatibility"""
    return HardwareDetector.get_hardware_info()

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
