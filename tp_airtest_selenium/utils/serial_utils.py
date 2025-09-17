# tp_airtest_selenium/utils/serial_utils.py
import serial
import time
import re
from collections import deque
import threading
from queue import Queue, Empty

class SerialManager:
    def __init__(self, port, baudrate=115200, timeout=1):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.log_file = f"{port.replace('/', '_').replace('.', '_')}_log.txt"
        self.log_buffer = deque(maxlen=10000)  # 保存最近10000行日志
        self.read_queue = Queue()
        self.is_reading = False
        self.read_thread = None

    def _read_data_thread(self):
        """后台线程，持续读取串口数据并存入队列和文件"""
        while self.is_reading and self.ser and self.ser.is_open:
            try:
                line_bytes = self.ser.readline()
                if line_bytes:
                    line = line_bytes.decode('utf-8', errors='ignore').strip()
                    if line:
                        self.log_buffer.append(line)
                        self.read_queue.put(line)
                        self._write_to_log_file(line)
            except (serial.SerialException, OSError):
                print(f"从串口 {self.port} 读取数据时出错。停止线程。")
                self.is_reading = False
                break

    def open_serial(self):
        """打开串口，并启动后台日志记录线程"""
        if self.ser and self.ser.is_open:
            print(f"串口 {self.port} 已经打开。")
            return True
        try:
            # 每次打开时，清空旧的日志文件并写入时间戳
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write(f"--- Log started at {time.ctime()} ---\n")
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"串口 {self.port} 已成功打开。")
            self.is_reading = True
            self.read_thread = threading.Thread(target=self._read_data_thread)
            self.read_thread.daemon = True
            self.read_thread.start()
            return True
        except serial.SerialException as e:
            print(f"打开串口 {self.port} 失败: {e}")
            self.ser = None
            return False

    def _read_from_queue(self, timeout=1):
        """从队列中读取一行数据，带超时"""
        try:
            return self.read_queue.get(timeout=timeout)
        except Empty:
            return None

    def serial_login(self, username, password, timeout=10):
        """通过串口登录设备，现在使用队列来实时获取输出进行交互"""
        if not (self.ser and self.ser.is_open):
            if not self.open_serial():
                return False

        self.ser.write(b'\n')
        time.sleep(1)

        def wait_for_prompt(prompt, search_timeout):
            search_end_time = time.time() + search_timeout
            while time.time() < search_end_time:
                line = self._read_from_queue(timeout=1)
                if line:
                    print(f"串口输出: {line}")
                    if prompt in line.lower():
                        return True
            return False

        if not wait_for_prompt("login:", 5):
            print("超时：未检测到登录提示 (login:)。")
            return False

        self.ser.write((username + '\n').encode('utf-8'))
        print(f"检测到登录提示，已输入用户名: {username}")

        if not wait_for_prompt("password:", 5):
            print("超时：未检测到密码提示 (password:)。")
            return False

        self.ser.write((password + '\n').encode('utf-8'))
        print("检测到密码提示，已输入密码。")

        if wait_for_prompt("busybox", 5):
            print("登录成功！检测到 'BusyBox'。")
            return True

        print("超时：登录后未检测到 'BusyBox' 关键字。")
        return False

    def send_cmd(self, command):
        """发送命令到串口"""
        if not (self.ser and self.ser.is_open):
            if not self.open_serial():
                return
        full_command = command + '\n'
        self.ser.write(full_command.encode('utf-8'))
        print(f"已发送命令: {command}")

    def serial_close(self):
        """关闭串口并安全停止后台线程"""
        self.is_reading = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"串口 {self.port} 已关闭。")
        self.read_thread = None

    def read_log_lines(self, lines=10):
        """从内存缓冲区中读取最近的指定行数日志"""
        buffer_copy = list(self.log_buffer)
        return buffer_copy[-lines:]

    def read_log_duration(self, duration=5):
        """在指定时间内持续从队列中读取新产生的日志"""
        start_time = time.time()
        log_data = []
        while time.time() - start_time < duration:
            line = self._read_from_queue(timeout=0.1)
            if line:
                log_data.append(line)
        return log_data

    def search_log(self, pattern, lines=None, duration=None):
        """在日志中搜索指定模式"""
        log_to_search = []
        if lines:
            log_to_search = self.read_log_lines(lines)
        elif duration:
            log_to_search.extend(self.read_log_duration(duration))

        if not lines and not duration:
            # 如果没有指定行数或时长，则搜索整个内存缓冲区
            log_to_search = list(self.log_buffer)

        # 从最新的日志开始反向搜索，效率更高
        for line in reversed(log_to_search):
            if re.search(pattern, line):
                return True, line
        return False, None

    def _write_to_log_file(self, line):
        """将单行日志写入文件"""
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')