import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser

#  第三方库导入
import psutil
import serial.tools.list_ports
from jinja2 import Environment, FileSystemLoader

#  PyQt6 库导入
from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                             QStackedWidget, QStyle, QStyledItemDelegate,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)


# =====================================================================================================================
#  自定义控件与委托
# =====================================================================================================================
class NoFocusDelegate(QStyledItemDelegate):
    """ 一个表格委托，用于移除单元格被选中时的虚线框。""" 
    def paint(self, painter, option, index):
        if option.state & QStyle.StateFlag.State_HasFocus:
            option.state = option.state & ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, option, index)


class ClickableLineEdit(QLineEdit):
    """ 一个可以发出点击信号的 QLineEdit。""" 
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DoubleClickLineEdit(QLineEdit):
    """ 一个需要双击才能进入编辑状态的 QLineEdit。""" 
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setReadOnly(True)
        self.setFrame(False)
        self.setStyleSheet("DoubleClickLineEdit { background-color: transparent; }")
        self.editingFinished.connect(self.on_editing_finished)

    def mouseDoubleClickEvent(self, event):
        """ 双击时，设置为可编辑状态。""" 
        self.setReadOnly(False)
        self.setFrame(True)
        self.setStyleSheet("")  # 恢复默认样式以显示边框
        self.selectAll()
        self.setFocus()
        super().mouseDoubleClickEvent(event)

    def on_editing_finished(self):
        """ 编辑完成后，恢复为只读状态。""" 
        self.setReadOnly(True)
        self.setFrame(False)
        self.setStyleSheet("DoubleClickLineEdit { background-color: transparent; }")
        self.deselect()


