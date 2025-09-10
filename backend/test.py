import pythoncom
import wmi

def test_gpu_info():
    """Test what WMI returns for GPU information"""
    try:
        pythoncom.CoInitialize()
        wmi_instance = wmi.WMI()

        print("=== VIDEO CONTROLLERS ===")
        for gpu in wmi_instance.Win32_VideoController():
            print(f"Name: {gpu.Name}")
            print(f"Driver Version: {gpu.DriverVersion}")
            print(f"Status: {gpu.Status}")
            print(f"Adapter RAM: {gpu.AdapterRAM}")
            if gpu.AdapterRAM:
                print(f"Adapter RAM (GB): {gpu.AdapterRAM / (1024 ** 3):.2f}")
            else:
                print("Adapter RAM: None or 0")
            print("Caption:", getattr(gpu, 'Caption', 'N/A'))
            print("Description:", getattr(gpu, 'Description', 'N/A'))
            print("Adapter Compatibility:", getattr(gpu, 'AdapterCompatibility', 'N/A'))
            print("Video Mode Description:", getattr(gpu, 'VideoModeDescription', 'N/A'))
            print("=" * 50)

    except Exception as e:
        print(f"Error: {e}")

def test_nvidia_memory():
    """Test NVIDIA GPU memory detection"""
    try:
        import pynvml

        print("=== NVIDIA GPU MEMORY ===")
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        print(f"Found {device_count} NVIDIA GPU(s)")

        for i in range(device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(handle)
            # Handle both string and bytes
            if isinstance(name, bytes):
                name = name.decode('utf-8')
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)

            print(f"GPU {i}: {name}")
            print(f"  Total Memory: {info.total / (1024 ** 3):.2f} GB")
            print(f"  Used Memory: {info.used / (1024 ** 3):.2f} GB")
            print(f"  Free Memory: {info.free / (1024 ** 3):.2f} GB")

        pynvml.nvmlShutdown()

    except ImportError:
        print("pynvml not available")
    except Exception as e:
        print(f"NVIDIA memory test error: {e}")

if __name__ == "__main__":
    test_gpu_info()
    print("\n")
    test_nvidia_memory()
