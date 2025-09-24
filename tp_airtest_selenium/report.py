# -*- coding: utf-8 -*-
import os
import io
from urllib.parse import unquote
import airtest.report.report as report
import json
import jinja2
from airtest.core.settings import Settings as ST
from airtest.report.report import nl2br, timefmt
LOGDIR = "log"

old_trans_screen = report.LogToHtml._translate_screen
old_trans_desc = report.LogToHtml._translate_desc
old_trans_code = report.LogToHtml._translate_code
old_trans_info = report.LogToHtml._translate_info
old_render = report.LogToHtml._render

screen_func = [
    "find_element_by_xpath", "find_element_by_id", "find_element_by_name", 
    "assert_screen", "assert_custom", "assert_exist", "assert_serial_log",
    "back", "forward", "switch_to_new_tab", "switch_to_previous_tab", "get",
    "click", "send_keys", "snapshot", "full_snapshot"
]

second_screen_func = ["click", "send_keys"]
other_func = [
    # serial_utils functions
    "serial_open", "serial_close", "serial_login", "serial_send", "serial_get", "serial_find","serial_wait_pattern",
    # network_utils functions
    "wifi_connect", "wifi_disconnect", "get_ip", "ping", "check_port",
    # ocr functions
    "ocr_click_text", "ocr_text_exists", "ocr_get_field_value", "ocr_get_text_position",
    "ocr_find_all_text", "ocr_recognize_all_text"
]

def new_trans_screen(self, step, code):
    trans = old_trans_screen(self, step, code)
    if "name" in step['data'] and step['data']["name"] in screen_func:
        screen = {
            "src": None,
            "rect": [],
            "pos": [],
            "vector": [],
            "confidence": None,
        }

        src = ""
        if step["data"]["name"] in second_screen_func:
            res = step["data"]['ret']
            src = res["screen"]
            if "pos" in res:
                screen["pos"] = res["pos"]

        for item in step["__children__"]:
            if item["data"]["name"] in ["_gen_screen_log", "try_log_screen"]:
                res = item["data"]['ret']
                src = res["screen"]
                if "pos" in res:
                    screen["pos"] = res["pos"]
                break

        if self.export_dir and src:
            src = os.path.join(LOGDIR, src)
        screen["src"] = src

        return screen
    else:
        if step["data"]["name"] in ["airtest_touch"]:
            # 将图像匹配得到的pos修正为最终pos
            display_pos = None
            if self.is_pos(step["data"].get("ret")):
                display_pos = step["data"]["ret"]
            elif self.is_pos(step["data"]["call_args"].get("v")):
                display_pos = step["data"]["call_args"]["v"]
            if display_pos:
                trans["pos"] = [display_pos]
        return trans


