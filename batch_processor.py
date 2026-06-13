#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量处理引擎
- 支持 TXT / CSV / Excel 文件导入
- 快速模式（跳过意图澄清）和完整模式
- 进度回调
- 结果汇总
"""

import os
import json
import time
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WritingDirection:
    """写作方向（文件导入）"""
    content: str
    doc_type: str = ""
    audience: str = ""
    key_points: str = ""
    purpose: str = ""


@dataclass
class BatchFileResult:
    """单个文件的处理结果"""
    direction: WritingDirection
    index: int
    success: bool
    file_path: str = ""
    error: str = ""
    topic: str = ""


@dataclass
class BatchResult:
    """批处理结果"""
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[BatchFileResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BatchProcessor:
    """批量处理引擎"""

    def __init__(self, output_dir: str, progress_callback: Callable = None):
        """
        :param output_dir: 输出目录
        :param progress_callback: 进度回调函数，参数 (current, total, message)
        """
        self.output_dir = output_dir
        self.progress_callback = progress_callback or (lambda c, t, m: None)

    def load_from_file(self, file_path: str) -> List[WritingDirection]:
        """
        解析导入文件
        支持：xlsx, csv, txt
        :param file_path: 文件路径
        :return: WritingDirection 列表
        """
        ext = Path(file_path).suffix.lower()

        if ext in ('.xlsx', '.xls'):
            return self._load_from_excel(file_path)
        elif ext == '.csv':
            return self._load_from_csv(file_path)
        elif ext == '.txt':
            return self._load_from_txt(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}，支持 xlsx/csv/txt")

    def _load_from_excel(self, file_path: str) -> List[WritingDirection]:
        """从 Excel 文件导入"""
        try:
            import pandas as pd
        except ImportError:
            raise Exception("未安装 pandas，无法读取 Excel 文件")

        df = pd.read_excel(file_path, dtype=str)
        return self._df_to_directions(df)

    def _load_from_csv(self, file_path: str) -> List[WritingDirection]:
        """从 CSV 文件导入"""
        try:
            import pandas as pd
        except ImportError:
            raise Exception("未安装 pandas，无法读取 CSV 文件")

        df = pd.read_csv(file_path, dtype=str, encoding='utf-8')
        return self._df_to_directions(df)

    def _load_from_txt(self, file_path: str) -> List[WritingDirection]:
        """从 TXT 文件导入（每行一个写作方向）"""
        directions = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    # 支持 | 分隔附加信息
                    parts = line.split('|')
                    direction = WritingDirection(content=parts[0].strip())
                    if len(parts) > 1:
                        direction.doc_type = parts[1].strip()
                    if len(parts) > 2:
                        direction.audience = parts[2].strip()
                    directions.append(direction)
        return directions

    def _df_to_directions(self, df) -> List[WritingDirection]:
        """将 DataFrame 转为 WritingDirection 列表"""
        directions = []
        # 列名映射（支持多种命名方式）
        col_map = {
            'direction': ['direction', '写作方向', '方向', 'content', '内容', '标题', 'title'],
            'doc_type': ['doc_type', '文种', '文档类型', 'type'],
            'audience': ['audience', '受众', '目标受众', '读者'],
            'key_points': ['key_points', '关键点', '要点', 'key point', 'key'],
            'purpose': ['purpose', '目的', '用途', '写作目的'],
        }

        def find_col(possible_names):
            for name in possible_names:
                if name in df.columns:
                    return name
            return None

        dir_col = find_col(col_map['direction'])
        if not dir_col:
            # 尝试第一列
            dir_col = df.columns[0]

        for _, row in df.iterrows():
            content = str(row.get(dir_col, '')).strip()
            if not content:
                continue

            direction = WritingDirection(content=content)

            doc_type_col = find_col(col_map['doc_type'])
            if doc_type_col:
                direction.doc_type = str(row.get(doc_type_col, '')).strip()

            audience_col = find_col(col_map['audience'])
            if audience_col:
                direction.audience = str(row.get(audience_col, '')).strip()

            key_col = find_col(col_map['key_points'])
            if key_col:
                direction.key_points = str(row.get(key_col, '')).strip()

            purpose_col = find_col(col_map['purpose'])
            if purpose_col:
                direction.purpose = str(row.get(purpose_col, '')).strip()

            directions.append(direction)

        return directions

    def process_all(self, directions: List[WritingDirection],
                    process_func: Callable,
                    mode: str = "quick") -> BatchResult:
        """
        批量处理所有写作方向
        :param directions: 写作方向列表
        :param process_func: 处理函数，参数 (direction, index, mode) 返回 BatchFileResult
        :param mode: "quick" 快速 / "full" 完整
        :return: BatchResult
        """
        result = BatchResult(total=len(directions))

        for i, direction in enumerate(directions):
            self.progress_callback(i + 1, len(directions), f"正在处理: {direction.content[:30]}...")

            try:
                file_result = process_func(direction, i + 1, mode)
                result.results.append(file_result)

                if file_result.success:
                    result.succeeded += 1
                else:
                    result.failed += 1
                    result.errors.append(f"[{i+1}] {file_result.error}")

            except Exception as e:
                result.failed += 1
                error_msg = f"[{i+1}] {direction.content[:20]}... 处理异常: {str(e)}"
                result.errors.append(error_msg)
                result.results.append(BatchFileResult(
                    direction=direction, index=i+1, success=False, error=error_msg
                ))

            self.progress_callback(i + 1, len(directions),
                                   f"完成 {i+1}/{len(directions)}"
                                   f"（成功: {result.succeeded}, 失败: {result.failed}）")

        return result

    @staticmethod
    def save_batch_result(result: BatchResult, output_dir: str):
        """保存批处理结果到 JSON 文件"""
        report = {
            "total": result.total,
            "succeeded": result.succeeded,
            "failed": result.failed,
            "results": [
                {
                    "index": r.index,
                    "content": r.direction.content[:50],
                    "success": r.success,
                    "file_path": r.file_path,
                    "topic": r.topic,
                    "error": r.error,
                }
                for r in result.results
            ],
        }

        from datetime import datetime
        report_path = os.path.join(
            output_dir,
            f"批量处理报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report_path
