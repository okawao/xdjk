"""
蓝牙设备控制器
这是一个基于 PyQt6 和 Bleak 的蓝牙设备控制应用程序
主要功能：
1. 扫描并连接指定名称的蓝牙设备
2. 读取设备特征值并解析数据
3. 通过 API 获取控制指令
4. 向设备写入控制数据
5. 提供图形界面进行设备管理和日志查看
"""

# 忽略警告信息
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

# 导入配置文件（在构建时会被更新）
try:
    from config import API_BASE_URL, HOST_IP, HOST_PORT
    if not HOST_IP or not HOST_PORT:
        raise ValueError("配置文件中缺少必需的 HOST_IP 或 HOST_PORT")
except (ImportError, ValueError) as e:
    import sys
    print(f"❌ 配置错误: {e}")
    print("请确保在构建时设置了 HOST_IP 和 HOST_PORT 环境变量")
    sys.exit(1)

# 蓝牙 BLE 服务和特征值的 UUID
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"  # 目标服务的 UUID
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"  # 目标特征值的 UUID

class BluetoothWorker(QThread):
    """
    蓝牙操作工作线程
    在后台线程中执行蓝牙设备的扫描、连接、读写等操作
    避免阻塞主界面
    """
    # 定义信号用于与主线程通信
    log_signal = pyqtSignal(str)  # 发送日志消息
    progress_signal = pyqtSignal(int)  # 发送进度更新
    finished_signal = pyqtSignal(bool)  # 发送操作完成信号 (成功/失败, 消息)

    def __init__(self, device_name, mode):
        """
        初始化蓝牙工作线程

        参数:
            device_name: 要连接的蓝牙设备名称
            mode: 运行模式 ("1" 表示复电模式, "2" 表示初始化模式)
        """
        super().__init__()
        self.device_name = device_name  # 设备名称
        self.mode = mode  # 运行模式
        self.device_address = None  # 设备的蓝牙地址 (MAC地址)

    def run(self):
        """
        线程的主执行函数
        执行完整的设备控制流程:
        1. 扫描并查找目标设备
        2. 根据模式获取控制数据 (复电或初始化)
        3. 连接设备并写入控制指令
        """
        try:
            self.log_signal.emit("==========================================")
            # 创建新的事件循环用于异步操作
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # 步骤1: 扫描蓝牙设备
            self.log_signal.emit("正在搜索蓝牙设备...")
            self.progress_signal.emit(20)

            self.device_address = loop.run_until_complete(self.scan_devices())
            if not self.device_address:
                self.finished_signal.emit(False)
                return

            self.progress_signal.emit(40)

            # 步骤2: 根据模式获取控制数据
            if self.mode == "1":
                # 复电模式: 需要先读取设备当前信息
                self.log_signal.emit("正在获取设备信息...")
                data, info = loop.run_until_complete(self.read_characteristic())
                if not data or not info:
                    self.log_signal.emit("获取设备信息失败！")
                    self.finished_signal.emit(False)
                    return

                self.progress_signal.emit(60)
                self.log_signal.emit("正在获取复电数据...")
                result = self.get_data(data, info)
            else:
                # 初始化模式: 直接获取初始化数据
                self.progress_signal.emit(60)
                self.log_signal.emit("正在获取初始化数据...")
                result = self.init_data()

            if not result:
                self.log_signal.emit("获取数据失败！")
                self.finished_signal.emit(False)
                return

            # 步骤3: 连接设备并写入控制数据
            self.progress_signal.emit(80)
            self.log_signal.emit("正在启动电源...")
            loop.run_until_complete(self.connect_and_write(result))

            # 操作完成
            self.progress_signal.emit(100)
            self.finished_signal.emit(True)

        except Exception as e:
            self.finished_signal.emit(False)

    async def scan_devices(self):
        """
        扫描附近的蓝牙设备并查找指定名称的设备

        返回:
            str: 设备的蓝牙地址(MAC地址), 如果未找到则返回 None
        """
        try:
            scanner = BleakScanner()
            devices = await scanner.discover()  # 扫描附近的所有蓝牙设备

            # 遍历扫描到的设备，查找匹配的设备名称
            for device in devices:
                if device.name == self.device_name:
                    self.log_signal.emit(f"搜索到设备: {device.name}")
                    return device.address
            self.log_signal.emit("未找到指定设备！")
            return None
        except Exception:
            self.log_signal.emit("需要打开蓝牙功能！")
            return None

    async def read_characteristic(self):
        """
        连接到蓝牙设备并读取特征值数据

        返回:
            tuple: (解析后的数据列表, 原始数据字符串), 失败时返回 (None, None)
        """
        try:
            # 使用 BleakClient 连接到设备，增加超时时间并启用配对
            async with BleakClient(
                self.device_address, 
                timeout=30.0,  # 增加连接超时时间到30秒
                winrt=dict(use_cached_services=False)  # Windows: 不使用缓存的服务，强制重新发现
            ) as client:
                # 获取设备的所有服务
                services = await client.get_services()

                # 查找目标服务
                target_service = next(
                    (s for s in services if s.uuid == SERVICE_UUID),
                    None
                )
                if not target_service:
                    self.log_signal.emit(f"❌ 未找到目标服务: {SERVICE_UUID}")
                    return None, None

                # 在服务中查找目标特征值
                target_char = next(
                    (c for c in target_service.characteristics if c.uuid == CHARACTERISTIC_UUID),
                    None
                )
                if not target_char:
                    self.log_signal.emit(f"❌ 未找到目标特征值: {CHARACTERISTIC_UUID}")
                    return None, None

                # 检查特征值是否支持读取操作
                if "read" in target_char.properties:
                    # 读取特征值数据
                    value = await client.read_gatt_char(target_char.uuid)
                    raw_data = value.decode('ascii')  # 将字节数据解码为 ASCII 字符串

                    # 解析数据格式: "key1:value1,key2:value2,..."
                    data_list = raw_data.split(",")
                    if len(data_list) != 13:  # 预期数据应包含 13 个字段
                        self.log_signal.emit(f"数据格式错误！")
                        return None, None

                    # 提取所有值部分 (忽略键)
                    result = []
                    for item in data_list:
                        key_value = item.split(":")
                        if len(key_value) == 2:
                            result.append(key_value[1])
                        else:
                            self.log_signal.emit(f"数据项格式错误: {item}！")
                            return None, None
                    return result, raw_data
                else:
                    self.log_signal.emit(f"特征值不可读！")
                    return None, None
        except Exception as e:
            self.log_signal.emit(f"读取设备数据异常: {type(e).__name__}: {e}！")
            return None, None

    def get_data(self, data, info):
        """
        从远程 API 获取复电控制数据

        参数:
            data: 从设备读取的解析后数据列表
            info: 从设备读取的原始数据字符串

        返回:
            str: 十六进制格式的控制数据字符串, 失败时返回 None
        """
        try:
            url = f"{API_BASE_URL}/apigetdata"
            headers = {"Content-Type": "application/json"}
            payload = {
                "data": data,
                "name": self.device_name,
                "info": info
            }

            # 向 API 发送 POST 请求，传递设备信息
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code == 403:
                self.log_signal.emit("你不是订阅用户，请联系管理员！")
                return None
            if response.status_code == 429:
                self.log_signal.emit("请求过于频繁，请咨询管理员！")
                return None
            if response.status_code == 200:
                return response.text  # 返回十六进制控制数据
            return None
        except Exception:
            return None

    def init_data(self):
        """
        从远程 API 获取初始化控制数据

        返回:
            str: 十六进制格式的初始化数据字符串, 失败时返回 None
        """
        try:
            url = f"{API_BASE_URL}/apiinitdata"
            params = {"name": self.device_name}

            # 向 API 发送 GET 请求，获取初始化数据
            response = requests.get(url, params=params)

            if response.status_code == 403:
                self.log_signal.emit("你不是订阅用户，请联系管理员！")
                return None
            if response.status_code == 429:
                self.log_signal.emit("请求过于频繁，请咨询管理员！")
                return None
            if response.status_code == 200:
                return response.text  # 返回十六进制初始化数据
            return None
        except Exception:
            return None

    async def connect_and_write(self, data):
        """
        连接到蓝牙设备并写入控制数据

        参数:
            data: 十六进制格式的控制数据字符串
        """
        # 将十六进制字符串转换为字节数组
        byte_array = bytearray.fromhex(data)

        try:
            # 使用相同的连接配置，增加超时和禁用缓存
            async with BleakClient(
                self.device_address,
                timeout=30.0,
                winrt=dict(use_cached_services=False)
            ) as client:
                # 启用通知，监听设备的响应数据
                await client.start_notify(CHARACTERISTIC_UUID, self.notification_handler)

                # 向设备写入控制数据
                await client.write_gatt_char(CHARACTERISTIC_UUID, byte_array)

                # 等待 2 秒以接收设备响应
                await asyncio.sleep(2)
        except Exception:
            self.log_signal.emit("连接设备出错，请重试！")
            raise

    def notification_handler(self, sender, data):
        """
        处理从蓝牙设备接收到的通知数据

        参数:
            sender: 发送通知的特征值句柄
            data: 接收到的字节数据
        """
        try:
            # 将字节数据解码为 ASCII 字符串
            raw_data = data.decode('ascii')

            # 只处理长度超过 40 的完整数据
            if len(raw_data) > 40:
                data_list = raw_data.split(",")
                parsed_data = ["0000000000"] * 50  # 初始化 50 个元素的数组

                # 解析键值对数据
                for i, item in enumerate(data_list):
                    key_value = item.split(":")
                    if len(key_value) > 1:
                        parsed_data[i] = key_value[1]

                # 将设备版本信息上传到 API
                url = f"{API_BASE_URL}/apideviceinfo"
                json_data = {
                    "name": self.device_name,
                    "info": parsed_data[18]  # 第 18 个字段为设备版本信息
                }
                requests.post(url, json=json_data)
                self.log_signal.emit(f"设备版本: {parsed_data[18]}")
        except Exception:
            self.log_signal.emit("解析设备版本信息出错！")
            raise

