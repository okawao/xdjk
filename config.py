"""
应用配置文件
此文件在构建时会被 GitHub Actions 自动更新
"""

# API 服务器配置 - 这些值会在构建时被替换
HOST_IP = ""
HOST_PORT = ""
API_BASE_URL = f"https://{HOST_IP}:{HOST_PORT}"
