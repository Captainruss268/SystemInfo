// Global types for the system monitoring application

export interface CpuInfo {
  cpu_count_physical: number;
  cpu_count_logical: number;
  cpu_percent: number[];
  cpu_freq?: {
    current: number;
    min: number;
    max: number;
  };
  temperatures?: Array<{
    label: string;
    current: number;
  }>;
}

export interface MemoryInfo {
  total: number;
  available: number;
  percent: number;
  used: number;
  free: number;
}

export interface DiskInfo {
  device: string;
  mountpoint: string;
  fstype: string;
  total: number;
  used: number;
  free: number;
  percent: number;
}

export interface IpInfo {
  ip?: string;
  country?: string;
  region?: string;
  city?: string;
  local_ipv4?: string;
  local_ipv6?: string;
  error?: string;
  source?: string;
}

export interface NetworkInfo {
  io_counters: {
    bytes_sent: number;
    bytes_recv: number;
    packets_sent: number;
    packets_recv: number;
    [key: string]: number;
  };
  ip_info?: IpInfo;
  local_ipv6?: string;
}

export interface PlatformInfo {
  system: string;
  release: string;
  version: string;
  architecture: string;
  processor: string;
}

export interface SystemInfoData {
  cpu: CpuInfo | null;
  memory: MemoryInfo | null;
  disk: DiskInfo[] | null;
  network: NetworkInfo | null;
  platform: PlatformInfo;
}

export interface ProcessorInfo {
  name: string;
  manufacturer: string;
  cores: number;
  logical_processors: number;
  generation?: string;
  codename?: string;
}

export interface GpuInfo {
  name: string;
  driver_version: string;
  status: string;
  adapter_ram: number;
}

export interface MotherboardInfo {
  manufacturer: string;
  product: string;
  serial_number: string;
}

export interface HardwareInfo {
  gpu: GpuInfo[];
  motherboard: MotherboardInfo;
  processor: ProcessorInfo;
}

export type ThemeMode = 'light' | 'dark';

export interface ThemeContextType {
  theme: ThemeMode;
  toggleTheme: () => void;
}

export interface HistoricalDataPoint {
  timestamp: number;
  cpu_percent: number[];
  memory_percent: number;
  network_bytes_sent: number;
  network_bytes_recv: number;
}