class MainWindow(QMainWindow):
    """
    主窗口类
    提供蓝牙设备控制的图形用户界面
    """
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        self.init_ui()  # 初始化用户界面
        self.worker = None  # 蓝牙工作线程

    def init_ui(self):
        """
        初始化用户界面
        创建所有 UI 组件并设置布局和样式
        """
        # 设置窗口标题和大小
        self.setWindowTitle("蓝牙设备控制器")
        self.setGeometry(100, 100, 850, 650)

        # 创建中央部件和主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 15, 20, 15)
        central_widget.setLayout(main_layout)

        # # 标题标签 - 添加渐变背景和图标
        # title_container = QWidget()
        # title_container.setStyleSheet("""
        #     QWidget {
        #         background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        #             stop:0 #667eea, stop:1 #764ba2);
        #         border-radius: 8px;
        #         padding: 12px;
        #     }
        # """)
        # title_layout = QVBoxLayout()
        # title_layout.setSpacing(2)
        # title_layout.setContentsMargins(0, 0, 0, 0)
        # title_container.setLayout(title_layout)
        
        # title_label = QLabel("蓝牙设备控制器")
        # title_label.setFont(QFont("Microsoft YaHei UI", 16, QFont.Weight.Bold))
        # title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # title_label.setStyleSheet("color: white; background: transparent;")
        # title_layout.addWidget(title_label)
        # main_layout.addWidget(title_container)

        # 使用说明标签
        info_label = QLabel("""
        <div style='line-height: 1.4;'>
        <b>📋 使用说明</b><br>
        • 正常复电选择 <b>复电</b> 模式<br>
        • 首次使用或出现异常选择 <b>初始化设备</b> 模式
        </div>
        """)
        info_label.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #ffecd2, stop:1 #fcb69f);
                padding: 10px 15px;
                border-radius: 8px;
                border-left: 4px solid #ff6b6b;
                color: #2c3e50;
                font-size: 13px;
            }
        """)
        main_layout.addWidget(info_label)

        # ========== 设备名称输入区域 ==========
        device_group = QGroupBox("📱 设备信息")
        device_group.setStyleSheet("""
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                color: #2c3e50;
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 8px;
                padding: 15px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 3px 8px;
                background-color: white;
            }
        """)
        device_layout = QVBoxLayout()
        device_layout.setSpacing(8)
        device_group.setLayout(device_layout)

        device_name_layout = QHBoxLayout()
        name_label = QLabel("设备名称:")
        name_label.setFont(QFont("Microsoft YaHei UI", 10))
        name_label.setStyleSheet("color: #555; font-weight: bold;")
        device_name_layout.addWidget(name_label)
        
        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("请输入设备名称（通常为二维码下面的字符）")
        self.device_name_edit.setFont(QFont("Microsoft YaHei UI", 9))
        self.device_name_edit.setStyleSheet("""
            QLineEdit {
                padding: 10px 12px;
                border: 2px solid #e0e0e0;
                border-radius: 6px;
                font-size: 10px;
                background-color: #f8f9fa;
            }
            QLineEdit:focus {
                border-color: #667eea;
                background-color: white;
            }
            QLineEdit:hover {
                border-color: #bbb;
            }
        """)
        device_name_layout.addWidget(self.device_name_edit)
        device_layout.addLayout(device_name_layout)

        main_layout.addWidget(device_group)

        # ========== 运行模式选择区域 ==========
        mode_group = QGroupBox("运行模式")
        mode_group.setStyleSheet("""
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                color: #2c3e50;
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 8px;
                padding: 15px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 3px 8px;
                background-color: white;
            }
        """)
        mode_layout = QHBoxLayout()
        mode_layout.setSpacing(15)
        mode_group.setLayout(mode_layout)

        # 创建单选按钮组
        self.mode_group = QButtonGroup()
        self.power_restore_radio = QRadioButton("复电")
        self.init_device_radio = QRadioButton("初始化设备")
        self.power_restore_radio.setChecked(True)  # 默认选中复电模式
        
        # 美化单选按钮
        radio_style = """
            QRadioButton {
                font-size: 11px;
                font-weight: bold;
                color: #2c3e50;
                padding: 8px;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #ccc;
            }
            QRadioButton::indicator:checked {
                background-color: #667eea;
                border: 2px solid #667eea;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #667eea;
            }
        """
        self.power_restore_radio.setStyleSheet(radio_style)
        self.init_device_radio.setStyleSheet(radio_style)

        # 将单选按钮添加到按钮组
        self.mode_group.addButton(self.power_restore_radio, 1)
        self.mode_group.addButton(self.init_device_radio, 2)

        mode_layout.addWidget(self.power_restore_radio)
        mode_layout.addWidget(self.init_device_radio)
        mode_layout.addStretch()

        main_layout.addWidget(mode_group)

        # ========== 控制按钮区域 ==========
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        # 开始按钮 - 改进样式
        self.start_button = QPushButton("▶ 开始")
        self.start_button.clicked.connect(self.start_operation)
        self.start_button.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        self.start_button.setMinimumHeight(45)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #56ab2f, stop:1 #a8e063);
                color: white;
                padding: 12px 30px;
                font-size: 14px;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #4a9428, stop:1 #95d14f);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3d7a20, stop:1 #7fb83b);
                padding-top: 14px;
                padding-bottom: 10px;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #888888;
            }
        """)

        # 停止按钮 - 改进样式
        self.stop_button = QPushButton("⬛ 停止")
        self.stop_button.clicked.connect(self.stop_operation)
        self.stop_button.setEnabled(False)  # 初始状态为禁用
        self.stop_button.setFont(QFont("Microsoft YaHei UI", 11, QFont.Weight.Bold))
        self.stop_button.setMinimumHeight(45)
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #eb3349, stop:1 #f45c43);
                color: white;
                padding: 12px 30px;
                font-size: 14px;
                border: none;
                border-radius: 10px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #d42b3e, stop:1 #dd4a38);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #bd2335, stop:1 #c63e30);
                padding-top: 14px;
                padding-bottom: 10px;
            }
            QPushButton:disabled {
                background: #cccccc;
                color: #888888;
            }
        """)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)

        # ========== 进度条 ==========
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)  # 默认隐藏，操作时显示
        self.progress_bar.setMinimumHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                background-color: #f0f0f0;
                text-align: center;
                font-weight: bold;
                font-size: 10px;
                color: #2c3e50;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 6px;
            }
        """)
        main_layout.addWidget(self.progress_bar)

        # ========== 日志显示区域 ==========
        log_group = QGroupBox("📝 操作日志")
        log_group.setStyleSheet("""
            QGroupBox {
                font-size: 12px;
                font-weight: bold;
                color: #2c3e50;
                background-color: white;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 8px;
                padding: 15px 12px 12px 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 3px 8px;
                background-color: white;
            }
        """)
        log_layout = QVBoxLayout()
        log_layout.setSpacing(8)
        log_group.setLayout(log_layout)

        # 日志文本框（只读）
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMinimumHeight(120)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 2px solid #333;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                line-height: 1.4;
            }
            QScrollBar:vertical {
                border: none;
                background-color: #2d2d2d;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #555;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666;
            }
        """)
        log_layout.addWidget(self.log_text)

        # 清空日志按钮
        clear_button = QPushButton("🗑️ 清空日志")
        clear_button.clicked.connect(self.clear_log)
        clear_button.setFont(QFont("Microsoft YaHei UI", 9))
        clear_button.setMinimumHeight(30)
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                padding: 6px 15px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
            QPushButton:pressed {
                background-color: #495057;
            }
        """)
        log_layout.addWidget(clear_button)

        main_layout.addWidget(log_group)

        # ========== 状态栏 ==========
        self.statusBar().showMessage("✅ 就绪")
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #f8f9fa;
                color: #495057;
                border-top: 1px solid #dee2e6;
                font-size: 11px;
                padding: 5px;
            }
        """)

        # ========== 设置全局样式表 ==========
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f5f7fa, stop:1 #e8ecf1);
            }
        """)

    def log_message(self, message):
        """
        在日志区域添加带时间戳的消息

        参数:
            message: 要显示的日志消息
        """
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 根据消息内容设置不同颜色
        color = "#4CAF50"  # 默认绿色
        if "失败" in message or "错误" in message or "出错" in message:
            color = "#f44336"  # 红色
        elif "警告" in message or "注意" in message:
            color = "#ff9800"  # 橙色
        elif "成功" in message or "完成" in message:
            color = "#4CAF50"  # 绿色
        elif "正在" in message:
            color = "#2196F3"  # 蓝色
        else:
            color = "#d4d4d4"  # 默认灰白色
        
        formatted_message = f'<span style="color: #888;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        self.log_text.append(formatted_message)

    def clear_log(self):
        """清空日志显示区域"""
        self.log_text.clear()

    def start_operation(self):
        """
        开始执行蓝牙设备操作
        验证输入，创建并启动工作线程
        """
        # 获取并验证设备名称
        device_name = self.device_name_edit.text().strip()
        if not device_name:
            QMessageBox.warning(self, "警告", "请输入设备名称！")
            return

        # 确定运行模式
        mode = "1" if self.power_restore_radio.isChecked() else "2"

        # 更新 UI 状态
        self.start_button.setEnabled(False)  # 禁用开始按钮
        self.stop_button.setEnabled(True)  # 启用停止按钮
        self.progress_bar.setVisible(True)  # 显示进度条
        self.progress_bar.setValue(0)  # 重置进度
        self.statusBar().showMessage("⚙️ 正在执行...")  # 更新状态栏

        # 创建并启动工作线程
        self.worker = BluetoothWorker(device_name, mode)
        self.worker.log_signal.connect(self.log_message)  # 连接日志信号
        self.worker.progress_signal.connect(self.progress_bar.setValue)  # 连接进度信号
        self.worker.finished_signal.connect(self.operation_finished)  # 连接完成信号
        self.worker.start()  # 启动线程

    def stop_operation(self):
        """
        停止正在运行的蓝牙操作
        终止工作线程并更新 UI 状态
        """
        if self.worker and self.worker.isRunning():
            self.worker.terminate()  # 终止线程
            self.worker.wait()  # 等待线程结束
            self.log_message("操作已停止")
            self.operation_finished(False)

    def operation_finished(self, success):
        """
        处理操作完成事件

        参数:
            success: 操作是否成功
            message: 结果消息
        """
        # 恢复 UI 状态
        self.start_button.setEnabled(True)  # 启用开始按钮
        self.stop_button.setEnabled(False)  # 禁用停止按钮
        self.progress_bar.setVisible(False)  # 隐藏进度条

        if success:
            # 操作成功
            self.statusBar().showMessage("✅ 操作成功完成")
            QMessageBox.information(self, "✅ 完成", "操作成功完成！")
        else:
            # 操作失败
            self.statusBar().showMessage("❌ 操作失败")
            QMessageBox.critical(self, "❌ 失败", "操作失败，查看日志获取详细信息")

    def closeEvent(self, event):
        """
        处理窗口关闭事件
        如果有操作正在进行，提示用户确认

        参数:
            event: 关闭事件对象
        """
        # 检查是否有操作正在运行
        if self.worker and self.worker.isRunning():
            # 弹出确认对话框
            reply = QMessageBox.question(self, '确认退出', '操作正在进行中，确认退出？',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 用户确认退出，终止线程
                self.worker.terminate()
                self.worker.wait()
                event.accept()  # 接受关闭事件
            else:
                # 用户取消退出
                event.ignore()  # 忽略关闭事件
        else:
            # 没有操作在运行，直接关闭
            event.accept()

def main():
    """
    程序入口函数
    创建 Qt 应用程序并显示主窗口
    """
    # 创建 Qt 应用程序实例
    app = QApplication(sys.argv)

    # 设置应用程序元数据
    app.setApplicationName("蓝牙设备控制器")
    app.setApplicationVersion("1.0")
    app.setOrganizationName("YDJK")

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    # 进入事件循环，等待应用程序退出
    sys.exit(app.exec())

if __name__ == "__main__":
    # 当脚本直接运行时，启动主函数
    main()