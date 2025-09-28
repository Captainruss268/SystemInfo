"""
Utility functions for the SystemInfo backend.
"""
import re
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from functools import wraps
import psutil
import platform

from config import Config, cache


# Set up logging
logger = logging.getLogger(__name__)


def time_function(func: Callable) -> Callable:
    """Decorator to time function execution."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.debug(f"{func.__name__} took {(end_time - start_time):.4f} seconds")
        return result
    return wrapper


def retry_on_failure(max_retries: int = 3, delay: float = 1.0):
    """Decorator to retry function on failure with exponential backoff."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
                        raise
                    time.sleep(delay * (2 ** attempt))
            return None
        return wrapper
    return decorator


def validate_temperature(temp: float) -> bool:
    """Check if temperature is in valid range."""
    return Config.MIN_TEMP_CELSIUS <= temp <= Config.MAX_TEMP_CELSIUS


def validate_kelvin_temperature(temp_kelvin: float) -> bool:
    """Check if Kelvin temperature is in valid range."""
    return (Config.WMI_TEMP_KELVIN_MIN <= temp_kelvin <= Config.WMI_TEMP_KELVIN_MAX)


def safe_execute(default_return=None):
    """Decorator to safely execute functions with error handling."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Error in {func.__name__}: {e}")
                return default_return
        return wrapper
    return decorator


def parse_lm_sensor_line(line: str) -> Optional[float]:
    """Parse temperature from lm-sensors output line."""
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


def parse_sysctl_line(line: str) -> Optional[float]:
    """Parse temperature from sysctl output line."""
    try:
        temp_str = line.split(':')[-1].strip()
        return float(temp_str)
    except (ValueError, IndexError):
        pass
    return None


def process_cpu_name(name: str, generation: Optional[str] = None, manufacturer: str = 'Intel') -> tuple[str, str]:
    """Process CPU name: clean, format, and get codename."""
    if not name:
        return name, 'Unknown'

    # Clean name - remove generation prefixes and trademarks
    cleaned = re.sub(r'^\d+(?:st|nd|rd|th)\s+G(?:en|eneration)?\s+|[®™©®®™®©®®™©®®™®©®™©]', '', name)

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
        codename = Config.INTEL_CODENAMES.get(gen_num, f'Gen {gen_num}' if gen_num else 'Unknown')

        # Add mobile suffix for laptop CPUs
        if any(term in cleaned.lower() for term in ['laptop', 'mobile', ' m ']):
            codename += ' (Mobile)'

    elif generation and 'AMD' in manufacturer:
        if any(series in name for series in ['Ryzen 9', 'Ryzen 8', 'Ryzen 7']):
            codename = 'Zen 4'
        else:
            codename = 'Zen Architecture'

    return final_name, codename


def get_mock_temperature() -> Dict[str, Any]:
    """Generate mock temperature data when no sensors are available."""
    import random
    mock_temp = Config.MOCK_TEMP_BASE + random.uniform(0, Config.MOCK_TEMP_RANGE)
    logger.info(f"Using mock temperature data (no real sensors detected): {mock_temp:.1f}°C")
    return {
        'label': 'CPU Core (Mock)',
        'current': mock_temp
    }


def extract_generation_from_cpu_name(cpu_name: str) -> Optional[str]:
    """Extract generation from CPU name."""
    match = re.search(r'(\d+)(?:th|th\s+Gen|st|st\s+Gen|nd|nd\s+Gen|rd|rd\s+Gen)', cpu_name)
    return match.group(1) + 'th Gen' if match else None


def is_physical_wifi_adapter(adapter) -> bool:
    """Check if adapter is a physical WiFi adapter."""
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
    is_ethernet = any(keyword in adapter_name.upper() for keyword in Config.ETHERNET_KEYWORDS)
    is_wifi = (any(keyword in adapter_name.upper() for keyword in Config.WIFI_KEYWORDS)
              and not is_ethernet and adapter.MACAddress)

    return is_wifi


def extract_adapter_info(adapter) -> Optional[Dict[str, Any]]:
    """Extract information from a WiFi adapter."""
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


def match_nvidia_memory(gpu_name: str, nvidia_memory: Dict[str, int]) -> Optional[int]:
    """Match GPU name with NVIDIA memory info."""
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


def get_local_ipv6() -> Optional[str]:
    """Get local IPv6 address."""
    try:
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family.name == 'AF_INET6' and addr.address and not addr.address.startswith('fe80'):
                    return addr.address
    except Exception as e:
        logger.warning(f"Could not get local IPv6: {e}")
    return None


def get_basic_local_ip_info() -> Dict[str, Any]:
    """Get basic local IP information when external services fail."""
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


@retry_on_failure(max_retries=Config.MAX_RETRIES)
def fetch_ip_info() -> Dict[str, Any]:
    """Fetch IP info with caching."""
    cache_key = 'ip_info'

    # Check cache first
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data

    import requests

    for service_url, parser_func in Config.IP_SERVICES.items():
        try:
            response = requests.get(service_url, timeout=Config.REQUEST_TIMEOUT)
            if response.status_code == 200:
                ip_data = parser_func(response.json())
                cache.set(cache_key, ip_data)
                return ip_data
            elif response.status_code == 429:  # Rate limited
                time.sleep(2)
                continue
        except requests.exceptions.RequestException:
            continue

    logger.warning("All IP services failed, using local fallback")
    local_info = get_basic_local_ip_info()
    cache.set(cache_key, local_info)
    return local_info
