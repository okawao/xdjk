# xdjk

蓝牙设备控制器 - 基于 PyQt6 和 Bleak 的蓝牙设备管理应用程序

## 功能特点

- 🔍 扫描并连接指定名称的蓝牙设备
- 📊 读取设备特征值并解析数据
- 🔌 通过 API 获取控制指令
- ✍️ 向设备写入控制数据
- 🖥️ 提供图形界面进行设备管理和日志查看

## 构建配置

### 在 GitHub Actions 中配置 API 服务器地址

本项目支持在构建时通过环境变量配置 API 服务器地址，构建出的可执行程序会包含指定的配置。

#### ⚠️ 必需配置：

**必须**在 GitHub 中配置以下 Secrets，否则构建会失败：

1. **配置 GitHub Secrets**（必需）
   - 进入仓库 → **Settings** → **Secrets and variables** → **Actions**
   - 添加以下 secrets：
     - `HOST_IP`: API 服务器 IP 地址（例如：`192.168.1.100`）
     - `HOST_PORT`: API 服务器端口（例如：`8887`）

2. **触发构建**
   - Push 代码到 `main` 分支
   - 或创建 Pull Request
   - GitHub Actions 会自动构建并打包应用

#### 工作原理：

```yaml
# .github/workflows/main.yml 中的配置
env:
  HOST_IP: ${{ secrets.HOST_IP }}
  HOST_PORT: ${{ secrets.HOST_PORT }}
```

构建流程：
1. 📥 从 GitHub Secrets 读取 `HOST_IP` 和 `HOST_PORT`
2. 🔧 运行 `build_config.py` 生成 `config.py` 文件（如果环境变量缺失会报错）
3. 📦 PyInstaller 将 `config.py` 打包到可执行程序中
4. ✅ 生成的应用程序包含指定的 API 服务器配置

### 本地开发

本地开发时，需要先生成配置文件：

```bash
# 设置环境变量
$env:HOST_IP = "你的服务器IP"
$env:HOST_PORT = "你的端口"

# 生成配置文件
python build_config.py

# 运行程序
python xdjkgui.py
```

或者直接编辑 `config.py` 文件：

```python
HOST_IP = "你的服务器IP"
HOST_PORT = "你的端口"
API_BASE_URL = f"https://{HOST_IP}:{HOST_PORT}"
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 文件说明

- `xdjkgui.py` - 主程序文件
- `config.py` - 配置文件（包含默认 API 服务器地址）
- `build_config.py` - 构建时配置生成脚本
- `.github/workflows/main.yml` - GitHub Actions 工作流配置

## 许可证

MIT