# =====================================================================================================================
#  其他参数设置页面
# =====================================================================================================================
class OtherSettingsPage(QWidget):
    """ 用于显示和编辑非主要UI参数的页面。""" 
    MAIN_UI_KEYS = {
        "model_name", "software_version", "img_file", "serial_port",
        "wired_adapter", "wireless_adapter", "adapter_support_6g", "selected_scripts"
    }

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._setup_ui()

    def _setup_ui(self):
        """ 初始化UI组件。""" 
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 20, 25, 15)
        layout.setSpacing(10)

        # 顶部标题和返回按钮
        top_header_layout = QHBoxLayout()
        title_label = QLabel("其他参数设置", objectName="titleLabel")
        top_header_layout.addWidget(title_label)
        top_header_layout.addStretch()
        back_button = QPushButton(" 返回主页")
        back_button.setIcon(QIcon("./source/back.png"))
        back_button.setObjectName("subtleTextButton")
        back_button.setToolTip("返回主页")
        back_button.setIconSize(QSize(16, 16))
        back_button.clicked.connect(lambda: self.main_window.stacked_widget.setCurrentIndex(0))
        top_header_layout.addWidget(back_button)
        layout.addLayout(top_header_layout)

        # 第二行标题和添加按钮
        second_header_layout = QHBoxLayout()
        self.card_title = QLabel("自定义参数列表", objectName="cardTitle")
        self.card_title.setStyleSheet("padding-left: 5px;")
        second_header_layout.addWidget(self.card_title)
        second_header_layout.addStretch()
        add_button = QPushButton()
        add_button.setIcon(QIcon("./source/add.png"))
        add_button.setObjectName("iconButton")
        add_button.setToolTip("直接添加一个新的参数条目")
        add_button.setFixedSize(30, 30)
        add_button.setIconSize(QSize(20, 20))
        add_button.clicked.connect(self.add_parameter)
        second_header_layout.addWidget(add_button)
        layout.addLayout(second_header_layout)

        # 参数列表滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("card")
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.params_container = QWidget()
        self.params_container.setStyleSheet("background-color: transparent;")

        self.params_grid = QGridLayout(self.params_container)
        self.params_grid.setContentsMargins(15, 15, 15, 15)
        self.params_grid.setHorizontalSpacing(10)
        self.params_grid.setVerticalSpacing(15)
        self.params_grid.setColumnStretch(0, 1)
        self.params_grid.setColumnStretch(2, 4)

        self.scroll_area.setWidget(self.params_container)
        layout.addWidget(self.scroll_area)
        layout.addStretch(1)

    @staticmethod
    def _value_to_string(value):
        """ 将Python值安全地转换为JSON字符串。""" 
        if value is None:
            return "null"
        try:
            return json.dumps(value)
        except TypeError:
            return str(value)

    def _clear_grid_layout(self):
        """ 清空网格布局中的所有小部件。""" 
        while self.params_grid.count():
            item = self.params_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def update_dynamic_height(self):
        """ 根据条目数量精确计算并设置卡片高度。""" 
        num_rows = 0
        for i in range(self.params_grid.rowCount()):
            if self.params_grid.itemAtPosition(i, 0) is not None:
                num_rows += 1
        
        # Changed: 移除了隐藏标题的逻辑，现在标题永远可见
        if num_rows == 0:
            # 当没有参数时，显示一个较小的固定高度卡片
            self.scroll_area.setMinimumHeight(120)
            self.scroll_area.setMaximumHeight(120)
        else:
            # --- 常量定义 ---
            # base_padding: 卡片上下边距和标题等基本高度
            # row_height: 每个参数条目大约占用的高度
            # max_visible_rows: 在出现滚动条前，最多显示的条目数
            base_padding = 40
            row_height = 52
            max_visible_rows = 15

            # --- 高度计算 ---
            target_height = base_padding + (num_rows * row_height)
            max_height = base_padding + (max_visible_rows * row_height)
            final_height = min(target_height, max_height)

            # --- 设置高度 ---
            # 同时设置最小和最大高度为一个固定值，以精确控制尺寸
            self.scroll_area.setMinimumHeight(final_height)
            self.scroll_area.setMaximumHeight(final_height)

    def load_other_settings(self):
        """ 从主窗口的设置中加载所有“其他”参数并显示。""" 
        self._clear_grid_layout()
        settings = self.main_window.settings
        other_params = {k: v for k, v in settings.items() if k not in self.MAIN_UI_KEYS}
        param_keys = list(other_params.keys())

        last_row_index = 0
        for i, key in enumerate(param_keys):
            value = other_params[key]
            last_row_index = i

            # 创建 Key, :, Value 和 Delete 按钮
            key_editor = DoubleClickLineEdit(key)
            colon_label = QLabel(":")
            colon_label.setFixedWidth(10)
            colon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value_editor = QLineEdit(self._value_to_string(value))
            delete_button = QPushButton()
            delete_button.setIcon(QIcon("./source/delete.png"))
            delete_button.setObjectName("iconButton")
            delete_button.setToolTip(f"删除参数 '{key}'")
            delete_button.setFixedSize(32, 32)
            delete_button.setIconSize(QSize(18, 18))
            
            value_container = QWidget()
            value_hbox = QHBoxLayout(value_container)
            value_hbox.setContentsMargins(0, 0, 0, 0)
            value_hbox.setSpacing(5)
            value_hbox.addWidget(value_editor, 1)
            value_hbox.addWidget(delete_button)

            # 连接信号和槽
            key_editor.editingFinished.connect(
                lambda old_key=key, editor=key_editor: self.update_parameter_key(old_key, editor)
            )
            value_editor.editingFinished.connect(
                lambda k_editor=key_editor, v_editor=value_editor: self.update_setting(k_editor, v_editor)
            )
            delete_button.clicked.connect(
                lambda checked=False, key_to_delete=key: self.delete_parameter(key_to_delete)
            )

            # 将小部件添加到网格
            self.params_grid.addWidget(key_editor, i, 0)
            self.params_grid.addWidget(colon_label, i, 1)
            self.params_grid.addWidget(value_container, i, 2)
        
        # 在列表末尾添加一个弹簧，将所有条目推到顶部
        self.params_grid.setRowStretch(last_row_index + 1, 1)
        
        # 每次加载后都更新卡片高度
        self.update_dynamic_height()

    def add_parameter(self):
        """ 添加一个新的参数条目。""" 
        i = 1
        while True:
            new_key = f"new_param_{i}"
            if new_key not in self.main_window.settings:
                break
            i += 1
        
        self.main_window.settings[new_key] = None
        self.main_window.save_settings_silently()
        self.load_other_settings()
        self.main_window.status_label.setText(f"已添加新条目: '{new_key}', 请修改。")

    def delete_parameter(self, key_to_delete):
        """ 删除指定的参数条目。""" 
        if key_to_delete in self.main_window.settings:
            del self.main_window.settings[key_to_delete]
            self.main_window.save_settings_silently()
            self.load_other_settings()
            self.main_window.status_label.setText(f"已删除参数: '{key_to_delete}'")

    def update_parameter_key(self, old_key, key_editor):
        """ 当参数的键被修改时调用。""" 
        new_key = key_editor.text().strip()

        if not new_key or new_key == old_key:
            key_editor.setText(old_key)
            return

        if new_key in self.main_window.settings or new_key in self.MAIN_UI_KEYS:
            self.main_window.status_label.setText(f"错误: 参数名 '{new_key}' 已存在或为保留字!")
            key_editor.setText(old_key)
            return
        
        # 重建设置字典以保留顺序
        new_settings = {}
        for k, v in self.main_window.settings.items():
            if k == old_key:
                new_settings[new_key] = v
            else:
                new_settings[k] = v
        self.main_window.settings = new_settings
        
        self.main_window.save_settings_silently()
        self.load_other_settings()
        self.main_window.status_label.setText(f"参数 '{old_key}' 已重命名为 '{new_key}'")

    def update_setting(self, key_editor, value_editor):
        """ 当参数的值被修改时调用。""" 
        key = key_editor.text()
        if key not in self.main_window.settings:
            return
            
        new_text_value = value_editor.text()
        
        try:
            # 尝试将值解析为JSON（例如数字、布尔值、列表）
            new_typed_value = json.loads(new_text_value)
        except json.JSONDecodeError:
            # 如果解析失败，则将其视为普通字符串
            new_typed_value = new_text_value

        self.main_window.settings[key] = new_typed_value
        self.main_window.save_settings_silently()
        self.main_window.status_label.setText(f"参数 '{key}' 的值已更新")


