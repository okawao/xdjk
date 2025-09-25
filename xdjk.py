import warnings
warnings.filterwarnings("ignore")
import asyncio
import requests
import sys
from bleak import BleakScanner, BleakClient

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

def notification_handler(sender, data):
    try:
        raw_data = data.decode('ascii')

        if len(raw_data) > 40:
            data_list = raw_data.split(",")

            # 初始化一个长度为 50 的数组，每个元素初始化为 "0000000000"
            parsed_data = ["0000000000"] * 50

            for i, item in enumerate(data_list):
                key_value = item.split(":")
                if len(key_value) > 1:
                    parsed_data[i] = key_value[1]

            # 返回结果数据格式
            # result = {
            #     "deviceName": parsed_data[0],
            #     "YEAR": parsed_data[1][0:4],
            #     "MONTH": parsed_data[1][4:6],
            #     "DAY": parsed_data[1][6:8],
            #     "HOUR": parsed_data[2][0:2],
            #     "MINUTE": parsed_data[2][2:4],
            #     "SECOND": parsed_data[2][4:6],
            #     "Electric_Quantity": parsed_data[3],
            #     "Power": parsed_data[4],
            #     "Voltage": parsed_data[5],
            #     "Electric_Current": parsed_data[6],
            #     "Power_Factor": parsed_data[7],
            #     "PowerOver_Alarm_Count": parsed_data[8],
            #     "PowerRise_Alarm_Count": parsed_data[9],
            #     "Power_Factor_Alarm_Count": parsed_data[10],
            #     "PowerRise_Continue_Alarm_Count": parsed_data[11],
            #     "KeepPower_State": parsed_data[12],
            #     "Power_B": parsed_data[13],
            #     "Electric_Current_B": parsed_data[14],
            #     "Power_Factor_B": parsed_data[15],
            #     "KeepPower_State_B": parsed_data[16],
            #     "current_fw_title": parsed_data[17],
            #     "current_fw_version": parsed_data[18],
            #     "MicroWave_PowerOff_Count": parsed_data[19],
            #     "MicroWave_PowerOff_Count_Time_YEAR": parsed_data[20][0:4],
            #     "MicroWave_PowerOff_Count_Time_MONTH": parsed_data[20][4:6],
            #     "MicroWave_PowerOff_Count_Time_DAY": parsed_data[20][6:8],
            #     "MicroWave_PowerOff_Count_Time_HOUR": parsed_data[21][0:2],
            #     "MicroWave_PowerOff_Count_Time_MINUTE": parsed_data[21][2:4],
            #     "MicroWave_PowerOff_Count_Time_SECOND": parsed_data[21][4:6],
            #     "ChooseRunningMode": parsed_data[22],
            #     "setElectricControlSwitch": parsed_data[23],
            #     "setTimeControlSwitch": parsed_data[24],
            #     "setElectricityOffOfRoomStatic": parsed_data[25],
            #     "setTimer": parsed_data[26],
            # }

            url = "https://47.93.186.159:8887/apideviceinfo"
            json = {
                "name": device_name,
                "info": parsed_data[18]
            }
            requests.post(url, json=json)

            print("设备版本: ", parsed_data[18], "\n")
    except Exception as e:
        print("解析设备信息出错，请重试！！！\n")

async def scan_devices():
    scanner = BleakScanner()
    try:
        devices = await scanner.discover()
        for device in devices:
            if device.name == device_name:
                print("搜索到设备 ", device.name, "\n")
                return device.address
        else:
            print("\n未搜索到设备，请重试！！！\n")
    except Exception as e:
        print(f"\n未扫描到设备，请打开蓝牙并重试！！！\n")

async def connect_and_write(address, data):

    byte_array = bytearray.fromhex(data)

    try:
        async with BleakClient(address) as client:

            await client.start_notify(CHARACTERISTIC_UUID, notification_handler)
            await client.write_gatt_char(CHARACTERISTIC_UUID, byte_array)
            await asyncio.sleep(2)
            
            print("电源启动成功！", "\n")

    except Exception as e:
        print(f"连接设备出错，请重试！！！\n")

