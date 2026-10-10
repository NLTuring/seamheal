# -*- coding: utf-8 -*-
"""定位脚本中的转义符与字符画，便于统一修复。"""
import io

path = 'tools/build_brief.py'
lines = io.open(path, encoding='utf-8').read().split('\n')

print('=== 含 u00a5 转义或 $ 包裹的行 ===')
for i, line in enumerate(lines, 1):
    if 'u00a5' in line or '$' in line:
        print('%4d| %s' % (i, line.strip()[:130]))

print()
print('=== 含制表框线字符（字符画）的行 ===')
box = set('┌┐└┘─│├┤┬┴┼▼')
for i, line in enumerate(lines, 1):
    if any(c in box for c in line):
        print('%4d| %s' % (i, line.strip()[:130]))

print()
print('=== 出现“壁垒”的行 ===')
for i, line in enumerate(lines, 1):
    if '壁垒' in line:
        print('%4d| %s' % (i, line.strip()[:130]))
