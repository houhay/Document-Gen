#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档内容生成器
- 按大纲分节生成内容（分节策略保证长文本质量）
- 上下文传递保持连贯性
- 调用 LLM 生成文件名
"""

import json
from typing import List

from prompts import (
    SECTION_CONTENT_PROMPT,
    FILENAME_GENERATION_PROMPT,
)
from llm_client import LLMClient
from intent_engine import WritingIntent
from doc_planner import Section


class DocGenerator:
    """文档内容生成器"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def generate_full_document(self, intent: WritingIntent, outline: List[Section]) -> str:
        """
        按大纲逐节生成完整文档内容
        :param intent: 写作意图
        :param outline: 大纲章节列表
        :return: 完整文档内容（Markdown 格式）
        """
        doc_title = intent.topic
        doc_summary = intent.to_summary()

        all_sections_content = []
        previous_summary = ""

        # 遍历所有一级章节
        for i, section in enumerate(outline):
            # 生成当前章节内容
            print(f"  ├─ 正在生成章节: {section.title}")

            section_content = self._generate_section(
                doc_title=doc_title,
                doc_summary=doc_summary,
                section=section,
                previous_summary=previous_summary,
            )

            all_sections_content.append(section_content)

            # 更新前文摘要（取最后 200 字作为上下文）
            previous_summary = section_content[-200:] if len(section_content) > 200 else section_content

        # 合并完整文档
        full_content = f"# {doc_title}\n\n" + "\n\n".join(all_sections_content)
        return full_content

    def _generate_section(self, doc_title: str, doc_summary: str,
                          section: Section, previous_summary: str) -> str:
        """
        生成单个章节的内容
        :param doc_title: 文档标题
        :param doc_summary: 文档概要
        :param section: 当前章节
        :param previous_summary: 前一章节内容摘要
        :return: 章节内容
        """
        prompt = SECTION_CONTENT_PROMPT.format(
            document_title=doc_title,
            document_summary=doc_summary,
            section_title=section.title,
            section_description=section.description or f"撰写关于{section.title}的内容",
            previous_section_summary=previous_summary or "本文档的开头部分",
        )

        try:
            content = self.llm_client.chat_with_prompt(prompt)
        except Exception as e:
            print(f"    ├─ 生成失败: {e}")
            content = f"## {section.title}\n\n（本节内容生成失败，请重试）\n"

        # 处理子章节
        if section.subsections:
            sub_contents = []
            for sub in section.subsections:
                sub_prompt = SECTION_CONTENT_PROMPT.format(
                    document_title=doc_title,
                    document_summary=doc_summary,
                    section_title=sub.title,
                    section_description=sub.description or f"撰写关于{sub.title}的内容",
                    previous_section_summary=content[-200:] if len(content) > 200 else content,
                )
                try:
                    sub_content = self.llm_client.chat_with_prompt(sub_prompt)
                    sub_contents.append(f"\n### {sub.title}\n\n{sub_content}")
                except Exception as e:
                    print(f"    ├─ 子章节生成失败: {e}")
                    sub_contents.append(f"\n### {sub.title}\n\n（内容生成失败）\n")

            content += "\n" + "\n".join(sub_contents)

        return content

    def generate_file_name(self, content: str, intent: WritingIntent) -> str:
        """
        调用 LLM 根据文档内容生成文件名
        :param content: 文档内容
        :param intent: 写作意图
        :return: 文件名（不含扩展名）
        """
        summary = content[:200] if len(content) > 200 else content
        prompt = FILENAME_GENERATION_PROMPT.format(
            doc_title=intent.topic,
            content_summary=summary,
        )

        try:
            result = self.llm_client.chat_with_prompt(prompt)
            # 清理
            import re
            result = result.strip().strip('"').strip("'")
            result = re.sub(r'[\\/:*?"<>|]', '_', result)
            if result:
                return result[:60]
        except Exception:
            pass

        # 回退
        import re
        fallback = re.sub(r'[\\/:*?"<>|]', '_', intent.topic)[:40]
        return fallback or "文档"
