# -*- coding: utf-8 -*-
"""从流水线日志中提取关键指标。"""
import io
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(BASE, 'preview', 'pipeline.log')

KEYS = ['非宋体', '总页数', '偏少页', '已渲染', '页数 =', '全包', '目录已含',
        '字体归一化完成', 'updateFields', '带大纲级别', '正文中使用',
        '目录占位', '目录域指令', '目录已保存', '打开成功', '导出方式',
        '结果 =', '流水线全部完成', '未找到']

txt = io.open(LOG, encoding='utf-8', errors='replace').read()
for line in txt.split('\n'):
    s = line.strip()
    if any(k in s for k in KEYS):
        print(s[:170])
