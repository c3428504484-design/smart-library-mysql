CREATE DATABASE IF NOT EXISTS smart_library DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- 启动 app.py 后由 SQLAlchemy 建表和创建索引。
EXPLAIN SELECT * FROM loans WHERE status='借阅中' AND due_at < CURDATE();
