# FocusGuard · 专注守卫

一个电脑端的专注力工具，灵感来自番茄 TODO 的「白名单模式」，并额外支持把**网页/网站**也加入白名单。开启专注后，只允许运行白名单内的 App、访问白名单内的网站，帮助你上网课时保持专注。

## 功能特性

- ⏱ **专注倒计时**：自定义专注时长
- 🚫 **App 白名单**：专注期间自动关闭非白名单应用
- 🌐 **网页白名单**：通过本地代理拦截非白名单网站
- 📋 **白名单管理**：随时添加、删除允许的 App 和网站
- 📊 **专注统计**：记录专注次数、总时长、拦截次数
- ⚙️ **严格模式**：开启后专注中无法暂停或停止
- 💻 **Windows 桌面应用**：也可在 Linux/macOS 上运行（功能可能有差异）

## 项目结构

```
focus-guard/
├── core/
│   ├── __init__.py
│   ├── config.py         # 配置持久化
│   ├── timer.py          # 专注计时器
│   ├── process_guard.py  # App 白名单拦截
│   └── web_guard.py      # 网页白名单代理
├── gui/
│   └── app.py            # CustomTkinter 图形界面
├── assets/               # 图标等资源（可扩展）
├── main.py               # 程序入口
├── requirements.txt
├── .gitignore
└── README.md
```

## 环境要求

- Python 3.11+
- Windows 10/11（推荐）
- 管理员权限（修改系统代理、终止部分进程需要）

## 安装与运行

### 方式一：双击批处理文件（新手推荐）

1. 解压 `focus-guard.zip` 到任意文件夹（例如桌面）。
2. **双击 `setup.bat`**：检查 Python、创建虚拟环境、安装依赖。第一次需要联网，约 1 分钟。
3. **双击 `test_dry.bat`**：安全干跑测试，看看哪些程序会被拦截（不会真的关闭程序）。
4. 右键 **`start.bat`** → **以管理员身份运行**：启动 FocusGuard。

程序目录中的批处理文件：

| 文件 | 作用 |
|---|---|
| `setup.bat` | 安装 Python 依赖环境 |
| `start.bat` | 启动 FocusGuard（需要管理员权限） |
| `test_dry.bat` | 安全干跑测试 |
| `reset_proxy.bat` | 紧急恢复系统代理 |

### 方式二：命令行（可选）

```bash
# 1. 克隆或下载本项目
cd focus-guard

# 2. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 运行
python main.py
```

## 打包成 exe（Windows）

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name FocusGuard main.py
```

打包完成后，`dist/FocusGuard.exe` 即可独立运行。

## 使用说明

1. **白名单设置**
   - 在「白名单」标签页中添加允许的 App 进程名（如 `chrome.exe`、`zoom.exe`）和网站域名（如 `classroom.google.com`）。
   - 白名单为空时不会拦截任何内容。

2. **开始专注**
   - 在「专注计时」标签页设置时长，点击「开始专注」。
   - 程序会启动进程监控和本地网络代理，自动拦截非白名单内容。

3. **停止专注**
   - 点击「停止」结束本次专注，系统代理会恢复，App 拦截停止。
   - 严格模式下无法提前停止。

## 注意事项

- **管理员权限**：关闭部分程序、修改系统代理需要管理员权限，建议右键以管理员身份运行。
- **系统关键进程**：已内置保护列表，不会关闭 Windows 核心进程。
- **浏览器兼容性**：网页拦截通过系统代理实现，Chrome/Edge/Firefox 等主流浏览器均支持；部分独立客户端可能不遵守系统代理设置。
- **数据存储**：配置文件和统计数据保存在用户目录下的 `~/.focusguard/config.json`。

## 测试

### 安全干跑（推荐先跑这个）

```bash
python tests/test_dry.py
```

这个脚本**不会关闭任何程序、不会修改系统代理**，只列出当前有哪些进程会被你的白名单拦截。

### 真实功能测试

1. 右键以管理员身份运行 `python main.py`
2. 在「白名单」里至少加入：
   - `explorer.exe`
   - 你正在使用的浏览器（如 `msedge.exe` / `chrome.exe`）
   - `python.exe` 和 `focusguard.exe`
3. 网站白名单加入 `example.com`
4. 专注时长设为 2 分钟，点击「开始专注」
5. 打开「画图 (`mspaint.exe`)」——应被自动关闭
6. 在浏览器访问 `example.com`（应能打开），访问 `baidu.com`（应被拦截）
7. 点击「停止」或等倒计时结束

### 紧急情况：恢复系统代理

如果程序异常退出导致浏览器无法上网：

```bash
python tests/reset_proxy.py
```

或在 Windows 设置 → 网络和 Internet → 代理 → 关闭「使用代理服务器」。

## 注意事项与风险提示

- **请先使用 `test_dry.py` 了解会被拦截的程序**，避免误关重要应用。
- 程序不会拦截系统关键进程（如 `svchost.exe`、`explorer.exe` 等），但仍可能关闭你需要的程序，请务必将它们加入白名单。
- 网页拦截依赖系统代理设置，部分独立客户端（如微信、QQ、某些游戏）可能不遵守系统代理，因此不会被拦截。
- 建议在虚拟机或非生产环境首次测试。

## 待增强功能（P1）

- [ ] 系统托盘最小化
- [ ] 开机自启
- [ ] 局域网手机 Web 仪表盘
- [ ] 更精细的网站黑白名单规则
- [ ] 多语言支持

## 许可证

[MIT License](LICENSE) © 2026 katsoa-lunta
