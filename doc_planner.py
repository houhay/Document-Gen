#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档规划器
- 根据 WritingIntent 生成文档大纲
- 支持不同文种的大纲模板
- 用户可反馈修改大纲
"""

import json
import re
from typing import List, Optional
from dataclasses import dataclass, field

from prompts import (
    OUTLINE_GENERATION_PROMPT,
    DOC_TYPE_REQUIREMENTS,
)
from llm_client import LLMClient
from intent_engine import WritingIntent


@dataclass
class Section:
    """大纲章节"""
    title: str
    level: int
    description: str = ""
    subsections: List["Section"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "level": self.level,
            "description": self.description,
            "subsections": [s.to_dict() for s in self.subsections],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Section":
        return cls(
            title=data.get("title", ""),
            level=data.get("level", 1),
            description=data.get("description", ""),
            subsections=[cls.from_dict(s) for s in data.get("subsections", [])],
        )


class DocPlanner:
    """文档规划器"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def generate_outline(self, intent: WritingIntent) -> List[Section]:
        """
        根据意图生成大纲
        :param intent: 写作意图
        :return: 章节列表
        """
        intent_summary = intent.to_summary()

        # 获取文种结构要求
        doc_type = intent.doc_type
        doc_type_req = DOC_TYPE_REQUIREMENTS.get(doc_type, "")

        prompt = OUTLINE_GENERATION_PROMPT.format(
            intent_summary=intent_summary,
            doc_type_requirements=doc_type_req,
        )

        try:
            result = self.llm_client.chat_with_prompt(prompt)
            sections = self._parse_outline(result)
            if sections:
                return sections
        except Exception as e:
            print(f"[大纲生成] API 调用失败: {e}")

        # 回退：使用默认模板
        return self._generate_default_outline(intent)

    def refine_outline(self, outline: List[Section], feedback: str) -> List[Section]:
        """
        根据用户反馈修改大纲
        :param outline: 原大纲
        :param feedback: 用户反馈
        :return: 修改后的大纲
        """
        if not feedback.strip():
            return outline

        # 简单修改：重新调用 LLM 生成
        outline_json = json.dumps(
            [s.to_dict() for s in outline],
            ensure_ascii=False,
            indent=2,
        )

        prompt = f"""请根据用户反馈修改以下大纲。

原大纲：
{outline_json}

用户反馈：
{feedback}

请按原有 JSON 格式输出修改后的大纲。"""

        try:
            result = self.llm_client.chat_with_prompt(prompt)
            sections = self._parse_outline(result)
            if sections:
                return sections
        except Exception:
            pass

        return outline

    def _parse_outline(self, text: str) -> Optional[List[Section]]:
        """解析 LLM 返回的大纲文本"""
        # 尝试 JSON
        json_str = None
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            json_str = match.group(1).strip()
        else:
            match = re.search(r'(\{[\s\S]*"sections"[\s\S]*\})', text)
            if match:
                json_str = match.group(1).strip()

        if json_str:
            try:
                data = json.loads(json_str)
                sections_data = data.get("sections", [])
                if "subsections" in data:
                    # 整篇文档结构
                    sections_data = data.get("subsections", sections_data)
                return [Section.from_dict(s) for s in sections_data]
            except json.JSONDecodeError:
                pass

        # 文本格式回退解析
        return self._parse_outline_text(text)

    def _parse_outline_text(self, text: str) -> List[Section]:
        """从 Markdown 文本中解析大纲"""
        sections = []
        current_section = None
        stack = []

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # 匹配标题 # ## ###
            match = re.match(r'^(#{1,3})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                section = Section(title=title, level=level)

                if level == 1:
                    sections.append(section)
                    stack = [section]
                elif level == 2 and stack:
                    stack[-1].subsections.append(section)
                    stack = [stack[-1], section]
                elif level == 3 and len(stack) >= 2:
                    stack[-1].subsections.append(section)

        return sections

    def _generate_default_outline(self, intent: WritingIntent) -> List[Section]:
        """生成默认大纲（模板回退）"""
        topic = intent.topic or "文档主题"
        doc_type = intent.doc_type or "报告"

        # 基础模板
        templates = {
            "报告": [
                Section("引言", 1, "阐述研究背景、目的和意义"),
                Section("现状分析", 1, "分析当前发展状况"),
                Section("主要内容", 1, "阐述核心内容"),
                Section("问题与对策", 1, "分析存在问题及对策"),
                Section("结论与展望", 1, "总结全文，展望未来"),
            ],
            "方案": [
                Section("指导思想", 1, "阐述总体思路"),
                Section("工作目标", 1, "明确目标任务"),
                Section("重点任务", 1, "列出主要任务"),
                Section("实施步骤", 1, "时间安排"),
                Section("保障措施", 1, "组织、制度保障"),
            ],
        }

        return templates.get(doc_type, [
            Section(f"一、引言", 1, f"阐述{topic}的背景和意义"),
            Section(f"二、{topic}现状", 1, f"分析{topic}的当前状况"),
            Section(f"三、{topic}分析", 1, f"深入分析{topic}的核心内容"),
            Section(f"四、对策建议", 1, f"提出针对性的建议"),
            Section(f"五、结语", 1, "总结全文"),
        ])
