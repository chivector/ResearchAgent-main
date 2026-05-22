# ResearchFlowAgent

> 面向**前沿科研问题**（物理 / 数学 / 生命科学等）的多 Agent 协作框架，强调**义务感知（Obligation-aware）上下文管理**与**可审计的证据闭包**，专为高难度推导题、综合性研究问题以及长上下文场景设计。

ResearchFlowAgent 基于 [smolagents](https://github.com/huggingface/smolagents) + [LiteLLM](https://github.com/BerriAI/litellm) 构建，可在同一框架内编排 **25+ 个角色化 Agent**（Director / ContextMiner / HypothesisModeler / FormalDeriver / Verification / Writer …），并通过自研的 **PayloadView / OPC（Obligation-aware Payload Compiler）** 机制把上下文管理形式化为**受约束的最小充分集合选择问题**，在控制 token 成本的同时保证义务覆盖、证据支持闭包和角色许可。

---

## 目录

- [项目特点](#项目特点)
- [系统架构](#系统架构)
- [仓库结构](#仓库结构)
- [安装](#安装)
- [环境变量配置](#环境变量配置)
- [快速开始](#快速开始)
- [命令行参数说明](#命令行参数说明)
- [输入与输出格式](#输入与输出格式)
- [PayloadView：理论与报告](#payloadview理论与报告)
- [扩展与二次开发](#扩展与二次开发)
- [测试与脚本](#测试与脚本)
- [常见问题](#常见问题)
- [许可协议](#许可协议)

---

## 项目特点

- **多 Agent 协作管线**：Director 统一调度，前置阶段（题意对齐、问题分解、轴线构建）→ 方法设计阶段（湿实验 / 干实验 / 数据分析）→ 推导阶段（ProofPlanner / FormalDeriver / ProofAuditor）→ 综合阶段（Synthesis / Writer / Polisher / MetaReviewer）。
- **义务感知的上下文编译**：每次 Agent 调用从全局记忆图 (OC-HMG) 中编译一个**最小充分的 PayloadView**，避免把整份 dossier 灌给每个角色，显著降低 token 开销与领域污染风险。
- **支持闭包与许可序**：claim 必须有可见的 evidence / derivation 支持路径；Writer / FormalDeriver 仅允许引用 `supported` 或 `verified` 的内容，`speculative / prohibited` 内容自动被分流到 warning 视图。
- **可对比的 token 报告**：每次运行可导出 `payload_report.json`，包含按角色聚合的渲染 token、对照式 legacy token、节省比例和验证状态。
- **统一的 LiteLLM 接入**：所有 Agent 共享同一 API_BASE / API_KEY，模型可按角色独立指定（如 Director 用 `gpt-5.4`、推导 Agent 用 `claude-opus-4-6`、网搜 Agent 用 `gemini-3.1-pro-preview`）。
- **快/优两档运行模式**：`--mode fast`（轻量管线，便于调试）/ `--mode hq`（完整 high-quality 管线）。
- **题目运行接口**：既支持单文件题目（`--input-file`），也支持 JSONL 数据集 + 题号定位（`--dataset-file --problem-id`）。

---

## 系统架构

```
┌─────────────────────────── Director ───────────────────────────┐
│                                                                │
│ 1. 题意对齐：QuestionIntentAligner ─► AxiomBuilder             │
│ 2. 上下文挖掘：ContextMiner ─► GroundTruthSearcher（web 检索） │
│ 3. 任务分解：TaskGraphBuilder ─► PromptProximitySelector       │
│ 4. 方法设计：HypothesisModeler / WetLab / InSilico / DataAna.  │
│ 5. 形式化推导：ProofPlanner ─► FormalDeriver ─► ProofAuditor   │
│ 6. 综合写作：Synthesizer ─► Writer ─► Polisher ─► MetaReviewer │
│ 7. 修补回路：PatcherAgent / Critique / Tradeoff / Verification │
│                                                                │
└────────────────────────────────────────────────────────────────┘
            │                                  ▲
            ▼                                  │
   PayloadView 编译                    Memory Graph (OC-HMG)
   （义务覆盖 + 支持闭包 + 角色许可 + 预算约束）
```

> 完整理论细节见 [`docs/payloadview_theory.md`](docs/payloadview_theory.md)。

---

## 仓库结构

```
ResearchAgent-main/
├── run.py                        # CLI 入口
├── run.sh                        # 示例启动脚本
├── requirements.txt              # 主依赖
├── test.jsonl                    # 示例题目数据集（物理推导题）
├── smoke_problem.txt             # 单题示例
├── src/sciagent/
│   ├── runner.py                 # 主流程编排
│   ├── agents/                   # 25+ 个 Agent builder
│   ├── tools/                    # 自定义工具（web 检索、契约检查、任务图、维度校验等）
│   ├── memory.py / memory_graph.py
│   ├── payload_compiler.py       # OPC：义务感知 Payload 编译器
│   ├── prompts.py                # 各 Agent 的提示词
│   └── schemas.py                # ResearchDossier 等数据结构
├── scripts/                      # 批量实验与报告生成脚本
│   ├── run_midterm_batch.py
│   ├── analyze_midterm_batch.py
│   ├── run_payload_compiler_experiment.py
│   ├── analyze_payload_experiment.py
│   ├── llm_judge_answer.py
│   └── make_full_dossier_comparison_figure.py
├── tests/                        # pytest 测试
├── docs/
│   └── payloadview_theory.md     # PayloadView 形式化定义与最小充分性证明
├── outputs/                      # 运行产物（默认目录）
└── smolagents-main/              # 内嵌的可编辑安装版 smolagents
```

---

## 安装

> 建议 Python 3.10+；推荐使用 `venv` 或 `conda` 隔离环境。

```bash
# 1) 主依赖
pip install -r requirements.txt

# 2) 以可编辑模式安装内嵌的 smolagents（仓库已自带）
pip install -e smolagents-main/
```

如需联网检索（GroundTruthSearcher），请额外安装并配置 Tavily 的依赖（已包含在 `smolagents` 内置工具集中）。

---

## 环境变量配置

在仓库根目录创建 `.env` 文件（已被 `.gitignore` 忽略）：

```ini
# 统一的 LLM 网关（兼容 OpenAI / Anthropic / Gemini / LiteLLM Proxy）
API_BASE=https://your-llm-gateway.example.com/v1
API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Web 检索 API（可选，仅 GroundTruthSearcher 需要）
TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxx
```

> 也支持等价的旧变量名 `DF_API_URL` / `DF_API_KEY`。

模型 ID 在命令行通过 `--director-model` 等参数指定，例如 `openai/gemini-3-flash-preview`、`anthropic/claude-opus-4-6`、`openai/gpt-5.4` 等（前缀由 LiteLLM 路由决定）。各 Agent 若未单独覆盖，将沿用 [`src/sciagent/runner.py`](src/sciagent/runner.py) 中的 `DEFAULT_AGENT_MODELS`，并自动复用 director 的 provider 前缀。

---

## 快速开始

### 1) 跑示例数据集中的第 1 题

```bash
python run.py \
    --dataset-file test.jsonl \
    --problem-id 1 \
    --director-model "openai/gemini-3-flash-preview" \
    --mode fast \
    --output-file "outputs/output.md" \
    --log-file "outputs/output.log"
```

或直接运行：

```bash
bash run.sh
```

### 2) 跑自己的单题文件

```bash
python run.py \
    --input-file my_problem.txt \
    --director-model "openai/gpt-5.4" \
    --mode hq \
    --output-file outputs/my_problem.md \
    --log-file outputs/my_problem.log \
    --payload-report-file outputs/my_problem.payload.json
```

`--payload-report-file` 触发完整 dossier 模式，会额外导出按角色聚合的 PayloadView token 报告（参见下文 [PayloadView 章节](#payloadview理论与报告)）。

### 3) 为不同 Agent 指定不同模型

```bash
python run.py \
    --dataset-file test.jsonl --problem-id 2 \
    --director-model "openai/gpt-5.4" \
    --formal-deriver-model "anthropic/claude-opus-4-6" \
    --writer-model "anthropic/claude-opus-4-6" \
    --ground-truth-model "openai/gemini-3.1-pro-preview" \
    --mode hq \
    --output-file outputs/p2.md
```

---

## 命令行参数说明

| 参数 | 说明 |
| --- | --- |
| `--director-model` *(必填)* | Director 使用的模型 ID（LiteLLM 风格，含 provider 前缀） |
| `--input-file` | 单题纯文本路径 |
| `--dataset-file` + `--problem-id` | JSONL 数据集路径 + 1-based 题号 |
| `--mode {fast,hq}` | 运行模式，`fast` 调试用，`hq` 完整管线 |
| `--output-file` | 最终答案保存路径（Markdown） |
| `--log-file` | 完整运行日志（stdout/stderr Tee） |
| `--payload-report-file` | 启用 dossier 模式并导出 PayloadView 报告（JSON） |
| `--*-model` | 为单个 Agent 覆盖模型，详见 [`run.py`](run.py)；未设置则回退到 `DEFAULT_AGENT_MODELS` |

可被覆盖的 Agent 模型包括：`context / ground-truth / question-intent / task-graph / axiom-builder / hypothesis / prompt-proximity / pathway-mapping / comparison-matrix / wetlab / insilico / data-analysis / mechanism-inferer / critique / estimator / synthesizer / tradeoff / verification / writer / polisher / meta-reviewer / proof-planner / formal-deriver / proof-auditor / patcher`。

---

## 输入与输出格式

### 输入

- **单题文件**：纯文本，包含 `Context: …` 和 `Question: …` 两部分即可。
- **JSONL 数据集**：每行一个对象，至少包含字段：

  ```json
  {"problem": "...题目正文...", "answer": "...评分细则（可选）...", "subject": "physics", "task_group_id": "..."}
  ```

  示例参见 [`test.jsonl`](test.jsonl)（来自前沿物理 / 数学 / 量子信息推导题）。

### 输出

- `--output-file` 指定的 Markdown 文件：最终答卷，包含推导、公式与结论。
- `--log-file`：完整管线日志（含每个 Agent 的输入/输出、工具调用、补丁回路）。
- `--payload-report-file`：PayloadView 报告，结构示例：

  ```json
  {
    "summary": {
      "payload_view_count": 42,
      "verified_count": 41,
      "fail_soft_count": 1,
      "total_rendered_token_cost": 51234,
      "total_legacy_token_cost": 187456,
      "total_token_savings_vs_legacy": 136222,
      "total_token_savings_ratio_vs_legacy": 0.7267,
      "by_role": { "writer": { "count": 3, "rendered_token_cost": 8421, ... } }
    },
    "payload_views": [ /* 每次 Agent 调用的逐条 PayloadView 记录 */ ]
  }
  ```

---

## PayloadView：理论与报告

PayloadView 把"该让 Agent 看到什么"形式化为一个**受约束的集合选择问题**：

```
minimize    Cost(C) + λ Risk(C)
subject to  Coverage(C, O_a) = 1        # 义务覆盖
            SupportClosure(C, a) = 1    # 支持闭包
            DependencyClosure(C, a) = 1 # 依赖闭包（公式 / 变量 / 单位不可拆散）
            RoleLicense(C, a) = 1       # 角色许可（Writer 只能见 supported/verified）
```

实际系统采用轻量打分近似 + 五条候选轨迹（`minimal / support_complete / dependency_complete / critic_safe / broad_fallback`）+ 有限 repair 路径，结合 verifier 给出 fail-soft 兜底。

完整推导、记忆图原子定义、support license 序、minimal sufficiency 证明、与 RAG/摘要/prompt trimming 的对比见：

📄 [`docs/payloadview_theory.md`](docs/payloadview_theory.md)

对照实验脚本：
- [`scripts/run_payload_compiler_experiment.py`](scripts/run_payload_compiler_experiment.py) — payload-on/off 双跑
- [`scripts/analyze_payload_experiment.py`](scripts/analyze_payload_experiment.py) — token 消耗与得分分析
- [`scripts/make_full_dossier_comparison_figure.py`](scripts/make_full_dossier_comparison_figure.py) — 出图

---

## 扩展与二次开发

- **新增 Agent**：在 [`src/sciagent/agents/`](src/sciagent/agents/) 下新建 `build_xxx_agent`，在 `agents/__init__.py` 中导出，并在 [`runner.py`](src/sciagent/runner.py) 的 `DEFAULT_AGENT_MODELS` 注册默认模型；如需被 Director 调度，在 prompts / dual_track_routing 中加入相应分支。
- **新增工具**：在 [`src/sciagent/tools/`](src/sciagent/tools/) 实现一个继承自 `smolagents.Tool` 的类（或装饰器函数），并在 `tools/__init__.py` 导出。
- **新增题型**：在 [`scripts/`](scripts/) 编写批跑脚本（参考 `run_midterm_batch.py` 的 dataset 读取与并发约束写法）。
- **修改 PayloadView 策略**：见 [`src/sciagent/payload_compiler.py`](src/sciagent/payload_compiler.py) 与 [`src/sciagent/agents/payload_builder.py`](src/sciagent/agents/payload_builder.py)。

---

## 测试与脚本

```bash
# 单元测试
pytest tests/ -v

# 批量评测（示例：中期实验集）
python scripts/run_midterm_batch.py
python scripts/analyze_midterm_batch.py

# LLM-as-Judge 评分
python scripts/llm_judge_answer.py
```

---

## 常见问题

**Q：API_BASE 该填什么？**
A：任何兼容 OpenAI Chat Completions 接口的网关都可以（OpenAI 官方、Anthropic、LiteLLM Proxy、自建中转）。模型名通过 `--*-model` 参数以 LiteLLM 风格传入。

**Q：`fast` 与 `hq` 的区别？**
A：`fast` 跳过部分重量级 Agent（如 ProofAuditor / MetaReviewer 的多轮回路），用于快速调试；`hq` 启用完整管线，含修补回路与多次验证。

**Q：跑一次大约消耗多少 token？**
A：取决于题目复杂度与所选模型。开启 PayloadView 编译后，一次完整 `hq` 跑通常比"把整份 dossier 灌给每个 Agent"的 legacy 方案节省 **60%–75%** 的 prompt token（实测见 PayloadView 报告）。

**Q：联网检索是否必须？**
A：非必须。未设置 `TAVILY_API_KEY` 时 GroundTruthSearcher 会降级为基于已有上下文的"概念检索"，不影响主管线。

---

## 许可协议

本项目以 [Apache License 2.0](LICENSE) 发布。内嵌的 [`smolagents-main/`](smolagents-main/) 子目录遵循其原项目的许可协议（Apache-2.0）。

---

## 致谢

- [smolagents](https://github.com/huggingface/smolagents) — 提供底层 Agent 抽象与工具协议
- [LiteLLM](https://github.com/BerriAI/litellm) — 统一的 LLM 网关
- [Tavily](https://tavily.com/) — Web 检索 API

如果本项目对你的科研工作有帮助，欢迎 Star ⭐ 或在 issue 中分享你的使用案例。
