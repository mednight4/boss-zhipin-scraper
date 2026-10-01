# 已完成数据只读查询工作流

> 本文只适用于数据库中已经存在列表、BOSS 公司详情和爱企查洞察的分析任务。新抓取、恢复抓取和管道状态检查请读取 [`agent_workflow.md`](agent_workflow.md)。

## 1. 任务分流

用户要求从已有结果中筛选岗位或公司时：

- 不启动 Edge，不执行 CDP 检查；
- 不重新抓取，不因数据过期自动刷新；
- 不现场拼接 SQL；
- 使用只读查询入口读取 `output/jobs.db`。

当前三表连接键仍是：

```text
company_list.encrypt_brand_id
    = company_detail.brand_id
    = company_insight.brand_id
```

统一社会信用代码 `credit_code` 只用于爱企查搜索，不是三表连接键。

## 2. 参保人数语义

`company_insight.employee_count` 是爱企查公开信息中的“参保人数”，不是：

- BOSS 的企业规模筛选，例如 `100-499人`；
- 公司总员工数；
- 当前在招岗位数量。

该字段已规范为可空整数：

- `50` 和 `100` 可以参与 `50 <= employee_count <= 100` 的闭区间筛选；
- `NULL` 表示未披露、空值或无法确认；
- `0` 只有页面明确显示 0 时才表示 0。

回答用户时使用“爱企查参保人数”或“社保缴纳人数（爱企查参保人数）”，不要笼统写成“员工人数”。

1. 查询可用批次（不知道 `query_hash` 时）：

```powershell
uv run python -m scripts.company_list.query --db-path output/jobs.db --list-batches --format json
```

2. 核对关键词、城市和原始筛选条件后，按选中的 `query_hash` 执行筛选：

```powershell
uv run python -m scripts.company_list.query `
  --db-path output/jobs.db `
  --query-hash QUERY_HASH `
  --employee-min 50 `
  --employee-max 100 `
  --format json
```

也可将已有批次返回的规范化 BOSS `query_url` 传给 `--query-url`。默认返回最多 100 条职位记录，可以使用：

```text
--limit 50 --offset 0
```

同一公司在批次中有多个命中职位时允许返回多条记录。结果数量应称为“命中职位记录数”，不要擅自改称为去重后的公司数。

## 4. 固定执行顺序

1. 确认用户条件：关键词、BOSS 搜索城市、行业/规模筛选、参保人数上下限。
2. 使用 `--query-hash` 查询批次元信息，核对关键词、城市、原始筛选条件和数据状态。
3. 使用 `--employee-min` 与 `--employee-max` 执行闭区间查询。
4. 检查结果是否包含岗位标题、工作地点、BOSS 公司详情 URL 和爱企查详情 URL。
5. 向用户说明返回的是职位记录；如果同一公司出现多次，保留这些记录即可。
6. 输出真实链接的 Markdown 链接，不重新根据 `credit_code` 猜测爱企查详情 URL。
7. 说明数据时间，并把 `NULL`、0 和正常整数分开描述。

## 5. 批次和结果解释

- 批次不存在：报告没有找到对应批次，不启动抓取。
- 批次存在但没有命中：报告“没有匹配的已入库职位记录”，不能说数据库没有抓取结果。
- 洞察待办大于 0：结果可能不完整，应提示洞察尚未全部闭环；不要把缺失洞察解释成不符合人数条件。
- BOSS 搜索城市表示职位搜索条件。结果中的企业注册地可以是其他城市，不额外用注册地筛除公司。
- `company_detail.url` 是 BOSS 公司详情链接，`company_insight.url` 是已保存的爱企查详情链接，优先使用这两个字段。

## 6. 只读保证

`scripts.company_list.query` 使用 SQLite 只读连接：

- 不创建不存在的数据库文件；
- 不执行 `init_schema()`；
- 不修改 `has_detail`、`has_insight` 或任何业务字段；
- 不连接浏览器，不调用抓取函数。

如果数据库还是旧的 `employee_count TEXT` 结构，应先由正常的可写数据库入口执行迁移，再重新运行只读查询；查询入口本身不会自行修复数据库。
