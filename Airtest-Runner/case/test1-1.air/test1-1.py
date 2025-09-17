# -*- encoding=utf8 -*-
__author__ = "Administrator"
__brief__ = "这是一个简单的测试脚本内容"
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
driver.get("http://tplogin.cn")
logs = {"log":"aaaaaaaaaaaaaaa"}
driver.assert_custom(True,logs,"111.")
driver.assert_custom(True,setting,"222")
# driver.find_element_by_id("pwdTipStr").click()
# driver.find_element_by_id("lgPwd").send_keys("tplink123")
# dic = {"q":"测试工程师小站","p":False,"g":[{"type":"sug","sa":"s_1","q":"一个测试工程师"},{"type":"sug","sa":"s_2","q":"测试开发工程师"},{"type":"sug","sa":"s_3","q":"测试技术工程师"},],"slid":"1536329420958301","queryid":"0x7c62fdc7d"}
# log(dic, desc="请求返回的数据")
# driver.find_element_by_xpath("//input[@type='button']").click()
# sleep(1.0)
# driver.assert_custom(True,"创建tplink-id.")
# driver.assert_screen("C:\\Users\\Administrator\\Pictures\\1757735395.png", threshold=0.99, msg="检查搜索后页面是否发生变化")
# driver.snapshot()


