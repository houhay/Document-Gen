#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具函数模块
- 文件名校验
- 路径处理
- 其他通用工具
"""

import os
import re


def sanitize_filename(name: str, max_length: int = 80) -> str:
    """
    清理文件名，移除 Windows 不允许的字符并截断
    :param name: 原始文件名（不含扩展名）
    :param max_length: 最大长度
    :return: 安全的文件名
    """
    # 移除非法字符 \\ / : * ? " < > |
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # 替换连续空白为单个空格
    name = re.sub(r'\s+', ' ', name).strip()
    # 截断
    if len(name) > max_length:
        name = name[:max_length].rstrip('_').strip()
    return name or "未命名文档"


def ensure_file_path(output_dir: str, base_name: str, extension: str = ".docx") -> str:
    """
    生成安全的完整文件路径
    :param output_dir: 输出目录
    :param base_name: 文件名（不含扩展名）
    :param extension: 扩展名（含点）
    :return: 完整的文件路径
    """
    safe_name = sanitize_filename(base_name)
    os.makedirs(output_dir, exist_ok=True)
    return os.path.join(output_dir, f"{safe_name}{extension}")


def generate_sequential_filename(output_dir: str, base_name: str, seq: int = None) -> str:
    """
    生成带序号的唯一文件名，避免覆盖
    :param output_dir: 输出目录
    :param base_name: 基础文件名
    :param seq: 序号（可选）
    :return: 唯一文件路径
    """
    if seq is not None:
        name = f"{sanitize_filename(base_name)}_{seq:03d}"
    else:
        name = sanitize_filename(base_name)

    # 如果文件已存在，自动添加序号
    path = os.path.join(output_dir, f"{name}.docx")
    if not os.path.exists(path):
        return path

    counter = 1
    while True:
        new_path = os.path.join(output_dir, f"{name}_{counter:03d}.docx")
        if not os.path.exists(new_path):
            return new_path
        counter += 1


def open_folder(path: str):
    """在文件管理器中打开指定路径"""
    try:
        import subprocess
        if os.path.isfile(path):
            path = os.path.dirname(path)
        subprocess.Popen(f'explorer "{os.path.normpath(path)}"')
    except Exception:
        pass


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本并添加省略号"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
