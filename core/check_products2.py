import sqlite3
conn = sqlite3.connect(r'F:\Claude_Project\Database\database.db')
cur = conn.cursor()

# 检查 id=10 的所有字段
print("=== product id=10 完整数据 ===")
cur.execute("SELECT * FROM product WHERE id=10 LIMIT 1")
row = cur.fetchone()
if row is None:
    print("  [找不到 id=10]")
else:
    cols = [desc[0] for desc in cur.description]
    for i, col in enumerate(cols):
        val = row[i]
        print(f"  {col}: {repr(val)[:120]}")

print()
print("=== is_main_push=1 产品列表 ===")
cur.execute("SELECT id, sku_code, name_en, is_main_push FROM product WHERE is_main_push=1 ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]}  sku={r[1]}  name_en={r[2]}")

print()
print("=== is_main_push=0 产品列表 ===")
cur.execute("SELECT id, sku_code, name_en, is_main_push FROM product WHERE is_main_push=0 ORDER BY id")
for r in cur.fetchall():
    print(f"  id={r[0]}  sku={r[1]}  name_en={r[2]}")

conn.close()