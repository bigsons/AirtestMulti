# tp_airtest_selenium/utils/network_utils.py
import pywifi
from pywifi import const
import time
import subprocess
import platform
import psutil

class WifiManager:
    def __init__(self, interface_name):
        self.wifi = pywifi.PyWiFi()
        self.iface = self.wifi.interfaces()[0] # 默认使用第一个无线网卡
        for iface in self.wifi.interfaces():
            if iface.name() == interface_name:
                self.iface = iface
                break
    
    def connect_wifi(self, ssid, password):
        """连接WiFi"""
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

def get_ip_address(interface_name):
    """获取指定网络接口的IP地址"""
    try:
        addrs = psutil.net_if_addrs()
        if interface_name in addrs:
            for addr in addrs[interface_name]:
                if addr.family == 2: # AF_INET (IPv4)
                    return addr.address
    except Exception as e:
        print(f"获取IP地址失败: {e}")
    return None

def ping(ip_address, count=4):
    """Ping 指定的IP地址"""
    param = '-n' if platform.system().lower() == 'windows' else '-c'
    command = ['ping', param, str(count), ip_address]
    try:
        output = subprocess.check_output(command)
        print(output.decode('utf-8'))
        return True
    except subprocess.CalledProcessError:
        print(f"Ping {ip_address} 失败")
        return False