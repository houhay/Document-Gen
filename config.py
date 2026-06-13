#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
- 从 key.txt 读取默认 API 配置
- 支持多 API 提供商（DeepSeek / OpenAI / Anthropic / 自定义）
- 运行时配置通过 config.local.json 持久化
"""

import os
import json
import sys


# ==============================================
# 默认路径
# ==============================================
def get_project_root() -> str:
    """获取项目根目录（exe 所在目录或当前目录）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PROJECT_ROOT = get_project_root()
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
KEY_FILE = os.path.join(PROJECT_ROOT, "key.txt")
LOCAL_CONFIG_FILE = os.path.join(PROJECT_ROOT, "政企文档生成系统", "config.local.json")


# ==============================================
# API 提供商定义
# ==============================================
API_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "default_api_base": "https://api.deepseek.com",
        "api_path": "/v1/chat/completions",
        "format": "openai",  # OpenAI 兼容接口
    },
    "openai": {
        "label": "OpenAI 兼容",
        "default_api_base": "https://api.openai.com",
        "api_path": "/v1/chat/completions",
        "format": "openai",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "default_api_base": "https://api.anthropic.com",
        "api_path": "/v1/messages",
        "format": "anthropic",
    },
    "custom": {
        "label": "自定义",
        "default_api_base": "",
        "api_path": "/v1/chat/completions",
        "format": "openai",
    },
}


def parse_key_file() -> dict:
    """
    解析 key.txt 文件，提取 API 配置
    key.txt 格式：
        第一行：API Key
        后续：JSON 格式配置（model, extra_body 等）
        最后一行：API 地址
    """
    config = {
        "api_key": "",
        "api_base": "",
        "model": "deepseek-v4-flash",
        "provider": "deepseek",
    }

    if not os.path.exists(KEY_FILE):
        return config

    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()

        lines = content.strip().split("\n")
        if not lines:
            return config

        # 第一行是 API Key
        config["api_key"] = lines[0].strip()

        # 最后一行是 API 地址
        config["api_base"] = lines[-1].strip()

        # 中间部分是 JSON 配置
        json_part = "\n".join(lines[1:-1]).strip()
        if json_part:
            try:
                json_config = json.loads(json_part)
                if "model" in json_config:
                    config["model"] = json_config["model"]
                if "extra_body" in json_config:
                    config["extra_body"] = json_config["extra_body"]
            except json.JSONDecodeError:
                pass

        # 自动检测提供商
        api_base_lower = config["api_base"].lower()
        if "deepseek" in api_base_lower:
            config["provider"] = "deepseek"
        elif "anthropic" in api_base_lower:
            config["provider"] = "anthropic"
        elif "openai" in api_base_lower:
            config["provider"] = "openai"

    except Exception:
        pass

    return config


def load_local_config() -> dict:
    """加载本地运行时配置（config.local.json）"""
    if os.path.exists(LOCAL_CONFIG_FILE):
        try:
            with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_local_config(config: dict):
    """保存运行时配置到 config.local.json"""
    try:
        os.makedirs(os.path.dirname(LOCAL_CONFIG_FILE), exist_ok=True)
        with open(LOCAL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[配置] 保存本地配置失败: {e}")


def get_api_config() -> dict:
    """
    获取最终 API 配置（合并优先级：local > key.txt > 默认值）
    """
    # 1. 默认配置
    default_config = {
        "provider": "deepseek",
        "api_base": API_PROVIDERS["deepseek"]["default_api_base"],
        "api_key": "",
        "model": "deepseek-v4-flash",
        "max_tokens": 4096,
        "temperature": 0.7,
    }

    # 2. key.txt 配置
    key_config = parse_key_file()

    # 3. 本地运行时配置（优先级最高）
    local_config = load_local_config()

    # 合并（local > key > default）
    result = {**default_config, **key_config, **local_config}
    return result


def ensure_output_dir(path: str = None) -> str:
    """确保输出目录存在"""
    output_dir = path or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)
    return output_dir