async def read_characteristic(address):
    try:
        async with BleakClient(address) as client:
            services = await client.get_services()
            target_service = next(
                (s for s in services if s.uuid == SERVICE_UUID),
                None
            )
            if not target_service:
                print(f"未搜索到服务！\n")
                return None, None

            target_char = next(
                (c for c in target_service.characteristics if c.uuid == CHARACTERISTIC_UUID),
                None
            )
            if not target_char:
                print(f"未搜索到特征值！\n")
                return None, None

            if "read" in target_char.properties:
                value = await client.read_gatt_char(target_char.uuid)
                raw_data = value.decode('ascii')
                data_list = raw_data.split(",")
                if len(data_list) != 13:
                    print("获取设备信息错误，请重试！\n")
                    return None, None

                result = []
                for item in data_list:
                    key_value = item.split(":")
                    if len(key_value) == 2:
                        result.append(key_value[1])
                    else:
                        print("获取设备信息错误，请重试！\n")
                        return None, None
                return result, raw_data
            else:
                print("该特征值不可读！\n")
    except Exception as e:
        print("连接设备出错，请重试！\n")
        return None, None

def get_data(data, device_name, info):
    try:
        url = "https://47.93.186.159:8887/apigetdata"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "data": data,
            "name": device_name,
            "info": info
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 403:
            print("你不是订阅用户，请联系管理员！！！\n")
            return None
        if response.status_code == 200:
            return response.text
        print("获取数据失败！\n")
        return None
    except Exception as e:
        print("获取数据失败！\n")

def init_data(device_name):
    try:
        url = "https://47.93.186.159:8887/apiinitdata"
        params = {
            "name": device_name
        }
        response = requests.get(url, params=params)
        if response.status_code == 403:
            print("你不是订阅用户，请联系管理员！！！\n")
            return None
        if response.status_code == 200:
            # print("获取数据成功！\n")
            return response.text
        print("获取数据失败！\n")
        return None
    except Exception as e:
        print("获取数据失败！\n")
        return None

try:
    print('''注意事项：
        1.正常复电请在后续步骤选择模式: 1
        2.第一次使用时选择模式: 2
        3.注意用电安全
    ''')
    device_name = input("请输入设备名称(通常为二维码下面的字符)：")
    if not device_name:
        print("设备名称不能为空！\n")
        input("任意键退出...")
        sys.exit()

    loop = asyncio.get_event_loop()

    print("\n正在搜索蓝牙设备...\n")
    device_address = loop.run_until_complete(scan_devices())
    if device_address is None:
        input("任意键退出...")
        sys.exit()

    run_mode = input("请输入运行模式(1: 复电，2: 初始化设备，回车默认 1)：")
    if not run_mode or run_mode == "1":
        print("\n正在获取设备信息...\n")
        data, info = loop.run_until_complete(read_characteristic(device_address))
        if data is None or info is None:
            input("任意键退出...")
            sys.exit()

        print("正在获取复电数据...\n")
        result = get_data(data, device_name, info)
        if result is None:
            input("任意键退出...")
            sys.exit()

        print("正在启动电源...\n")
        loop.run_until_complete(connect_and_write(device_address, result))

        input("任意键退出...")
    elif run_mode == "2":
        print("\n获取初始化数据...\n")
        result = init_data(device_name)
        if result is None:
            input("任意键退出...")
            sys.exit()
        
        print("正在启动电源...\n")
        loop.run_until_complete(connect_and_write(device_address, result))
        input("任意键退出...")
    else:
        print("输入错误！\n")
        input("任意键退出...")
except KeyboardInterrupt:
    print("\n程序已终止！\n")
    input("任意键退出...")
