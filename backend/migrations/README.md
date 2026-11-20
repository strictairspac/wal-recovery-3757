# 初始化结构
SQLAlchemy metadata.create_all首次建users、log_sets、crash_cases、recoveries、audits。log_sets.name、crash_cases.name唯一，关联使用外键，入队冻结日志和崩溃点快照。暂无在线schema升级器。

# 旧库升级
2026-11-20-sampling-corrections.sql给log_sets补sample_times（JSON，默认{}）与parent_log_set_id（自引用外键）。旧行的sample_times为{}时读数接口返回422，恢复演练与既有证据不受影响；种子脚本只对缺失采样时刻的演示日志集补齐，不覆盖用户修改。
