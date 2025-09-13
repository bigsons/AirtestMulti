# -*- encoding=utf-8 -*-
import os
import traceback
import subprocess
import webbrowser
import time
import json
import shutil
from airtest.core.android.adb import ADB
from jinja2 import Environment, FileSystemLoader

model = "Archer BE550v1"

def run(cases):
    """
        先清除以前的log、result
    """
    report_log = get_report_dir()
    if os.path.isdir(report_log):
        shutil.rmtree(report_log)
        os.mkdir(report_log)

    log_dir = os.path.join(os.getcwd(), 'result\log')
    if os.path.isdir(log_dir):
        shutil.rmtree(log_dir)

    try:
        data_r = []
        global time_s
        time_s = time.time()
        for case in cases:
            results = load_json_data(case)
            tasks = run_on_device(case, results)
            for task in tasks:
                status = task['process'].wait()
                results['tests'][task['dev']] = run_one_report(task['case'], task['dev'])  # {'status': -1, 'device': dev, 'path': ''}
                results['tests'][task['dev']]['status'] = status

                name = case.split(".")[0]
                file = os.path.join(report_log, name + "_data.json")
                json.dump(results, open(file, "w"), indent=4)
            data_r.append(results)
        print(data_r)
        run_summary(data_r)
    except Exception as e:
        traceback.print_exc()


def run_on_device(case, results):
    tasks = []
    run_dev = "web"
    log_dir = get_log_dir(case)
    print("执行脚本，保存日志路径====>" + str(log_dir))
    cmd = [ "airtest", "run", os.path.join(os.getcwd(),"case", case), "--log", log_dir, "--recording"]
    try:
        tasks.append({
            'process': subprocess.Popen(cmd, cwd=os.getcwd()),
            'dev': run_dev,
            'case': case
        })
    except Exception as e:
        traceback.print_exc()
    return tasks

def run_one_report(case, dev):
    try:
        log_dir = get_log_dir(case)
        log = os.path.join(log_dir, 'log.txt')
        print("生成报告，日志读取日志路径===>>" + str(log_dir))
        if os.path.isfile(log):
            cmd = [ "airtest", "report", os.path.join(os.getcwd(),"case", case), "--log_root", log_dir, "--outfile", os.path.join(log_dir, 'log.html'), "--lang", "zh", "--plugin", "airtest_selenium.report" ]

            ret = subprocess.call(cmd, shell=True, cwd=os.getcwd())
            return {
                'status': ret,
                'path': os.path.join(".\\log", case.replace(".air",".log"),'log.html') # os.path.join(os.getcwd(), "log", "follow.log", "log.html")
            }
        else:
            print("Report build Failed. File not found in dir %s" % log)
    except Exception as e:
        traceback.print_exc()
    return {'status': -1, 'device': dev, 'path': ''}


def load_json_data(case):
    return {
        'start': time.time(),
        'script': case,
        'tests': { }
    }


def run_summary(data):
    try:
        for dt in data:
            res = get_value_by_key(dt, "status")

        summary = {
            'model': model,
            'time': "%.3f" % (time.time() - time_s),
            'success': res.count(0),
            'count': len(res)
        }
        summary['start_all'] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_s))
        summary["result"] = data

        env = Environment(loader=FileSystemLoader(os.getcwd()), trim_blocks=True)
        html = env.get_template('template').render(data=summary)

        with open(".\\result\\result.html", "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open(".\\result\\result.html")
    except Exception as e:
        traceback.print_exc()


def get_value_by_key(in_json, target_key,results=[]):
    for key, value in in_json.items():  # 循环获取key,value
        if key == target_key:
            results.append(value)
        if isinstance(value, dict):
            get_value_by_key(value, target_key)
    return results

def get_cases():
    cases = []
    for name in os.listdir(os.path.join(os.getcwd(),"case")): 
        if name.endswith(".air"):
            cases.append(name)
    return cases

def get_log_dir(case, device=None):
    log_dir = os.path.join(os.getcwd(), 'result\log', case.replace(".air", ".log"))
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    return log_dir

def get_report_dir():
    report_path = os.path.join(os.getcwd(), "result")
    if not os.path.isdir(report_path):
        os.mkdir(report_path)
    return report_path

if __name__ == '__main__':
    cases = get_cases()
    run(cases)