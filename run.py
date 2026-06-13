#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动器 - 内嵌 Streamlit 服务器
用于 PyInstaller 打包后的入口
模仿 streamlit run 的完整启动流程
"""

import os
import sys
import webbrowser
import threading
import time


def resolve_base_dir() -> str:
    """解析项目基础目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后，文件在 _MEIPASS 临时目录
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        return os.path.dirname(os.path.abspath(__file__))


def start_streamlit():
    """启动 Streamlit 服务器 — 完整模拟 streamlit run 的流程"""
    base_dir = resolve_base_dir()
    app_path = os.path.join(base_dir, "app.py")

    if not os.path.exists(app_path):
        # 尝试 exe 同级目录
        base_dir = os.path.dirname(sys.executable)
        app_path = os.path.join(base_dir, "app.py")

    if not os.path.exists(app_path):
        print(f"错误：找不到 app.py（搜索路径: {base_dir}）")
        sys.exit(1)

    # Streamlit 需要工作目录正确
    os.chdir(base_dir)

    # 第一步：像 CLI 那样先设置 main_script_path（让 config 能找到 .streamlit/config.toml）
    import streamlit.config as _config
    _config._main_script_path = app_path

    # 第二步：像 CLI 那样加载配置选项（force_reparse）
    # 这里的 key 用下划线分隔（Click 格式），load_config_options 会转成点号格式
    from streamlit.web import bootstrap
    bootstrap.load_config_options(flag_options={
        "global_developmentMode": False,   # 修复 PyInstaller 下的 developmentMode 误判
        "server_port": 8501,
        "server_headless": True,
    })

    # 第三步：启动 Streamlit（与 CLI 完全相同的参数格式）
    bootstrap.run(app_path, False, [], {
        "global_developmentMode": False,
        "server_port": 8501,
        "server_headless": True,
    })


def open_browser():
    """延迟打开浏览器"""
    time.sleep(2)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    print("=" * 50)
    print("   政企文档生成系统 v1.0")
    print("   Powered by LLM")
    print("=" * 50)
    print()
    print("正在启动服务...")
    print("浏览器将自动打开 http://localhost:8501")
    print("关闭浏览器窗口或按 Ctrl+C 退出")
    print()

    # 启动浏览器线程
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动 Streamlit
    start_streamlit()
