#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建时配置生成脚本
此脚本在 GitHub Actions 中运行，用于生成包含环境变量的配置文件
"""
import os
import sys
import io

# 设置 Windows 控制台编码为 UTF-8
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def generate_config():
    """从环境变量生成配置文件"""
    host_ip = os.getenv('HOST_IP')
    host_port = os.getenv('HOST_PORT')
    
    # 检查必需的环境变量
    if not host_ip:
        print("[ERROR] 环境变量 HOST_IP 未设置")
        sys.exit(1)
    if not host_port:
        print("[ERROR] 环境变量 HOST_PORT 未设置")
        sys.exit(1)
    
    config_content = f'''"""
应用配置文件
此文件在构建时由 GitHub Actions 自动生成
构建时间: {os.getenv('BUILD_TIME', 'N/A')}
"""

# API 服务器配置
HOST_IP = "{host_ip}"
HOST_PORT = "{host_port}"
API_BASE_URL = f"https://{{HOST_IP}}:{{HOST_PORT}}"
'''
    
    # 写入配置文件
    with open('config.py', 'w', encoding='utf-8') as f:
        f.write(config_content)
    
    print("[OK] 配置文件已生成:")
    print(f"   HOST_IP: {host_ip}")
    print(f"   HOST_PORT: {host_port}")
    print(f"   API_BASE_URL: https://{host_ip}:{host_port}")

if __name__ == '__main__':
    generate_config()
