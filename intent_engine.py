#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
意图理解引擎
- 分析写作方向，识别已知/缺失的写作要素
- 多轮追问澄清写作意图
- 综合生成结构化的 WritingIntent
"""

import json
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict

from prompts import (
    INTENT_ANALYSIS_PROMPT,
    INTENT_PROCESS_PROMPT,
    INTENT_QUICK_PARSE_PROMPT,
)
from llm_client import LLMClient


@dataclass
class Question:
    """追问问题"""
    field: str          # 对应字段名
    question: str       # 问题内容
    options: List[str]  # 选项列表


@dataclass
class QA:
    """问答记录"""
    question: Question
    answer: str


@dataclass
class WritingIntent:
    """写作意图"""
    direction: str              # 写作方向（用户原始输入）
    topic: str = ""             # 提炼后的核心主题
    doc_type: str = ""          # 文种
    target_audience: str = ""   # 目标受众
    purpose: str = ""           # 写作目的
    key_points: List[str] = field(default_factory=list)  # 关键要点
    tone: str = ""              # 语气风格
    length_requirement: str = ""  # 篇幅要求
    is_confirmed: bool = False  # 是否已确认

    def to_summary(self) -> str:
        """生成意图摘要（用于后续 prompt）"""
        parts = [
            f"主题：{self.topic}",
            f"文种：{self.doc_type}",
            f"受众：{self.target_audience}",
            f"目的：{self.purpose}",
        ]
        if self.key_points:
            parts.append(f"关键要点：{'、'.join(self.key_points)}")
        parts.append(f"语气：{self.tone}")
        parts.append(f"篇幅：{self.length_requirement}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        result = asdict(self)
        return result


class IntentEngine:
    """意图理解引擎"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.qa_history: List[QA] = []  # 多轮问答历史
        self.current_intent: Optional[WritingIntent] = None

    def analyze_direction(self, direction: str) -> Dict:
        """
        第一步：分析写作方向，识别已知/缺失要素
        :param direction: 用户输入的写作方向
        :return: 分析结果 {"known": {...}, "missing": [...], "questions": [...]}
        """
        prompt = INTENT_ANALYSIS_PROMPT.format(user_direction=direction)

        try:
            result = self.llm_client.chat_with_prompt(prompt)

            # 提取 JSON 部分
            json_str = self._extract_json(result)
            if json_str:
                analysis = json.loads(json_str)
                return analysis
        except Exception as e:
            print(f"[意图分析] API 调用失败: {e}")

        # 回退：默认返回一些基本问题
        return self._fallback_analysis(direction)

    def generate_questions(self, analysis: Dict) -> List[Question]:
        """
        从分析结果中提取追问问题
        :param analysis: analyze_direction 的返回结果
        :return: Question 列表
        """
        questions = []
        for q_data in analysis.get("questions", []):
            question = Question(
                field=q_data.get("field", ""),
                question=q_data.get("question", ""),
                options=q_data.get("options", []),
            )
            questions.append(question)
        return questions

    def process_answers(self, direction: str, qa_pairs: List[QA]) -> WritingIntent:
        """
        第三步：综合所有信息生成结构化意图
        :param direction: 原始写作方向
        :param qa_pairs: 问答对列表
        :return: WritingIntent
        """
        self.qa_history = qa_pairs

        # 构建问答记录文本
        qa_records = []
        for i, qa in enumerate(qa_pairs, 1):
            qa_records.append(f"第{i}轮：")
            qa_records.append(f"问：{qa.question.question}")
            qa_records.append(f"答：{qa.answer}")

        qa_text = "\n".join(qa_records)

        prompt = INTENT_PROCESS_PROMPT.format(
            direction=direction,
            qa_records=qa_text,
        )

        try:
            result = self.llm_client.chat_with_prompt(prompt)
            json_str = self._extract_json(result)

            if json_str:
                data = json.loads(json_str)
                intent = WritingIntent(
                    direction=direction,
                    topic=data.get("topic", ""),
                    doc_type=data.get("doc_type", ""),
                    target_audience=data.get("target_audience", ""),
                    purpose=data.get("purpose", ""),
                    key_points=data.get("key_points", []),
                    tone=data.get("tone", ""),
                    length_requirement=data.get("length_requirement", ""),
                )
                self.current_intent = intent
                return intent
        except Exception as e:
            print(f"[意图处理] API 调用失败: {e}")

        # 回退
        intent = WritingIntent(direction=direction, topic=direction[:30])
        self.current_intent = intent
        return intent

    def quick_parse(self, direction: str) -> WritingIntent:
        """
        快速模式：一次调用完成意图理解，跳过追问
        """
        prompt = INTENT_QUICK_PARSE_PROMPT.format(direction=direction)

        try:
            result = self.llm_client.chat_with_prompt(prompt)
            json_str = self._extract_json(result)

            if json_str:
                data = json.loads(json_str)
                intent = WritingIntent(
                    direction=direction,
                    topic=data.get("topic", direction[:30]),
                    doc_type=data.get("doc_type", ""),
                    target_audience=data.get("target_audience", ""),
                    purpose=data.get("purpose", ""),
                    key_points=data.get("key_points", []),
                    tone=data.get("tone", ""),
                    length_requirement=data.get("length_requirement", ""),
                )
                self.current_intent = intent
                return intent
        except Exception as e:
            print(f"[快速意图分析] API 调用失败: {e}")

        intent = WritingIntent(direction=direction, topic=direction[:30])
        self.current_intent = intent
        return intent

    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 部分"""
        # 尝试 ```json ... ``` 块
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if match:
            return match.group(1).strip()

        # 尝试 { ... } 直接匹配
        match = re.search(r'(\{[\s\S]*\})', text)
        if match:
            return match.group(1).strip()

        return None

    def _fallback_analysis(self, direction: str) -> Dict:
        """回退分析逻辑"""
        return {
            "known": {
                "doc_type": "",
                "audience": "",
                "purpose": "",
                "key_points": [],
                "length": "",
            },
            "missing": ["doc_type", "audience", "purpose"],
            "questions": [
                {
                    "field": "doc_type",
                    "question": "请问您希望生成哪种类型的文档？",
                    "options": ["报告", "方案", "通知", "请示", "函", "讲话稿", "工作总结", "调研报告"],
                },
                {
                    "field": "audience",
                    "question": "这份文档的目标读者是谁？",
                    "options": ["上级领导", "同级部门", "下属单位", "外部单位", "公众"],
                },
            ],
        }
