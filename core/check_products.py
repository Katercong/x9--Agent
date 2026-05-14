import sqlite3
conn = sqlite3.connect(r'F:\Claude_Project\Database\database.db')
cur = conn.cursor()

# 1. 列结构
print("=== product 表结构 ===")
cur.execute("PRAGMA table_info(product)")
for r in cur.fetchall():
    print("  ", r[1], r[2])

print()

# 2. id 10-28 的产品
print("=== id 10-28 产品详情 ===")
cur.execute("SELECT id, sku_code, name_en, is_main_push, tier FROM product WHERE id BETWEEN 10 AND 28 ORDER BY id")
rows = cur.fetchall()
for r in rows:
    print(f"  id={r[0]}  sku={r[1]}  name_en={r[2]}  is_main_push={r[3]}  tier={r[4]}")

print()

# 3. 全部 is_main_push 分布
print("=== is_main_push 分布 ===")
cur.execute("SELECT is_main_push, COUNT(*) as cnt FROM product GROUP BY is_main_push")
for r in cur.fetchall():
    print(f"  is_main_push={r[0]} -> {r[1]} 条")

print()

# 4. 主推产品全部列出
print("=== 全部主推产品(id+sku+name_en) ===")
cur.execute("SELECT id, sku_code, name_en FROM product WHERE is_main_push=1 ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]}  sku={r[1]}  name={r[2]}")

conn.close()