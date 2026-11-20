-- 采样读数与迟到校正（2026-11-20）
-- 旧库在已有表上补列；新建库由 create_all 直接按模型建表。
ALTER TABLE log_sets ADD COLUMN IF NOT EXISTS sample_times JSON NOT NULL DEFAULT '{}';
ALTER TABLE log_sets ADD COLUMN IF NOT EXISTS parent_log_set_id INTEGER REFERENCES log_sets(id);

-- 说明：
-- 1) sample_times 为 {账本键: ISO 8601 时刻 或 [时刻, ...]}；为空表示该日志集没有采样时刻，
--    读数接口会返回 422，恢复演练与旧证据不受影响。
-- 2) parent_log_set_id 指向派生校正所基于的原日志集；原日志集记录不再被改写，校正总是生成新日志集。
-- 3) correct 日志记录直接存在 records JSON 中，无需新增列。
