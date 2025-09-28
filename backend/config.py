"""
Configuration constants and settings for the SystemInfo backend.
"""
import os
from typing import Dict, List, Tuple


class Config:
    """Application configuration constants."""

    # Cache settings
    CACHE_DURATION = 300  # seconds
    MAX_CACHE_SIZE = 100

    # Temperature validation
    MAX_TEMP_CELSIUS = 150
    MIN_TEMP_CELSIUS = 0
    MOCK_TEMP_BASE = 35
    MOCK_TEMP_RANGE = 30

    # Network settings
    REQUEST_TIMEOUT = 5
    MAX_RETRIES = 2
    WIFI_SPEED_MAX = 10000000

    # WMI temperature ranges (Kelvin)
    WMI_TEMP_KELVIN_MIN = 273
    WMI_TEMP_KELVIN_MAX = 423

    # Hardware detection patterns
    WIFI_KEYWORDS = [
        'WIFI', 'WIRELESS', '802.11', 'WLAN', 'AX', 'BE', 'AC',
        'BROADCOM', 'ATHEROS', 'REALTEK', 'INTEL', 'QUALCOMM', 'MEDIATEK',
        'RALIINK', 'RALINK'
    ]

    ETHERNET_KEYWORDS = [
        'ETHERNET', 'GBE', 'PCIE GBE', 'LAN', 'ETHERNET CONTROLLER'
    ]

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

    # IP service endpoints with their response parsers
    IP_SERVICES = {
        'https://ipinfo.io/json': lambda d: {
            'ip': d.get('ip'),
            'country': d.get('country'),
            'region': d.get('region'),
            'city': d.get('city')
        },
        'http://ip-api.com/json/?fields=query,country,regionName,city': lambda d: {
            'ip': d.get('query'),
            'country': d.get('country'),
            'region': d.get('regionName'),
            'city': d.get('city')
        },
        'https://api.ipify.org/?format=json': lambda d: {
            'ip': d.get('ip'),
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown'
        },
        'https://httpbin.org/ip': lambda d: {
            'ip': d.get('origin', '').split(',')[0].strip(),
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown'
        }
    }

    # Extended sensor names for temperature detection
    SENSOR_NAMES = [
        'coretemp', 'cpu_thermal', 'k10temp', 'acpi_thermal', 'thermal_zone0',
        'cpu_0', 'cpu_1', 'cpu_2', 'cpu_3', 'cpu_4', 'cpu_5', 'cpu_6', 'cpu_7',
        'cpu', 'thermal', 'hwmon', 'sensors', 'temperatures'
    ]

    # Intel codenames by generation
    INTEL_CODENAMES = {
        '13': 'Raptor Lake', '14': 'Meteor Lake', '15': 'Arrow Lake',
        '12': 'Broadwell', '11': 'Haswell', '10': 'Ivy Bridge',
        '9': 'Sandy Bridge', '7': 'Nehalem', '6': 'Core', '4': 'NetBurst'
    }

    # Flask settings
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))


class Cache:
    """Simple in-memory cache with TTL support."""

    def __init__(self):
        self._cache: Dict[str, Dict] = {}
        self._max_size = Config.MAX_CACHE_SIZE

    def get(self, key: str) -> any:
        """Get value from cache if not expired."""
        if key in self._cache:
            entry = self._cache[key]
            if entry['expires'] > time.time():
                return entry['value']
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: any, ttl: int = Config.CACHE_DURATION) -> None:
        """Set value in cache with TTL."""
        # Simple LRU: remove oldest entries if cache is full
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]['expires'])
            del self._cache[oldest_key]

        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl
        }

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


# Global cache instance
cache = Cache()
