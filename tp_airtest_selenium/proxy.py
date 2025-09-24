# -*- coding: utf-8 -*-

from selenium.webdriver import Chrome, ActionChains, Firefox, Remote
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from airtest.core.settings import Settings as ST
from airtest.core.helper import logwrap
from airtest import aircv
from airtest.core.cv import Template
from tp_airtest_selenium.utils.airtest_api import loop_find, try_log_screen, set_step_log, set_step_traceback
from tp_airtest_selenium.exceptions import IsNotTemplateError
from airtest.aircv import get_resolution
from pynput.mouse import Controller, Button
from airtest.core.error import TargetNotFoundError
from airtest.aircv.cal_confidence import cal_rgb_confidence
from .utils.serial_utils import SerialManager
from .utils.network_utils import WifiManager, get_ip_address, ping
import selenium
import os
import time
import sys
import numpy as np
import json
import cv2

from airtest import aircv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions.wheel_input import ScrollOrigin

class WebChrome(Chrome):

    def __init__(self, executable_path="chromedriver", port=0,
                 options=None, service=None, keep_alive=None, service_args=None,
                 desired_capabilities=None, service_log_path=None,
                 chrome_options=None):
        if "darwin" in sys.platform:
            os.environ['PATH'] += ":/Applications/AirtestIDE.app/Contents/Resources/selenium_plugin"
        if selenium.__version__ >= "4.10.0":
            if port != 0 or service_args != None or desired_capabilities != None or chrome_options != None or service_log_path != None:
                print("Warning: 'Valid parameters = options, service, keep_alive'.")
            super(WebChrome, self).__init__(options=options, service=service,
                                            keep_alive=keep_alive)
        else:
            super(WebChrome, self).__init__(chrome_options=chrome_options, executable_path=executable_path,
                                            port=port, options=options, service_args=service_args,
                                            service_log_path=service_log_path,
                                            desired_capabilities=desired_capabilities)
        self.father_number = {0: 0}
        self.action_chains = ActionChains(self)
        self.number = 0
        self.mouse = Controller()
        self.operation_to_func = {"elementsD": self.find_any_element, "xpath": self.find_element_by_xpath,
                                  "id": self.find_element_by_id,
                                  "name": self.find_element_by_name, "css": self.find_element_by_css_selector}
        self.settings = self._load_settings()
        # 多串口管理器字典，支持通过index访问
        self.serial_managers = {}
        self.wifi_manager = None

        # 初始化默认串口（index=0，来自setting.json）
        if self.settings.get("serial_port"):
            self.serial_managers[0] = SerialManager(self.settings["serial_port"], log_dir=f"{ST.PROJECT_ROOT}\\result")

        if self.settings.get("wireless_adapter"):
            try:
                self.wifi_manager = WifiManager(self.settings["wireless_adapter"])
            except Exception as e:
                print(f"初始化WifiManager失败: {e}")

    def _load_settings(self):
        """
        加载配置文件
        """
        try:
            with open(ST.PROJECT_ROOT + "/setting.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            print("未找到 setting.json 配置文件。")
            return {}

    def get_setting(self, key=None, default=None):
        """
        获取setting.json中的配置.
        :param key: 要获取的配置项的键，如果为None，则返回整个配置字典.
        :param default: 当键不存在时返回的默认值.
        :return: 配置值或整个配置字典.
        """
        if key:
            return self.settings.get(key, default)
        return self.settings

    def loop_find_element(self, func, text, by=By.ID, timeout=10, interval=0.5):
        """
        Loop to find the target web element by func.

        Args:
            func: function to find element
            text: param of function
            by: find an element given a By strategy
            timeout: time to find the element
            interval: interval between operation
        Returns:
            element that been found
        """
        start_time = time.time()
        while True:
            try:
                element = func(by, text)
            except NoSuchElementException:
                print("Element not found!")
                # 超时则raise，未超时则进行下次循环:
                if (time.time() - start_time) > timeout:
                    # try_log_screen(screen)
                    raise NoSuchElementException(
                        'Element %s not found in screen' % text)
                else:
                    time.sleep(interval)
            else:
                return element

    def loop_find_element_noExc(self, func, text, by=By.ID, timeout=3, interval=0.5):
        """
        Loop to find the target web element by func.

        Args:
            func: function to find element
            text: param of function
            by: find an element given a By strategy
            timeout: time to find the element
            interval: interval between operation
        Returns:
            element that been found
        """
        start_time = time.time()
        while True:
            try:
                element = func(by, text)
            except NoSuchElementException:
                print("Element not found!")
                # 超时则raise，未超时则进行下次循环:
                if (time.time() - start_time) > timeout:
                    # try_log_screen(screen)
                    return None
                else:
                    time.sleep(interval)
            else:
                print('element found')
                return element

    @logwrap
    def find_any_element(self, elementsD):
        """
        Find the web element by the indicated parameters.

        Args:
            elementsD: a dictionary with keys = by's, values=value
        Returns:
            Web element of current page.
        """
        web_element = None
        for key in elementsD:
            value = elementsD[key]
            print(value)
            if key.upper() == 'ID':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.ID)
            elif key.upper() == 'XPATH':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.XPATH)
            elif key.upper() == 'CSS':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.CSS_SELECTOR)
            elif key.upper() == 'NAME':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.NAME)
            elif key.upper() == 'LINKTEXT':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.LINK_TEXT)
            elif key.upper() == 'CLASSNAME':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.CLASS_NAME)
            elif key.upper() == 'PARTIALLINKTEXT':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.PARTIAL_LINK_TEXT)
            elif key.upper() == 'TAGNAME':
                web_element = self.loop_find_element_noExc(super().find_element, value, by=By.TAG_NAME)
            # check by position/ picture / visual testing
            if web_element is not None:
                break
        if web_element is not None:
            log_res = self._gen_screen_log(web_element)
            return Element(web_element, log_res)
        raise NoSuchElementException('Element not found in screen')

    def find_elements_by_class_name(self, name):
        """
        Finds elements by class name.

        :Args:
         - name: The class name of the elements to find.

        :Returns:
         - list of WebElement - a list with elements if any was found.  An
           empty list if not

        :Usage:
            elements = driver.find_elements_by_class_name('foo')
        """
        return self.find_elements(by=By.CLASS_NAME, value=name)

    def find_elements_by_xpath(self, xpath):
        """
        Finds multiple elements by xpath.

        :Args:
         - xpath - The xpath locator of the elements to be found.

        :Returns:
         - list of WebElement - a list with elements if any was found.  An
           empty list if not

        :Usage:
            elements = driver.find_elements_by_xpath("//div[contains(@class, 'foo')]")
        """
        return self.find_elements(by=By.XPATH, value=xpath)

    @logwrap
    def find_element_by_xpath(self, xpath):
        """
        Find the web element by xpath.

        Args:
            xpath: find the element by xpath.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebChrome, self).find_element, xpath, by=By.XPATH)
        # web_element = super(WebChrome, self).find_element_by_xpath(xpath)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_id(self, id):
        """
        Find the web element by id.

        Args:
            id: find the element by attribute id.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebChrome, self).find_element, id, by=By.ID)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_css_selector(self, css_selector):
        """
        Find the web element by css_selector.

        Args:
            css_selector: find the element by attribute css_selector.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebChrome, self).find_element, css_selector, by=By.CSS_SELECTOR)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_class_name(self, name):
        """
        Find the web element by name.

        Args:
            name: find the element by attribute name.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebChrome, self).find_element, name, by=By.CLASS_NAME)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_name(self, name):
        """
        Find the web element by name.

        Args:
            name: find the element by attribute name.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebChrome, self).find_element, name, by=By.NAME)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def switch_to_new_tab(self):
        """
        Switch to the new tab.
        """
        _father = self.number
        self.number = len(self.window_handles) - 1
        self.father_number[self.number] = _father
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def switch_to_previous_tab(self):
        """
        Switch to the previous tab(which to open current tab).
        """
        self.number = self.father_number[self.number]
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def airtest_touch(self, v):
        """
        Perform the touch action on the current page by image identification.

        Args:
            v: target to touch, either a Template instance or absolute coordinates (x, y)
        Returns:
            Finial position to be clicked.
        """
        if isinstance(v, Template):
            _pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
        else:
            screen = self.screenshot()
            try_log_screen(screen)
            _pos = v
        x, y = _pos
        # self.action_chains.move_to_element_with_offset(root_element, x, y)
        # self.action_chains.click()
        pos = self._get_left_up_offset()
        pos = (pos[0] + x, pos[1] + y)
        self._move_to_pos(pos)
        self._click_current_pos()
        time.sleep(1)
        return _pos

    @logwrap
    def assert_template(self, v, msg=""):
        """
        Assert target exists on the current page.

        Args:
            v: target to touch, either a Template instance
        Raise:
            AssertionError - if target not found.
        Returns:
            Position of the template.
        """
        if isinstance(v, Template):
            try:
                pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
            except TargetNotFoundError:
                raise AssertionError("Target template not found on screen.")
            else:
                return pos
        else:
            raise IsNotTemplateError("args is not a template")

    @logwrap
    def assert_exist(self, param, operation, msg=""):
        """
        Assert element exist.

        Args:
            operation: the method that to find the element.
            param: the param of method.
        Raise:
            AssertionError - if assertion failed.
        """
        try:
            func = self.operation_to_func[operation]
        except Exception:
            raise AssertionError("There was no operation: %s" % operation)
        try:
            func(param)
        except Exception as e:
            raise AssertionError("Target element not find.")
        
    @logwrap
    def assert_custom(self, param, log_msg=None, snap=None, msg=" "):
        """
        Assert Custom step execution.

        Args:
            param: the param of method.
            log: the output log of method.
        Raise:
            AssertionError - if assertion failed.
        """
        if isinstance(snap, dict):
            snapshot_path = os.path.join(ST.LOG_DIR, snap["screen"])
            screen = aircv.imread(snapshot_path,)
            try_log_screen(screen,snapshot_path)
        elif isinstance(snap, str):
            screen = aircv.imread(snap)
            try_log_screen(screen,snap)
        elif snap == True:
            self._gen_screen_log()

        if not (param) :
            if isinstance(log_msg, dict):
                log_msg = json.dumps(log_msg, indent=4, ensure_ascii=False)
            raise AssertionError("%s Custom step execution failed. Log: \n\n%s" % (msg, log_msg))
        else :
            pass

    @logwrap
    def assert_screen(self, old_screen_path, threshold=0.9, msg=" "):
        # 1. Take new screenshot
        new_screen = self.screenshot()
        self._gen_screen_log()
        # 2. Read old screenshot
        try:
            old_screen = aircv.imread(old_screen_path)
        except Exception as e:
            raise IOError("Failed to read old screen image at path: %s. Error: %s" % (old_screen_path, e))

        # 3. Compare them using the correct function: aircv.cal_rgb_confidence
        try:
            result = cal_rgb_confidence(old_screen, new_screen)
        except Exception as e:
            print("Could not compare images, likely due to different sizes. Error: %s" % e)
            raise AssertionError("%s Screens could not be compared due to different sizes." % msg)

        # 检查图片尺寸是否一致
        if old_screen.shape != new_screen.shape:
            raise ValueError("Images must have the same dimensions for comparison. "
                            "Old: %s, New: %s" % (old_screen.shape, new_screen.shape))
        # 生成并获取对比图的文件名
        self._generate_diff_image(old_screen, new_screen)

        if result < threshold:
            raise AssertionError("%s 图片差异过大:%s." % (msg, result))


    @logwrap
    def assert_two_picture(self, old_screen_path, new_screen_path,threshold=0.9, msg=""):
        try:
            old_screen = aircv.imread(old_screen_path)
            new_screen = aircv.imread(new_screen_path)
        except Exception as e:
            raise IOError("Failed to read old screen image at path: %s. Error: %s" % (old_screen_path, e))

        # 3. Compare them using the correct function: aircv.cal_rgb_confidence
        try:
            result = cal_rgb_confidence(old_screen, new_screen)
        except Exception as e:
            print("Could not compare images, likely due to different sizes. Error: %s" % e)
            raise AssertionError("%s Screens could not be compared)." % msg)

        # 检查图片尺寸是否一致
        if old_screen.shape != new_screen.shape:
            raise ValueError("Images must have the same dimensions for comparison. "
                            "Old: %s, New: %s" % (old_screen.shape, new_screen.shape))
        # 生成并获取对比图的文件名
        self._generate_diff_image(old_screen, new_screen)

        if result < threshold:
            raise AssertionError("%s 图片差异过大:%s." % (msg, result))

    def _generate_diff_image(self, old_screen, new_screen, diff_threshold=10):
        """
        [Optimized Version]
        Generates a side-by-side comparison image with differences highlighted.
        diff_threshold: 阈值越小越精确
        Returns the filename of the saved comparison image.
        """
        # 轻微高斯模糊减少噪点
        old_gray = cv2.cvtColor(old_screen, cv2.COLOR_BGR2GRAY)
        new_gray = cv2.cvtColor(new_screen, cv2.COLOR_BGR2GRAY)
        old_blur = cv2.GaussianBlur(old_gray, (5, 5), 0)
        new_blur = cv2.GaussianBlur(new_gray, (5, 5), 0)

        # 使用处理后的灰度图计算差异
        diff = cv2.absdiff(old_blur, new_blur)
        
        # 将差异大于可调阈值的像素变为白色，其余为黑色
        _, thresh = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)
        
        # 放大差异区域，使其更容易连接成块
        dilated = cv2.dilate(thresh, None, iterations=5)
        # 找到差异区域的轮廓
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 在新的彩色截图上绘制差异区域的矩形框
        new_screen_with_rects = new_screen.copy()
        for contour in contours:
            # 忽略过小的噪点轮廓
            if cv2.contourArea(contour) < 20:
                continue
            (x, y, w, h) = cv2.boundingRect(contour)
            cv2.rectangle(new_screen_with_rects, (x, y), (x + w, y + h), (0, 0, 255), 2)

        # 获取图片尺寸
        h, w, _ = old_screen.shape
        
        # 创建一个横向拼接的画布
        comparison_image = np.zeros((h + 40, w * 2, 3), dtype=np.uint8)
        
        # 粘贴旧图和新图
        comparison_image[40:, :w] = old_screen
        comparison_image[40:, w:] = new_screen_with_rects

        # 在图片上方添加标签
        cv2.putText(comparison_image, 'Before', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(comparison_image, 'New (Differences Highlighted)', (w + 10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # --- 优化点 4: 保存为无损 PNG 格式 ---
        png_file_name = str(int(time.time())) + '_compare.png'
        png_path = os.path.join(ST.LOG_DIR, png_file_name)
        cv2.imwrite(png_path, comparison_image, [cv2.IMWRITE_PNG_COMPRESSION, 0])
        try_log_screen(comparison_image, png_path)

    @logwrap
    def serial_wait_pattern(self, pattern, timeout=10,  index=0, msg="",):
        """
        断言在指定时间内，串口日志中出现了符合指定模式的内容。
        如果断言失败，会将最近的串口日志作为上下文记录在报告中。

        Args:
            pattern: 要在日志中搜索的正则表达式模式。
            timeout: 等待日志出现的最长秒数。
            msg: 自定义断言失败信息。
            index: 串口索引，默认0（使用setting.json中配置的串口）
        """
        serial_manager = self._get_serial_manager(index)
        if not serial_manager:
            set_step_log(f"串口索引 {index} 不可用，跳过等待模式")
            return False, None

        found, line = serial_manager.wait_for_log(pattern, duration=timeout)

        if found:
            # 断言成功，记录找到的行
            log_data = {"match": True, "line": line, "pattern": pattern, "serial_index": index}
            set_step_log(f"串口{index}找到表达式\'{pattern}\' \n {log_data}")
        else:
            set_step_log(f"串口{index}未等到表达式\'{pattern}\', {timeout}s已超时 \n")
        return found, line

    @logwrap
    def serial_open(self, port, baudrate=115200,index=0, timeout=1):
        """
        动态添加串口配置
        :param index: 串口索引，必须为正整数且不能是0（0为默认串口）
        :param port: 串口名称，如 'COM3' 或 '/dev/ttyUSB0'
        :param baudrate: 波特率，默认115200
        :param timeout: 超时时间，默认1秒
        :return: 添加成功返回True，失败返回False
        """
        if not isinstance(index, int) or index < 0:
            set_step_traceback(f"错误：串口索引必须为正整数 {index}")
            return False

        if index in self.serial_managers:
            print(f"警告：串口索引 {index} 已存在，将替换现有配置")
            self.serial_managers[index].serial_close()

        try:
            self.serial_managers[index] = SerialManager(port, baudrate, timeout, log_dir=f"{ST.PROJECT_ROOT}\\result")
            ret = self.serial_managers[index].serial_open()
            if ret:
                set_step_log(f"成功打开串口 {index}: {port} 波特率: {baudrate})")
            else:
                set_step_traceback(f"添加串口失败")
            return ret
        except Exception as e:
            set_step_traceback(f"添加串口失败: {e}")
            return False

    @logwrap
    def serial_close(self, index):
        """
        移除串口配置
        :param index: 要移除的串口索引
        :return: 移除成功返回True，失败返回False
        """
        if index not in self.serial_managers:
            set_step_traceback(f"警告：串口索引 {index} 不存在")
            return False

        try:
            self.serial_managers[index].serial_close()
            del self.serial_managers[index]
            set_step_log(f"成功移除串口 {index}")
            return True
        except Exception as e:
            set_step_traceback(f"移除串口失败: {e}")
            return False

    def list_serial_ports(self):
        """
        列出所有已配置的串口
        :return: 包含串口信息的字典
        """
        ports_info = {}
        for index, manager in self.serial_managers.items():
            is_open = manager.ser and manager.ser.is_open if manager else False
            ports_info[index] = {
                'port': manager.port if manager else 'Unknown',
                'baudrate': manager.baudrate if manager else 'Unknown',
                'is_open': is_open,
                'is_default': (index == 0)
            }
        return ports_info

    def _get_serial_manager(self, index=0):
        """
        获取指定索引的串口管理器
        :param index: 串口索引，默认0
        :return: SerialManager实例或None
        """
        if index not in self.serial_managers:
            if index == 0:
                print("错误：默认串口未配置")
            else:
                print(f"错误：串口索引 {index} 不存在，请先使用 add_serial_port() 添加")
            return None
        return self.serial_managers[index]

    @logwrap
    def serial_login(self, username="root", password=None,index=0, timeout=10):
        """
        登录设备串口.
        :param username: 登录用户名, 默认为'root'.
        :param password: 登录密码, 如为None则从setting.json获取serial_passwd
        :param timeout: 等待登录成功的超时时间.
        :param index: 串口索引，默认0（使用setting.json中配置的串口）
        :return: True表示登录成功, False表示失败.
        """
        serial_manager = self._get_serial_manager(index)
        if serial_manager:
            if not password:
                password = self.get_setting("serial_passwd")
            if not password:
                set_step_log(f"错误: 未在 setting.json 中找到serial_passwd字段（串口{index}）")
                return False
            result = serial_manager.serial_login(username, password, timeout)
            if result:
                set_step_log(f"串口{index}登录成功")
            else:
                set_step_log(f"串口{index}登录失败")
            return result
        else:
            set_step_traceback(f"串口索引 {index} 未初始化。")
            return False

    @logwrap
    def serial_send(self, command, index=0):
        """
        向串口发送命令
        :param command: 要发送的命令
        :param index: 串口索引，默认0（使用setting.json中配置的串口）
        """
        serial_manager = self._get_serial_manager(index)
        if serial_manager:
            serial_manager.send_cmd(command)
            logs = serial_manager.get_serial_log(duration=2)
            set_step_log(f"串口{index}发送命令: {command}\n\n{logs}")
        else:
            set_step_traceback(f"串口未打开，跳过发送：{command}")

    @logwrap
    def serial_get(self, lines=None, duration=None, index=0):
        """
        获取历史n行串口log或n秒串口日志
        :param lines: 获取最近n行日志
        :param duration: 获取最近n秒内的日志
        :param index: 串口索引，默认0（使用setting.json中配置的串口）
        :return: 日志字符串
        """
        serial_manager = self._get_serial_manager(index)
        if serial_manager:
            logs = serial_manager.get_serial_log(lines, duration)
            set_step_log(f"串口{index}日志:\n{logs}")
            return logs
        else:
            set_step_traceback(f"串口{index}未配置，无法获取Log")
            return ""

    @logwrap
    def serial_find(self, pattern, lines=None, duration=None, index=0):
        """
        检查串口日志中是否包含指定内容
        :param pattern: 要搜索的正则表达式模式
        :param lines: 搜索最近n行日志
        :param duration: 搜索最近n秒内的日志
        :param index: 串口索引，默认0（使用setting.json中配置的串口）
        :return: (找到状态, 匹配的日志行)
        """
        serial_manager = self._get_serial_manager(index)
        if serial_manager:
            ret, logs = serial_manager.search_log(pattern, lines, duration)
            if ret == True:
                set_step_log(f"串口{index}已找到包含{pattern}的logs:\n {logs}")
                return True, logs
            else:
                set_step_log(f"串口{index}未找到包含{pattern}的logs")
                return False, None
        else:
            set_step_traceback(f"串口{index}未配置，无法搜索日志")
            return False, None

    @logwrap
    def wifi_connect(self, ssid, password):
        """连接到指定的WiFi"""
        if self.wifi_manager:
            ret = self.wifi_manager.connect_wifi(ssid, password)
            if ret:
                set_step_log("已连接上无线:"+ssid)
            else:
                set_step_log("连接无线失败:"+ssid)
            return ret
        else:
            set_step_traceback("未在 setting.json 中配置无线网卡")
            return False

    @logwrap
    def wifi_disconnect(self):
        """断开WiFi连接"""
        if self.wifi_manager:
            ret = self.wifi_manager.disconnect_wifi()
            if ret:
                set_step_log("已成功断开无线")
            else:
                set_step_traceback("断开无线失败")
            return ret
        else:
            set_step_traceback("未在 setting.json 中配置无线网卡")
            return False

    @logwrap
    def get_ip(self, interface_type=None):
        """获取无线或有线网卡的IP地址"""
        if interface_type == "wired":
            interface_name = self.settings.get("wired_adapter")
        else:
            interface_name = self.settings.get("wireless_adapter")
            
        if interface_name:
            ip = get_ip_address(interface_name)
            set_step_log("当前IP: "+ip)
            return ip
        else:
            set_step_traceback(f"未在 setting.json 中配置 {interface_type} 网卡。")
            return None
    
    @logwrap
    def ping(self, ip_address, count=5):
        """Ping一个IP地址"""
        return ping(ip_address, count)


    @logwrap
    def get(self, address):
        """
        Access the web address.

        Args:
            address: the address that to accesss
        """
        super(WebChrome, self).get(address)
        time.sleep(2)

    @logwrap
    def back(self):
        """
        Back to last page.
        """
        super(WebChrome, self).back()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def forward(self):
        """
        Forward to next page.
        """
        super(WebChrome, self).forward()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def snapshot(self, filename=None):
        return self._gen_screen_log(filename=filename)
    
    @logwrap
    def full_snapshot(self, filename=None, msg="", quality=90, max_height=12000):
        """
        [Modified] Captures a full-page screenshot with a fallback stitching mechanism.
        """
        if ST.LOG_DIR is None:
            return None

        if not filename:
            png_file_name = f"{int(time.time())}_full.png"
            filepath = os.path.join(ST.LOG_DIR, png_file_name)
        else:
            filepath = os.path.join(ST.LOG_DIR, filename)

        # Phase 1: Capture images and get the scroll amount
        # **MODIFICATION**: Now unpacks two return values
        image_parts, scroll_amount_used = self._scroll_and_capture()

        if not image_parts:
            set_step_log("Error: image parts is NULL.")
            return None

        if len(image_parts) == 1:
            final_image = image_parts[0]
        else:
            # **MODIFICATION**: Implement fallback logic
            # Step 1: Try the primary (more accurate) anchor-based method first
            detected_footer_height = self._detect_footer_height(image_parts[0], image_parts[1])
            final_image = self._stitch_images_with_anchor(image_parts,detected_footer_height)
            # Step 2: If the primary method fails, use the fallback scroll-based method
            if final_image is None:
                final_image = self._stitch_images_by_scroll(image_parts, scroll_amount_used, detected_footer_height)
                
            #     # If it fails, dynamically detect the footer

        # Phase 4: Save and Log the final result
        if final_image is not None:
            cv2.imwrite(filepath, final_image)
            try_log_screen(final_image, filepath)
            return {"screen": filepath}
        else:
            set_step_log("Error: Stitching failed with both primary and fallback methods.")
        
    def _scroll_and_capture(self, scroll_amount=0.25, post_scroll_delay=0.8):
        """
        [Modified] Scrolls through the page and captures screenshots.
        
        Returns:
            tuple: A tuple containing (list_of_images, scroll_amount_pixels).
        """
        self.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.1)

        viewport_h_js = self.execute_script("return window.innerHeight")
        viewport_w_pixels = self.get_window_size()['width']
        
        saved_screenshot = []
        last_screenshot_data = None
        
        scroll_amount = int(viewport_h_js * scroll_amount)
        
        for i in range(30):
            current_screenshot_data = self.screenshot()

            if last_screenshot_data is not None and np.array_equal(last_screenshot_data, current_screenshot_data):
                break

            saved_screenshot.append(current_screenshot_data)
            last_screenshot_data = current_screenshot_data
            
            scroll_origin = ScrollOrigin.from_viewport(int(viewport_w_pixels / 2), int(viewport_h_js * 4 / 5))
            ActionChains(self).scroll_from_origin(scroll_origin, 0, scroll_amount).perform()
            
            time.sleep(post_scroll_delay)
        
        return saved_screenshot, scroll_amount

    def _stitch_images_with_anchor(self, images, footer_height):
        """
        结合页脚检测，使用内容区域最底部、上移5像素的中心区域锚点来拼接图像。
        """
        if not images or len(images) < 2:
            return None

        try:
            stitched_image = images[0]

            for i in range(len(images) - 1):
                image_top = stitched_image
                image_bottom = images[i + 1]

                # 1. 精确计算内容区域的高度
                h_top, w_top, _ = image_top.shape
                content_area_h = h_top - footer_height - 3
                if content_area_h <= 60: # 内容区至少要比锚点+buffer高
                    print("内容区域过小，跳过锚点拼接。")
                    return None 

                content_top = image_top[:content_area_h, :]
                content_bottom = image_bottom[:content_area_h, :]
                
                # 2. 从内容区最底部上移几像素，并在此创建锚点
                
                anchor_y_end = int(content_area_h * 0.99)
                anchor_y_start = int(content_area_h * 0.80)

                anchor_x_start = int(w_top * 0.40)
                anchor_x_end = int(w_top * 0.60)
                
                anchor = content_top[anchor_y_start:anchor_y_end, anchor_x_start:anchor_x_end]

                # 3. 在下方图片的内容区域中寻找锚点
                result = cv2.matchTemplate(content_bottom, anchor, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                print(f"V5锚点法匹配度 ({max_val:.4f})。，{max_loc[1]}")
                # 4. 检查匹配质量
                if max_val < 0.95:
                    print(f"V5锚点法匹配度 ({max_val:.4f}) 过低，中止。")
                    return None

                # 5. 精确拼接
                top_part_to_keep = image_top[:anchor_y_end, :]
                match_y_end_in_bottom = max_loc[1] + (anchor_y_end - anchor_y_start)
                bottom_part_to_keep = image_bottom[match_y_end_in_bottom:, :]
                stitched_image = np.vstack((top_part_to_keep, bottom_part_to_keep))

            return stitched_image

        except Exception as e:
            print(f"V5锚点拼接过程中发生异常: {e}")
            return None

    def _stitch_images_by_scroll(self, images, scroll_amount, footer_height):
        """
        [最终优化版] 通过迭代拼接内容区域并智能处理最后一帧来构建完整页面截图。
        此版本专门优化了当页面滚动到底部，最后一次滚动高度不足 scroll_amount 的情况。
        """
        if not images or len(images) < 2 or scroll_amount <= 0:
            return None

        try:
            screenshot_h, _, _ = images[0].shape
            content_area_h = screenshot_h - footer_height - 5
            if content_area_h <= 0: return images[-1] # 如果没有内容区域，直接返回最后一张图

            stitched_content = images[0][:content_area_h, :]

            for i in range(1, len(images) - 1):
                current_content_area = images[i][:content_area_h, :]
                new_part = current_content_area[content_area_h - scroll_amount:, :]
                stitched_content = np.vstack((stitched_content, new_part))
            
            # 4. [末尾拼接] 特殊处理最后一张图，以应对滚动高度不足的情况
            last_image = images[-1]
            last_content_area = last_image[:content_area_h, :]
            
            # 从已拼接图像的底部取一个高度为50像素的锚点
            stitched_h, stitched_w, _ = stitched_content.shape
            anchor_height = 50
            # 确保锚点高度不超过已拼接高度
            if stitched_h < anchor_height:
                anchor_height = stitched_h
            
            anchor = stitched_content[stitched_h - anchor_height:, :]

            # 在最后一张截图的内容区域中寻找这个锚点
            result = cv2.matchTemplate(last_content_area, anchor, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            final_new_part = None
            # 如果找到了高可信度的匹配点
            if max_val > 0.9:
                # 新增的内容就是匹配点Y坐标 + 锚点高度之后的所有部分
                print(f"末帧锚点法匹配度 ({max_val:.4f}) 过低。")

                match_y = max_loc[1]
                final_new_part = last_content_area[match_y + anchor_height:, :]
            else:
                final_new_part = last_content_area[content_area_h - scroll_amount:, :]

            # 如果最后的新增部分有内容，则拼接到长图上
            if final_new_part.shape[0] > 0:
                stitched_content = np.vstack((stitched_content, final_new_part))

            # 5. 获取并拼接最终的页脚
            final_footer = images[-1][content_area_h:, :]
            final_image = np.vstack((stitched_content, final_footer))
            
            return final_image

        except Exception as e:
            print(f"基于滚动的拼接过程中发生异常: {e}")
            return None

    def _detect_footer_height(self, image1, image2, max_check_height=300):
        """
        Dynamically detects the height of a fixed footer by comparing two consecutive images.
        It compares the images from bottom to top.
        """
        h, w, _ = image1.shape
        # Limit the check to a reasonable height to avoid excessive computation
        check_height = min(h, max_check_height)

        for y in range(1, check_height):
            # Row index from the bottom
            row_y = h - y
            
            # Get the pixel rows from both images
            row1 = image1[row_y, :]
            row2 = image2[row_y, :]
            
            # If the rows are not identical, the footer ends at the previous row
            if not np.array_equal(row1, row2):
                footer_height = y - 1
                return footer_height
                
        # If the entire checked area is identical, assume it's all footer
        return check_height

    @logwrap
    def _gen_screen_log(self, element=None, filename=None, ):
        if ST.LOG_DIR is None:
            return None
        if not filename:
            png_file_name = str(int(time.time())) + '.png'
            png_path = os.path.join(ST.LOG_DIR, png_file_name)
            print("this is png path:", png_path)
            filename=png_path
        self.screenshot(filename)
        saved = {"screen": filename}
        if element:
            size = element.size
            location = element.location
            x = size['width'] / 2 + location['x']
            y = size['height'] / 2 + location['y']
            if "darwin" in sys.platform:
                x, y = x * 2, y * 2
            saved.update({"pos": [[x, y]]})
        return saved

    def screenshot(self, file_path=None):
        if file_path:
            try:
                self.save_screenshot(file_path)
            except:
                """
                   由于chromedriver版本升级，出现screenshot时句柄失效导致截图失败。
                   触发说明：driver.back()后调用截图。
                """
                print("Unable to capture screenshot.")
        else:
            if not ST.LOG_DIR:
                file_path = "temp.png"
            else:
                file_path = os.path.join(ST.LOG_DIR, "temp.png")
            try:
                self.save_screenshot(file_path)
            except:
                pass
            screen = aircv.imread(file_path)
            return screen

    def _get_left_up_offset(self):
        window_pos = self.get_window_position()
        window_size = self.get_window_size()
        mouse = Controller()
        screen = self.screenshot()
        screen_size = get_resolution(screen)
        offset = window_size["width"] - \
                 screen_size[0], window_size["height"] - screen_size[1]
        pos = (int(offset[0] / 2 + window_pos['x']),
               int(offset[1] + window_pos['y'] - offset[0] / 2))
        return pos

    def _move_to_pos(self, pos):
        self.mouse.position = pos

    def _click_current_pos(self):
        self.mouse.click(Button.left, 1)

    def to_json(self):
        # add this method for json encoder in logwrap
        return repr(self)


class WebRemote(Remote):

    def __init__(self, command_executor='http://127.0.0.1:4444/wd/hub',
                 desired_capabilities=None, browser_profile=None, proxy=None,
                 keep_alive=False, file_detector=None, options=None):

        if selenium.__version__ >= "4.10.0":
            if desired_capabilities != None or browser_profile != None or proxy != None:
                print("Warning: 'Valid parameters = command_executor, options, file_detector, keep_alive'.")
            super(WebRemote, self).__init__(command_executor=command_executor, options=options,
                                            file_detector=file_detector, keep_alive=keep_alive)
        else:
            super(WebRemote, self).__init__(command_executor=command_executor,
                                            desired_capabilities=desired_capabilities, browser_profile=browser_profile,
                                            proxy=proxy,
                                            keep_alive=keep_alive, file_detector=file_detector, options=options)
        self.father_number = {0: 0}
        self.action_chains = ActionChains(self)
        self.number = 0
        self.mouse = Controller()
        self.operation_to_func = {"xpath": self.find_element_by_xpath, "id": self.find_element_by_id,
                                  "name": self.find_element_by_name, "css": self.find_element_by_css_selector}

    def loop_find_element(self, func, text, by=By.ID, timeout=10, interval=0.5):
        """
        Loop to find the target web element by func.

        Args:
            func: function to find element
            text: param of function
            by: find an element given a By strategy
            timeout: time to find the element
            interval: interval between operation
        Returns:
            element that been found
        """
        start_time = time.time()
        while True:
            try:
                element = func(by, text)
            except NoSuchElementException:
                print("Element not found!")
                # 超时则raise，未超时则进行下次循环:
                if (time.time() - start_time) > timeout:
                    # try_log_screen(screen)
                    raise NoSuchElementException('Element %s not found in screen' % text)
                else:
                    time.sleep(interval)
            else:
                return element

    def find_elements_by_class_name(self, name):
        """
        Finds elements by class name.

        :Args:
         - name: The class name of the elements to find.

        :Returns:
         - list of WebElement - a list with elements if any was found.  An
           empty list if not

        :Usage:
            elements = driver.find_elements_by_class_name('foo')
        """
        return self.find_elements(by=By.CLASS_NAME, value=name)

    def find_elements_by_xpath(self, xpath):
        """
        Finds multiple elements by xpath.

        :Args:
         - xpath - The xpath locator of the elements to be found.

        :Returns:
         - list of WebElement - a list with elements if any was found.  An
           empty list if not

        :Usage:
            elements = driver.find_elements_by_xpath("//div[contains(@class, 'foo')]")
        """
        return self.find_elements(by=By.XPATH, value=xpath)

    @logwrap
    def find_element_by_xpath(self, xpath):
        """
        Find the web element by xpath.

        Args:
            xpath: find the element by xpath.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebRemote, self).find_element, xpath, by=By.XPATH)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_id(self, id):
        """
        Find the web element by id.

        Args:
            id: find the element by attribute id.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebRemote, self).find_element, id, by=By.ID)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_css_selector(self, css_selector):
        """
        Find the web element by css_selector.

        Args:
            css_selector: find the element by attribute css_selector.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebRemote, self).find_element, css_selector, by=By.CSS_SELECTOR)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_name(self, name):
        """
        Find the web element by name.

        Args:
            name: find the element by attribute name.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(WebRemote, self).find_element, name, by=By.NAME)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def switch_to_new_tab(self):
        """
        Switch to the new tab.
        """
        _father = self.number
        self.number = len(self.window_handles) - 1
        self.father_number[self.number] = _father
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def switch_to_previous_tab(self):
        """
        Switch to the previous tab(which to open current tab).
        """
        self.number = self.father_number[self.number]
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def airtest_touch(self, v):
        """
        Perform the touch action on the current page by image identification.

        Args:
            v: target to touch, either a Template instance or absolute coordinates (x, y)
        Returns:
            Finial position to be clicked.
        """
        if isinstance(v, Template):
            _pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
        else:
            _pos = v
        x, y = _pos
        # self.action_chains.move_to_element_with_offset(root_element, x, y)
        # self.action_chains.click()
        pos = self._get_left_up_offset()
        pos = (pos[0] + x, pos[1] + y)
        self._move_to_pos(pos)
        self._click_current_pos()
        time.sleep(1)
        return _pos

    @logwrap
    def assert_template(self, v, msg=""):
        """
        Assert target exists on the current page.

        Args:
            v: target to touch, either a Template instance
        Raise:
            AssertionError - if target not found.
        Returns:
            Position of the template.
        """
        if isinstance(v, Template):
            try:
                pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
            except TargetNotFoundError:
                raise AssertionError("Target template not found on screen.")
            else:
                return pos
        else:
            raise IsNotTemplateError("args is not a template")

    @logwrap
    def assert_exist(self, param, operation, msg=""):
        """
        Assert element exist.

        Args:
            operation: the method that to find the element.
            param: the param of method.
        Raise:
            AssertionError - if assertion failed.
        """
        try:
            func = self.operation_to_func[operation]
        except Exception:
            raise AssertionError("There was no operation: %s" % operation)
        try:
            func(param)
        except Exception as e:
            raise AssertionError("Target element not find.")
        
    @logwrap
    def assert_custom(self, param, log, msg=""):
        """
        Assert Custom step execution.

        Args:
            param: the param of method.
            log: the output log of method.
        Raise:
            AssertionError - if assertion failed.
        """
        if not (param) :
            raise AssertionError("Custom step execution failed. Log: \n\n%s" % log)
        else :
            self._gen_screen_log()

    @logwrap
    def get(self, address):
        """
        Access the web address.

        Args:
            address: the address that to accesss
        """
        super(WebRemote, self).get(address)
        time.sleep(2)

    @logwrap
    def back(self):
        """
        Back to last page.
        """
        super(WebRemote, self).back()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def forward(self):
        """
        Forward to next page.
        """
        super(WebRemote, self).forward()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def snapshot(self, filename=None):
        return self._gen_screen_log(filename=filename)

    @logwrap
    def _gen_screen_log(self, element=None, filename=None, ):
        if ST.LOG_DIR is None:
            return None
        if not filename:
            png_file_name = str(int(time.time())) + '.png'
            png_path = os.path.join(ST.LOG_DIR, png_file_name)
            print("this is png path:", png_path)
            filename=png_path
        self.screenshot(filename)
        saved = {"screen": filename}
        if element:
            size = element.size
            location = element.location
            x = size['width'] / 2 + location['x']
            y = size['height'] / 2 + location['y']
            if "darwin" in sys.platform:
                x, y = x * 2, y * 2
            saved.update({"pos": [[x, y]]})
        return saved

    def screenshot(self, file_path=None):
        if file_path:
            try:
                self.save_screenshot(file_path)
            except:
                """
                   由于chromedriver版本升级，出现screenshot时句柄失效导致截图失败。
                   触发说明：driver.back()后调用截图。
                """
                print("Unable to capture screenshot.")
        else:
            if not ST.LOG_DIR:
                file_path = "temp.png"
            else:
                file_path = os.path.join(ST.LOG_DIR, "temp.png")
            try:
                self.save_screenshot(file_path)
            except:
                pass
            screen = aircv.imread(file_path)
            return screen

    def _get_left_up_offset(self):
        window_pos = self.get_window_position()
        window_size = self.get_window_size()
        mouse = Controller()
        screen = self.screenshot()
        screen_size = get_resolution(screen)
        offset = window_size["width"] - \
                 screen_size[0], window_size["height"] - screen_size[1]
        pos = (int(offset[0] / 2 + window_pos['x']),
               int(offset[1] + window_pos['y'] - offset[0] / 2))
        return pos

    def _move_to_pos(self, pos):
        self.mouse.position = pos

    def _click_current_pos(self):
        self.mouse.click(Button.left, 1)

    def to_json(self):
        # add this method for json encoder in logwrap
        return repr(self)


class WebFirefox(Firefox):

    def __init__(self, firefox_profile=None, firefox_binary=None,
                 timeout=30, capabilities=None, proxy=None,
                 executable_path="geckodriver", options=None, service=None, keep_alive=None, firefox_options=None,
                 service_args=None, desired_capabilities=None, log_path=None):
        print("Please make sure your geckodriver is in your path before proceeding using this driver")
        if selenium.__version__ >= "4.10.0":
            if firefox_profile != None or firefox_binary != None or timeout != None or capabilities != None\
                    or proxy != None or executable_path != None or firefox_options != None or service_args!=None\
                    or desired_capabilities!=None or log_path!=None:
                print("Warning: 'Valid parameters = options, service, keep_alive'.")
            super(WebFirefox, self).__init__(options=options, service=service,
                                            keep_alive=keep_alive)
        else:
            super(WebFirefox, self).__init__(firefox_profile=firefox_profile, firefox_binary=firefox_binary,
                                             capabilities=capabilities, proxy=proxy,
                                             executable_path=executable_path, options=options,
                                             firefox_options=firefox_options,
                                             service_args=service_args, desired_capabilities=desired_capabilities,
                                             log_path=log_path)
        self.father_number = {0: 0}
        self.action_chains = ActionChains(self)
        self.number = 0
        self.mouse = Controller()
        self.operation_to_func = {"xpath": self.find_element_by_xpath, "id": self.find_element_by_id,
                                  "name": self.find_element_by_name, "css": self.find_element_by_css_selector}

    def loop_find_element(self, func, text, by=By.ID, timeout=10, interval=0.5):
        """
        Loop to find the target web element by func.

        Args:
            func: function to find element
            text: param of function
            by: find an element given a By strategy
            timeout: time to find the element
            interval: interval between operation
        Returns:
            element that been found
        """
        start_time = time.time()
        while True:
            try:
                element = func(by, text)
            except NoSuchElementException:
                print("Element not found!")
                # 超时则raise，未超时则进行下次循环:
                if (time.time() - start_time) > timeout:
                    # try_log_screen(screen)
                    raise NoSuchElementException('Element %s not found in screen' % text)
                else:
                    time.sleep(interval)
            else:
                return element

    def find_elements_by_xpath(self, xpath):
        """
        Finds multiple elements by xpath.

        :Args:
         - xpath - The xpath locator of the elements to be found.

        :Returns:
         - list of WebElement - a list with elements if any was found.  An
           empty list if not

        :Usage:
            elements = driver.find_elements_by_xpath("//div[contains(@class, 'foo')]")
        """
        return self.find_elements(by=By.XPATH, value=xpath)

    @logwrap
    def find_element_by_xpath(self, xpath):
        """
        Find the web element by xpath.

        Args:
            xpath: find the element by xpath.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(Firefox, self).find_element, xpath, by=By.XPATH)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_id(self, id):
        """
        Find the web element by id.

        Args:
            id: find the element by attribute id.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(Firefox, self).find_element, id, by=By.ID)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_css_selector(self, css_selector):
        """
        Find the web element by css_selector.

        Args:
            css_selector: find the element by attribute css_selector.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(Firefox, self).find_element, css_selector, by=By.CSS_SELECTOR)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def find_element_by_name(self, name):
        """
        Find the web element by name.

        Args:
            name: find the element by attribute name.
        Returns:
            Web element of current page.
        """
        web_element = self.loop_find_element(super(Firefox, self).find_element, name, by=By.NAME)
        log_res = self._gen_screen_log(web_element)
        return Element(web_element, log_res)

    @logwrap
    def switch_to_new_tab(self):
        """
        Switch to the new tab.
        """
        _father = self.number
        self.number = len(self.window_handles) - 1
        self.father_number[self.number] = _father
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def switch_to_previous_tab(self):
        """
        Switch to the previous tab(which to open current tab).
        """
        self.number = self.father_number[self.number]
        self.switch_to.window(self.window_handles[self.number])
        self._gen_screen_log()
        time.sleep(0.5)

    @logwrap
    def airtest_touch(self, v):
        """
        Perform the touch action on the current page by image identification.

        Args:
            v: target to touch, either a Template instance or absolute coordinates (x, y)
        Returns:
            Finial position to be clicked.
        """
        if isinstance(v, Template):
            _pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
        else:
            _pos = v
        x, y = _pos
        # self.action_chains.move_to_element_with_offset(root_element, x, y)
        # self.action_chains.click()
        pos = self._get_left_up_offset()
        pos = (pos[0] + x, pos[1] + y)
        self._move_to_pos(pos)
        self._click_current_pos()
        time.sleep(1)
        return _pos

    @logwrap
    def assert_template(self, v, msg=""):
        """
        Assert target exists on the current page.

        Args:
            v: target to touch, either a Template instance
        Raise:
            AssertionError - if target not found.
        Returns:
            Position of the template.
        """
        if isinstance(v, Template):
            try:
                pos = loop_find(v, timeout=ST.FIND_TIMEOUT, driver=self)
            except TargetNotFoundError:
                raise AssertionError("Target template not found on screen.")
            else:
                return pos
        else:
            raise IsNotTemplateError("args is not a template")

    @logwrap
    def assert_exist(self, param, operation, msg=""):
        """
        Assert element exist.

        Args:
            operation: the method that to find the element.
            param: the param of method.
        Raise:
            AssertionError - if assertion failed.
        """
        try:
            func = self.operation_to_func[operation]
        except Exception:
            raise AssertionError("There was no operation: %s" % operation)
        try:
            func(param)
        except Exception as e:
            raise AssertionError("Target element not find.")

    @logwrap
    def assert_custom(self, param, log, msg=""):
        """
        Assert Custom step execution.

        Args:
            param: the param of method.
            log: the output log of method.
        Raise:
            AssertionError - if assertion failed.
        """
        if not (param) :
            raise AssertionError("Custom step execution failed. Log: \n\n%s" % log)
        else :
            self._gen_screen_log()

    @logwrap
    def get(self, address):
        """
        Access the web address.

        Args:
            address: the address that to accesss
        """
        super(WebFirefox, self).get(address)
        time.sleep(2)

    @logwrap
    def back(self):
        """
        Back to last page.
        """
        super(WebFirefox, self).back()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def forward(self):
        """
        Forward to next page.
        """
        super(WebFirefox, self).forward()
        self._gen_screen_log()
        time.sleep(1)

    @logwrap
    def snapshot(self, filename=None):
        self._gen_screen_log(filename=filename)

    @logwrap
    def _gen_screen_log(self, element=None, filename=None, ):
        if ST.LOG_DIR is None:
            return None
        if not filename:
            png_file_name = str(int(time.time())) + '.png'
            png_path = os.path.join(ST.LOG_DIR, png_file_name)
            print("this is png path:", png_path)
            filename=png_path
        self.screenshot(filename)
        saved = {"screen": filename}
        if element:
            size = element.size
            location = element.location
            x = size['width'] / 2 + location['x']
            y = size['height'] / 2 + location['y']
            if "darwin" in sys.platform:
                x, y = x * 2, y * 2
            saved.update({"pos": [[x, y]]})
        return saved

    def screenshot(self, file_path=None):
        if file_path:
            try:
                self.save_screenshot(file_path)
            except:
                """
                   由于chromedriver版本升级，出现screenshot时句柄失效导致截图失败。
                   触发说明：driver.back()后调用截图。
                """
                print("Unable to capture screenshot.")
        else:
            if not ST.LOG_DIR:
                file_path = "temp.png"
            else:
                file_path = os.path.join(ST.LOG_DIR, "temp.png")
            try:
                self.save_screenshot(file_path)
            except:
                pass
            screen = aircv.imread(file_path)
            return screen

    def _get_left_up_offset(self):
        window_pos = self.get_window_position()
        window_size = self.get_window_size()
        mouse = Controller()
        screen = self.screenshot()
        screen_size = get_resolution(screen)
        offset = window_size["width"] - \
                 screen_size[0], window_size["height"] - screen_size[1]
        pos = (int(offset[0] / 2 + window_pos['x']),
               int(offset[1] + window_pos['y'] - offset[0] / 2))
        return pos

    def _move_to_pos(self, pos):
        self.mouse.position = pos

    def _click_current_pos(self):
        self.mouse.click(Button.left, 1)

    def to_json(self):
        # add this method for json encoder in logwrap
        return repr(self)


class Element(WebElement):

    def __init__(self, _obj, log):
        if selenium.__version__ >= "4.1.2":
            super(Element, self).__init__(parent=_obj._parent, id_=_obj._id)
        else:
            super(Element, self).__init__(parent=_obj._parent, id_=_obj._id, w3c=_obj._w3c)
        self.res_log = log

    def click(self):
        super(Element, self).click()
        time.sleep(0.5)
        return self.res_log

    def send_keys(self, text, keyborad=None):
        if keyborad:
            super(Element, self).send_keys(text, keyborad)
        else:
            super(Element, self).send_keys(text)
        time.sleep(0.5)
        return self.res_log
