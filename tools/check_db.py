import sqlite3

# 连接数据库
conn = sqlite3.connect('events.db')
cursor = conn.cursor()

# 查看表结构
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='events'")
schema = cursor.fetchone()
print("表结构:")
print(schema[0] if schema else "表不存在")
print()

# 查看事件总数
cursor.execute('SELECT COUNT(*) FROM events')
count = cursor.fetchone()[0]
print(f'总事件数: {count}')
print()

# 查看前5条事件
cursor.execute('SELECT date, title, event_type FROM events ORDER BY date LIMIT 5')
print('前5条事件:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]} ({row[2]})')
print()

# 查看按日期分组的事件数量
cursor.execute('SELECT date, COUNT(*) as count FROM events GROUP BY date ORDER BY date LIMIT 10')
print('按日期分组的事件数量 (前10天):')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1]}条事件')

conn.close()
print('\n数据库检查完成！')