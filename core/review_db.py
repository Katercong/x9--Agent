import sqlite3
conn = sqlite3.connect(r'F:\Claude_Project\Database\database.db')
cur = conn.cursor()

print("=== outbox 表结构 ===")
cur.execute("PRAGMA table_info(outbox)")
for r in cur.fetchall(): print(" ", r[1], r[2])

print()
print("=== outbox 状态 x channel 分布 ===")
cur.execute("SELECT status, channel, COUNT(*) as cnt FROM outbox GROUP BY status, channel ORDER BY status, channel")
for r in cur.fetchall(): print(f"  {str(r[0]):15} {str(r[1]):12} {r[2]}")

print()
print("=== creator 关键字段 ===")
cur.execute("PRAGMA table_info(creator)")
for r in cur.fetchall():
    print(f"  {r[1]:30} {r[2]}")

print()
print("=== creator 粉丝区间分布 ===")
cur.execute("""
SELECT 
  CASE 
    WHEN CAST(followers AS REAL) < 1000 THEN '0-1K'
    WHEN CAST(followers AS REAL) < 10000 THEN '1K-10K'
    WHEN CAST(followers AS REAL) < 50000 THEN '10K-50K'
    WHEN CAST(followers AS REAL) < 100000 THEN '50K-100K'
    ELSE '100K+'
  END as bucket,
  COUNT(*) as cnt
FROM creator
WHERE followers IS NOT NULL AND followers != ''
GROUP BY bucket
ORDER BY bucket
""")
for r in cur.fetchall(): print(f"  {str(r[0]):12} -> {r[1]} 个达人")

print()
print("=== outreach 表结构 ===")
cur.execute("PRAGMA table_info(outreach)")
for r in cur.fetchall(): print(" ", r[1], r[2])

print()
print("=== outreach_example 表结构 ===")
cur.execute("PRAGMA table_info(outreach_example)")
for r in cur.fetchall(): print(" ", r[1], r[2])

print()
print("=== llm_feature 表结构 ===")
cur.execute("PRAGMA table_info(llm_feature)")
for r in cur.fetchall(): print(" ", r[1], r[2])

print()
print("=== app_config 当前值 ===")
cur.execute("SELECT key, value FROM app_config")
for r in cur.fetchall(): print(f"  {r[0]:40} = {repr(r[1])[:80]}")

conn.close()