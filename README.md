# 🖼️ TermPaper

A lightweight, fast, local desktop wallpaper manager powered by Python, Flask, and PyStray.

TermPaper brings a full-featured wallpaper manager directly to your system tray and browser. Browse, preview, rotate, and manage high-resolution wallpapers seamlessly with minimal resource footprint and zero bloat.

## ✨ Features

- 🌐 Flask Web UI: Sleek, responsive web interface to browse, preview, and apply wallpapers instantly.

- 📌 System Tray Integration: Runs silently in the background with quick access menus via PyStray.

- 🎨 Dynamic Pillow Graphics: Real-time canvas operations, thumbnail generation, and custom tray icons.

- ⚡ Ultra-Fast with uv: Blazing-fast dependency resolution and virtualenv execution.

- 🔒 100% Local & Privacy-Focused: No telemetry, heavy background services, or required cloud sign-ins.

## 🚀 Getting Started

TermPaper uses uv — an extremely fast Python package and project manager written in Rust.

### Prerequisites

Ensure you have uv installed. If you don't have it yet:

macOS / Linux:


```curl -LsSf https://astral.sh/uv/install.sh | sh```

Windows (PowerShell):
```powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"```

## 🛠️ Installation & Setup

1. Clone the repository:
```bash
   git clone https://github.com/y3script/TermPaper.git
   cd TermPaper
```

2. Sync and create virtual environment:
   uv automatically manages environments and dependencies specified in pyproject.toml / uv.lock.
```bash
   uv sync
```

## 🏃 Usage

### Run the Application

Launch TermPaper instantly inside the managed environment:

```bash
uv run tp ui -p 8080 -t
```

- The system tray icon will appear in your OS taskbar/tray area.

- Open your browser and navigate to http://127.0.0.1:8080 to access the Web UI.

## ⚙️ Built With

- Python 3.12+

- uv – High-performance Python project management

- Flask – Web interface backend

- PyStray – System tray controls

- Pillow – Image processing & dynamic icon generation

## 🌐 Connect With the Developer

If you like this project or want to check out more web, app, and terminal-based software engineering projects, follow me here:

- **GitHub:** [@y3script](https://github.com/y3script)

- **Instagram:** [@yescript](https://instagram.com/yescript)



Made with 🐍, 💻, and a deep love for coding.
