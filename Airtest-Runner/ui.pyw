import os,time,json,sys,re,shutil,traceback,subprocess,webbrowser,psutil
import serial.tools.list_ports
from jinja2 import Environment, FileSystemLoader
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QHeaderView, QCheckBox, QFrame, QProgressBar, QDialog, QFileDialog,
                             QStyledItemDelegate, QStyle, QComboBox, QGridLayout)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer, QSize

# =====================================================================================================================
#  自定义委托，用于在绘制单元格时不显示焦点虚线框
# =====================================================================================================================
class NoFocusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if option.state & QStyle.StateFlag.State_HasFocus:
            option.state = option.state & ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)

# =====================================================================================================================
# Runner.py 逻辑部分
# =====================================================================================================================
def get_script_description(case_script):
    try:
        script_name = os.path.splitext(case_script)[0]
        script_path = os.path.join(os.getcwd(), "case", case_script, f"{script_name}.py")

        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
                # 使用正则表达式查找 __brief__ 的值
                match = re.search(r'\s*__brief__\s*=\s*["\'](.*?)["\']', content)
                if match:
                    return match.group(1).strip()  # 返回匹配到的描述
    except Exception as e:
        print(f"读取 {case_script} 的 __brief__ 时出错: {e}")
    
    return "暂无脚本描述"

def get_report_dir():
    return os.path.join(os.getcwd(), "result")

def get_log_dir(case, device, log_base_dir):
    safe_device_name = device.replace(":", "_").replace(".", "_")
    log_dir = os.path.join(log_base_dir, case.replace(".air", ".log"), safe_device_name)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def get_cases():
    case_dir = os.path.join(os.getcwd(), "case")
    if not os.path.isdir(case_dir):
        return []
    return sorted([name for name in os.listdir(case_dir)])

