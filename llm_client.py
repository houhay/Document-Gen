#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大模型 API 客户端
- 支持多 API 提供商（DeepSeek / OpenAI / Anthropic / 自定义）
- 统一调用接口
- 错误重试与回退
"""

import json
import time
import requests
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class LLMConfig:
    """大模型配置"""
    provider: str = "deepseek"       # deepseek / openai / anthropic / custom
    api_base: str = ""               # API 地址
    api_key: str = ""                # API 密钥
    model: str = "deepseek-v4-flash" # 模型名
    max_tokens: int = 4096           # 最大 Token 数
    temperature: float = 0.7         # 温度
    extra_headers: dict = None       # 自定义请求头

    def to_dict(self) -> dict:
        return asdict(self)


class LLMClient:
    """大模型客户端 - 支持多 API 提供商"""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._last_error = None

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        """
        统一调用入口，根据 provider 自动路由
        :param messages: [{"role": "user", "content": "..."}, ...]
        :param stream: 是否流式输出
        :return: 模型返回的文本内容
        """
        provider = self.config.provider

        if provider == "anthropic":
            return self._call_anthropic(messages)
        else:
            # DeepSeek / OpenAI / 自定义 → OpenAI 兼容接口
            return self._call_openai_compatible(messages, stream)

    def _call_openai_compatible(self, messages: List[Dict], stream: bool = False) -> str:
        """调用 OpenAI 兼容接口（DeepSeek / OpenAI / 自定义）"""
        # 构建完整 API URL
        api_base = self.config.api_base.rstrip("/")
        if not api_base.endswith("/v1"):
            url = f"{api_base}/v1/chat/completions"
        else:
            url = f"{api_base}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}"
        }

        # 合并自定义请求头
        if self.config.extra_headers:
            headers.update(self.config.extra_headers)

        data = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": stream,
        }

        # 支持从配置中传递 extra_body（如 reasoning 配置）
        if hasattr(self.config, 'extra_body') and self.config.extra_body:
            data["extra_body"] = self.config.extra_body

        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"].strip()
                return content
            else:
                error_msg = f"API 错误 (HTTP {response.status_code}): {response.text[:200]}"
                self._last_error = error_msg
                raise Exception(error_msg)

        except requests.exceptions.Timeout:
            self._last_error = "API 请求超时（120秒）"
            raise
        except requests.exceptions.ConnectionError:
            self._last_error = f"无法连接到 API 地址: {self.config.api_base}"
            raise
        except Exception as e:
            self._last_error = str(e)
            raise

    def _call_anthropic(self, messages: List[Dict]) -> str:
        """调用 Anthropic Claude API"""
        try:
            import anthropic
        except ImportError:
            raise Exception("未安装 anthropic 包，无法调用 Claude API")

        client = anthropic.Anthropic(
            api_key=self.config.api_key,
            base_url=self.config.api_base if self.config.api_base else None,
        )

        # 转换消息格式
        system_prompt = ""
        anthropic_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user":
                anthropic_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                anthropic_messages.append({"role": "assistant", "content": msg["content"]})

        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": anthropic_messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            response = client.messages.create(**kwargs)
            return response.content[0].text.strip()
        except Exception as e:
            self._last_error = str(e)
            raise

    def chat_with_prompt(self, prompt: str, system: str = None) -> str:
        """便捷方法：直接传入 prompt 字符串"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)

    def test_connection(self) -> Tuple[bool, str]:
        """测试 API 连接是否正常"""
        try:
            start = time.time()
            result = self.chat_with_prompt("你好，请回复'连接正常'。")
            elapsed = time.time() - start

            if result:
                return True, f"连接成功 ({elapsed:.1f}秒)，回复: {result[:50]}"
            return False, "API 返回为空"
        except Exception as e:
            return False, f"连接失败: {str(e)}"

    def get_last_error(self) -> str:
        """获取最后一次错误信息"""
        return self._last_error or ""


# ==============================================
# 便捷函数
# ==============================================
def create_client_from_config(config_dict: dict) -> LLMClient:
    """从配置字典创建 LLMClient"""
    llm_config = LLMConfig(
        provider=config_dict.get("provider", "deepseek"),
        api_base=config_dict.get("api_base", ""),
        api_key=config_dict.get("api_key", ""),
        model=config_dict.get("model", "deepseek-v4-flash"),
        max_tokens=config_dict.get("max_tokens", 4096),
        temperature=config_dict.get("temperature", 0.7),
    )
    # 传递 extra_body
    if "extra_body" in config_dict:
        llm_config.extra_body = config_dict["extra_body"]
    return LLMClient(llm_config)
