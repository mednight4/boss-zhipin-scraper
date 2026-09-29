# Task: SKILL.md 渐进式披露拆分

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
