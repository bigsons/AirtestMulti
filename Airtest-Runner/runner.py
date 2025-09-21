# -*- encoding=utf-8 -*-
import os
import traceback
import subprocess
import webbrowser
import time
import json
import shutil
from jinja2 import Environment, FileSystemLoader

def get_script_description(case_script):
    """
    从用例目录下的readme文件中读取第一行作为脚本描述.
    """
    try:
        # 兼容不同操作系统，使用os.path.join
        readme_path = os.path.join(os.getcwd(), "case", case_script, "readme")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                # 读取并去除首尾空白字符
                description = f.readline().strip()
                return description if description else "暂无脚本描述"
    except Exception as e:
        print(f"读取 {case_script} 的readme文件时出错: {e}")
    return "暂无脚本描述"

def run(cases):
    """
    运行所有测试用例并生成报告.
    """
    report_dir = get_report_dir()
    log_base_dir = os.path.join(report_dir, 'log')

    # 清理旧的报告和日志
    if os.path.isdir(report_dir):
        shutil.rmtree(report_dir)
    os.makedirs(log_base_dir, exist_ok=True)

    try:
        results_data = []
        start_time = time.time()
        
        # 假设只有一个设备用于演示
        # 在实际多设备场景中, 你需要修改此处的设备列表逻辑
        devices = ["web_device_1"] 

        for case in cases:
            case_results = {'script': case, 'tests': {}}
            
            tasks = run_on_devices(case, devices, log_base_dir)

            for task in tasks:
                status = task['process'].wait()
                report_info = run_one_report(task['case'], task['dev'], log_base_dir)
                # 确保status总是存在
                report_info['status'] = status if status is not None else -1
                case_results['tests'][task['dev']] = report_info

            results_data.append(case_results)

        run_summary(results_data, start_time)

    except Exception:
        traceback.print_exc()

def run_on_devices(case, devices, log_base_dir):
    """
    在指定设备上运行单个测试用例.
    """
    case_name = os.path.splitext(case)[0]
    case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
    tasks = []
    for dev in devices:
        log_dir = get_log_dir(case, dev, log_base_dir)
        print(f"执行脚本 '{case}' 在设备 '{dev}' 上, 日志路径: {log_dir}")
        
        cmd = ["airtest", "run", case_path, "--log", log_dir, "--recording"]
        try:
            # 使用 shell=True (Windows) or False (Linux/MacOS)
            is_windows = os.name == 'nt'
            tasks.append({
                'process': subprocess.Popen(cmd, cwd=os.getcwd(), shell=is_windows),
                'dev': dev,
                'case': case
            })
        except Exception:
            traceback.print_exc()
    return tasks

def run_one_report(case, dev, log_base_dir):
    """
    为单次运行生成Airtest报告.
    """
    log_dir = get_log_dir(case, dev, log_base_dir)
    log_txt = os.path.join(log_dir, 'log.txt')
    case_name = os.path.splitext(case)[0]
    case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
    try:
        if os.path.isfile(log_txt):
            report_path = os.path.join(log_dir, 'log.html')
            static_source_path = os.path.join(os.getcwd(), "source")
            cmd = [
                "airtest", "report", case_path,
                "--log_root", log_dir,
                "--outfile", report_path,
                "--static_root", static_source_path,
                "--lang", "zh",
                "--plugin", "tp_airtest_selenium.report"
            ]
            is_windows = os.name == 'nt'
            subprocess.call(cmd, shell=is_windows, cwd=os.getcwd())
            
            relative_path = os.path.join("log", case, dev, 'log.html').replace('\\', '/')
            return {'status': 0, 'path': relative_path}
        else:
            print(f"报告生成失败: 未找到log.txt in {log_dir}")
    except Exception:
        traceback.print_exc()
    return {'status': -1, 'path': ''}

def run_summary(data, start_time):
    """
    汇总所有结果并生成最终的聚合报告.
    """
    try:
        all_statuses = []
        for dt in data:
            dt['description'] = get_script_description(dt['script'])
            for test in dt['tests'].values():
                all_statuses.append(test.get('status', -1))

        summary = {
            'time': f"{(time.time() - start_time):.3f}",
            'success': all_statuses.count(0),
            'count': len(all_statuses),
            'start_all': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
            "result": data
        }

        if os.path.exists("setting.json"):
            with open("setting.json", "r", encoding="utf-8") as f:
                summary.update(json.load(f))

        template_dir = os.path.join(os.getcwd(), "source")
        env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
        template = env.get_template('template')
        html = template.render(data=summary)

        report_path = os.path.join(get_report_dir(), "result.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html)
        
        # 使用file URI scheme确保跨平台兼容性
        webbrowser.open('file://' + os.path.realpath(report_path))

    except Exception:
        traceback.print_exc()

def get_log_dir(case, device, log_base_dir):
    """
    构建并创建单个测试运行的日志目录.
    """
    # 清理设备名中的非法字符
    safe_device_name = device.replace(":", "_").replace(".", "_")
    log_dir = os.path.join(log_base_dir, case, safe_device_name)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def get_report_dir():
    """
    获取报告的根目录.
    """
    return os.path.join(os.getcwd(), "result")

def get_cases():
    """ 从 'case' 文件夹获取所有测试用例。""" 
    case_dir = os.path.join(os.getcwd(), "case")
    if not os.path.isdir(case_dir):
        return []
    return sorted([name for name in os.listdir(case_dir)])

if __name__ == '__main__':
    all_cases = get_cases()
    if all_cases:
        run(all_cases)
    else:
        print("未找到任何测试用例，程序退出。")