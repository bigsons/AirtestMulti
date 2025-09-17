# tp_airtest_selenium/utils/network_utils.py
import pywifi
from pywifi import const
import time
import subprocess
import platform
import psutil
import socket
import re

class WifiManager:
    def __init__(self, interface_name):
        self.wifi = pywifi.PyWiFi()
        self.iface = self.wifi.interfaces()[0] # 默认使用第一个无线网卡
        for iface in self.wifi.interfaces():
            if iface.name() == interface_name:
                self.iface = iface
                break

    def connect_wifi(self, ssid, password):
        """
        连接WiFi
        """
        self.iface.disconnect()
        time.sleep(1)
        profile = pywifi.Profile()
        profile.ssid = ssid
        profile.auth = const.AUTH_ALG_OPEN
        profile.akm.append(const.AKM_TYPE_WPA2PSK)
        profile.cipher = const.CIPHER_TYPE_CCMP
        profile.key = password

        self.iface.remove_all_network_profiles()
        tmp_profile = self.iface.add_network_profile(profile)

        self.iface.connect(tmp_profile)

        # 检查连接状态
        for _ in range(10):
            if self.iface.status() == const.IFACE_CONNECTED:
                print(f"成功连接到 WiFi: {ssid}")
                return True
            time.sleep(1)
        print(f"连接 WiFi 失败: {ssid}")
        return False

    def disconnect_wifi(self):
        """断开WiFi连接"""
        self.iface.disconnect()
        if self.iface.status() in [const.IFACE_DISCONNECTED, const.IFACE_INACTIVE]:
            print("WiFi 已断开")
            return True
        else:
            print("WiFi 断开失败")
            return False


# 补充一些其他功能
def get_ip_address(interface_name):
    """
    获取指定网络接口的IP地址
    """
    try:
        addrs = psutil.net_if_addrs()
        if interface_name in addrs:
            for addr in addrs[interface_name]:
                if addr.family == 2: # AF_INET (IPv4)
                    return addr.address
    except Exception as e:
        print(f"获取IP地址失败: {e}")
    return None

def ping(ip_address, count=4, interface_name=None):
    """
    Ping 指定的IP地址，并返回成功状态和丢包率
    """
    # 检查是否为Windows系统
    if platform.system().lower() != 'windows':
        try:
            result = subprocess.run(['ping', '-c', str(count), ip_address], check=True)
            return {"success": result.returncode == 0, "packet_loss": 0 if result.returncode == 0 else 1.0, "raw_output": ""}
        except Exception as e:
             return {"success": False, "packet_loss": 1.0, "raw_output": str(e)}

    # Windows 平台的详细实现
    command = ['ping', '-n', str(count)]
    if interface_name:
        source_ip = get_ip_address(interface_name)
        if source_ip:
            command.extend(['-S', source_ip])
        else:
            print(f"警告: 无法获取接口 '{interface_name}' 的IP地址，将使用默认接口。")
    command.append(ip_address)

    try:
        print(f"正在执行命令: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        output_str = result.stdout + result.stderr
        print(output_str)

        packet_loss = 1.0  # 默认为100%丢包

        loss_match = re.search(r"Lost = \d+ \((\d+)% loss\)", output_str)
        if loss_match:
            packet_loss = float(loss_match.group(1)) / 100.0

        # 在Windows上，即使有丢包，只要不是100%丢包，通常也认为是可以通信的
        success = packet_loss == 0.0
        return {"success": success, "packet_loss": packet_loss, "raw_output": output_str}

    except Exception:
        error_msg = "错误: 'ping' 命令未找到。请确保它在系统的PATH中。"
        print(error_msg)
        return {"success": False, "packet_loss": 1.0, "raw_output": error_msg}


# 常用的端口列表：Web管理界面（80/443端口）、FTP服务（21端口）、SSH（22端口）
def check_port(host, port, timeout=3):
    """
    检查远程主机的特定TCP端口是否开放.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((host, port))
        print(f"端口 {host}:{port} 是开放的。")
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        print(f"端口 {host}:{port} 是关闭的或无响应。")
        return False
