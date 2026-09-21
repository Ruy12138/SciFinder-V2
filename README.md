# SciFinder V2

> An Undermind-first literature discovery and browser-based paper retrieval skill for Codex.

SciFinder V2 将 **Undermind、Google Scholar 与 InstSci** 串联成一个完整工作流：

**研究主题 → 文献发现 → 相关性筛选 → 元数据去重 → 出版社拆批 → PDF 下载 → 统一报告**

[中文](#中文) | [English](#english)

<a id="中文"></a>

## 中文

### 项目简介

SciFinder V2 是面向 Codex 的文献检索与下载 Skill。

它以 [InstSci](https://github.com/Rimagination/instsci) 作为论文下载和机构访问引擎，在此基础上增加：

- Undermind 优先的自然语言文献检索
- Google Scholar 低频补充检索
- 多来源元数据标准化与去重
- 相关性筛选和下载数量控制
- 按出版社拆分 DOI 下载任务
- Elsevier 浏览器机构认证下载
- JSON、CSV 和 Markdown 统一结果报告

SciFinder V2 不修改 InstSci 的 Python 包、CLI 或 MCP 公共接口，而是作为上层编排 Skill 使用现有能力。

## 为什么需要 V2

### 1. 避免依赖 Elsevier 全文 API

Elsevier API Key 可能可以返回题名、DOI 等元数据，但没有机构级全文 API 权限时，通常无法通过 API 批量获取 PDF。反复尝试 API 下载会造成较长等待，并不能提高成功率。

SciFinder V2 默认不使用 Elsevier API 下载全文，也不会在下载流程中调用：

- `fetch_paper`
- `instsci fetch`
- `instsci elsevier-setup`
- Elsevier FULL XML、object/eid 或其他全文 API 路径

Elsevier 文献默认直接通过 InstSci 的可见浏览器和机构认证下载：

```bash
instsci papers <doi-file> \
  --publisher elsevier \
  --institution "Beijing Normal University" \
  --concurrency 1
```

需要登录、SSO、2FA 或验证码时，由用户在可见 CloakBrowser 中手动完成。

已有 Elsevier API Key 可以继续保留，但 SciFinder V2 不会默认使用或验证它。只有用户明确要求启用 API 路径时才会使用。

这项改动消除了对 Elsevier 全文 API 授权的依赖，但不会绕过出版社订阅权限；最终下载能力仍取决于用户所在机构的合法访问权限。

### 2. 避免 Google Scholar 异常导致任务长时间等待

Google Scholar 容易出现：

- 页面访问超时
- CAPTCHA 或异常流量提示
- 连续刷新后触发进一步限制
- 过长检索式返回不稳定
- 批量访问导致会话被限制

SciFinder V2 将 Google Scholar 定位为补充来源，而不是整个检索流程的唯一入口：

- 首先使用 Undermind 执行一次自然语言深度检索
- 再根据研究主题和高相关论文生成 2–4 条紧凑的 Scholar 查询
- 查询串行执行，不并行打开多个检索标签页
- 每条查询默认只读取第一页
- 只有新增候选少于 5 篇且没有风控提示时才读取第二页
- 不自动批量展开 `Cited by`
- 不使用无头浏览器、代理轮换、指纹伪装或验证码绕过
- 出现 CAPTCHA 时保留页面，等待用户手动完成
- 同一任务再次出现风控时停止 Scholar 分支
- 连续两次页面超时时停止 Scholar 分支
- Scholar 失败不会阻断 Undermind 结果的筛选和下载

该策略遵循 [Google Scholar 官方使用说明](https://scholar.google.com/intl/uk/scholar/help.html)，重点是减少无效等待和风控风险，而不是规避平台限制。

### 3. Undermind 优先检索

用户只需要提供自然语言研究主题，不必先编写复杂的布尔检索式。

默认流程会：

1. 读取 Undermind 使用说明。
2. 自动选择唯一可写的 workspace。
3. 将研究问题作为自然语言目标发起 deep search。
4. 检查排名前 30 篇结果。
5. 根据研究对象、核心变量或干预、结局、方法和主题中心性判断相关性。
6. 默认保留最多 20 篇直接相关论文。
7. 为每篇保留论文记录简短的相关性理由。

如果用户明确表示继续同一项检索，可以复用已有 deep search；否则创建新的检索任务。

### 4. 自动生成并清洗 Scholar 查询词

SciFinder V2 从原始研究主题和 Undermind 高相关论文中提取：

- 核心概念
- 英文同义词
- 缩写
- 拼写变体
- 常见自然语言表达

生成查询前会进行：

- Unicode NFKC 标准化
- 大小写和标点统一
- 单复数重复清理
- 包含关系清理
- 多词短语加双引号
- 医学主题按需参考 MeSH
- 将 MeSH 倒装词转换为自然英语

每个概念组最多保留 6 个词，最终生成 2–4 条易于理解的查询，而不是一个过长的检索式。

### 5. 保守而确定的文献去重

SciFinder V2 使用 `scripts/merge_literature_results.py` 合并 Undermind 和 Google Scholar 结果。

自动合并规则：

1. DOI 统一为小写，并移除 `doi:`、`doi.org` 前缀和尾部标点。
2. 相同 DOI 的记录必须合并。
3. 没有 DOI 时，只有同时满足以下条件才会自动合并：
   - 规范化标题完全一致
   - 第一作者一致
   - 年份相差不超过 1 年
4. 不使用模糊标题相似度直接合并论文。
5. 无法确认的预印本、会议论文和期刊正式版本分别保留，并标记为 `possible_duplicate`。
6. 下载时优先选择具有 DOI 的正式发表版本。

元数据优先级为：

```text
DOI 或出版社元数据 > Undermind > Google Scholar
```

每篇论文会保留来源数组，以说明它来自 Undermind、Google Scholar，还是同时来自两者。

### 6. 开放获取优先和出版社拆批

下载顺序为：

1. 优先使用 Undermind 已返回的合法开放获取 PDF。
2. 验证 PDF 文件头、文件大小、页数以及 DOI 或标题匹配。
3. 跳过已经验证成功的文件。
4. 对剩余 DOI 使用 InstSci 识别出版社。
5. 为每个出版社生成独立 DOI 文件。
6. 每个出版社分别运行下载任务，默认 `--concurrency 1`。

不同出版社的 DOI 不会混入同一个 `instsci papers` 任务。

没有 DOI 且没有合法开放 PDF 的论文会标记为：

```text
metadata_resolution_failed
```

有 DOI、但 InstSci 暂无对应出版社 profile 的闭源论文会标记为：

```text
profile_missing
```

`profile_missing` 不会被错误报告为“不支持”。

### 7. 可复核的统一报告

每次任务默认写入独立目录：

```text
~/.instsci/runs/<topic-slug>-<timestamp>/
├── discovery/
│   ├── undermind.json
│   ├── google_scholar.json
│   └── search_queries.json
├── doi_batches/
│   └── <publisher>.txt
├── downloads/
└── reports/
    ├── search_manifest.json
    ├── search_manifest.csv
    └── final_report.md
```

最终报告包括：

- 题名
- DOI
- 数据来源
- 相关性及判断理由
- 重复或可能重复关系
- 出版社
- 下载状态
- PDF 路径
- 后续操作建议

JSON、CSV 和 Markdown 报告从同一份记录生成，确保以下统计数量一致：

- `success`：PDF 已下载并完成验证
- `unverified`：存在 PDF，但身份或内容验证不足
- `missing`：未获得有效 PDF
- `pending`：正在等待下载、登录或用户操作

默认只下载高相关论文，去重后的下载上限为 30 篇。

## 工作流程

```text
研究主题
   │
   ▼
Undermind deep search
   │
   ├── 检查前 30 篇
   └── 保留最多 20 篇高相关论文
   │
   ▼
生成 2–4 条 Google Scholar 补充查询
   │
   ├── 低频串行访问
   ├── CAPTCHA 由用户处理
   └── 超时或重复风控时立即降级
   │
   ▼
元数据标准化与保守去重
   │
   ▼
筛选高相关论文，最多 30 篇
   │
   ├── 开放获取 PDF 优先
   └── 剩余 DOI 按出版社拆批
   │
   ▼
InstSci 可见浏览器下载
   │
   ▼
JSON + CSV + Markdown 统一报告
```

## 依赖

使用完整工作流需要：

- Codex
- 已连接且具有可写 workspace 的 Undermind
- [InstSci](https://github.com/Rimagination/instsci)
- Python 3.10 或更高版本
- 普通可见 Chrome，用于 Google Scholar
- InstSci CloakBrowser，用于出版社和机构认证
- 用户本人合法拥有的学校、图书馆或机构访问权限

本项目默认机构配置为：

```text
北京师范大学
Beijing Normal University
```

机构名称可在实际运行时覆盖。

## 安装

首先安装 InstSci：

```bash
pipx install git+https://github.com/Rimagination/instsci.git

# 或
uv tool install git+https://github.com/Rimagination/instsci.git
```

配置机构：

```bash
instsci setup --school "Beijing Normal University"
```

然后在 Codex 中安装本 Skill：

```text
请帮我安装并配置这个 Codex skill：
https://github.com/Ruy12138/SciFinder-V2
```

## 使用示例

### 根据研究主题检索并下载

```text
使用 $scifinder 检索生成式人工智能对大学生批判性思维的影响，
完成去重，并下载高相关论文。
```

### 仅检索，不立即下载

```text
使用 $scifinder 检索数字游戏化学习与学生认知负荷相关研究，
先返回去重后的高相关论文清单，不下载 PDF。
```

### 已有 DOI 列表

```text
使用 $scifinder 按出版社整理这些 DOI，并通过机构认证下载论文。
```

### 继续同一次检索

```text
继续刚才的 Undermind 检索，补充 Google Scholar 结果并完成下载。
```

## 测试

运行离线去重和拆批测试：

```bash
python3 scripts/test_merge_literature_results.py
```

测试不会真实批量访问 Google Scholar，也不会调用出版社 API 下载论文。

## 项目结构

```text
SciFinder-V2/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── literature-discovery.md
│   └── publisher-pdf-workflow.md
└── scripts/
    ├── merge_literature_results.py
    └── test_merge_literature_results.py
```

## 访问与合规

- 不绕过出版社付费墙或机构权限。
- 不自动填写或保存密码、OTP、2FA 和验证码。
- 不使用 CAPTCHA 求解器或反检测技术。
- 不将 API Key、Cookie、Token 或机构凭据写入报告或提交到 Git。
- Google Scholar 仅作为小规模、低频、人工监督的补充来源。
- 出版社 PDF 是否可获取，以可见浏览器中的最终结果为准。
- HTTP 请求、日志、Cookie 和 DOI 路由只作为预检查或辅助证据。
- 所有下载应符合出版社、数据库和所在机构的使用条款。

## 与 InstSci 的关系

SciFinder V2 是 InstSci 的上层检索和任务编排 Skill，不是 InstSci Python 包的替代品。

- InstSci 负责开放获取发现、出版社识别、机构访问和 PDF 下载。
- SciFinder V2 负责 Undermind/Scholar 检索、筛选、去重、拆批和报告。
- 本项目不会更改 InstSci 的公共 CLI 或 MCP 接口。

上游项目：

- [Rimagination/instsci](https://github.com/Rimagination/instsci)

## 免责声明

本项目中的“SciFinder”是该 Codex Skill 的项目名称，与 CAS SciFinder 产品及其运营方不存在隶属、授权或合作关系。

---

<a id="english"></a>

## English

### Overview

SciFinder V2 is a Codex skill that combines literature discovery, metadata deduplication, publisher routing, institutional authentication, and PDF retrieval in one workflow:

```text
Research topic
→ Undermind
→ low-frequency Google Scholar supplementation
→ relevance screening
→ deduplication
→ publisher-specific DOI batches
→ InstSci browser retrieval
→ unified reports
```

It uses [InstSci](https://github.com/Rimagination/instsci) as the paper retrieval and institutional-access engine without changing InstSci's public Python, CLI, or MCP interfaces.

### Why V2

#### Browser-first Elsevier retrieval

An Elsevier API key may provide metadata without granting institutional full-text API access. SciFinder V2 therefore does not use Elsevier full-text APIs for downloads by default.

Elsevier papers are routed directly through InstSci's visible, institution-authenticated browser workflow:

```bash
instsci papers <doi-file> \
  --publisher elsevier \
  --institution "Beijing Normal University" \
  --concurrency 1
```

The existing API key may remain configured, but the skill does not use or validate it for downloads unless the user explicitly requests an API workflow.

Passwords, SSO, 2FA, and CAPTCHA are completed by the user in the visible CloakBrowser window.

#### Scholar failure does not block the workflow

Google Scholar is a supplementary source rather than the primary search engine.

SciFinder V2:

- searches Undermind first;
- generates 2–4 compact Scholar queries;
- executes queries serially in a normal visible Chrome session;
- reads the first results page by default;
- reads page two only when fewer than five new candidates were found and no risk signal appeared;
- pauses for manual CAPTCHA completion;
- stops Scholar after a second risk event or two consecutive timeouts;
- continues screening and downloading the Undermind results when Scholar is unavailable.

It does not use headless browsing, proxy rotation, fingerprint manipulation, CAPTCHA solvers, or other challenge-evasion techniques.

### Additional capabilities

- Natural-language Undermind deep searches
- Flexible relevance screening
- DOI normalization
- Conservative title/author/year deduplication
- `possible_duplicate` handling for preprints and published versions
- Open Access PDF verification
- One DOI batch per InstSci publisher profile
- Maximum of 30 high-relevance downloads by default
- Consistent JSON, CSV, and Markdown reports
- Explicit `metadata_resolution_failed` and `profile_missing` states

### Requirements

- Codex
- A connected Undermind account with a writable workspace
- [InstSci](https://github.com/Rimagination/instsci)
- Python 3.10+
- Visible Chrome for Google Scholar
- InstSci CloakBrowser for publisher and institutional access
- Legitimate university, library, or institutional entitlements

### Installation

Install InstSci:

```bash
pipx install git+https://github.com/Rimagination/instsci.git

# or
uv tool install git+https://github.com/Rimagination/instsci.git
```

Configure the default institution:

```bash
instsci setup --school "Beijing Normal University"
```

Then ask Codex to install this skill:

```text
Install and configure this Codex skill:
https://github.com/Ruy12138/SciFinder-V2
```

### Example

```text
Use $scifinder to find literature about the effects of generative AI
on university students' critical thinking, deduplicate the results,
and download the highly relevant papers.
```

### Testing

Run the offline merge and publisher-batching tests:

```bash
python3 scripts/test_merge_literature_results.py
```

The tests do not perform live bulk Scholar access or publisher PDF downloads.

### Compliance

- No paywall or entitlement bypassing
- No automated CAPTCHA solving
- No storage of passwords, OTPs, API keys, tokens, cookies, or institutional credentials
- Low-frequency, human-supervised Scholar use
- Visible-browser evidence for final closed-access PDF results
- Downloads must comply with publisher, database, and institutional terms

### Upstream

- [Rimagination/instsci](https://github.com/Rimagination/instsci)

### Disclaimer

“SciFinder” is the name of this independent Codex skill. It is not affiliated with, endorsed by, or sponsored by CAS SciFinder or its operator.
