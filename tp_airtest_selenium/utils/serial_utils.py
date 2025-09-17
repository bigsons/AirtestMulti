# tp_airtest_selenium/utils/serial_utils.py
import serial
import time
import re
from collections import deque

class SerialManager:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.log_file = f"{port.replace('/', '_').replace('.', '_')}_log.txt"
        self.log_buffer = deque(maxlen=10000)  # 保存最近1000行日志

    def open_serial(self):
        """打开串口，并增加一个标志来避免重复打开"""
        if self.ser and self.ser.is_open:
            print(f"串口 {self.port} 已经打开。")
            return True
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"串口 {self.port} 已成功打开。")
            return True
        except serial.SerialException as e:
            print(f"打开串口 {self.port} 失败: {e}")
            self.ser = None # 确保失败后ser对象为None
            return False

    def serial_login(self, username, password, timeout=10):

        if not (self.ser and self.ser.is_open):
            print("串口未打开，正在尝试自动打开...")
            if not self.open_serial():
                print("自动打开串口失败，无法登录。")
                return False
        
        end_time = time.time() + timeout
        
        self.ser.write(b'\n')
        time.sleep(1)
        
        login_prompt_found = False
        while time.time() < end_time:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"串口输出: {line}")
                self._write_to_log_file(line) # 记录日志
            if "login:" in line.lower():
                self.ser.write((username + '\n').encode('utf-8'))
                print(f"检测到登录提示，已输入用户名: {username}")
                login_prompt_found = True
                break
        
        if not login_prompt_found:
            print("超时：未检测到登录提示 (login:)。")
            return False

        password_prompt_found = False
        while time.time() < end_time:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"串口输出: {line}")
                self._write_to_log_file(line)
            if "password:" in line.lower():
                self.ser.write((password + '\n').encode('utf-8'))
                print("检测到密码提示，已输入密码。")
                password_prompt_found = True
                break
        
        if not password_prompt_found:
            print("超时：未检测到密码提示 (password:)。")
            return False
            
        while time.time() < end_time:
            line = self.ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(f"串口输出: {line}")
                self._write_to_log_file(line)
            if "busybox" in line.lower():
                print("登录成功！检测到 'BusyBox'。")
                return True
        
        print("超时：登录后未检测到 'BusyBox' 关键字。")
        return False


    def send_cmd(self, command):
        """发送命令到串口 (自动打开串口)"""
        # +++ 新增：如果串口未打开，则尝试打开 +++
        if not (self.ser and self.ser.is_open):
            print("串口未打开，正在尝试自动打开...")
            if not self.open_serial():
                print("自动打开串口失败，无法发送命令。")
                return
        full_command = command + '\n'
        self.ser.write(full_command.encode('utf-8'))
        print(f"已发送命令: {command}")

    def serial_close(self):
        """关闭串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"串口 {self.port} 已关闭。")

    def read_log_lines(self, lines=10):
        """读取指定行数的日志"""
        log_data = []
        if self.ser and self.ser.is_open:
            for _ in range(lines):
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    log_data.append(line)
                    self._write_to_log_file(line)
                    self.log_buffer.append(line)
        return log_data

    def read_log_duration(self, duration=5):
        """在指定时间内持续读取日志"""
        log_data = []
        if self.ser and self.ser.is_open:
            start_time = time.time()
            while time.time() - start_time < duration:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    log_data.append(line)
                    self._write_to_log_file(line)
                    self.log_buffer.append(line)
        return log_data

    def search_log(self, pattern, lines=None, duration=None):
        """在日志中搜索指定模式"""
        log_to_search = []
        if lines:
            log_to_search = self.read_log_lines(lines)
        elif duration:
            log_to_search = self.read_log_duration(duration)
        
        for line in log_to_search:
            if re.search(pattern, line):
                return True, line 
        return False, None

    def _write_to_log_file(self, line):
        """将日志写入文件"""
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')