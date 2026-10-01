# 已完成洞察数据查询与参保人数迁移规范

## 1. 背景

当前 `company_insight.employee_count` 保存爱企查“参保人数”，但历史数据库和洞察 JSON 中可能同时存在 `"28"`、`"28人"`、`0` 和空字符串。Agent 为回答“参保人数在某个区间的职位/公司链接”时，不应现场拼接 SQL，也不应因为这是只读分析任务而启动抓取。

本变更只处理：

- 参保人数的统一数据契约和历史数据库迁移；
- 已入库批次的只读筛选查询接口；
- Agent Skill 的只读查询工作流和渐进式文档路由。

不处理公司去重、链接 Markdown 渲染或企业注册地与搜索城市之间的推导。

## 2. 数据契约

`company_insight.employee_count` 保留字段名，迁移为可空整数：

- `INTEGER`：爱企查公开的“参保人数”；
- `NULL`：页面未披露、空值或无法确认；
- `0`：只有原始页面明确显示 0 时才保留为 0；
- 它不是公司总员工数，也不是 BOSS `company_scale`。

规范化函数必须同时用于抓取输出和数据库导入，接受以下历史形式：

```text
28、"28"、"28人"、" 1,234 人 " → 整数
""、"-"、"暂无"、"未公示"、None → None
```

无法确认的复杂文本不猜测提取数字，返回 `None`。原始字段仍保留在 `business_info_raw_json` 中。

## 3. 数据库迁移

- 新建 `company_insight` 表时声明 `employee_count INTEGER`。
- `JobDatabase.init_schema()` 检测已有列类型；旧 `TEXT` 表执行事务化迁移。
- 迁移显式复制全部列，转换 `employee_count`，恢复既有索引，并保证幂等。
- 迁移失败必须回滚，不能丢失或部分替换旧表。
- 历史洞察 JSON 继续可以通过 `import_insight_from_json()` 入库。
- 迁移和导入均不把缺失值转换为 0。

## 4. 只读查询接口

新增 `scripts.company_list.query` 模块，提供命令行入口；可复用查询方法放入 `JobDatabase`。查询必须使用 SQLite URI 的只读模式：

- 不创建不存在的数据库文件；
- 不调用 `init_schema()`；
- 不执行 `INSERT`、`UPDATE`、`DELETE` 或状态变更；
- 不访问 CDP，不刷新批次，不因为数据过期自动抓取。

查询以 `company_list` 职位记录为结果粒度，允许同一公司因多个命中职位出现多行。至少支持：

- `query_hash` 批次筛选；
- `employee_count` 最小值和最大值，闭区间；
- 返回批次元信息、岗位字段、BOSS 公司链接、爱企查详情链接、参保人数和洞察时间；
- JSON 和人类可读输出。

查询不存在批次、无洞察记录、缺失链接和无匹配结果时，必须显式表达状态。

## 5. Skill 路由

- `SKILL.md` 只负责最小入口和任务分流。
- 新增 `skill/query_workflow.md`，规定已完成数据库只读查询流程。
- `skill/agent_workflow.md` 只负责抓取、恢复和管道状态；只读查询不默认执行 CDP 检查或抓取。
- `skill/reference.md`、`skill/install.md`、README 双语文档和 `CHANGELOG.md` 同步新增入口与字段语义。

## 6. 验收标准

- 新抓取结果的 `employee_count` 为整数或 JSON `null`。
- 旧数据库迁移后列类型为 `INTEGER`，行数、主键、索引和其他字段保持不变。
- `50` 和 `100` 包含在 `50 <= employee_count <= 100` 查询结果中，`49` 和 `101` 排除。
- 只读查询不会创建或修改数据库文件。
- 查询任务不会要求启动 Edge 或重新抓取。
- 数据库、洞察、管道和新增查询单元测试通过。
