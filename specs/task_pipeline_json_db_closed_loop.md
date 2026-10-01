# 修复管道时序与 JSON 入库闭环

## 目标

以 SQLite 状态作为列表、详情和洞察是否完成的唯一依据，统一列表 JSON、数据库批次和抓取入口的查询身份；发生中断时优先补导入已落盘 JSON，避免重复访问页面。

## 数据不变量

- 列表批次的 `query_url`、`query_hash`、`city_code` 在抓取 JSON 与 `company_list` 中保持一致；旧 JSON 通过明确的城市输入兼容恢复，不再把职位地点作为首选身份来源。
- 详情完成要求 `company_detail` 存在对应 `brand_id` 且 `company_list.has_detail=1`。
- 洞察完成要求 `company_insight` 存在对应 `brand_id` 且 `company_list.has_insight=1`。
- 完成状态基于数据库待办；JSON 落盘只是可恢复输入。用户选择跳过的阶段与实际完成分开返回。
- 列表、详情、洞察链路依次为 `list → detail.credit_code → insight`；爱企查输入 `credit_code`，项目表连接键仍为 `brand_id`。

## 实现范围

1. 列表抓取 JSON 写入规范化的 `query_url`、`query_hash`、`city_code`；导入优先读这些元数据，并兼容旧 JSON。
2. 详情步骤先补导入当前数据库待办品牌的 JSON，再抓取剩余品牌；洞察独立入口始终在抓取后补导入残留文件。损坏文件或无对应品牌的文件应记录并跳过，不阻断整批恢复。
3. `PipelineState` 先处理详情待办，再判断可执行洞察输入和数据新鲜度；列表 JSON 已存在时不得重抓。详情风控异常继续向上传播。最终状态和待办数从数据库重读，明确返回跳过阶段。
4. URL、数据库 `all` 和独立 Pipeline CLI 复用统一阶段编排与数据库路径；完整流程必须真正尝试洞察。独立公司详情提取器仅作为 JSON 抓取入口；单条洞察 CLI 在 JSON 不能入库时以非零退出。
5. 通过临时 SQLite、JSON 和假抓取函数覆盖批次一致性、中断恢复、阶段入口、状态机优先级、风控退出与单条 CLI 入库闭环。
6. 同步 `skill/agent_workflow.md`、`skill/pipeline.md`、`SKILL.md`、中英文 README 和 `CHANGELOG.md`。

## 验收

使用 `uv run python -m unittest` 运行列表数据库、管道、洞察和 Chrome 设置测试；使用 `uv run python -m py_compile` 做语法检查。此工作不执行真实抓取、不修改用户数据库、不提交远程仓库。抓取链路真实 Edge 验证作为后续合并前检查，按 `AGENTS.md` 的 `--check → --smoke-test → --pages 2 --no-detail` 执行。
