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










