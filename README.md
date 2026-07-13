# 智阅馆 SmartLibraryMS

面向校园场景的 MySQL 图书借阅数据库管理系统。功能包括图书、读者、借还、逾期预警、运营仪表盘与可解释 AI 洞察。

AI 洞察基于近 7 / 30 天借阅量、周期变化、热门图书、逾期和缺货数据生成可追溯结论。可在 `.env` 配置 `AI_API_BASE`、`AI_API_KEY` 和 `AI_MODEL`，接入 OpenAI 兼容的文本生成接口，为当前统计生成补充建议；未配置密钥时不会发送任何数据。

## 启动
1. 在 MySQL 执行 `sql/setup.sql`。
2. 复制 `.env.example` 为 `.env` 并填写数据库密码。
3. `pip install -r requirements.txt`。
4. `python app.py`，访问 `http://127.0.0.1:5000`。

## 优化说明
系统在图书检索、分类库存筛选、读者检索、逾期查询与读者借阅记录等高频路径建立了索引。运行 `sql/setup.sql` 中的 `EXPLAIN` 可展示索引命中。
