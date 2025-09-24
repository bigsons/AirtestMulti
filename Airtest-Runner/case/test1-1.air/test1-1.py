# -*- encoding=utf8 -*-
__author__ = "Administrator"
__brief__ = "这是一个简单的测试脚本内容这是一个简单的测试脚本内容这是一个简单的测试脚本内容这是一个简单的测试脚本内容这是一个简单的测试脚本内容"
from airtest.core.api import *
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from tp_airtest_selenium.proxy import WebChrome
auto_setup(__file__,project_root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

driver = WebChrome()
driver.implicitly_wait(20)

setting=driver.get_setting()
print(setting)
driver.serial_send("aaaaa")
driver.get("http://192.168.1.1")
driver.serial_login(password="79d05758")
driver.serial_send("ifconfig") # 例如发送一个重启命令
sleep(1)
vl = driver.serial_find("192\.168\.1\.1")
logs = driver.serial_get(50)
driver.wifi_disconnect()
ret = driver.wifi_connect("Redmi_9C67","1169302692")
driver.assert_custom(ret,logs,driver.snapshot())
driver.serial_send("rebowot") # 例如发送一个重启命令
driver.serial_send("reboot") # 例如发送一个重启命令
logs = driver.serial_get(duration=10)
log(logs,desc="串口日志")
log(driver.get_ip(),desc="无线ip")
log(driver.get_ip("wired"),desc="无线ip")
ret,info = driver.ping("192.168.1.1")
driver.assert_custom(ret,info,True,"ping结果")
driver.find_element_by_xpath("//input[@aria-required='true']").send_keys("admin123")
driver.find_element_by_xpath("//*[@id=\"app\"]/div/div[2]/div[3]/main/div/button/div[2]/span").click()
driver.find_element_by_xpath("//div[@data-cy='networkMapRouterBtn']").click()
driver.full_snapshot()
print("jiaobenzhixzhix111111111111111")

# sleep(1)
# # driver.get("http://192.168.1.1/webpages/index.html#/storageSharing")
# sleep(1)
# # Call the new function to capture the long screenshot
# driver.full_snapshot()
# 等待并断言串口日志中是否出现了 "login:" 提示
# try:
#     driver.assert_serial_log("login1:", timeout=20, msg="设备重启后未能进入登录界面")
#     print("断言成功：设备已重启并准备登录。")
# except AssertionError as e:
#     print(f"断言失败: {e}")

# logs = {"aaaaa":11111}
# driver.full_snapshot()
# driver.assert_custom(True,logs,driver.snapshot())
# print("jiaobenzhixzhix111111111111111")
# driver.assert_custom(True,logs,"C:\\Users\\Administrator\\Pictures\\1757735395.png","222")
# driver.assert_custom(True,setting,)
# driver.assert_custom(True,setting,True,"333")
# dic = {"q":"测试工程师小站","p":False,"g":[{"type":"sug","sa":"s_1","q":"一个测试工程师"},{"type":"sug","sa":"s_2","q":"测试开发工程师"},{"type":"sug","sa":"s_3","q":"测试技术工程师"},],"slid":"1536329420958301","queryid":"0x7c62fdc7d"}
# driver.assert_custom(True,logs,"C:\\Users\\Administrator\\Pictures\\1757735395.png","222")
# driver.assert_custom(True,setting,False,"aaa")
# print("这回是真的在重启")
# driver.serial_send("reboot ") # 例如发送一个重启命令
# # logs = driver.serial_get(duration=120)
# driver.assert_custom(True,logs,True,"重启测试")
# log(dic, desc="请求返回的数据")
# sleep(1.0)
# driver.assert_custom(False,"创建tplink-id.")
# # driver.assert_screen("C:\\Users\\Administrator\\Pictures\\1757735395.png", threshold=0.95, msg="检查搜索后页面是否发生变化")
# driver.snapshot()










