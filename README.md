# 政企文档生成系统 v1.0

> 基于大语言模型（LLM）的政企文档自动生成工具，输入写作方向即可一键生成规范的 Word 文档。

## ✨ 核心功能

- **📝 单方向文档生成** — 输入写作意图（如"写一份关于2025年数字化转型的工作汇报"），系统自动理解意图、规划大纲、逐节生成内容，最终导出为标准公文格式的 Word 文档。
- **📊 批量文档生成** — 支持从 Excel（.xlsx）、CSV、TXT 文件批量导入写作方向，快速生成多份文档。
- **📰 新闻抓取** — 输入新闻 URL，自动识别单篇文章或列表页，抓取正文内容并保存为 Word 文档。
- **🤖 多轮意图澄清** — 当写作方向不够明确时，系统会主动提问补充关键信息（读者、目的、语气、篇幅等）。
- **📋 历史记录** — 会话级别的生成历史，支持搜索、筛选、下载和打开文件夹。

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| UI 框架 | [Streamlit](https://streamlit.io/) |
| 编程语言 | Python 3 |
| 大模型接口 | OpenAI 兼容 API / Anthropic SDK |
| 文档生成 | [python-docx](https://python-docx.readthedocs.io/) |
| 数据处理 | pandas, openpyxl |
| 网页抓取 | requests, BeautifulSoup4, lxml |
| 打包发布 | PyInstaller |

### 支持的 LLM 提供商

- **DeepSeek**（默认）
- **OpenAI** 兼容接口
- **Anthropic Claude**
- **自定义**（任意兼容 OpenAI 格式的 API 端点）

## 🚀 快速开始

### 方式一：源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/houhay/Document-Gen.git
cd Document-Gen

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动应用
python run.py
```

启动后浏览器会自动打开 `http://localhost:8501`。

也可以直接使用 Streamlit 命令：

```bash
streamlit run app.py
```

### 方式二：使用打包好的可执行文件

下载 `dist/政企文档生成系统.exe`，双击运行即可。

### 配置 API 密钥

**方法一（推荐）**：在应用侧边栏的「API 配置」中填写密钥，自动保存到 `config.local.json`。

**方法二**：在项目根目录创建 `key.txt` 文件：
```
你的API密钥
https://api.deepseek.com/v1（或其他API地址）
```
第一行为 API Key，最后一行为 API Base URL。

## 📁 项目结构

```
Document-Gen/
├── app.py                  # Streamlit 主应用（4 个标签页）
├── run.py                  # 启动器（嵌入式服务器 + 自动打开浏览器）
├── config.py               # 配置管理（多提供商、持久化）
├── llm_client.py           # LLM 客户端（OpenAI 兼容 + Anthropic）
├── intent_engine.py        # 意图理解引擎（分析 + 多轮澄清）
├── doc_planner.py          # 文档大纲规划器
├── doc_generator.py        # 逐节文档生成器
├── word_exporter.py        # Word 导出器（公文格式）
├── news_scraper.py         # 新闻抓取器
├── batch_processor.py      # 批量处理引擎
├── prompts.py              # 集中式提示词模板
├── utils.py                # 工具函数
├── requirements.txt        # Python 依赖
├── 政企文档生成系统.spec      # PyInstaller 打包配置
└── dist/
    └── 政企文档生成系统.exe   # 独立可执行文件
```

## 🏗 架构设计

系统采用**流水线架构**，文档生成依次经过以下阶段：

```
写作方向 → 意图理解 → 大纲规划 → 内容生成 → Word 导出
```

- **IntentEngine** — 分析写作意图，识别已知/缺失要素（文档类型、读者、目的、要点、语气、篇幅），必要时进行多轮对话补全信息。
- **DocPlanner** — 根据意图生成结构化大纲（章节/小节），支持 LLM 生成和本地模板回退。
- **DocGenerator** — 逐节调用 LLM 生成正文内容，节与节之间传递上下文保持连贯性。
- **WordExporter** — 按中文公文标准格式导出 .docx（仿宋正文、黑体标题、标准页边距、行间距）。

### 支持文档类型

| 文档类型 | 适用场景 |
|----------|----------|
| 报告 | 工作汇报、项目报告 |
| 方案 | 实施方案、工作计划 |
| 通知 | 会议通知、事项通知 |
| 请示 | 向上级请示事项 |
| 函 | 平行单位往来函件 |
| 讲话稿 | 会议讲话、致辞 |
| 工作总结 | 年度/季度工作总结 |
| 调研报告 | 调查研究报告 |

## 📦 打包发布

```bash
pyinstaller "政企文档生成系统.spec" --clean
```

打包产物位于 `dist/` 目录。

## 📄 许可证

本项目仅用于学习和研究目的。

---

**Powered by Streamlit + LLM**
