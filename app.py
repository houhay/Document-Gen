#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政企风格文档生成系统 - Streamlit Web 界面

功能：
1. 单方向生成 - 支持多轮意图澄清对话
2. 批量生成 - 支持 Excel/CSV/TXT 批量导入
3. 新闻抓取 - 输入网址自动抓取新闻并保存为 Word
4. 历史记录 - 当前会话已生成的文档列表

用法：streamlit run app.py
"""

import os
import sys
import json
import time
import datetime
import tempfile
from pathlib import Path
from typing import List, Optional

import streamlit as st

# 添加项目目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_api_config, save_local_config, ensure_output_dir, API_PROVIDERS, DEFAULT_OUTPUT_DIR
from llm_client import LLMClient, LLMConfig, create_client_from_config
from intent_engine import IntentEngine, WritingIntent, Question, QA
from doc_planner import DocPlanner, Section
from doc_generator import DocGenerator
from word_exporter import WordExporter
from news_scraper import NewsScraper, NewsArticle, ScrapeResult
from batch_processor import BatchProcessor, WritingDirection, BatchResult
from utils import sanitize_filename, open_folder, truncate_text
from prompts import DOC_TYPE_REQUIREMENTS

# ==============================================
# 页面配置
# ==============================================
st.set_page_config(
    page_title="政企文档生成系统",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ==============================================
# 状态初始化
# ==============================================
def init_session_state():
    """初始化所有 session_state 变量"""
    # API 配置
    if "api_config" not in st.session_state:
        st.session_state.api_config = get_api_config()

    if "llm_client" not in st.session_state:
        config = st.session_state.api_config
        llm_config = LLMConfig(
            provider=config.get("provider", "deepseek"),
            api_base=config.get("api_base", ""),
            api_key=config.get("api_key", ""),
            model=config.get("model", ""),
            max_tokens=config.get("max_tokens", 4096),
            temperature=config.get("temperature", 0.7),
        )
        st.session_state.llm_client = LLMClient(llm_config)

    # 输出路径
    if "output_dir" not in st.session_state:
        st.session_state.output_dir = DEFAULT_OUTPUT_DIR

    # 单方向生成状态机
    if "gen_state" not in st.session_state:
        st.session_state.gen_state = "input"  # input / clarifying / confirmed / planning / reviewing / generating / done
    if "writing_direction" not in st.session_state:
        st.session_state.writing_direction = ""
    if "current_intent" not in st.session_state:
        st.session_state.current_intent = None
    if "qa_history" not in st.session_state:
        st.session_state.qa_history = []
    if "current_questions" not in st.session_state:
        st.session_state.current_questions = []
    if "current_outline" not in st.session_state:
        st.session_state.current_outline = None
    if "generated_content" not in st.session_state:
        st.session_state.generated_content = None
    if "generated_file_path" not in st.session_state:
        st.session_state.generated_file_path = None

    # 批量生成
    if "batch_directions" not in st.session_state:
        st.session_state.batch_directions = []
    if "batch_result" not in st.session_state:
        st.session_state.batch_result = None

    # 新闻抓取
    if "news_result" not in st.session_state:
        st.session_state.news_result = None

    # 历史记录（会话级）
    if "history" not in st.session_state:
        st.session_state.history = []


init_session_state()


# ==============================================
# 辅助函数
# ==============================================
def get_client() -> LLMClient:
    """获取当前的 LLM 客户端"""
    return st.session_state.llm_client


def update_api_config():
    """更新 API 配置并重建客户端"""
    config = st.session_state.api_config
    llm_config = LLMConfig(
        provider=config.get("provider", "deepseek"),
        api_base=config.get("api_base", ""),
        api_key=config.get("api_key", ""),
        model=config.get("model", ""),
        max_tokens=config.get("max_tokens", 4096),
        temperature=config.get("temperature", 0.7),
    )
    if "extra_body" in config:
        llm_config.extra_body = config["extra_body"]
    st.session_state.llm_client = LLMClient(llm_config)


def add_to_history(file_path: str, doc_type: str, topic: str):
    """添加到历史记录"""
    st.session_state.history.append({
        "file_path": file_path,
        "file_name": os.path.basename(file_path),
        "doc_type": doc_type,
        "topic": topic,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    })


def reset_generation():
    """重置生成状态"""
    st.session_state.gen_state = "input"
    st.session_state.writing_direction = ""
    st.session_state.current_intent = None
    st.session_state.qa_history = []
    st.session_state.current_questions = []
    st.session_state.current_outline = None
    st.session_state.generated_content = None
    st.session_state.generated_file_path = None


# ==============================================
# 侧边栏 - API 配置
# ==============================================
def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.title("⚙️ 系统配置")

        with st.expander("🤖 大模型 API 配置", expanded=True):
            # 提供商选择
            provider_options = {k: v["label"] for k, v in API_PROVIDERS.items()}
            current_provider = st.session_state.api_config.get("provider", "deepseek")

            provider = st.selectbox(
                "API 提供商",
                options=list(provider_options.keys()),
                format_func=lambda x: provider_options[x],
                index=list(provider_options.keys()).index(current_provider)
                if current_provider in provider_options else 0,
                key="sidebar_provider",
            )

            # 根据提供商更新默认地址
            if provider != current_provider:
                st.session_state.api_config["provider"] = provider
                if provider in API_PROVIDERS:
                    st.session_state.api_config["api_base"] = API_PROVIDERS[provider]["default_api_base"]
                update_api_config()

            # API 地址
            api_base = st.text_input(
                "API 地址",
                value=st.session_state.api_config.get("api_base", ""),
                placeholder="https://api.deepseek.com",
                key="sidebar_api_base",
            )
            if api_base != st.session_state.api_config.get("api_base"):
                st.session_state.api_config["api_base"] = api_base
                update_api_config()

            # API Key
            api_key = st.text_input(
                "API Key",
                value=st.session_state.api_config.get("api_key", ""),
                type="password",
                placeholder="sk-...",
                key="sidebar_api_key",
            )
            if api_key != st.session_state.api_config.get("api_key"):
                st.session_state.api_config["api_key"] = api_key
                update_api_config()

            # 模型名
            model = st.text_input(
                "模型名称",
                value=st.session_state.api_config.get("model", ""),
                placeholder="deepseek-v4-flash",
                key="sidebar_model",
            )
            if model != st.session_state.api_config.get("model"):
                st.session_state.api_config["model"] = model
                update_api_config()

            # 高级参数
            with st.expander("高级参数"):
                temperature = st.slider(
                    "温度 (Temperature)",
                    min_value=0.0, max_value=2.0, step=0.1,
                    value=st.session_state.api_config.get("temperature", 0.7),
                    key="sidebar_temperature",
                )
                st.session_state.api_config["temperature"] = temperature

                max_tokens = st.number_input(
                    "最大 Token 数",
                    min_value=1024, max_value=32768, step=1024,
                    value=st.session_state.api_config.get("max_tokens", 4096),
                    key="sidebar_max_tokens",
                )
                st.session_state.api_config["max_tokens"] = max_tokens

            # 测试连接
            if st.button("🔌 测试连接", use_container_width=True):
                with st.spinner("正在测试连接..."):
                    client = get_client()
                    success, msg = client.test_connection()
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

            # 保存配置
            if st.button("💾 保存配置", use_container_width=True):
                save_local_config(st.session_state.api_config)
                st.success("配置已保存")

        # 输出设置
        with st.expander("📁 输出设置", expanded=False):
            output_dir = st.text_input(
                "输出目录",
                value=st.session_state.output_dir,
                key="sidebar_output_dir",
            )
            st.session_state.output_dir = output_dir
            ensure_output_dir(output_dir)

            if st.button("📂 打开输出目录", use_container_width=True):
                open_folder(output_dir)

        # 关于
        with st.expander("ℹ️ 关于", expanded=False):
            st.markdown("**政企文档生成系统 v1.0**")
            st.markdown("基于大模型驱动的政企风格文档自动生成工具。")
            st.markdown("支持 DeepSeek / OpenAI / Anthropic 等多种大模型。")


# ==============================================
# Tab 1: 单方向生成
# ==============================================
def render_single_tab():
    """渲染单方向生成 Tab"""
    st.header("📝 单方向文档生成")

    state = st.session_state.gen_state

    if state == "input":
        render_input_stage()
    elif state == "clarifying":
        render_clarifying_stage()
    elif state == "confirmed":
        render_intent_confirmed_stage()
    elif state == "planning":
        render_planning_stage()
    elif state == "reviewing":
        render_reviewing_stage()
    elif state == "generating":
        render_generating_stage()
    elif state == "done":
        render_done_stage()


def render_input_stage():
    """输入写作方向阶段"""
    direction = st.text_area(
        "请输入写作方向",
        height=120,
        placeholder="例如：请写一份关于公司2025年数字化转型的工作报告",
        help="描述您想生成的文档主题、文种、受众、用途等",
        key="input_direction",
    )

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("🚀 开始理解意图", use_container_width=True, type="primary"):
            if not direction.strip():
                st.warning("请输入写作方向")
                st.stop()

            st.session_state.writing_direction = direction.strip()

            with st.spinner("正在分析写作方向..."):
                try:
                    engine = IntentEngine(get_client())
                    analysis = engine.analyze_direction(direction)
                    questions = engine.generate_questions(analysis)

                    if questions:
                        st.session_state.current_questions = questions
                        st.session_state.gen_state = "clarifying"
                    else:
                        # 没有追问，直接生成意图
                        intent = engine.quick_parse(direction)
                        st.session_state.current_intent = intent
                        st.session_state.gen_state = "confirmed"
                except Exception as e:
                    st.error(f"分析失败: {str(e)}")

            st.rerun()

    with col2:
        if st.button("快速生成（跳过追问）", use_container_width=True):
            if not direction.strip():
                st.warning("请输入写作方向")
                st.stop()

            st.session_state.writing_direction = direction.strip()

            with st.spinner("正在快速分析..."):
                try:
                    engine = IntentEngine(get_client())
                    intent = engine.quick_parse(direction)
                    st.session_state.current_intent = intent
                    st.session_state.gen_state = "confirmed"
                except Exception as e:
                    st.error(f"分析失败: {str(e)}")

            st.rerun()

    # 常见写作方向示例
    with st.expander("📋 常见写作方向示例"):
        examples = [
            "请写一份关于2025年一季度工作总结的报告",
            "请起草一份关于加强网络安全管理的实施方案",
            "请撰写一篇在年度工作会议上的讲话稿",
            "请拟一份关于申请信息化建设经费的请示",
            "请写一份关于全市数字经济发展情况的调研报告",
        ]
        for ex in examples:
            if st.button(ex, use_container_width=True):
                st.session_state.input_direction = ex
                st.rerun()


def render_clarifying_stage():
    """意图澄清多轮对话阶段"""
    st.subheader("💬 意图澄清对话")

    # 显示写作方向
    st.info(f"**您的写作方向**：{st.session_state.writing_direction}")

    # 显示历史问答
    for qa in st.session_state.qa_history:
        with st.chat_message("assistant"):
            st.markdown(f"**{qa.question.question}**")
        with st.chat_message("user"):
            st.markdown(qa.answer)

    # 显示当前问题
    questions = st.session_state.current_questions
    if questions:
        for q_idx, q in enumerate(questions):
            st.markdown(f"**{q.question}**")

            # 选项按钮
            cols = st.columns(len(q.options))
            for i, (col, opt) in enumerate(zip(cols, q.options)):
                with col:
                    if st.button(opt, key=f"opt_{q_idx}_{i}", use_container_width=True):
                        st.session_state.qa_history.append(
                            QA(question=q, answer=opt)
                        )
                        # 检查是否还有更多问题
                        _process_next_question()
                        st.rerun()

            # 自定义输入
            custom = st.text_input("或输入其他回答", key=f"custom_{q_idx}", label_visibility="collapsed")
            if st.button("提交", key=f"submit_{q_idx}"):
                if custom.strip():
                    st.session_state.qa_history.append(
                        QA(question=q, answer=custom.strip())
                    )
                    _process_next_question()
                    st.rerun()

    # 返回修改
    if st.button("← 重新输入"):
        st.session_state.gen_state = "input"
        st.session_state.qa_history = []
        st.session_state.current_questions = []
        st.rerun()


def _process_next_question():
    """处理下一轮问题或生成意图"""
    try:
        engine = IntentEngine(get_client())
        # 再次分析，看是否还有缺失要素
        direction = st.session_state.writing_direction
        analysis = engine.analyze_direction(direction)
        questions = engine.generate_questions(analysis)

        # 过滤掉已经问过的
        asked_fields = {qa.question.field for qa in st.session_state.qa_history}
        questions = [q for q in questions if q.field not in asked_fields]

        if questions and len(st.session_state.qa_history) < 3:
            st.session_state.current_questions = questions
        else:
            # 够了，生成意图
            intent = engine.process_answers(direction, st.session_state.qa_history)
            st.session_state.current_intent = intent
            st.session_state.current_questions = []
            st.session_state.gen_state = "confirmed"

    except Exception as e:
        st.error(f"处理失败: {str(e)}，请尝试重新输入")
        st.session_state.gen_state = "input"


def render_intent_confirmed_stage():
    """意图确认阶段"""
    st.subheader("✅ 意图理解结果")
    intent = st.session_state.current_intent

    if intent:
        # 展示结构化意图
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**核心主题**：{intent.topic}")
            st.markdown(f"**文种**：{intent.doc_type}")
            st.markdown(f"**目标受众**：{intent.target_audience}")
        with col2:
            st.markdown(f"**写作目的**：{intent.purpose}")
            st.markdown(f"**语气风格**：{intent.tone}")
            st.markdown(f"**篇幅要求**：{intent.length_requirement}")

        if intent.key_points:
            st.markdown(f"**关键要点**：{'、'.join(intent.key_points)}")

        # 操作按钮
        col1, col2, col3 = st.columns([1, 1, 3])

        with col1:
            if st.button("✓ 确认并生成大纲", use_container_width=True, type="primary"):
                with st.spinner("正在生成大纲..."):
                    try:
                        planner = DocPlanner(get_client())
                        outline = planner.generate_outline(intent)
                        st.session_state.current_outline = outline
                        st.session_state.gen_state = "reviewing"
                    except Exception as e:
                        st.error(f"大纲生成失败: {str(e)}")
                st.rerun()

        with col2:
            if st.button("← 重新理解意图"):
                st.session_state.gen_state = "input"
                st.session_state.qa_history = []
                st.session_state.current_questions = []
                st.rerun()


def render_reviewing_stage():
    """大纲确认阶段"""
    st.subheader("📋 文档大纲")

    intent = st.session_state.current_intent
    outline = st.session_state.current_outline

    if intent:
        st.markdown(f"**文档标题**：{intent.topic}（{intent.doc_type}）")

    if outline:
        # 展示大纲树
        for section in outline:
            with st.container():
                if section.level == 1:
                    st.markdown(f"### 📌 {section.title}")
                else:
                    st.markdown(f"**{section.title}**")
                if section.description:
                    st.caption(section.description)
                for sub in section.subsections:
                    st.markdown(f"- **{sub.title}**")
                    if sub.description:
                        st.caption(f"  {sub.description}")

    # 修改反馈
    feedback = st.text_area(
        "如需修改大纲，请描述您的修改意见（留空则直接确认）",
        placeholder="例如：增加一个关于风险分析的章节，调整章节顺序...",
        key="outline_feedback",
    )

    col1, col2, col3 = st.columns([1, 1, 3])

    with col1:
        if st.button("✓ 确认大纲并生成文档", use_container_width=True, type="primary"):
            if feedback.strip() and outline:
                with st.spinner("正在根据反馈修改大纲..."):
                    try:
                        planner = DocPlanner(get_client())
                        outline = planner.refine_outline(outline, feedback)
                        st.session_state.current_outline = outline
                    except Exception:
                        pass  # 使用原大纲

            st.session_state.gen_state = "generating"
            st.rerun()

    with col2:
        if st.button("← 返回修改意图"):
            st.session_state.gen_state = "confirmed"
            st.rerun()


def render_planning_stage():
    """规划中（过渡状态）"""
    st.info("正在准备大纲...")
    time.sleep(0.5)
    st.rerun()


def render_generating_stage():
    """文档生成阶段"""
    st.subheader("⏳ 正在生成文档")

    intent = st.session_state.current_intent
    outline = st.session_state.current_outline

    if not intent or not outline:
        st.error("缺少意图或大纲信息，请重新开始")
        st.session_state.gen_state = "input"
        st.rerun()

    progress_bar = st.progress(0, text="正在生成文档内容...")
    status_text = st.empty()

    try:
        # 生成内容
        status_text.text("正在逐节生成内容...")
        generator = DocGenerator(get_client())
        content = generator.generate_full_document(intent, outline)
        progress_bar.progress(80, text="内容生成完成，正在导出 Word...")

        # 导出 Word
        status_text.text("正在导出 Word 文档...")
        exporter = WordExporter()

        # 生成文件名
        file_name = generator.generate_file_name(content, intent)

        output_dir = ensure_output_dir(st.session_state.output_dir)
        file_path = exporter.export(
            content=content,
            intent=intent,
            output_dir=output_dir,
            file_name=file_name,
            add_cover=False,
        )

        progress_bar.progress(100, text="完成！")

        st.session_state.generated_content = content
        st.session_state.generated_file_path = file_path

        # 加入历史
        add_to_history(file_path, intent.doc_type, intent.topic)

        st.session_state.gen_state = "done"
        st.rerun()

    except Exception as e:
        st.error(f"生成失败: {str(e)}")
        st.session_state.gen_state = "confirmed"

        if st.button("重试"):
            st.session_state.gen_state = "generating"
            st.rerun()


def render_done_stage():
    """生成完成阶段"""
    st.subheader("✅ 文档生成完成！")

    file_path = st.session_state.generated_file_path
    content = st.session_state.generated_content

    if file_path:
        file_name = os.path.basename(file_path)

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📂 打开所在文件夹", use_container_width=True):
                open_folder(file_path)
        with col2:
            with open(file_path, "rb") as f:
                st.download_button(
                    "📥 下载文档",
                    data=f,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
        with col3:
            if st.button("🔄 继续生成新文档", use_container_width=True):
                reset_generation()
                st.rerun()

        st.success(f"文档已保存至：{file_path}")

        # 内容预览
        if content:
            with st.expander("📄 内容预览", expanded=False):
                st.markdown(content[:2000] + ("..." if len(content) > 2000 else ""))

    # 会话中的其他操作建议
    st.info("提示：您可以继续在「批量生成」或「新闻抓取」Tab 中执行其他任务。")


# ==============================================
# Tab 2: 批量生成
# ==============================================
def render_batch_tab():
    """渲染批量生成 Tab"""
    st.header("📂 批量文档生成")

    # 文件上传
    uploaded_file = st.file_uploader(
        "上传文件（支持 xlsx / csv / txt）",
        type=["xlsx", "csv", "txt"],
        help="文件需包含「写作方向」列，可选列：文种、受众、关键点",
    )

    directions = []

    if uploaded_file:
        # 保存到临时文件
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name

        try:
            processor = BatchProcessor(output_dir=st.session_state.output_dir)
            directions = processor.load_from_file(tmp_path)
            os.unlink(tmp_path)
        except Exception as e:
            st.error(f"文件解析失败: {str(e)}")
            return

        if directions:
            st.success(f"成功读取 {len(directions)} 个写作方向")

            # 显示数据预览
            st.subheader("数据预览")
            preview_data = []
            for i, d in enumerate(directions[:10]):
                preview_data.append({
                    "序号": i + 1,
                    "写作方向": truncate_text(d.content, 40),
                    "文种": d.doc_type or "（自动识别）",
                    "受众": d.audience or "（自动识别）",
                })
            st.table(preview_data)

            if len(directions) > 10:
                st.caption(f"... 还有 {len(directions) - 10} 项")

    # 处理模式选择
    mode = st.radio(
        "处理模式",
        options=["quick", "full"],
        format_func=lambda x: {"quick": "⚡ 快速模式（跳过追问，直接生成）", "full": "🔍 完整模式（带意图理解和大纲确认）"}[x],
        horizontal=True,
        key="batch_mode",
        help="快速模式效率高，完整模式质量更可控",
    )

    # 开始生成
    col1, col2 = st.columns([1, 3])
    with col1:
        start_disabled = not directions
        if st.button("🚀 开始批量生成", use_container_width=True, type="primary", disabled=start_disabled):
            st.session_state.batch_directions = directions
            _run_batch_process(directions, mode)

    # 显示批处理结果
    if st.session_state.batch_result:
        render_batch_result(st.session_state.batch_result)


def _run_batch_process(directions: List[WritingDirection], mode: str):
    """执行批量处理"""
    output_dir = ensure_output_dir(st.session_state.output_dir)

    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)

    def update_progress(current, total, msg):
        progress_bar.progress(current / total)
        status_placeholder.text(f"[{current}/{total}] {msg}")

    processor = BatchProcessor(output_dir=output_dir, progress_callback=update_progress)

    def process_one(direction: WritingDirection, index: int, mode: str):
        """处理单个写作方向的回调函数"""
        from batch_processor import BatchFileResult

        try:
            client = get_client()
            content = direction.content

            if mode == "quick":
                # 快速模式
                engine = IntentEngine(client)
                intent = engine.quick_parse(content)
            else:
                # 完整模式
                engine = IntentEngine(client)
                analysis = engine.analyze_direction(content)
                questions = engine.generate_questions(analysis)
                if questions:
                    # 使用默认选项回答
                    qa_pairs = [QA(q=q, answer=q.options[0]) for q in questions[:1]]
                    intent = engine.process_answers(content, qa_pairs)
                else:
                    intent = engine.quick_parse(content)

            # 生成大纲
            planner = DocPlanner(client)
            outline = planner.generate_outline(intent)

            # 生成内容
            generator = DocGenerator(client)
            doc_content = generator.generate_full_document(intent, outline)

            # 导出
            exporter = WordExporter()
            file_name = generator.generate_file_name(doc_content, intent)
            file_path = exporter.export(
                content=doc_content, intent=intent,
                output_dir=output_dir, file_name=file_name,
            )

            # 加入历史
            add_to_history(file_path, intent.doc_type, intent.topic)

            return BatchFileResult(
                direction=direction, index=index, success=True,
                file_path=file_path, topic=intent.topic,
            )

        except Exception as e:
            return BatchFileResult(
                direction=direction, index=index, success=False,
                error=str(e),
            )

    result = processor.process_all(directions, process_one, mode=mode)

    # 保存结果
    processor.save_batch_result(result, output_dir)

    st.session_state.batch_result = result


def render_batch_result(result: BatchResult):
    """显示批处理结果"""
    st.subheader("📊 批量处理结果")

    col1, col2, col3 = st.columns(3)
    col1.metric("总计", result.total)
    col2.metric("成功", result.succeeded)
    col3.metric("失败", result.failed)

    if result.results:
        # 结果列表
        result_data = []
        for r in result.results:
            result_data.append({
                "序号": r.index,
                "写作方向": truncate_text(r.direction.content, 30),
                "状态": "✅ 成功" if r.success else "❌ 失败",
                "文件": os.path.basename(r.file_path) if r.file_path else "-",
                "错误": r.error if r.error else "",
            })
        st.table(result_data)

        # 打开输出目录
        if st.button("📂 打开输出目录"):
            open_folder(st.session_state.output_dir)


# ==============================================
# Tab 3: 新闻抓取
# ==============================================
def render_news_tab():
    """渲染新闻抓取 Tab"""
    st.header("🌐 新闻抓取")

    # URL 输入
    url = st.text_input(
        "目标网址",
        placeholder="请输入新闻页面 URL（单篇文章或列表页均可）",
        key="news_url",
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        mode = st.radio(
            "抓取模式",
            options=["auto", "single", "list"],
            format_func=lambda x: {
                "auto": "🔄 自动检测",
                "single": "📄 单篇文章",
                "list": "📑 列表页批量",
            }[x],
            horizontal=True,
            key="news_mode",
        )
    with col2:
        max_articles = st.number_input(
            "最大抓取数量",
            min_value=1, max_value=50, value=20,
            key="news_max",
        )

    if st.button("🔍 开始抓取", use_container_width=True, type="primary"):
        if not url.strip():
            st.warning("请输入目标网址")
            st.stop()

        with st.spinner("正在抓取..."):
            try:
                scraper = NewsScraper()
                result = scraper.scrape(url, mode=mode)
                st.session_state.news_result = result
            except Exception as e:
                st.error(f"抓取失败: {str(e)}")

    # 显示抓取结果
    if st.session_state.news_result:
        result = st.session_state.news_result
        render_news_result(result)


def render_news_result(result: ScrapeResult):
    """显示新闻抓取结果"""
    st.subheader("📊 抓取结果")

    col1, col2, col3 = st.columns(3)
    col1.metric("发现", result.total)
    col2.metric("抓取成功", result.succeeded)
    col3.metric("失败", result.failed)

    if not result.articles:
        st.warning("未抓取到任何文章")
        return

    # 文章列表
    st.subheader("文章列表")

    selected_indices = []
    for i, article in enumerate(result.articles):
        with st.container():
            col1, col2 = st.columns([0.05, 0.95])
            with col1:
                selected = st.checkbox("", key=f"news_sel_{i}", value=True)
                if selected:
                    selected_indices.append(i)
            with col2:
                st.markdown(f"**{article.title or '（无标题）'}**")
                st.caption(f"来源：{article.source or '未知'}　日期：{article.publish_date or '未知'}　作者：{article.author or '未知'}")
                if article.summary:
                    st.text(truncate_text(article.summary, 200))
            st.divider()

    # 保存按钮
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("💾 保存选中为 Word", use_container_width=True, type="primary"):
            _save_news_to_word(result.articles, selected_indices)

    with col2:
        if st.button("💾 保存全部为 Word", use_container_width=True):
            _save_news_to_word(result.articles, list(range(len(result.articles))))


def _save_news_to_word(articles: List[NewsArticle], indices: List[int]):
    """保存选中的新闻文章为 Word 文档"""
    if not indices:
        st.warning("请至少选择一篇文章")
        return

    output_dir = ensure_output_dir(st.session_state.output_dir)
    exporter = WordExporter()
    saved_files = []

    progress_bar = st.progress(0, text="正在保存...")

    for i, idx in enumerate(indices):
        article = articles[idx]
        try:
            progress_bar.progress((i + 1) / len(indices),
                                  text=f"正在保存: {article.title[:30]}...")

            file_path = exporter.export_news(
                title=article.title or "未命名新闻",
                source=article.source,
                publish_date=article.publish_date,
                content=article.content,
                output_dir=output_dir,
                author=article.author,
            )
            saved_files.append(file_path)

            # 加入历史
            add_to_history(file_path, "新闻", article.title)

        except Exception as e:
            st.error(f"保存失败: {article.title[:20]}... - {str(e)}")

    progress_bar.progress(1.0, text="完成！")

    if saved_files:
        st.success(f"成功保存 {len(saved_files)} 篇新闻文章")

        # 显示文件列表
        for fp in saved_files:
            st.text(f"📄 {os.path.basename(fp)}")

        if st.button("📂 打开输出目录"):
            open_folder(saved_files[0])


# ==============================================
# Tab 4: 历史记录
# ==============================================
def render_history_tab():
    """渲染历史记录 Tab"""
    st.header("📋 历史记录（当前会话）")

    if not st.session_state.history:
        st.info("暂无历史记录。请先在「单方向生成」或「批量生成」Tab 中生成文档。")
        return

    # 搜索
    search = st.text_input("🔍 搜索", placeholder="搜索文件名或主题...")

    # 筛选
    history = st.session_state.history
    if search:
        history = [h for h in history if search.lower() in h["file_name"].lower()
                   or search.lower() in h["topic"].lower()]

    # 显示列表
    for h in reversed(history):
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{h['topic']}**")
                st.caption(f"{h['time']}　|　{h['doc_type']}　|　{h['file_name']}")
            with col2:
                if st.button("📂 打开", key=f"open_{h['file_path']}"):
                    open_folder(h['file_path'])
            with col3:
                if os.path.exists(h['file_path']):
                    with open(h['file_path'], "rb") as f:
                        st.download_button(
                            "📥 下载",
                            data=f,
                            file_name=h['file_name'],
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_{h['file_path']}",
                        )
            st.divider()

    # 清空历史
    if st.button("清空历史"):
        st.session_state.history = []
        st.rerun()


# ==============================================
# 主界面
# ==============================================
def main():
    """主函数"""
    # 渲染侧边栏
    render_sidebar()

    # Tab 布局
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 单方向生成",
        "📂 批量生成",
        "🌐 新闻抓取",
        "📋 历史记录",
    ])

    with tab1:
        render_single_tab()

    with tab2:
        render_batch_tab()

    with tab3:
        render_news_tab()

    with tab4:
        render_history_tab()


if __name__ == "__main__":
    main()