class RunnerThread(QThread):
    """
    RunnerThread is a QThread worker class designed to handle the test execution
    process in the background, preventing the main GUI from freezing.
    Its primary responsibilities include:
    - Managing the entire lifecycle of a test run, from setup to report generation.
    - Executing each selected 'airtest' script as a separate subprocess.
    - Monitoring and controlling these subprocesses, allowing for graceful termination.
    - Emitting Qt signals (status_update, progress_update, finished) to provide
      real-time feedback (e.g., status messages, progress bar updates) to the main UI thread.
    - Generating a final, consolidated HTML report upon completion of all tests.
    """
    status_update = pyqtSignal(str)
    progress_update = pyqtSignal(int)
    finished = pyqtSignal(str)

    def __init__(self, cases, settings):
        super().__init__()
        self.cases = sorted(cases)
        self.settings = settings
        self.running = True
        self.process_list = []

    def run(self):
        report_dir = get_report_dir()
        log_base_dir = os.path.join(report_dir, 'log')

        if os.path.isdir(report_dir):
            try:
                shutil.rmtree(report_dir)
            except PermissionError as e:
                self.status_update.emit(f"清理报告目录失败: {e}")
                time.sleep(1)
                try:
                    shutil.rmtree(report_dir)
                except Exception as e_retry:
                    self.status_update.emit(f"重试清理失败: {e_retry}")
                    self.finished.emit("")
                    return
        os.makedirs(log_base_dir, exist_ok=True)

        try:
            results_data = []
            total_cases = len(self.cases)

            for i, case in enumerate(self.cases):
                if not self.running: break
                self.status_update.emit(f"正在运行: {case} ({i+1}/{total_cases})")
                case_results = {'script': case, 'tests': {}}
                tasks = self.run_on_devices(case, ["web_device_1"], log_base_dir)
                for task in tasks:
                    if not self.running: break
 
                    while task['process'].poll() is None:
                        if not self.running:
                            task['process'].terminate()
                            break
                        time.sleep(0.1)
                    
                    if not self.running: break
                    
                    try:
                        task['process'].communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        task['process'].kill()
                        task['process'].communicate()

                    status = task['process'].returncode
                    report_info = self.run_one_report(task['case'], task['dev'], log_base_dir)
                    report_info['status'] = status if status is not None else -1
                    case_results['tests'][task['dev']] = report_info
                results_data.append(case_results)
                self.progress_update.emit(int(((i + 1) / total_cases) * 100))

            if self.running:
                self.progress_update.emit(100)
                report_path = self.run_summary(results_data, self.settings['start_time'])
                self.status_update.emit("所有脚本运行完毕")
                self.finished.emit(report_path)
            else:
                self.status_update.emit("运行已停止")
                self.finished.emit("")
        except Exception as e:
            self.status_update.emit(f"发生错误: {e}")
            traceback.print_exc()
            self.finished.emit("")

    def run_on_devices(self, case, devices, log_base_dir):
        tasks = []
        case_name = os.path.splitext(case)[0]
        case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
        for dev in devices:
            log_dir = get_log_dir(case, dev, log_base_dir)
            cmd = ["airtest", "run", case_path, "--log", log_dir, "--recording"]
            try:
                is_windows = os.name == 'nt'
                process = subprocess.Popen(cmd, cwd=os.getcwd(), shell=is_windows,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0)
                self.process_list.append(process)
                tasks.append({'process': process, 'dev': dev, 'case': case})
            except Exception:
                traceback.print_exc()
        return tasks

    def run_one_report(self, case, dev, log_base_dir):
        log_dir = get_log_dir(case, dev, log_base_dir)
        log_txt = os.path.join(log_dir, 'log.txt')
        case_name = os.path.splitext(case)[0]
        case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
        max_retries = 5
        retry_delay = 0.5
        for attempt in range(max_retries):
            if os.path.isfile(log_txt):
                try:
                    with open(log_txt, 'r', encoding='utf-8') as f:
                        f.read(1)
                    break
                except PermissionError:
                    if attempt < max_retries - 1:
                        print(f"Warning: '{log_txt}' is locked. Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                    else:
                        print(f"Error: Could not access '{log_txt}' after multiple retries.")
                        return {'status': -1, 'path': ''}
                except Exception as e:
                    print(f"An unexpected error occurred while checking '{log_txt}': {e}")
                    return {'status': -1, 'path': ''}
            else:
                time.sleep(retry_delay)
        
        if not os.path.isfile(log_txt):
            print(f"Error: Log file not found at '{log_txt}'")
            return {'status': -1, 'path': ''}
            
        try:
            report_path = os.path.join(log_dir, 'log.html')
            cmd = [
                "airtest", "report", case_path,
                "--log_root", log_dir, "--outfile", report_path,
                "--lang", "zh", "--plugin", "airtest_selenium.report"
            ]
            is_windows = os.name == 'nt'
            report_process = subprocess.Popen(cmd, shell=is_windows, cwd=os.getcwd(),
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            report_process.communicate(timeout=60)

            relative_path = os.path.join("log", case_name+'.log', dev, 'log.html').replace('\\', '/')
            return {'status': 0, 'path': relative_path}
        except Exception:
            traceback.print_exc()
            
        return {'status': -1, 'path': ''}

    def run_summary(self, data, start_time):
        try:
            summary = {
                'time': f"{(time.time() - start_time):.3f}",
                'success': sum(1 for dt in data for test in dt['tests'].values() if test.get('status') == 0),
                'count': sum(len(dt['tests']) for dt in data),
                'start_all': time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time)),
                "result": data,
                "model_name": self.settings.get("model_name", "N/A"),
                "software_version": self.settings.get("software_version", "N/A"),
            }
            for dt in data:
                dt['description'] = get_script_description(dt['script'])
            template_dir = os.path.join(os.getcwd(), "source")
            env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
            template = env.get_template('template')
            html = template.render(data=summary)
            report_path = os.path.join(get_report_dir(), "result.html")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(html)
            return 'file:///' + os.path.realpath(report_path).replace('\\', '/')
        except Exception:
            traceback.print_exc()
        return ""

    def stop(self):
        self.running = False
        for p in self.process_list:
            if p.poll() is None:
                try:
                    p.terminate()
                except ProcessLookupError:
                    pass

