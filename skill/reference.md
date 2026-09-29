# 参数速查与输出格式

## 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--keyword` | - | 搜索关键词 |
| `--city` | 上海 | 城市名（中文）或 9 位代码；没传时默认上海，无法识别的城市名会报错退出 |
| `--pages` | 3 | 抓取页数（上限 10，每页 30 条） |
| `--output` | ~/.boss-zhipin-scraper/job-result/... | 列表输出路径 |
| `--detail-output` | ~/.boss-zhipin-scraper/job-result/... | 详情输出路径 |
| `--format` | json | 输出格式: json / csv；csv 同时导出列表和详情 CSV |
| `--detail` | 开启（默认） | 抓取详情页 JD |
| `--no-detail` | - | 不抓取详情页（关闭默认行为） |
| `--max-details` | 全部 | 详情页数量上限 |
| `--analysis` | 关闭 | 输出分析报告 |
| `--allow-dom-fallback` | 关闭 | API 无数据时允许降级 DOM 提取；默认关闭，薪资可能不可信 |
| `--merge FILE` | - | 合并已有 JSON（按 job_id 去重） |
| `--cdp-port` | 9222 | CDP 端口 |
| `--setup-chrome` | 关闭 | 一键启动 Chrome CDP（持久隔离 profile） |
| `--setup-edge` | 关闭 | 一键启动 Microsoft Edge CDP（与 `--setup-chrome` 共用隔离 profile） |
| `--browser` | chrome | 搭配 `--setup-chrome` 选择浏览器（chrome/edge）；与 `--setup-edge` 显式冲突时以 `--setup-edge` 为准并提示 |
| `--copy-login-state` | 关闭 | 手动导入主浏览器（`--setup-chrome` 取主 Chrome、`--setup-edge` 取主 Edge）的 Local State + Cookie 相关文件到隔离 profile；默认、首次启动、重复启动都不复制 |
| `--reset-chrome-profile` | 关闭 | 重建 BOSS 专用 profile，会清除此专用浏览器登录态 |
| `--no-wait-login` | 关闭 | `--setup-chrome` 启动后不等待 BOSS 登录完成 |
| `--login-timeout` | 300 | `--setup-chrome` 等待登录完成的秒数 |
| `--stop-chrome` | 关闭 | 关闭 BOSS 专用 CDP Chrome（按隔离 profile 精准匹配，不碰主 Chrome） |
| `--stop-edge` | 关闭 | 关闭 BOSS 专用浏览器 CDP（与 `--stop-chrome` 共用隔离 profile） |
| `--close-chrome` | 关闭 | 抓取正常结束后自动关闭专用 Chrome（默认不关；异常退出不触发，保留登录态） |
| `--check` | 关闭 | 环境检查 |
| `--smoke-test` | 关闭 | 真实 Chrome/CDP 搜索 API smoke test，不写结果文件 |
| `--version` | - | 查看版本号 |
| `--db` | 关闭 | 启用 SQLite 三表桥接管道（company_list / company_detail） |
| `--db-path` | output/jobs.db | SQLite 数据库路径 |
| `--step` | all | 执行哪一步: list / detail / insight / all |
| `--list-json` | - | 从已有 JSON 导入列表（跳过列表抓取） |
| `--detail-json-dir` | - | 从已有 JSON 目录导入详情（跳过详情抓取） |
| `--url` | - | 给 URL 跑完整管道（自动解析 keyword + city + 筛选条件） |

### 筛选参数

| 参数 | 值 |
|------|-----|
| `--scale` | 301=0-20人 302=20-99 303=100-499 304=500-999 305=1000-9999 306=10000+ |
| `--salary` | 402=3K以下 403=3-5K 404=5-10K 405=10-20K 406=20-50K 407=50K+ |
| `--experience` | 108=在校生 102=应届生 101=经验不限 103=1年内 104=1-3年 105=3-5年 106=5-10年 107=10年+ |
| `--degree` | 209=初中及以下 208=中专/中技 206=高中 202=大专 203=本科 204=硕士 205=博士 |

### 城市代码

全国 100010000 | 北京 101010100 | 上海 101020100 | 广州 101280100 | 深圳 101280600 | 杭州 101210100 | 成都 101270100 | 武汉 101200100 | 南京 101190100 | 厦门 101230200

## 输出格式

### JSON

```json
{
  "keyword": "AI Agent",
  "city": "上海",
  "total": 60,
  "jobs": [
    {
      "job_id": "c4420e8bce3a6e25",
      "title": "AI Agent工程师",
      "salary": "30-60K·15薪",
      "location": "上海·闵行区·虹桥",
      "tags": "5-10年 | 本科",
      "boss_name": "SHEIN",
      "boss_title": "招聘者",
      "company_scale": "10000人以上",
      "company_stage": "D轮及以上",
      "company_industry": "电子商务",
      "skills": "Java | Spring | AI",
      "job_link": "https://www.zhipin.com/job_detail/xxx.html",
      "company_link": "https://www.zhipin.com/gongsi/xxx.html",
      "welfare": "节日福利 | 零食下午茶 | 定期体检"
    }
  ]
}
```

### CSV

`--format csv` 时自动在同目录生成 `.csv` 文件：列表 CSV 跟随 `--output`，详情 CSV 跟随 `--detail-output` 或默认详情 JSON 路径。CSV 使用 UTF-8 BOM 编码，Excel 直接打开无乱码。

## 工作原理

1. 通过 Chrome DevTools Protocol (CDP) 连接到已打开的 Chrome 浏览器
2. 在 BOSS直聘页面内注入 JS，用同步 XHR 调用 `/wapi/zpgeek/search/joblist.json` API
3. API 返回明文 `salaryDesc`（如 `30-60K·15薪`），绕过前端字体反爬
4. 列表 API 保留 `securityId` / `lid` 等上下文，进入详情页时带上这些参数
5. 默认禁用 DOM fallback，避免把字体反爬后的薪资写入结果；只有显式 `--allow-dom-fallback` 才降级
6. 每页 30 条，每页抓完立即写入文件，异常退出不丢数据
7. 按 `job_id`（job_link 的 MD5 哈希前 16 位）去重

## 数据安全策略

`--setup-chrome` 默认使用持久隔离 profile，不软链接、不读取、不复制主 Chrome profile。首次启动和后续重复启动都只会创建或复用 `~/.boss-zhipin-scraper/chrome-profile`，不会清空其中的 BOSS 登录态。

`--input ... --analysis --no-detail` 会优先加载 `--detail-output`，其次加载与输入列表同目录、同时间戳的 `boss_details_*.json`，最后查找 `~/.boss-zhipin-scraper/job-result` 下最新详情文件。

需要清空 BOSS 专用浏览器登录态时使用：

```bash
python3 "$SCRIPT_PATH" --setup-chrome --reset-chrome-profile --cdp-port 9222
```
