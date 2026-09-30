# Task: SKILL.md 渐进式披露拆分

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件记录 Skill 文档拆分的历史计划。当前三表连接键是 `company_list.encrypt_brand_id = company_detail.brand_id = company_insight.brand_id`；`company_list` 没有 `credit_code` 列，详情 extractor 产生的 `company_detail.credit_code` 才是爱企查搜索输入。空库顺序为 `list → company_list → detail → company_detail.credit_code → insight → company_insight`，不能把 detail 和 insight 描述为列表入库后的直接并发。
>
> 当前还需显式说明：`PipelineState.decide()` 可能在 `detail_pending>0` 时返回 `SKIP`，`LIST_JSON_SAVED` 下的 `run()` 会再次抓列表，URL 入口不注入 `scrape_insight_fn`，`--step all` 总是报错。
>
> **历史记录标记**：下文的拆分结构、命令和验收标准保留原计划背景；与当前契约冲突的内容属于原方案（已过时）。

## 现状问题

SKILL.md 当前约 430 行，agent 初次阅读项目时一次性灌入全部信息（Pipeline 状态机、参数速查、安装说明、工作原理、数据安全策略等），导致信息过曝产生幻觉。

核心矛盾：agent 需要知道"能做什么"和"怎么快速开始"，但不需要在第一眼就看到所有实现细节。

## 目标

将 SKILL.md 拆为 4 文件，实现渐进式披露：

| 文件 | 定位 | 行数 | 何时读 |
|------|------|------|--------|
| `SKILL.md` | 入口（快速上手） | ~80 | agent 初次读项目 |
| `skill/pipeline.md` | Pipeline 详解 | ~100 | 当用户涉及管道/URL 查询时 |
| `skill/reference.md` | 参数速查 + 输出格式 | ~80 | 需要具体参数或输出结构时 |
| `skill/install.md` | 安装说明 | ~60 | 安装 skill 到 Hermes 时 |

## SKILL.md 入口内容大纲

- frontmatter (保持不变，Hermes 必须)
- 项目一句话定位
- 前置条件 (3 行)
- 脚本位置 (文件列表)
- 依赖安装 (代码块)
- 自动化流程 (简版 3 步: --check → --setup-chrome → 抓取)
- Pipeline 入口 (--url 一行说明)
- 常见问题 (简版 3 条)
- 子模块索引表 (何时读哪个 skill/*.md)

## skill/pipeline.md 内容

从 SKILL.md 提取整个 Pipeline 章节：
- 状态图
- 决策流程
- 表关系与联立键
- 文件路径表
- 使用方式 (Python API + CLI)
- 中断恢复场景
- Agent 快速参考

## skill/reference.md 内容

从 SKILL.md 提取：
- 完整参数速查表
- 筛选参数表
- 城市代码
- JSON 输出示例
- CSV 输出说明
- 工作原理 (精简)
- 数据安全策略 (精简)

## skill/install.md 内容

从 SKILL.md 提取：
- 脚本路径查找方法（两种方法）
- curl 一键安装命令
- git clone 手动复制命令

## 执行步骤

1. 创建 `skill/` 目录
2. 写 `skill/install.md`
3. 写 `skill/pipeline.md`
4. 写 `skill/reference.md`
5. 重写 `SKILL.md` 为精简入口 + 索引
6. 验证 frontmatter 完整、子模块索引链接正确
7. git add + commit

## 提交

单 commit: `docs: SKILL.md 渐进式披露拆分，agent 入口精简 + 子模块按需加载`

## 溯源

- Plan 文件: `skill渐进式披露拆分_1771102f.plan.md`