# =====================================================================================================================
#  测试脚本执行逻辑
# =====================================================================================================================
def get_script_description(case_script):
    """ 从测试脚本文件中提取 __brief__ 描述。""" 
    try:
        script_name = os.path.splitext(case_script)[0]
        script_path = os.path.join(os.getcwd(), "case", case_script, f"{script_name}.py")
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'\s*__brief__\s*=\s*["\'](.*?)["\']', content)
                if match:
                    return match.group(1).strip()
    except Exception as e:
        print(f"读取 {case_script} 的 __brief__ 时出错: {e}")
    return "暂无脚本描述"


def get_report_dir():
    """ 获取报告存放的根目录。""" 
    return os.path.join(os.getcwd(), "result")


def get_log_dir(case, device, log_base_dir):
    """ 根据用例和设备生成一个安全的日志目录路径。""" 
    safe_device_name = device.replace(":", "_").replace(".", "_")
    log_dir = os.path.join(log_base_dir, case.replace(".air", ".log"), safe_device_name)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def get_cases():
    """ 从 'case' 文件夹获取所有测试用例。""" 
    case_dir = os.path.join(os.getcwd(), "case")
    if not os.path.isdir(case_dir):
        return []
    return sorted([name for name in os.listdir(case_dir)])


class RunnerThread(QThread):
    """ 在一个单独的线程中运行Airtest测试脚本。""" 
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
        """ 线程的主执行函数。""" 
        report_dir = get_report_dir()
        log_base_dir = os.path.join(report_dir, 'log')
        
        # 1. 清理旧的报告目录
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

        # 2. 依次运行所有选定的用例
        try:
            results_data = []
            total_cases = len(self.cases)
            for i, case in enumerate(self.cases):
                if not self.running:
                    break
                self.status_update.emit(f"正在运行: {case} ({i+1}/{total_cases})")
                case_results = {'script': case, 'tests': {}}
                
                # 在指定设备上运行单个用例
                tasks = self.run_on_devices(case, ["web_device_1"], log_base_dir)
                
                for task in tasks:
                    if not self.running:
                        break
                    # 等待子进程完成
                    while task['process'].poll() is None:
                        if not self.running:
                            task['process'].terminate()
                            break
                        time.sleep(0.1)
                    if not self.running:
                        break
                    
                    # 确保子进程被彻底清理
                    try:
                        task['process'].communicate(timeout=5)
                    except subprocess.TimeoutExpired:
                        task['process'].kill()
                        task['process'].communicate()
                    
                    status = task['process'].returncode
                    
                    # 为该次运行生成报告
                    report_info = self.run_one_report(task['case'], task['dev'], log_base_dir)
                    report_info['status'] = status if status is not None else -1
                    case_results['tests'][task['dev']] = report_info
                
                results_data.append(case_results)
                self.progress_update.emit(int(((i + 1) / total_cases) * 100))

            # 3. 生成最终的总结报告
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
        """ 为单个用例启动一个或多个Airtest子进程。""" 
        tasks = []
        case_name = os.path.splitext(case)[0]
        case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
        for dev in devices:
            log_dir = get_log_dir(case, dev, log_base_dir)
            cmd = ["airtest", "run", case_path, "--log", log_dir, "--recording"]
            try:
                is_windows = (os.name == 'nt')
                creation_flags = subprocess.CREATE_NO_WINDOW if is_windows else 0
                process = subprocess.Popen(
                    cmd,
                    cwd=os.getcwd(),
                    shell=is_windows,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=creation_flags
                )
                self.process_list.append(process)
                tasks.append({'process': process, 'dev': dev, 'case': case})
            except Exception:
                traceback.print_exc()
        return tasks

    def run_one_report(self, case, dev, log_base_dir):
        """ 为单次用例运行生成HTML报告。""" 
        log_dir = get_log_dir(case, dev, log_base_dir)
        log_txt = os.path.join(log_dir, 'log.txt')
        case_name = os.path.splitext(case)[0]
        case_path = os.path.join(os.getcwd(), "case", case, f"{case_name}.py")
        
        # 等待日志文件可读
        for attempt in range(5):
            if os.path.isfile(log_txt):
                try:
                    with open(log_txt, 'r', encoding='utf-8') as f:
                        f.read(1)
                    break
                except (PermissionError, IOError):
                    if attempt < 4:
                        time.sleep(0.5)
                    else:
                        return {'status': -1, 'path': ''}
            else:
                time.sleep(0.5)

        if not os.path.isfile(log_txt):
            return {'status': -1, 'path': ''}
        
        # 调用Airtest命令生成报告
        try:
            report_path = os.path.join(log_dir, 'log.html')
            cmd = [
                "airtest", "report", case_path,
                "--log_root", log_dir,
                "--outfile", report_path,
                "--lang", "zh",
                "--plugin", "airtest_selenium.report"
            ]
            is_windows = (os.name == 'nt')
            report_process = subprocess.Popen(
                cmd,
                shell=is_windows,
                cwd=os.getcwd(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            report_process.communicate(timeout=60)
            
            relative_path = os.path.join("log", case_name + '.log', dev, 'log.html').replace('\\', '/')
            return {'status': 0, 'path': relative_path}
        except Exception:
            traceback.print_exc()
            return {'status': -1, 'path': ''}

    def run_summary(self, data, start_time):
        """ 使用Jinja2模板生成最终的总结报告。""" 
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
        """ 停止线程和所有由它创建的子进程。"""
        self.running = False
        

        for p in self.process_list:
            if p.poll() is None:
                try:
                    # 在 Windows 上, 由于使用了 shell=True, airtest 进程是 cmd.exe 的子进程。
                    # 使用 taskkill 命令可以最可靠地终止整个进程树。
                    # /F 表示强制终止, /T 表示终止进程树。
                    subprocess.run(
                        f"taskkill /F /T /PID {p.pid}",
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )

                except (subprocess.CalledProcessError, psutil.NoSuchProcess, ProcessLookupError):
                    pass
        self.process_list.clear()

# =====================================================================================================================
#  设置对话框
# =====================================================================================================================
class SettingsDialog(QDialog):
    """ 设置对话框，提供导入/导出配置等功能。""" 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self):
        """ 初始化对话框UI。""" 
        primary_color = "#4F46E5"
        primary_hover_color = "#4338CA"
        self.setStyleSheet(f""" 
            QDialog, QLabel, QCheckBox {{ 
                font-size: 14px; 
                font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; 
            }}
            QPushButton {{ 
                background-color: {primary_color}; 
                color: #fff; border: none; 
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
        """ )
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        self.hide_params_checkbox = QCheckBox("隐藏主界面的参数设置面板")
        self.hide_params_checkbox.setChecked(not self.main_window.settings_card.isVisible())
        self.hide_params_checkbox.stateChanged.connect(self.toggle_params_card)
        layout.addWidget(self.hide_params_checkbox)

        config_layout = QHBoxLayout()
        import_button = QPushButton("导入配置...")
        import_button.clicked.connect(self.import_config_file)
        export_button = QPushButton("保存配置...")
        export_button.clicked.connect(self.export_config_file)
        config_layout.addWidget(import_button)
        config_layout.addWidget(export_button)
        layout.addLayout(config_layout)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red; font-size: 12px;")
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)
        layout.addStretch()

    def toggle_params_card(self, state):
        """ 切换主界面参数面板的可见性。""" 
        is_checked = (state == Qt.CheckState.Checked.value)
        self.main_window.settings_card.setVisible(not is_checked)

    def import_config_file(self):
        """ 导入JSON配置文件。""" 
        self.error_label.setVisible(False)
        file_path, _ = QFileDialog.getOpenFileName(self, "选择要导入的配置文件", "", "JSON Files (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                imported_settings = json.load(f)

            current_settings = self.main_window.settings
            other_params_keys = [k for k in current_settings if k not in self.main_window.MAIN_UI_KEYS]
            for k in other_params_keys:
                del current_settings[k]

            current_settings.update(imported_settings)
            
            self.main_window.populate_ui_from_settings()
            self.main_window.select_all_checkbox.setChecked(False)
            self.main_window.save_settings_silently()
            self.main_window.status_label.setText(f"已成功导入配置: {os.path.basename(file_path)}")
            self.close()
        except (json.JSONDecodeError, IOError):
            self.error_label.setText("导入失败，请选择有效的JSON文件")
            self.error_label.setVisible(True)
    
    def export_config_file(self):
        """ 导出用户自定义的参数到JSON文件。""" 
        self.error_label.setVisible(False)
        self.main_window.save_settings_silently()
        model_name = self.main_window.settings.get("model_name", "model")
        version = self.main_window.settings.get("software_version", "version")
        default_filename = f"{model_name}_{version}_setting.json"
        
        file_path, _ = QFileDialog.getSaveFileName(self, "导出配置文件", default_filename, "JSON Files (*.json)")
        if not file_path:
            return
        try:
            # 导出时只导出自定义参数
            other_params = {
                k: v for k, v in self.main_window.settings.items() 
                if k not in self.main_window.MAIN_UI_KEYS
            }
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(other_params, f, indent=2, ensure_ascii=False)
            self.main_window.status_label.setText(f"配置已导出至: {os.path.basename(file_path)}")
            self.close()
        except IOError as e:
            self.error_label.setText(f"导出失败: {e}")
            self.error_label.setVisible(True)


# =====================================================================================================================
#  主应用程序界面
# =====================================================================================================================
class App(QWidget):
    """ 应用程序的主窗口。""" 
    def __init__(self):
        super().__init__()
        self.settings = {}
        self.settings_path = "setting.json"
        self.runner_thread = None
        self.start_time = 0
        self.MAIN_UI_KEYS = OtherSettingsPage.MAIN_UI_KEYS

        self.execution_timer = QTimer(self)
        self.execution_timer.timeout.connect(self.update_execution_time)
        
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """ 初始化主窗口UI。""" 
        self.setWindowTitle("自动化自测工具")
        self.setWindowIcon(QIcon("./source/logo.png"))
        self.setGeometry(100, 100, 1000, 720)
        
        self._set_stylesheet()
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建并添加左侧边栏
        left_panel = self._create_left_panel()
        main_layout.addWidget(left_panel)

        # 创建主页面和参数页面
        main_page = self._create_main_page()
        self.other_settings_page = OtherSettingsPage(self)
        
        # 使用 QStackedWidget 进行页面切换
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(main_page)
        self.stacked_widget.addWidget(self.other_settings_page)
        main_layout.addWidget(self.stacked_widget, 1)

        # 连接信号
        self.stacked_widget.currentChanged.connect(self.on_page_changed)
        self._connect_signals()

    def _set_stylesheet(self):
        """ 设置全局QSS样式表。""" 
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
            QLabel {{ font-size: 14px; background-color: transparent; }}
            QCheckBox {{ background-color: transparent; }}
            QLabel#titleLabel {{
                font-size: 24px; font-weight: 600; color: {text_color};
                padding-bottom: 5px;
            }}
            QLabel#cardTitle {{
                font-size: 16px; font-weight: 600;
                color: {text_color};
            }}
            QLineEdit, QComboBox {{
                background-color: {card_bg_color};
                border: 1px solid {border_color};
                border-radius: 6px; padding: 8px; font-size: 14px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border-color: {primary_color}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right;
                width: 20px; border-left-width: 1px;
                border-left-color: {border_color}; border-left-style: solid;
                border-top-right-radius: 6px; border-bottom-right-radius: 6px;
            }}
            QComboBox::down-arrow {{ image: url(./source/down-arrow.png); }}
            QTableWidget {{
                background-color: {card_bg_color}; border: none;
                gridline-color: {border_color}; font-size: 14px;
                alternate-background-color: #F8F9FA;
                selection-background-color: #E6E6FA;
                selection-color: {text_color};
            }}
            QTableWidget::item {{
                padding: 12px 10px;
                border-bottom: 1px solid #F1F3F5;
            }}
            QTableWidget::item:selected {{ background-color: #E9EBF8; }}
            QTableWidget::item:focus {{ outline: none; }}
            QHeaderView::section {{
                background-color: #F8F9FA; padding: 10px; border: none;
                border-bottom: 1px solid {border_color};
                font-weight: 600; font-size: 14px;
            }}
            QPushButton {{
                background-color: {primary_color};
                color: #fff; border: none; padding: 10px 20px;
                border-radius: 6px; font-size: 14px;
                font-weight: 500; min-height: 20px;
            }}
            QPushButton:hover {{ background-color: {primary_hover_color}; }}
            QPushButton:disabled {{
                background-color: #E9ECEF; color: {secondary_text_color};
            }}
            QPushButton#stopButton {{ background-color: {stop_button_color}; }}
            QPushButton#stopButton:hover {{ background-color: {stop_button_hover_color}; }}
            QPushButton#iconButton, QPushButton#iconTextButton {{
                background-color: transparent; border: none; padding: 5px;
            }}
            QPushButton#iconTextButton {{
                color: {secondary_text_color}; font-size: 14px;
            }}
            QPushButton#iconButton:hover, QPushButton#iconTextButton:hover {{
                background-color: #E9ECEF; border-radius: 4px;
            }}
            QPushButton#subtleTextButton {{
                background-color: transparent; color: {secondary_text_color};
                font-size: 14px; border: 1px solid {border_color};
                padding: 4px 10px; border-radius: 5px;
            }}
            QPushButton#subtleTextButton:hover {{
                background-color: #E9ECEF; border-color: #ADB5BD;
            }}
            QFrame#leftPanel {{
                background-color: {dark_sidebar_color};
                border-right: 1px solid #252525;
            }}
            QPushButton#sideBarButton {{
                background-color: transparent; color: #D0D0D0;
                text-align: center; padding: 12px 5px;
                font-weight: 600; border: none;
                border-radius: 6px; margin: 0px 5px;
            }}
            QPushButton#sideBarButton:hover {{ background-color: {dark_sidebar_hover_color}; }}
            QProgressBar {{
                border: 1px solid {border_color}; border-radius: 6px;
                text-align: center; background-color: #E9ECEF;
                color: {secondary_text_color};
            }}
            QProgressBar::chunk {{
                background-color: {primary_color};
                border-radius: 6px;
            }}
        """ )

    def _create_left_panel(self):
        """ 创建左侧的图标按钮侧边栏。""" 
        left_panel = QFrame(objectName="leftPanel")
        left_panel.setFixedWidth(60)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 15, 5, 15)
        left_layout.setSpacing(10)

        main_page_button = QPushButton("", objectName="sideBarButton")
        main_page_button.setIcon(QIcon("./source/logo1.png"))
        main_page_button.setIconSize(QSize(30, 30))
        main_page_button.setToolTip("测试主页")
        main_page_button.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        


        self.params_icon = QIcon("./source/params-icon.png")
        self.home_icon = QIcon("./source/home.png")
        self.other_settings_button = QPushButton("", objectName="sideBarButton")
        self.other_settings_button.setIcon(self.params_icon)
        self.other_settings_button.setIconSize(QSize(30, 30))
        self.other_settings_button.setToolTip("参数")
        self.other_settings_button.clicked.connect(self.toggle_other_settings_page)

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
        
        left_layout.addWidget(main_page_button)
        left_layout.addStretch() 
        left_layout.addWidget(self.other_settings_button)
        left_layout.addWidget(report_button)
        left_layout.addWidget(settings_button)
        
        return left_panel

    def _create_main_page(self):
        """ 创建主内容页面。""" 
        main_page = QWidget()
        right_layout = QVBoxLayout(main_page)
        right_layout.setContentsMargins(25, 20, 25, 15)
        right_layout.setSpacing(15) 
        
        title = QLabel("TP-Link 自动化自测工具", objectName="titleLabel")
        right_layout.addWidget(title)
        
        # 机型信息卡片
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
        model_row2_layout = QHBoxLayout()
        model_row2_layout.addWidget(QLabel("软件路径:"))
        self.img_file_entry = ClickableLineEdit()
        self.img_file_entry.setReadOnly(True)
        self.img_file_entry.setPlaceholderText("点击选择文件夹...")
        model_row2_layout.addWidget(self.img_file_entry)
        model_info_layout.addLayout(model_row2_layout)
        right_layout.addWidget(self.model_info_card)

        # 参数设置卡片
        self.settings_card = QFrame(objectName="card")
        settings_layout = QVBoxLayout(self.settings_card)
        settings_layout.setSpacing(15)
        settings_layout.setContentsMargins(20, 15, 20, 20)
        settings_layout.addWidget(QLabel("参数设置", objectName="cardTitle"))
        params_row1_layout = QHBoxLayout()
        params_row1_layout.addWidget(QLabel("串口端口:"))
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setMinimumWidth(230)
        params_row1_layout.addWidget(self.serial_port_combo, 1)
        params_row1_layout.addSpacing(20)
        params_row1_layout.addWidget(QLabel("有线网卡:"))
        self.wired_adapter_combo = QComboBox()
        params_row1_layout.addWidget(self.wired_adapter_combo, 1)
        params_row1_layout.addSpacing(20)
        params_row1_layout.addWidget(QLabel("无线网卡:"))
        wireless_container = QWidget()
        wireless_layout = QGridLayout(wireless_container)
        wireless_layout.setContentsMargins(0, 0, 0, 0)
        self.wireless_adapter_combo = QComboBox()
        self.adapter_support_6g_checkbox = QCheckBox("支持6G")
        self.adapter_support_6g_checkbox.setStyleSheet("background-color: white; margin-right: 25px; padding-left: 2px")
        wireless_layout.addWidget(self.wireless_adapter_combo, 0, 0)
        wireless_layout.addWidget(self.adapter_support_6g_checkbox, 0, 0, Qt.AlignmentFlag.AlignRight)
        params_row1_layout.addWidget(wireless_container, 1)
        settings_layout.addLayout(params_row1_layout)
        right_layout.addWidget(self.settings_card)
        self.populate_serial_ports()
        self.populate_network_interfaces(self.wired_adapter_combo)
        self.populate_network_interfaces(self.wireless_adapter_combo)

        # 脚本列表卡片
        scripts_card = QFrame(objectName="card")
        scripts_layout = QVBoxLayout(scripts_card)
        scripts_layout.setSpacing(10)
        scripts_layout.setContentsMargins(20, 20, 20, 20)
        table_header_layout = QHBoxLayout()
        table_header_layout.addWidget(QLabel("脚本列表", objectName="cardTitle"))
        table_header_layout.addStretch()
        self.select_all_checkbox = QCheckBox("全选")
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
        scripts_layout.addWidget(self.scripts_table)
        right_layout.addWidget(scripts_card, 1)

        # 执行控制卡片
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
        control_layout.addWidget(self.action_button)
        right_layout.addWidget(control_card)

        return main_page

    def _connect_signals(self):
        """ 集中连接所有UI组件的信号和槽。""" 
        # 主页面输入变化的保存
        self.model_name_entry.textChanged.connect(self.save_settings_silently)
        self.software_version_entry.textChanged.connect(self.save_settings_silently)
        self.img_file_entry.textChanged.connect(self.save_settings_silently)
        self.serial_port_combo.currentTextChanged.connect(self.save_settings_silently)
        self.wired_adapter_combo.currentTextChanged.connect(self.save_settings_silently)
        self.wireless_adapter_combo.currentTextChanged.connect(self.save_settings_silently)
        self.adapter_support_6g_checkbox.stateChanged.connect(self.save_settings_silently)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)

        # 按钮点击
        self.img_file_entry.clicked.connect(self.browse_img_file_path)
        self.select_all_checkbox.stateChanged.connect(self.toggle_select_all)
        self.action_button.clicked.connect(self.toggle_runner)

    def on_page_changed(self, index):
        """ 当页面切换时，改变参数按钮的图标和提示。""" 
        if index == 1:
            self.other_settings_button.setIcon(self.home_icon)
            self.other_settings_button.setToolTip("返回主页")
        else:
            self.other_settings_button.setIcon(self.params_icon)
            self.other_settings_button.setToolTip("参数")

    def toggle_other_settings_page(self):
        """ 切换主页和参数设置页面。""" 
        current_index = self.stacked_widget.currentIndex()
        self.stacked_widget.setCurrentIndex(1 - current_index)

    def browse_img_file_path(self):
        """ 打开文件夹选择对话框以选择软件路径。""" 
        directory = QFileDialog.getExistingDirectory(self, "选择软件文件夹")
        if directory:
            self.img_file_entry.setText(directory)

    def populate_serial_ports(self):
        """ 填充串口下拉框。""" 
        self.serial_port_combo.addItem("不使用")
        try:
            ports = serial.tools.list_ports.comports()
            for port in sorted(ports):
                self.serial_port_combo.addItem(port.device)
        except Exception as e:
            print(f"无法获取串口: {e}")

    def populate_network_interfaces(self, combo_box):
        """ 填充网卡下拉框。""" 
        combo_box.addItem("不使用")
        try:
            addrs = psutil.net_if_addrs()
            for name in sorted(addrs.keys()):
                combo_box.addItem(name)
        except Exception as e:
            print(f"无法获取网络接口: {e}")
            combo_box.addItem("获取失败")

    def update_execution_time(self):
        """ 更新执行计时器标签。""" 
        if self.start_time > 0:
            elapsed_seconds = int(time.time() - self.start_time)
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.timer_label.setText(f"执行时间: {hours:02}:{minutes:02}:{seconds:02}")

    def load_settings(self):
        """ 从 setting.json 加载设置。""" 
        if os.path.exists(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.status_label.setText(f"加载配置文件失败: {e}，将使用默认设置")
                self.settings = {}
        else:
            self.settings = {}
        
        self.populate_ui_from_settings()
        if not os.path.exists(self.settings_path) or not self.settings:
            self.save_settings_silently()

    def populate_ui_from_settings(self):
        """ 根据加载的设置填充UI界面。""" 
        # 暂时断开信号连接，以避免在填充UI时触发不必要的保存操作
        all_widgets = [self.model_name_entry, self.software_version_entry, self.img_file_entry]
        for widget in all_widgets:
            widget.textChanged.disconnect(self.save_settings_silently)
        
        all_combos = [self.serial_port_combo, self.wired_adapter_combo, self.wireless_adapter_combo]
        for combo in all_combos:
            combo.currentTextChanged.disconnect(self.save_settings_silently)
            
        self.adapter_support_6g_checkbox.stateChanged.disconnect(self.save_settings_silently)
        self.scripts_table.itemChanged.disconnect(self.save_settings_silently)
        
        # 填充主UI
        self.model_name_entry.setText(self.settings.get("model_name", "Archer AXE300"))
        self.software_version_entry.setText(self.settings.get("software_version", ""))
        self.img_file_entry.setText(self.settings.get("img_file", ""))
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
        
        # 填充脚本列表
        selected_scripts = self.settings.get("selected_scripts", [])
        cases = get_cases()
        self.scripts_table.setRowCount(len(cases))
        for i, case in enumerate(cases):
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check_state = Qt.CheckState.Checked if case in selected_scripts else Qt.CheckState.Unchecked
            check_item.setCheckState(check_state)
            self.scripts_table.setItem(i, 0, check_item)
            self.scripts_table.setItem(i, 1, QTableWidgetItem(case))
            self.scripts_table.setItem(i, 2, QTableWidgetItem(get_script_description(case)))
        self.scripts_table.resizeColumnToContents(1)
        
        # 填充其他参数页面
        self.other_settings_page.load_other_settings()

        # 重新连接信号
        for widget in all_widgets:
            widget.textChanged.connect(self.save_settings_silently)
        for combo in all_combos:
            combo.currentTextChanged.connect(self.save_settings_silently)
        self.adapter_support_6g_checkbox.stateChanged.connect(self.save_settings_silently)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)

    def _get_main_page_settings(self):
        """ 从UI控件中收集主页面的设置。""" 
        selected_scripts = []
        for i in range(self.scripts_table.rowCount()):
            if self.scripts_table.item(i, 0).checkState() == Qt.CheckState.Checked:
                selected_scripts.append(self.scripts_table.item(i, 1).text())

        def get_combo_value(combo):
            text = combo.currentText()
            return "" if text == "不使用" else text

        return {
            "model_name": self.model_name_entry.text(),
            "software_version": self.software_version_entry.text(),
            "img_file": self.img_file_entry.text(),
            "serial_port": get_combo_value(self.serial_port_combo),
            "wired_adapter": get_combo_value(self.wired_adapter_combo),
            "wireless_adapter": get_combo_value(self.wireless_adapter_combo),
            "adapter_support_6g": self.adapter_support_6g_checkbox.isChecked(),
            "selected_scripts": selected_scripts
        }

    def save_settings(self):
        """ 保存当前设置到 setting.json。""" 
        main_page_settings = self._get_main_page_settings()
        self.settings.update(main_page_settings)
        
        try:
            full_path = os.path.abspath(self.settings_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
        except (IOError, TypeError) as e:
            print(f"保存设置失败: {e}")
            
    def save_settings_silently(self):
        """ 静默保存设置，通常由UI事件触发。""" 
        self.save_settings()

    def toggle_runner(self):
        """ 根据当前状态开始或停止测试。""" 
        if self.runner_thread and self.runner_thread.isRunning():
            self.stop_runner()
        else:
            self.start_runner()

    def start_runner(self):
        """ 开始执行测试。""" 
        self.save_settings_silently() 
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
        """ 停止正在运行的测试。""" 
        if self.runner_thread:
            self.runner_thread.stop()
            self.action_button.setText("正在停止...")
            self.action_button.setEnabled(False)
        self.execution_timer.stop()

    def on_runner_finished(self, report_path):
        """ 测试完成后恢复UI状态。""" 
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
        """ 全选或全不选所有脚本。""" 
        self.scripts_table.itemChanged.disconnect(self.save_settings_silently)
        check_state = Qt.CheckState.Checked if state > 0 else Qt.CheckState.Unchecked
        for i in range(self.scripts_table.rowCount()):
            self.scripts_table.item(i, 0).setCheckState(check_state)
        self.scripts_table.itemChanged.connect(self.save_settings_silently)
        self.save_settings_silently()

    def open_last_report(self):
        """ 在浏览器中打开最新的报告文件。""" 
        report_path = os.path.join(get_report_dir(), "result.html")
        if os.path.exists(report_path):
            url = 'file:///' + os.path.realpath(report_path).replace('\\', '/')
            webbrowser.open(url)
            self.status_label.setText(f"已打开报告: {report_path}")
        else:
            self.status_label.setText("未找到报告文件，请先运行测试")

    def open_settings_dialog(self):
        """ 打开设置对话框。""" 
        dialog = SettingsDialog(self)
        dialog.exec()


# =====================================================================================================================
#  程序入口
# =====================================================================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())