def new_translate_desc(self, step, code):
    trans = old_trans_desc(self, step, code)
    if "name" in step['data'] and (step['data']["name"] in screen_func or step["data"]["name"] in other_func):
        name = step["data"]["name"]
        args = {}
        url = ""
        for item in code["args"]:
            if (name=='get'):
                url = unquote(item['value'])
                item['value'] = "<a href='%s' target='_blank' style='color:cornflowerblue'>%s</a>" % (url, url)
            args[item['key']] = item['value']
        desc = {
            "find_element_by_xpath": lambda: u"Find element by xpath: %s" % args.get("xpath"),
            "find_element_by_id": lambda: u"Find element by id: %s" % args.get("id"),
            "find_element_by_name": lambda: u"Find element by name: %s" % args.get("name"),
            "assert_screen": "Assert a picture with screen snapshot",
            "assert_custom": "Assert custom",
            "assert_exist": u"Assert element exists.",
            "assert_serial_log": lambda: f"Assert serial log: \"{args.get('pattern')}\"",
            "click": u"Click the element that been found.",
            "send_keys": u"Send some text and keyboard event to the element that been found.",
            "get": lambda: u"Get the web address: %s" % (url),
            "switch_to_last_window": u"Switch to the last tab.",
            "switch_to_latest_window": u"Switch to the new tab.",
            "back": u"Back to the last page.",
            "forward": u"Forward to the next page.",
            "snapshot": lambda: (u"Screenshot description: %s" % args.get("msg")) if args.get("msg") else u"Snapshot current page",
            "full_snapshot": lambda: f"full snapshot: {args.get('msg')}" if args.get('msg') else "full snapshot"

        }

        desc_zh = {
            # Selenium Web 操作
            "find_element_by_xpath": lambda: f"寻找页面元素: \"{args.get('xpath')}\"",
            "find_element_by_id": lambda: f"寻找页面元素: \"{args.get('id')}\"",
            "find_element_by_name": lambda: f"寻找页面元素: \"{args.get('name')}\"",
            "click": "点击找到的页面元素",
            "send_keys": f"向选中文本框输入文本: \"{args.get('text', '')}\"",
            "get": lambda: f"访问网址: {url}",
            "switch_to_previous_tab": "切换到上一个标签页",
            "switch_to_new_tab": "切换到最新标签页",
            "back": "后退到上一个页面",
            "forward": "前进到下一个页面",
            
            # Airtest 操作
            "touch": "点击屏幕坐标",
            "airtest_touch": "点击屏幕坐标",
            "snapshot": lambda: f"截图页面: {args.get('msg')}" if args.get('msg') else "截取当前页面",
            "full_snapshot": lambda: f"截图完整页面: {args.get('msg')}" if args.get('msg') else "截取当前完整页面",

            # 断言操作
            "assert_screen": lambda: f"对比截图: {args.get('msg')}" if args.get('msg') else "对比截图和图片",
            "assert_custom": lambda: f"断言: {args.get('msg')}" if args.get('msg') else "自定义断言",
            "assert_exist": lambda: f"断言元素: {args.get('msg')}" if args.get('msg') else "断言元素",
            "assert_serial_log": lambda: f"断言串口日志中包含: \"{args.get('pattern')}\"",

            # --- 新增串口工具函数描述 ---
            "serial_open": "打开串口",
            "serial_close": "关闭串口",
            "serial_login": lambda: f"串口登录: \"{args.get('password')}\"",
            "serial_send": lambda: f"发送命令: {args.get('command')}",
            "serial_get": lambda: f"获取串口 {args.get('lines')}s/{args.get('duration')}行内Logs",
            "serial_find": lambda: f"搜索串口: \"{args.get('pattern')}\"正则表达式",
            "serial_wait_pattern": lambda: f"等待串口日志出现: \"{args.get('pattern')}表达式\"",

            # --- 新增网络工具函数描述 ---
            "wifi_connect": lambda: f"连接WiFi: {args.get('ssid')}",
            "wifi_disconnect": "断开WiFi连接",
            "get_ip": "获取" + ("有线" if args.get('interface_type') else "无线") + "网卡IP",
            "ping": lambda: f"Ping地址: {args.get('ip_address')}",
            "check_port": lambda: f"检查端口状态: {args.get('host')}:{args.get('port')}",

            # --- 新增OCR工具函数描述 ---
            "ocr_click_text": lambda: f"OCR点击文字: \"{args.get('text')}\"",
            "ocr_text_exists": lambda: f"OCR检查文字是否存在: \"{args.get('text')}\"",
            "ocr_get_field_value": lambda: f"OCR获取字段值: \"{args.get('field_name')}\" ({args.get('search_direction', 'right')}方向)",
            "ocr_get_text_position": lambda: f"OCR获取文字位置: \"{args.get('text')}\"",
            "ocr_find_all_text": lambda: f"OCR查找所有文字: \"{args.get('text')}\"",
            "ocr_recognize_all_text": "OCR识别屏幕中的所有文字",
        }

        # 根据语言选择描述
        desc = desc_zh if self.lang == 'zh' else desc_zh
        ret = desc.get(name)
        return ret() if callable(ret) else ret
    return trans


def new_translate_code(self, step):
    """
    处理代码显示逻辑。
    核心改动：增加了一个过滤器，当函数是 assert_custom 或 assert_serial_log 时，
    会主动移除名为 'logs' 的参数，避免其在报告中重复显示。
    """
    # 先调用原始的翻译函数获取所有参数
    trans = old_trans_code(self, step)

    if trans:
        # 准备一个要过滤掉的参数名列表
        params_to_filter = ["self"]

        # 额外把 'logs' 也加入过滤列表
        # func_name = step["data"]["name"]
        # if func_name in ["assert_custom", "assert_serial_log"]:
        params_to_filter.append("log_msg")

        trans["args"] = [arg for arg in trans["args"] if arg.get("key") not in params_to_filter]
        
    return trans

def new_translate_info(self, step):
    trace_msg, log_msg = old_trans_info(self, step)
    if "log" in step["data"]:
        log_msg = step["data"]["log"]
    elif step["tag"] == "function" and "log_msg" in step["data"].get("call_args", {}):
        log_msg = step["data"]["call_args"]["log_msg"]

    if isinstance(log_msg, dict):
        try:
            # 尝试将字典格式化为JSON字符串
            pretty_json = json.dumps(log_msg, indent=4, ensure_ascii=False)
            log_msg = f"{pretty_json}"
        except Exception:
            pass

    return trace_msg, log_msg

@staticmethod
def new_render(template_name, output_file=None, **template_vars):
    # 到ST.PROJECT_ROOT/source下寻找报告模板
    template_path = os.path.join(ST.PROJECT_ROOT, "source")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_path),
        extensions=(),
        autoescape=True
    )
    env.filters['nl2br'] = nl2br
    env.filters['datetime'] = timefmt
    template = env.get_template(template_name)
    html = template.render(**template_vars)

    if output_file:
        with io.open(output_file, 'w', encoding="utf-8") as f:
            f.write(html)
        print(output_file)

    return html

report.LogToHtml._render = new_render
report.LogToHtml._translate_screen = new_trans_screen
report.LogToHtml._translate_desc = new_translate_desc
report.LogToHtml._translate_code = new_translate_code
report.LogToHtml._translate_info = new_translate_info

