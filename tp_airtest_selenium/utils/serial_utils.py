# -*- coding: utf-8 -*-
# tp_airtest_selenium/utils/serial_utils.py

import serial
import time
import re
import os
import threading
from collections import deque
from queue import Queue, Empty
from datetime import datetime

class SerialManager:
    """
    一个增强的串口管理类，提供稳定的日志记录、线程安全的读写和健壮的交互功能。
    新增功能：登录状态检查、自定义日志标记、字符串格式的日志获取。
    """
    def __init__(self, port, baudrate=115200, timeout=1, log_dir="."):
        """
        初始化SerialManager。

        Args:
            port (str): 串口号 (例如: Windows上的 'COM3', Linux上的 '/dev/ttyUSB0').
            baudrate (int): 波特率.
            timeout (int): 读取超时时间 (秒).
            log_dir (str): 保存日志文件的目录路径.
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None

        # 确保日志目录存在
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 创建一个可读性强的日志文件名
        log_filename = f"serial_{port.replace('/', '_').replace('.', '_')}.log"
        self.log_file = os.path.join(log_dir, log_filename)
        
        self.log_buffer = deque(maxlen=10000)
        self.read_queue = Queue()
        self.is_reading = False
        self.read_thread = None
        self.write_lock = threading.Lock()

    def _read_data_thread(self):
        """后台线程，持续读取串口数据，添加时间戳，并存入队列、缓冲区和文件。"""
        while self.is_reading and self.ser and self.ser.is_open:
            try:
                line_bytes = self.ser.readline()
                if line_bytes:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    try:
                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                    except UnicodeDecodeError:
                        line = f"[DECODE_ERROR] {line_bytes.hex()}"
                    
                    if line:
                        log_entry = f"[{timestamp}] {line}"
                        self.log_buffer.append(log_entry)
                        self.read_queue.put(log_entry)
                        self._write_to_log_file(log_entry)
            except (serial.SerialException, OSError):
                print(f"从串口 {self.port} 读取数据时出错。停止线程。")
                self.is_reading = False
                break

    def open_serial(self):
        """打开串口，并启动后台日志记录线程。日志以追加模式写入。"""
        if self.ser and self.ser.is_open:
            print(f"串口 {self.port} 已经打开。")
            return True
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n--- Serial Session Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            print(f"串口 {self.port} 已成功打开。")
            
            self.is_reading = True
            self.read_thread = threading.Thread(target=self._read_data_thread, daemon=True)
            self.read_thread.start()
            return True
        except serial.SerialException as e:
            print(f"打开串口 {self.port} 失败: {e}")
            self.ser = None
            return False

    def serial_close(self):
        """关闭串口并安全停止后台线程，同时在日志中写入结束标记。"""
        if not self.is_reading and not (self.ser and self.ser.is_open):
            return
            
        self.is_reading = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2)
            
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"串口 {self.port} 已关闭。")
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"--- Serial Session Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        self.read_thread = None

    def _read_from_queue(self, timeout=1):
        """从队列中读取一行数据，带超时机制。"""
        try:
            return self.read_queue.get(timeout=timeout)
        except Empty:
            return None

    def serial_login(self, username, password, timeout=10):
        """
        通过串口登录设备。会先检查是否已登录，如果已登录则直接返回True。
        """
        if not (self.ser and self.ser.is_open):
            if not self.open_serial():
                return False
        
        while not self.read_queue.empty():
            self.read_queue.get_nowait()

        def wait_for_patterns(patterns, search_timeout):
            """通用的等待函数，用于查找匹配的模式。"""
            search_end_time = time.time() + search_timeout
            while time.time() < search_end_time:
                line = self._read_from_queue(timeout=1)
                if line:
                    print(f"串口输出: {line}")
                    if re.search(patterns, line, re.IGNORECASE):
                        return True
            return False
        
        # 发送一个空命令（回车），正常登录的shell会返回一个提示符
        self.send_cmd("") 
        # 等待2秒看是否能匹配到常见的shell提示符
        if wait_for_patterns(r"(root@|#\s*$)", 2): # 匹配如 'root@OpenWrt:~#' 或行尾的 '#'
            print("检测到已登录状态。")
            return True

        # 如果未登录，则执行完整的登录流程
        print("未检测到登录状态，开始执行登录流程...")
        if not wait_for_patterns(r"login:|username:", 5):
            print("超时：未检测到登录提示。")
            return False
        
        self.send_cmd(username)
        print(f"检测到登录提示，已输入用户名: {username}")

        if not wait_for_patterns(r"password:", 5):
            print("超时：未检测到密码提示。")
            return False

        self.send_cmd(password)
        print("检测到密码提示，已输入密码。")

        if wait_for_patterns(r"busybox|root@", 5):
            print("登录成功！")
            return True

        print("超时：登录后未检测到成功标志。")
        return False

    def send_cmd(self, command):
        """线程安全地向串口发送命令，并记录到日志。"""
        if not (self.ser and self.ser.is_open):
            print("串口未打开，无法发送命令。")
            return
            
        full_command = command + '\n'
        with self.write_lock:
            self.ser.write(full_command.encode('utf-8'))
            log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [CMD SENT] -> {command}"
            self.log_buffer.append(log_entry)
            self._write_to_log_file(log_entry)
            print(f"已发送命令: {command}")
    
    # --- 新增和修改的日志获取功能 ---
    
    def add_marker_to_log(self, message):
        """
        **新增功能**：向串口日志文件和内存缓冲区中写入一条自定义的标记信息。
        这对于在日志中标记测试脚本的关键步骤非常有用。
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        # 使用特殊标记让自定义信息在日志中更显眼
        log_entry = f"[{timestamp}] [MARKER] --- {message} ---"
        print(f"写入日志标记: {message}")
        self.log_buffer.append(log_entry)
        self._write_to_log_file(log_entry)

    def get_serial_log(self, lines=None, duration=None):
        """
        **修改功能**：获取串口日志并以单个字符串的形式返回，每行以'\\n'分隔。
        可以指定获取最近的行数，或在一段时间内持续收集。
        """
        log_list = []
        if duration:
            # 内部函数仍然返回列表
            log_list = self._read_log_duration_internal(duration)
        elif lines:
            # 内部函数仍然返回列表
            log_list = self._read_log_lines_internal(lines)
        
        return "\n".join(log_list)

    # 内部方法，保持返回列表，供 search_log 等高级功能使用
    def _read_log_lines_internal(self, lines=10):
        """从内存缓冲区读取日志，返回列表。"""
        buffer_copy = list(self.log_buffer)
        return buffer_copy[-lines:]

    def _read_log_duration_internal(self, duration=5):
        """在一段时间内收集日志，返回列表。"""
        start_time = time.time()
        log_data = []
        while time.time() - start_time < duration:
            line = self._read_from_queue(timeout=0.1)
            if line:
                log_data.append(line)
        return log_data

    def search_log(self, pattern, lines=None, duration=None):
        """在日志中搜索指定模式。"""
        log_to_search = []
        if lines:
            log_to_search = self._read_log_lines_internal(lines)
        elif duration:
            log_to_search.extend(self._read_log_duration_internal(duration))
        else:
            log_to_search = list(self.log_buffer)

        for line in reversed(log_to_search):
            if re.search(pattern, line):
                return True, line
        return False, None

    def wait_for_log(self, pattern, timeout=10):
        """实时等待，直到在串口输出中找到指定模式的内容。"""
        end_time = time.time() + timeout
        while time.time() < end_time:
            remaining_time = end_time - time.time()
            line = self._read_from_queue(timeout=max(0.1, min(1, remaining_time)))
            if line:
                if re.search(pattern, line):
                    print(f"成功匹配到日志: {line}")
                    return True, line
        print(f"超时({timeout}s): 未在日志中匹配到 '{pattern}'")
        return False, None

    def _write_to_log_file(self, line):
        """将单行日志写入文件。"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception as e:
            print(f"写入日志文件失败: {e}")