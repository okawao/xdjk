import warnings
warnings.filterwarnings("ignore")
import sys
import asyncio
import requests
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                            QWidget, QPushButton, QLineEdit, QLabel, QTextEdit,
                            QRadioButton, QButtonGroup, QGroupBox, QMessageBox,
                            QProgressBar, QSplitter)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont, QIcon
from bleak import BleakScanner, BleakClient

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

class BluetoothWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, device_name, mode):
        super().__init__()
        self.device_name = device_name
        self.mode = mode
        self.device_address = None

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            self.log_signal.emit("正在搜索蓝牙设备...")
            self.progress_signal.emit(20)

            self.device_address = loop.run_until_complete(self.scan_devices())
            if not self.device_address:
                self.finished_signal.emit(False, "未找到指定设备")
                return

            self.progress_signal.emit(40)

            if self.mode == "1":
                self.log_signal.emit("正在获取设备信息...")
                data, info = loop.run_until_complete(self.read_characteristic())
                if not data or not info:
                    self.finished_signal.emit(False, "获取设备信息失败")
                    return

                self.progress_signal.emit(60)
                self.log_signal.emit("正在获取复电数据...")
                result = self.get_data(data, info)
            else:
                self.progress_signal.emit(60)
                self.log_signal.emit("正在获取初始化数据...")
                result = self.init_data()

            if not result:
                self.finished_signal.emit(False, "获取控制数据失败")
                return

            self.progress_signal.emit(80)
            self.log_signal.emit("正在启动电源...")
            loop.run_until_complete(self.connect_and_write(result))

            self.progress_signal.emit(100)
            self.finished_signal.emit(True, "操作完成")

        except Exception as e:
            self.finished_signal.emit(False, f"操作失败: {str(e)}")

    async def scan_devices(self):
        try:
            scanner = BleakScanner()
            devices = await scanner.discover()
            for device in devices:
                if device.name == self.device_name:
                    self.log_signal.emit(f"找到设备: {device.name}")
                    return device.address
            return None
        except Exception:
            return None

    async def read_characteristic(self):
        try:
            async with BleakClient(self.device_address) as client:
                services = await client.get_services()
                target_service = next(
                    (s for s in services if s.uuid == SERVICE_UUID),
                    None
                )
                if not target_service:
                    return None, None

                target_char = next(
                    (c for c in target_service.characteristics if c.uuid == CHARACTERISTIC_UUID),
                    None
                )
                if not target_char:
                    return None, None

                if "read" in target_char.properties:
                    value = await client.read_gatt_char(target_char.uuid)
                    raw_data = value.decode('ascii')
                    data_list = raw_data.split(",")
                    if len(data_list) != 13:
                        return None, None

                    result = []
                    for item in data_list:
                        key_value = item.split(":")
                        if len(key_value) == 2:
                            result.append(key_value[1])
                        else:
                            return None, None
                    return result, raw_data
                else:
                    return None, None
        except Exception:
            return None, None

    def get_data(self, data, info):
        try:
            url = "https://47.93.186.159:8887/apigetdata"
            headers = {"Content-Type": "application/json"}
            payload = {
                "data": data,
                "name": self.device_name,
                "info": info
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 403:
                self.log_signal.emit("你不是订阅用户，请联系管理员！")
                return None
            if response.status_code == 200:
                return response.text
            return None
        except Exception:
            return None

    def init_data(self):
        try:
            url = "https://47.93.186.159:8887/apiinitdata"
            params = {"name": self.device_name}
            response = requests.get(url, params=params)
            if response.status_code == 403:
                self.log_signal.emit("你不是订阅用户，请联系管理员！")
                return None
            if response.status_code == 200:
                return response.text
            return None
        except Exception:
            return None

    async def connect_and_write(self, data):
        byte_array = bytearray.fromhex(data)
        try:
            async with BleakClient(self.device_address) as client:
                await client.start_notify(CHARACTERISTIC_UUID, self.notification_handler)
                await client.write_gatt_char(CHARACTERISTIC_UUID, byte_array)
                await asyncio.sleep(2)
        except Exception:
            raise

    def notification_handler(self, sender, data):
        try:
            raw_data = data.decode('ascii')
            if len(raw_data) > 40:
                data_list = raw_data.split(",")
                parsed_data = ["0000000000"] * 50

                for i, item in enumerate(data_list):
                    key_value = item.split(":")
                    if len(key_value) > 1:
                        parsed_data[i] = key_value[1]

                url = "https://47.93.186.159:8887/apideviceinfo"
                json_data = {
                    "name": self.device_name,
                    "info": parsed_data[18]
                }
                requests.post(url, json=json_data)
                self.log_signal.emit(f"设备版本: {parsed_data[18]}")
        except Exception:
            self.log_signal.emit("解析设备信息出错")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.worker = None

    def init_ui(self):
        self.setWindowTitle("蓝牙设备控制器")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # 标题和说明
        title_label = QLabel("蓝牙设备控制器")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        info_label = QLabel("""注意事项：
1. 正常复电请选择模式: 复电
2. 第一次使用时选择模式: 初始化设备
3. 注意用电安全""")
        info_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        main_layout.addWidget(info_label)

        # 设备名称输入
        device_group = QGroupBox("设备信息")
        device_layout = QVBoxLayout()
        device_group.setLayout(device_layout)

        device_name_layout = QHBoxLayout()
        device_name_layout.addWidget(QLabel("设备名称:"))
        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("请输入设备名称（通常为二维码下面的字符）")
        device_name_layout.addWidget(self.device_name_edit)
        device_layout.addLayout(device_name_layout)

        main_layout.addWidget(device_group)

        # 运行模式选择
        mode_group = QGroupBox("运行模式")
        mode_layout = QVBoxLayout()
        mode_group.setLayout(mode_layout)

        self.mode_group = QButtonGroup()
        self.power_restore_radio = QRadioButton("复电")
        self.init_device_radio = QRadioButton("初始化设备")
        self.power_restore_radio.setChecked(True)

        self.mode_group.addButton(self.power_restore_radio, 1)
        self.mode_group.addButton(self.init_device_radio, 2)

        mode_layout.addWidget(self.power_restore_radio)
        mode_layout.addWidget(self.init_device_radio)

        main_layout.addWidget(mode_group)

        # 控制按钮
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.start_button.clicked.connect(self.start_operation)
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; padding: 10px; font-size: 14px; }")

        self.stop_button = QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_operation)
        self.stop_button.setEnabled(False)
        self.stop_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; padding: 10px; font-size: 14px; }")

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # 日志显示区域
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout()
        log_group.setLayout(log_layout)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)

        clear_button = QPushButton("清空日志")
        clear_button.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_button)

        main_layout.addWidget(log_group)

        # 状态栏
        self.statusBar().showMessage("就绪")

        # 设置样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                border: none;
                border-radius: 5px;
                padding: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                opacity: 0.8;
            }
            QLineEdit {
                padding: 8px;
                border: 2px solid #ddd;
                border-radius: 5px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border-color: #4CAF50;
            }
        """)

    def log_message(self, message):
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def clear_log(self):
        self.log_text.clear()

    def start_operation(self):
        device_name = self.device_name_edit.text().strip()
        if not device_name:
            QMessageBox.warning(self, "警告", "请输入设备名称！")
            return

        mode = "1" if self.power_restore_radio.isChecked() else "2"
        mode_text = "复电" if mode == "1" else "初始化设备"

        self.log_message(f"开始操作：{mode_text}")
        self.log_message(f"设备名称：{device_name}")

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("正在执行...")

        self.worker = BluetoothWorker(device_name, mode)
        self.worker.log_signal.connect(self.log_message)
        self.worker.progress_signal.connect(self.progress_bar.setValue)
        self.worker.finished_signal.connect(self.operation_finished)
        self.worker.start()

    def stop_operation(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            self.log_message("操作已停止")
            self.operation_finished(False, "操作被用户停止")

    def operation_finished(self, success, message):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setVisible(False)

        if success:
            self.log_message(f"✅ {message}")
            self.statusBar().showMessage("操作成功完成")
            QMessageBox.information(self, "成功", "电源启动成功！")
        else:
            self.log_message(f"❌ {message}")
            self.statusBar().showMessage("操作失败")
            QMessageBox.critical(self, "错误", message)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(self, '确认退出', '操作正在进行中，确定要退出吗？',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.terminate()
                self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

def main():
    app = QApplication(sys.argv)

    # 设置应用程序信息
    app.setApplicationName("蓝牙设备控制器")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("YDJK")

    # 创建主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()