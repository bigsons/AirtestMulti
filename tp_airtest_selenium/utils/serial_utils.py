# -*- coding: utf-8 -*-
# tp_airtest_selenium/utils/serial_utils.py

import serial
import time
import re
import os
import threading
from collections import deque
from queue import Queue, Empty
from datetime import datetime, timedelta

class SerialManager:
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

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_filename = f"serial_{port.replace('/', '_').replace('.', '_')}.log"
        self.log_file = os.path.join(log_dir, log_filename)
        
        self.log_buffer = deque(maxlen=20000)
        self.read_queue = Queue()
        self.is_reading = False
        self.read_thread = None
        self.write_lock = threading.Lock()
        self.log_write_lock = threading.Lock() 

    def _read_data_thread(self):
        """后台线程，持续读取串口数据，添加时间戳，并存入队列、缓冲区和文件。"""
        while self.is_reading and self.ser and self.ser.is_open:
            try:
                line_bytes = self.ser.readline()
                if line_bytes:
                    timestamp = datetime.now()
                    try:
                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                    except UnicodeDecodeError:
                        line = f"[DECODE_ERROR] {line_bytes.hex()}"
                    
                    if line:
                        log_entry = (timestamp, f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {line}")
                        self.log_buffer.append(log_entry)
                        self.read_queue.put(log_entry[1])
                        self._write_to_log_file(log_entry[1])
            except (serial.SerialException, OSError):
                print(f"从串口 {self.port} 读取数据时出错。停止线程。")
                self.is_reading = False
                break

    def serial_open(self):
        """打开串口，并启动后台日志记录线程。日志以追加模式写入。"""
        if self.ser and self.ser.is_open:
            print(f"串口 {self.port} 已经打开。")
            return True
        try:
            # 使用 with open 和锁确保文件操作安全
            self._write_to_log_file(f"\n--- Serial Session Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
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
            self._write_to_log_file(f"--- Serial Session Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        self.read_thread = None

    def _read_from_queue(self, timeout=1):
        """从队列中读取一行数据，带超时机制。"""
        try:
            return self.read_queue.get(timeout=timeout)
        except Empty:
            return None
            
    def _clear_read_queue(self):
        """清空读取队列中所有待处理的消息。"""
        while not self.read_queue.empty():
            try:
                self.read_queue.get_nowait()
            except Empty:
                break

    def serial_login(self, username, password, timeout=10):
        """
        通过串口登录设备。会先检查是否已登录，如果已登录则直接返回True。
        """
        if not (self.ser and self.ser.is_open):
            if not self.serial_open():
                return False
        
        self._clear_read_queue()

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
        
        self.send_cmd_quiet("") 
        if wait_for_patterns(r"(root@|#\s*$)", 2):
            return True

        print("串口未登录，开始执行登录流程...")
        self._clear_read_queue()
        self.send_cmd_quiet("")
        if not wait_for_patterns(r"login:|username:", 5):
            print("超时：未检测到串口登录提示。")
            return False
        
        self.send_cmd_quiet(username)
        print(f"检测到串口登录提示，已输入用户名: {username}")

        if not wait_for_patterns(r"password:", 5):
            print("超时：未检测到密码提示。")
            return False

        self.send_cmd_quiet(password)
        print("检测到串口输入密码提示，已输入。")

        if wait_for_patterns(r"busybox|root@|#\s*$", 5): 
            print("登录成功！")
            return True

        print("超时：串口登录后未检测到成功标志。")
        return False

    def send_cmd_quiet(self, command):
        if not (self.ser and self.ser.is_open):
            if not self.serial_open():
                return False
        full_command = command + '\n'
        with self.write_lock:
            self.ser.write(full_command.encode('utf-8'))

    def send_cmd(self, command):
        """线程安全地向串口发送命令，并记录到日志。"""
        if not (self.ser and self.ser.is_open):
            if not self.serial_open():
                return False
        full_command = command + '\n'
        with self.write_lock:
            self.ser.write(full_command.encode('utf-8'))
            timestamp = datetime.now()
            log_entry_str = f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] ===》 {command}"
            log_entry_tuple = (timestamp, log_entry_str)
            self.log_buffer.append(log_entry_tuple)
            self._write_to_log_file(log_entry_str)
            print(f"已发送命令: {command}")
    
    def add_marker_to_log(self, message):
        """
        向串口日志文件和内存缓冲区中写入一条自定义的标记信息。
        """
        timestamp = datetime.now()
        log_entry_str = f"[{timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [MARKER] --- {message} ---"
        log_entry_tuple = (timestamp, log_entry_str)
        print(f"写入日志标记: {message}")
        self.log_buffer.append(log_entry_tuple)
        self._write_to_log_file(log_entry_str)

    def get_serial_log(self, lines=None, duration=None):
        """
        获取串口日志并以单个字符串的形式返回，每行以'\\n'分隔。
        可以指定获取最近的行数，或获取过去一段时间内的日志。
        """
        log_list = []
        if duration:
            log_list = self._read_log_duration_internal(duration)
        elif lines:
            log_list = self._read_log_lines_internal(lines)
        
        return "\n".join(log_list)

    def _read_log_lines_internal(self, lines=10):
        """从内存缓冲区读取最近的N行日志，返回列表。"""
        buffer_copy = list(self.log_buffer)
        # 从元组中只返回格式化后的字符串
        return [item[1] for item in buffer_copy[-lines:]]

    def _read_log_duration_internal(self, duration=5):
        """
        从内存缓冲区中筛选出在过去`duration`秒内记录的所有日志。
        """
        now = datetime.now()
        time_threshold = now - timedelta(seconds=duration)
        
        # 从右向左遍历，效率更高
        log_data = []
        buffer_copy = list(self.log_buffer)
        for timestamp, log_str in reversed(buffer_copy):
            if timestamp >= time_threshold:
                log_data.append(log_str)
            else:
                # 因为日志是按时间顺序记录的，一旦时间戳早于阈值，就可以停止搜索
                break
        
        return list(reversed(log_data)) # 保持时间顺序

    def search_log(self, pattern, lines=None, duration=None):
        """在日志中搜索指定模式。"""
        log_to_search = []
        if lines:
            log_to_search = self._read_log_lines_internal(lines)
        elif duration:
            log_to_search = self._read_log_duration_internal(duration)
        else:
            # 默认搜索整个缓冲区
            log_to_search = [item[1] for item in list(self.log_buffer)]

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
        """将单行日志写入文件（线程安全）。"""
        with self.log_write_lock:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except Exception as e:
                print(f"写入日志文件失败: {e}")