# =====================================================================================================================
# 设置对话框的UI界面
# =====================================================================================================================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        
        primary_color = "#4F46E5"
        primary_hover_color = "#4338CA"
        self.setStyleSheet(f"""
            QDialog, QLabel, QCheckBox {{ 
                font-size: 14px;
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }}
            QPushButton {{
                background-color: {primary_color};
                color: #fff;
                border: none; 
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px; 
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }}
            QPushButton:hover {{
                background-color: {primary_hover_color};
            }}
            QLineEdit, QComboBox {{
                padding: 5px;
                font-size: 14px; 
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(5) # 减小间距，让提示更紧凑
        
        self.hide_params_checkbox = QCheckBox("隐藏主界面的参数设置面板")
        self.hide_params_checkbox.setChecked(not self.main_window.settings_card.isVisible())
        self.hide_params_checkbox.stateChanged.connect(self.toggle_params_card)
        layout.addWidget(self.hide_params_checkbox)

        config_layout = QHBoxLayout()
        config_label = QLabel("选择配置文件:")
        self.config_path_entry = QLineEdit(self.main_window.settings_path)
        self.config_path_entry.setReadOnly(True)
        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_config_file)
        
        config_layout.addWidget(config_label)
        config_layout.addWidget(self.config_path_entry)
        config_layout.addWidget(browse_button)
        layout.addLayout(config_layout)

        # 添加用于显示错误的标签
        self.error_label = QLabel("")
        # 修改样式：缩小字体
        self.error_label.setStyleSheet("color: red; padding-left: 92px; font-size: 12px;")
        self.error_label.setVisible(False) # 初始时隐藏
        layout.addWidget(self.error_label)
        
        layout.addStretch() # 添加伸缩，避免控件分散

    def toggle_params_card(self, state):
        is_checked = (state == Qt.CheckState.Checked.value)
        self.main_window.model_info_card.setVisible(not is_checked)
        self.main_window.settings_card.setVisible(not is_checked)

    def browse_config_file(self):
        # 新增：再次点击浏览时，立即隐藏上一次的错误提示
        self.error_label.setVisible(False)

        file_path, _ = QFileDialog.getOpenFileName(self, "选择配置文件", "", "JSON Files (*.json)")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                json.load(f)  # 仅用于验证JSON格式
            
            # 验证成功
            self.main_window.set_settings_path(file_path)
            self.config_path_entry.setText(file_path)

        except (json.JSONDecodeError, IOError):
            # 验证失败，显示错误信息
            self.error_label.setText("请选择有效的JSON文件")
            self.error_label.setVisible(True)


# =====================================================================================================================
# 主 UI 界面
# =====================================================================================================================
class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自动化自测工具")
        
        self.setWindowIcon(QIcon("./source/logo.png"))
        
        self.setGeometry(100, 100, 1000, 720)
        self.settings = {}
        self.settings_path = "setting.json"
        self.runner_thread = None
        
        self.execution_timer = QTimer(self)
        self.execution_timer.timeout.connect(self.update_execution_time)
        self.start_time = 0

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        primary_color = "#4ACBD6"
        primary_hover_color = "#43b6c0"
        stop_button_color = "#4F46E5"
        stop_button_hover_color = "#4338CA"
        dark_sidebar_color = "#2E2E2E"
        dark_sidebar_hover_color = "#3f3f3f"
        background_color = "#F8F9FA" 
        card_bg_color = "#FFFFFF"
        border_color = "#DEE2E6"
        text_color = "#212529" 
        secondary_text_color = "#6C757D"
        
        self.setStyleSheet(f"""
            QWidget {{ 
                color: {text_color};
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
                background-color: {background_color};
            }}
            QFrame#card {{
                background-color: {card_bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            QLabel {{ 
                font-size: 14px;
                background-color: transparent; 
            }}
            QCheckBox {{ 
                background-color: transparent;
            }}
            QLabel#titleLabel {{ 
                font-size: 24px;
                font-weight: 600; 
                color: {text_color}; 
                padding-bottom: 5px; 
            }}
            QLabel#cardTitle {{ 
                font-size: 16px;
                font-weight: 600; 
                color: {text_color}; 
            }}
            QLineEdit, QComboBox {{ 
                background-color: {card_bg_color};
                border: 1px solid {border_color}; 
                border-radius: 6px; 
                padding: 8px; 
                font-size: 14px;
            }}
            QLineEdit:focus, QComboBox:focus {{ 
                border-color: {primary_color};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left-width: 1px;
                border-left-color: {border_color};
                border-left-style: solid;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow {{
                image: url(./source/down-arrow.png);
            }}
            QTableWidget {{ 
                background-color: {card_bg_color};
                border: none; 
                gridline-color: {border_color};
                font-size: 14px; 
                alternate-background-color: #F8F9FA;
                selection-background-color: #E6E6FA; 
                selection-color: {text_color};
            }}
            QTableWidget::item {{ 
                padding: 12px 10px;
                border-bottom: 1px solid #F1F3F5; 
            }}
            QTableWidget::item:selected {{ 
                background-color: #E9EBF8;
            }}
            QTableWidget::item:focus {{ 
                outline: none;
            }}
            QHeaderView::section {{ 
                background-color: #F8F9FA;
                padding: 10px; 
                border: none;
                border-bottom: 1px solid {border_color}; 
                font-weight: 600; 
                font-size: 14px;
            }}
            QPushButton {{ 
                background-color: {primary_color};
                color: #fff; 
                border: none; 
                padding: 10px 20px; 
                border-radius: 6px; 
                font-size: 14px;
                font-weight: 500; 
                min-height: 20px;
            }}
            QPushButton:hover {{ 
                background-color: {primary_hover_color};
            }}
            QPushButton:disabled {{ 
                background-color: #E9ECEF;
                color: {secondary_text_color}; 
            }}
            QPushButton#stopButton {{ 
                background-color: {stop_button_color};
            }}
            QPushButton#stopButton:hover {{ 
                background-color: {stop_button_hover_color};
            }}
            QFrame#leftPanel {{
                background-color: {dark_sidebar_color};
                border-right: 1px solid #252525;
            }}
            QPushButton#sideBarButton {{
                background-color: transparent;
                color: #D0D0D0; 
                text-align: center; 
                padding: 12px 5px; 
                font-weight: 600;
                border: none; 
                border-radius: 6px; 
                margin: 0px 5px;
            }}
            QPushButton#sideBarButton:hover {{ 
                background-color: {dark_sidebar_hover_color};
            }}
            QProgressBar {{ 
                border: 1px solid {border_color};
                border-radius: 6px; 
                text-align: center; 
                background-color: #E9ECEF;
                color: {secondary_text_color};
            }}
            QProgressBar::chunk {{ 
                background-color: {primary_color};
                border-radius: 6px; 
            }}
        """)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_panel = QFrame(objectName="leftPanel")
        left_panel.setFixedWidth(60)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 15, 5, 15)
        left_layout.setSpacing(10)
        
        report_button = QPushButton("", objectName="sideBarButton")
        report_button.setIcon(QIcon("./source/report-icon.png"))
        report_button.setIconSize(QSize(30, 30))
        report_button.setToolTip("报告")
        report_button.clicked.connect(self.open_last_report)

        settings_button = QPushButton("", objectName="sideBarButton")
        settings_button.setIcon(QIcon("./source/settings-icon.png"))
        settings_button.setIconSize(QSize(30, 30))
        settings_button.setToolTip("设置")
        settings_button.clicked.connect(self.open_settings_dialog)

        left_layout.addStretch() 
        left_layout.addWidget(report_button)
        left_layout.addWidget(settings_button)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(25, 20, 25, 15)
        right_layout.setSpacing(15) 
        
        title = QLabel("TP-Link 自动化自测工具", objectName="titleLabel")
        right_layout.addWidget(title)
        
        self.model_info_card = QFrame(objectName="card")
        model_info_layout = QVBoxLayout(self.model_info_card)
        model_info_layout.setSpacing(15)
        model_info_layout.setContentsMargins(20, 15, 20, 20)
        model_info_layout.addWidget(QLabel("机型信息", objectName="cardTitle"))
        
        model_row1_layout = QHBoxLayout()
        model_row1_layout.addWidget(QLabel("机型名称:"))
        self.model_name_entry = QLineEdit()
        model_row1_layout.addWidget(self.model_name_entry)
        model_row1_layout.addSpacing(20)
        model_row1_layout.addWidget(QLabel("软件版本:"))
        self.software_version_entry = QLineEdit()
        model_row1_layout.addWidget(self.software_version_entry)
        model_info_layout.addLayout(model_row1_layout)
        right_layout.addWidget(self.model_info_card)

        self.settings_card = QFrame(objectName="card")
        settings_layout = QVBoxLayout(self.settings_card)
        settings_layout.setSpacing(15)
        settings_layout.setContentsMargins(20, 15, 20, 20)
        settings_layout.addWidget(QLabel("参数设置", objectName="cardTitle"))
        
        params_row1_layout = QHBoxLayout()
        params_row1_layout.addWidget(QLabel("串口端口:"))
        self.serial_port_combo = QComboBox()
        self.populate_serial_ports()
        self.serial_port_combo.setMinimumWidth(230)
        params_row1_layout.addWidget(self.serial_port_combo, 1)
        params_row1_layout.addSpacing(20)
        params_row1_layout.addWidget(QLabel("有线网卡:"))
        self.wired_adapter_combo = QComboBox()
        self.populate_network_interfaces(self.wired_adapter_combo)
        params_row1_layout.addWidget(self.wired_adapter_combo, 1)
        params_row1_layout.addSpacing(20)
        params_row1_layout.addWidget(QLabel("无线网卡:"))
        wireless_container = QWidget()
        wireless_layout = QGridLayout(wireless_container)
        wireless_layout.setContentsMargins(0, 0, 0, 0) # 去除内边距

        self.wireless_adapter_combo = QComboBox()
        self.populate_network_interfaces(self.wireless_adapter_combo)
        self.adapter_support_6g_checkbox = QCheckBox("支持6G")
        self.adapter_support_6g_checkbox.setStyleSheet("""
            QCheckBox {
             background-color: white;
                margin-right: 30px;
                padding-left: 5px
            }
        """)
        # 将下拉框和复选框都添加到布局的同一个单元格(0, 0)
        wireless_layout.addWidget(self.wireless_adapter_combo, 0, 0)
        # 将复选框对齐到单元格的右下角
        wireless_layout.addWidget(self.adapter_support_6g_checkbox, 0, 0, Qt.AlignmentFlag.AlignRight)
        
        # 将包含重叠控件的容器添加到主布局中
        params_row1_layout.addWidget(wireless_container, 1)
        # --- 结束修改 ---
        
        settings_layout.addLayout(params_row1_layout)
        right_layout.addWidget(self.settings_card)

        scripts_card = QFrame(objectName="card")
        scripts_layout = QVBoxLayout(scripts_card)
        scripts_layout.setSpacing(10)
        scripts_layout.setContentsMargins(20, 20, 20, 20)
        
        table_header_layout = QHBoxLayout()
        table_header_layout.addWidget(QLabel("脚本列表", objectName="cardTitle"))
        table_header_layout.addStretch()
        self.select_all_checkbox = QCheckBox("全选")
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        table_header_layout.addWidget(self.select_all_checkbox)
        scripts_layout.addLayout(table_header_layout)

        self.scripts_table = QTableWidget()
        self.scripts_table.setItemDelegate(NoFocusDelegate(self.scripts_table))
        self.scripts_table.setColumnCount(3)
        self.scripts_table.setHorizontalHeaderLabels(["选择", "脚本名称", "描述"])
        self.scripts_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.scripts_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.scripts_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.scripts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.scripts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.scripts_table.setShowGrid(False) 
        self.scripts_table.setAlternatingRowColors(True)
        self.scripts_table.setMinimumHeight(350)
        self.scripts_table.verticalHeader().setVisible(False)
        self.scripts_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scripts_table.verticalHeader().setStretchLastSection(True)
        scripts_layout.addWidget(self.scripts_table)
        right_layout.addWidget(scripts_card, 1)

        control_card = QFrame(objectName="card")
        control_layout = QVBoxLayout(control_card)
        control_layout.setSpacing(15)
        control_layout.setContentsMargins(20, 15, 20, 20)
        control_layout.addWidget(QLabel("执行控制", objectName="cardTitle"))
        
        status_layout = QHBoxLayout()
        self.status_label = QLabel("准备就绪")
        status_layout.addWidget(self.status_label, 1)
        self.timer_label = QLabel("执行时间: 00:00:00")
        self.timer_label.setVisible(False)
        status_layout.addWidget(self.timer_label)
        status_layout.addSpacing(20)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar, 1)
        control_layout.addLayout(status_layout)
        
        self.action_button = QPushButton("开始执行")
        self.action_button.clicked.connect(self.toggle_runner)
        control_layout.addWidget(self.action_button)
        right_layout.addWidget(control_card)

        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel, 1)
        
        self.model_name_entry.textChanged.connect(self.save_settings_silently)
        self.software_version_entry.textChanged.connect(self.save_settings_silently)
        self.serial_port_combo.currentTextChanged.connect(self.save_settings_silently)
        self.wired_adapter_combo.currentTextChanged.connect(self.save_settings_silently)
        self.wireless_adapter_combo.currentTextChanged.connect(self.save_settings_silently)
        self.adapter_support_6g_checkbox.stateChanged.connect(self.save_settings_silently)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)

    def populate_serial_ports(self):
        self.serial_port_combo.addItem("不使用")
        try:
            ports = serial.tools.list_ports.comports()
            for port in sorted(ports):
                self.serial_port_combo.addItem(port.device)
        except Exception as e:
            print(f"无法获取串口: {e}")

    def populate_network_interfaces(self, combo_box):
        combo_box.addItem("不使用")
        try:
            addrs = psutil.net_if_addrs()
            for name in sorted(addrs.keys()):
                combo_box.addItem(name)
        except Exception as e:
            print(f"无法获取网络接口: {e}")
            combo_box.addItem("获取失败")

    def update_execution_time(self):
        if self.start_time > 0:
            elapsed_seconds = int(time.time() - self.start_time)
            hours = elapsed_seconds // 3600
            minutes = (elapsed_seconds % 3600) // 60
            seconds = elapsed_seconds % 60
            self.timer_label.setText(f"执行时间: {hours:02}:{minutes:02}:{seconds:02}")

    def load_settings(self):
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.status_label.setText(f"加载配置文件失败: {e}，将使用默认设置")
                self.settings = {}
        else:
            self.settings = {}

        all_widgets = [
            self.model_name_entry, self.software_version_entry,
        ]
        for widget in all_widgets:
            widget.textChanged.disconnect(self.save_settings_silently)
        
        all_combos = [self.serial_port_combo, self.wired_adapter_combo, self.wireless_adapter_combo]
        for combo in all_combos:
            combo.currentTextChanged.disconnect(self.save_settings_silently)

        self.adapter_support_6g_checkbox.stateChanged.disconnect(self.save_settings_silently)
        self.scripts_table.itemChanged.disconnect(self.save_settings_silently)
        
        self.model_name_entry.setText(self.settings.get("model_name", "Archer AXE300"))
        self.software_version_entry.setText(self.settings.get("software_version", ""))
        self.adapter_support_6g_checkbox.setChecked(self.settings.get("adapter_support_6g", True))

        def set_combo_value(combo, key, default="不使用"):
            saved_value = self.settings.get(key, default)
            if combo.findText(saved_value) != -1:
                combo.setCurrentText(saved_value)
            else:
                combo.setCurrentText(default)
        
        set_combo_value(self.serial_port_combo, "serial_port")
        set_combo_value(self.wired_adapter_combo, "wired_adapter")
        set_combo_value(self.wireless_adapter_combo, "wireless_adapter")

        selected_scripts = self.settings.get("selected_scripts", [])
        cases = get_cases()
        self.scripts_table.setRowCount(len(cases))
        for i, case in enumerate(cases):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_item.setCheckState(Qt.CheckState.Checked if case in selected_scripts else Qt.CheckState.Unchecked)
            self.scripts_table.setItem(i, 0, check_item)
            self.scripts_table.setItem(i, 1, QTableWidgetItem(case))
            self.scripts_table.setItem(i, 2, QTableWidgetItem(get_script_description(case)))
        self.scripts_table.resizeColumnToContents(1)
        
        for widget in all_widgets:
            widget.textChanged.connect(self.save_settings_silently)
        for combo in all_combos:
            combo.currentTextChanged.connect(self.save_settings_silently)
        self.adapter_support_6g_checkbox.stateChanged.connect(self.save_settings_silently)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)

        if not os.path.exists(self.settings_path) or not self.settings:
             self.save_settings()

    def save_settings(self):
        current_disk_settings = {}
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    current_disk_settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        selected_scripts = []
        for i in range(self.scripts_table.rowCount()):
            if self.scripts_table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected_scripts.append(self.scripts_table.item(i, 1).text())
        
        def get_combo_value(combo):
            text = combo.currentText()
            return "" if text == "不使用" else text
        
        ui_settings = {
            "model_name": self.model_name_entry.text(),
            "software_version": self.software_version_entry.text(),
            "serial_port": get_combo_value(self.serial_port_combo),
            "wired_adapter": get_combo_value(self.wired_adapter_combo),
            "wireless_adapter": get_combo_value(self.wireless_adapter_combo),
            "adapter_support_6g": self.adapter_support_6g_checkbox.isChecked(),
            "selected_scripts": selected_scripts
        }
        
        current_disk_settings.update(ui_settings)
        self.settings = current_disk_settings

        try:
            full_path = os.path.abspath(self.settings_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except (IOError, TypeError) as e:
            print(f"Error saving settings to {self.settings_path}: {e}")

    def save_settings_silently(self):
        self.save_settings()

    def toggle_runner(self):
        if self.runner_thread and self.runner_thread.isRunning():
            self.stop_runner()
        else:
            self.start_runner()

    def start_runner(self):
        self.save_settings() 
        current_settings = self.settings.copy()
        start_timestamp = time.time()
        current_settings["start_time"] = start_timestamp
        selected_cases = current_settings.get("selected_scripts", [])

        if not selected_cases:
            self.status_label.setText("请至少选择一个脚本")
            return

        self.action_button.setText("停止运行")
        self.action_button.setObjectName("stopButton")
        self.action_button.style().polish(self.action_button)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.start_time = start_timestamp
        self.timer_label.setText("执行时间: 00:00:00")
        self.timer_label.setVisible(True)
        self.execution_timer.start(1000)
        self.progress_bar.setValue(1)

        self.runner_thread = RunnerThread(selected_cases, current_settings)
        self.runner_thread.status_update.connect(self.status_label.setText)
        self.runner_thread.progress_update.connect(self.progress_bar.setValue)
        self.runner_thread.finished.connect(self.on_runner_finished)
        self.runner_thread.start()

    def stop_runner(self):
        if self.runner_thread:
            self.runner_thread.stop()
            self.action_button.setText("正在停止...")
            self.action_button.setEnabled(False)
            self.execution_timer.stop()

    def on_runner_finished(self, report_path):
        self.action_button.setText("开始执行")
        self.action_button.setObjectName("")
        self.action_button.style().polish(self.action_button)
        self.action_button.setEnabled(True)
        self.execution_timer.stop()
        self.progress_bar.setVisible(False)
        self.start_time = 0

        if report_path:
            webbrowser.open(report_path)

    def toggle_select_all(self, state):
        self.scripts_table.itemChanged.disconnect(self.save_settings_silently)
        check_state = Qt.CheckState.Checked if state > 0 else Qt.CheckState.Unchecked
        for i in range(self.scripts_table.rowCount()):
            self.scripts_table.item(i, 0).setCheckState(check_state)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)
        self.save_settings_silently()

    def open_last_report(self):
        report_path = os.path.join(get_report_dir(), "result.html")
        if os.path.exists(report_path):
            url = 'file:///' + os.path.realpath(report_path).replace('\\', '/')
            webbrowser.open(url)
            self.status_label.setText(f"已打开报告: {report_path}")
        else:
            self.status_label.setText("未找到报告文件，请先运行测试")

    def open_settings_dialog(self):
        dialog = SettingsDialog(self)
        dialog.exec()
    
    def set_settings_path(self, path):
        # 路径已经由 SettingsDialog 预先验证，这里直接加载
        self.settings_path = path
        self.status_label.setText(f"已加载配置文件: {os.path.basename(path)}")
        self.load_settings()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())