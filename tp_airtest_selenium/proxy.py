# -*- coding: utf-8 -*-

from selenium.webdriver import Chrome, ActionChains, Firefox, Remote
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from airtest.core.settings import Settings as ST
from airtest.core.helper import logwrap, log
from airtest import aircv
from airtest.core.cv import Template
from tp_airtest_selenium.utils.airtest_api import loop_find, try_log_screen
from tp_airtest_selenium.exceptions import IsNotTemplateError
from airtest.aircv import get_resolution
from pynput.mouse import Controller, Button
from airtest.core.error import TargetNotFoundError
from airtest.aircv.cal_confidence import cal_rgb_confidence, cal_ccoeff_confidence
import selenium
import os
import time
import sys

import json
from .utils.serial_utils import SerialManager
from .utils.network_utils import WifiManager, get_ip_address, ping

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
        self.serial_manager = None
        self.wifi_manager = None
        if self.settings.get("serial_port"):
            self.serial_manager = SerialManager(self.settings["serial_port"])
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
    def assert_custom(self, param, log_msg, msg=""):
        """
        Assert Custom step execution.

        Args:
            param: the param of method.
            log: the output log of method.
        Raise:
            AssertionError - if assertion failed.
        """
        if not (param) :
            if isinstance(log_msg, dict):
                log_msg = json.dumps(log_msg, indent=4, ensure_ascii=False)
            raise AssertionError("%s Custom step execution failed. Log: \n\n%s" % (msg, log_msg))
        else :
            self._gen_screen_log()

    @logwrap
    def assert_screen(self, old_screen_path, threshold=0.9, msg=""):
        # 1. Take new screenshot
        new_screen = self.screenshot()
        self._gen_screen_log()
        # 2. Read old screenshot
        try:
            old_screen = aircv.imread(old_screen_path)
        except Exception as e:
            raise IOError("Failed to read old screen image at path: %s. Error: %s" % (old_screen_path, e))

        # 3. Compare them using the correct function: aircv.cal_rgb_confidence
        #    注意: aircv.cal_rgb_confidence 要求两张图片尺寸完全一致
        #    在Web自动化场景中，只要浏览器窗口大小不变，截图尺寸就是一致的
        #
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
        #    注意: aircv.cal_rgb_confidence 要求两张图片尺寸完全一致
        #    在Web自动化场景中，只要浏览器窗口大小不变，截图尺寸就是一致的
        #
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
        import cv2
        import numpy as np

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
    def assert_serial_log(self, pattern, timeout=1, msg=""):
        """
        断言在指定时间内，串口日志中出现了符合指定模式的内容。
        如果断言失败，会将最近的串口日志作为上下文记录在报告中。

        Args:
            pattern: 要在日志中搜索的正则表达式模式。
            timeout: 等待日志出现的最长秒数。
            msg: 自定义断言失败信息。
        """
        found, line = self.check_serial_log(pattern, duration=timeout)
        
        if found:
            # 断言成功，记录找到的行
            log_data = {"match": True, "line": line, "pattern": pattern}
            log(log_data,desc="记录串口Log")
            self._gen_screen_log()
        else:
            recent_logs = self.serial_manager.read_log_lines(lines=100) # 获取最近50行
            self._gen_screen_log()
            AssertionError(f"{msg} | 未在串口日志中找到表达式: '{recent_logs}'")

    @logwrap
    def open_serial(self):
        """打开串口"""
        if self.serial_manager:
            return self.serial_manager.open_serial()
        else:
            print("未在 setting.json 中配置串口。")
            return False

    @logwrap
    def serial_login(self, username="root",password=None, timeout=10):
        """
        登录OpenWrt设备串口.
        :param username: 登录用户名, 默认为'root'.
        :param timeout: 等待登录成功的超时时间.
        :return: True表示登录成功, False表示失败.
        """
        if self.serial_manager:
            if not password:
                password = self.get_setting("serial_passwd")
            if not password:
                print("错误: 未在 setting.json 中找到串口密码 (serial_passwd)。")
                return False
            return self.serial_manager.serial_login(username, password, timeout)
        else:
            print("串口未初始化。")
            return False
   
    @logwrap
    def serial_close(self):
        """关闭串口"""
        if self.serial_manager:
            self.serial_manager.serial_close()

    @logwrap
    def serial_send(self, command):
        """向串口发送命令"""
        if self.serial_manager:
            self.serial_manager.send_cmd(command)
    
    @logwrap
    def serial_get(self, lines=None, duration=None):
        """获取串口日志"""
        if self.serial_manager:
            if duration:
                return self.serial_manager.read_log_duration(duration)
            elif lines:
                return self.serial_manager.read_log_lines(lines)
        return []

    @logwrap
    def check_serial_log(self, pattern, lines=None, duration=None):
        """检查串口日志中是否包含指定内容"""
        if self.serial_manager:
            return self.serial_manager.search_log(pattern, lines, duration)
        return False, None

    @logwrap
    def connect_wifi(self, ssid, password):
        """连接到指定的WiFi"""
        if self.wifi_manager:
            return self.wifi_manager.connect_wifi(ssid, password)
        else:
            print("未在 setting.json 中配置无线网卡。")
            return False

    @logwrap
    def disconnect_wifi(self):
        """断开WiFi连接"""
        if self.wifi_manager:
            return self.wifi_manager.disconnect_wifi()
        return False

    @logwrap
    def get_ip(self, interface_type="wired"):
        """获取有线或无线网卡的IP地址"""
        if interface_type == "wired":
            interface_name = self.settings.get("wired_adapter")
        else:
            interface_name = self.settings.get("wireless_adapter")
            
        if interface_name:
            return get_ip_address(interface_name)
        else:
            print(f"未在 setting.json 中配置 {interface_type} 网卡。")
            return None
    
    @logwrap
    def ping(self, ip_address, count=4):
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
        self._gen_screen_log(filename=filename)

    @logwrap
    def full_snapshot(self, filename=None, msg=""):
        """
        通过滚动和拼接来截取完整的网页长图。
        注意: 此功能可能无法完美处理带有固定/粘性页眉页脚、或动态加载内容的复杂页面。
        Args:
            filename: 保存截图的文件名 (可选).
            msg: 截图描述 (可选).
        """
        log("开始截取长图...")
        if ST.LOG_DIR is None:
            return None

        # 确定文件路径
        if not filename:
            png_file_name = str(int(time.time())) + '_full.png'
            filepath = os.path.join(ST.LOG_DIR, png_file_name)
        else:
            filepath = os.path.join(ST.LOG_DIR, filename)

        try:
            # 1. 使用JavaScript获取页面和视口的高度
            total_height_js = self.execute_script("return document.body.scrollHeight")
            viewport_height_js = self.execute_script("return window.innerHeight")

            # 如果页面无需滚动，则调用普通截图
            if total_height_js <= viewport_height_js:
                 log("页面无需滚动，将执行普通截图。")
                 return self._gen_screen_log(filename=filename)

            # 2. 滚动到页面顶部
            self.execute_script("window.scrollTo(0, 0)")
            time.sleep(1) # 等待页面稳定

            # 3. 计算截图的实际像素尺寸 (处理Retina/HiDPI屏幕)
            part = self.screenshot()
            h, w, _ = part.shape
            device_pixel_ratio = h / viewport_height_js
            
            total_height_pixels = int(total_height_js * device_pixel_ratio)

            # 4. 创建一个足够大的空白画布来拼接所有截图
            stitched_image = np.zeros((total_height_pixels, w, 3), dtype=np.uint8)

            y_offset = 0
            while y_offset < total_height_pixels:
                # 截取当前视口
                current_screenshot = self.screenshot()
                current_h, _, _ = current_screenshot.shape

                # 计算需要粘贴的高度，防止最后一张图超出范围
                paste_h = current_h
                if y_offset + current_h > total_height_pixels:
                    paste_h = total_height_pixels - y_offset
                    current_screenshot = current_screenshot[:paste_h, :]

                # 将截图粘贴到画布的正确位置
                stitched_image[y_offset : y_offset + paste_h, :] = current_screenshot
                
                y_offset += paste_h

                # 如果已拼接完整，则退出循环
                if y_offset >= total_height_pixels:
                    break
                
                # 滚动到下一个位置
                self.execute_script(f"window.scrollTo(0, {int(y_offset / device_pixel_ratio)})")
                time.sleep(0.5)

            # 5. 保存最终拼接的图片
            aircv.imwrite(filepath, stitched_image)
            log(f"长截图已保存至: {filepath}")
            
            # 6. 返回报告所需的数据
            return {"screen": filepath}

        except Exception as e:
            log(f"截取长图失败: {e}", "error")
            return self._gen_screen_log() # 失败时回退到普通截图

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
