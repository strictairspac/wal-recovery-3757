# 海砾 · 采样账本 WAL 恢复演练
海砾计量数据保障组（8人）用可重放日志替代恢复演练时手工拼接的SQL片段和账本截图。

## 场景与模块
上游为事务日志样例，下游为值班复核人。原流程人工标记提交、表格算恢复余额、截图写结论；痛点是崩溃点不清、撤销顺序容易错、恢复证据缺失。模块为事务日志集 / 故障注入点 / 恢复队列 / 恢复证据 / 采样读数，实体LogSet/CrashCase/Recovery贯穿全栈；页面的采样读数查询与迟到校正录入见“采样读数与迟到校正”一节；旧演练照常。

**Python WAL教学模型，不注入真实PostgreSQL故障，不执行数据库物理恢复。** PostgreSQL真实保存业务输入、冻结快照、任务和结果，Redis实际用于worker互斥，后台Python实际演算恢复历史。

## 启动
```bash
cp .env.example .env
docker compose up -d --build
# http://localhost:18246
# http://localhost:19246/docs
docker compose exec -T backend python -m scripts.seed_demo
docker compose down --remove-orphans
```
SEED_DEMO=true时启动自动执行种子；自然键查重，不覆盖用户修改。初始化失败显式阻止启动，不隐藏结构错误。删除数据需显式down -v。

|账号|密码|权限|典型动作|
|---|---|---|---|
|admin@haili.local|Recovery2026!|读写/导出/审计|查询审计记录|
|operator@haili.local|Recovery2026!|新增日志/场景/运行/导出|设置断电点10|
|viewer@haili.local|Recovery2026!|只读/导出|核对恢复账本|

## 一天的复核剧本
09:00操作员登录；09:05查看海砾采样账本-晚班（A100、B50）；09:10复制日志集保存shift-20261117；09:15在第10条日志后注入断电点；09:20提交恢复；09:25核对检查点LSN4、已提交T3、未提交T2两条写入逆序撤销，最终A60/B50；09:30下载JSON；09:40观察员核对且写操作403；10:00管理员查看/api/audits；10:10在“采样读数”页按08:00与提交位置LSN4查读数并录入迟到校正C1（补08:00—12:00）；10:20勾选“对照补录前后”核对补录前后读数，旧演练记录照常可查。

## 采样读数与迟到校正
采样时刻在日志集上声明为`sample_times`（账本键 → ISO 8601时刻或时刻数组）；write也可用`at`标注单条写入的采样时刻。读数是“账本键 × 采样时刻”的一格，只包含查询提交位置（`commit_lsn`，即LSN）之前已提交的事务，因此在同一提交点整笔事务的改动一起生效。

`correct`记录带`tx/key/value/start/end`，时段左闭右开`[start, end)`：它只改写自己时段内的读数，不改页面值；重叠时以提交位置更晚者为准（同一次提交内以LSN更晚者为准）。未提交的校正不入账，已abort的校正列出但不生效。校正总是生成新的派生日志集（`parent_log_set_id`指向原日志集），原记录不被改写。

接口：`GET /log-sets/{id}/readings?at=&commit_lsn=&key=&corrections=&compare=`、`GET /log-sets/{id}/handovers`、`POST /log-sets/{id}/corrections`（`{name, tx, corrections:[{key,value,start,end}], commit}`）、`GET /crash-cases/{id}/readings`与`/handovers`（默认提交位置为该场景断电点）、`GET /recoveries/{id}/readings`与`/recoveries/{id}/handovers`（使用冻结快照）。`compare=true`返回补录前后对照。

恢复只重放最近静止检查点之后的日志，检查点以前的日志不再重放；但每个检查点的交班账仍列在`checkpoints`/`/handovers`里，检查点以前的账可继续查。恢复结果附`late_corrections`（已入账）、`uncommitted_corrections`（未提交，不入账）、`aborted_corrections`（已撤销）与补录前后读数对照。未声明采样时刻的旧日志集不返回读数（422），恢复结果与旧演练一致。

## 算法、格式和失败态
日志为JSON数组，操作为begin/write/correct/commit/abort/checkpoint；write包含tx/key/value（可选`at`），correct另含start/end，其他事务操作包含tx，checkpoint不带tx。键必须在初始整数账本存在。事务ID不可复用；严格写锁直到commit/abort释放，同键重叠活动事务拒绝；检查点仅在无活动事务时允许。最多200条日志/30键/整数绝对值不超过10亿；每个键最多200个采样时刻。

crash_after=N表示前N条日志已持久化。最近静止检查点保存全部数据页，检查点后数据页假定均未写回（no-force）。恢复重放日志写入和已abort的撤销，再按LSN倒序撤销未结束事务。独立oracle从检查点账本仅应用已提交事务写入，结果须相同。输出重做/撤销轨迹、事务集合、各阶段账本、SHA256和模型版本。空输入、未知键、事务顺序非法、检查点有活动事务、写锁冲突、崩溃点超限均拒绝。模型不涉及页LSN、CLR、模糊检查点或真实磁盘故障；不是完整ARIES实现。

## 工程与开发
前端原生HTML/CSS/JS+Nginx1.27；后端Python3.11+FastAPI+SQLAlchemy+PyJWT；PostgreSQL16和Redis7；5服务均healthcheck。持久任务队列在PG，单worker通过Redis锁互斥。20条待执行配额，审计记录写入操作，JWT8小时、PBKDF2随机盐密码。后端路由不含/api，Nginx/api/去前缀代理。

目录frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}与backend/src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}。本地开发安装backend/requirements.txt并设DATABASE_URL/REDIS_URL/JWT_SECRET，再运行uvicorn src.main:app；前端需代理/api。migrations/README.md记录初始化结构，migrations/2026-11-20-sampling-corrections.sql给出旧库补列语句，暂无在线升级器。

环境COMPOSE_PROJECT_NAME控制命名，FRONTEND_PORT/BACKEND_PORT/DB_PORT为18246/19246/17746，DB_PASSWORD控制演示数据库密码，JWT_SECRET签名密钥，SEED_DEMO控制种子。命名卷db-data/redis-data/artifacts；共享artifacts预留，导出由冻结快照即时生成。Google Fonts需外网，业务离线可运行。默认凭据仅本地演示。

共享枚举roles与任务states定义于backend/src/constants/enums.py、frontend/src/constants/enums.js，状态使用models/entities.py/services/recovery_service.py/worker.py/components/common/status.js；日志操作类型在schemas/log_set.py和pages/logs.js中声明/说明。MIT许可。真实验证见批次test-artifacts/gb-4107/TESTING.md。
