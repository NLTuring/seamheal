# -*- coding: utf-8 -*-
"""一键流水线：生成 → 固化目录 → 字体归一化 → 收尾 → 审计 → 导出 PDF → 渲染 → 定位。"""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(BASE, 'tools')

STEPS = [
    ('生成文档', 'build_brief.py'),
    ('固化目录', 'update_toc.py'),
    ('字体归一化', 'normalize_fonts.py'),
    ('收尾处理', 'finalize.py'),
    ('字体审计', 'audit_fonts.py'),
    ('导出 PDF', 'export_pdf.py'),
    ('渲染页面', 'render_png.py'),
    ('定位内容', 'locate_pages.py'),
]

env = dict(os.environ, PYTHONIOENCODING='utf-8')

for i, (label, script) in enumerate(STEPS, 1):
    print('\n' + '=' * 62)
    print('[%d/%d] %s  (%s)' % (i, len(STEPS), label, script))
    print('=' * 62)
    r = subprocess.run([sys.executable, os.path.join(TOOLS, script)],
                       cwd=BASE, env=env)
    if r.returncode != 0:
        print('!! 步骤失败：%s（返回码 %d）' % (label, r.returncode))
        sys.exit(r.returncode)

print('\n流水线全部完成')
