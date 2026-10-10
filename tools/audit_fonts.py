# -*- coding: utf-8 -*-
"""全包字体审计：统计 DOCX 内每个 w:r 的实际字体设置。"""
import os
import zipfile
import lxml.etree as ET
from docx.oxml.ns import qn

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')

z = zipfile.ZipFile(PATH)
tot = bad = 0
badmap = {}

for name in z.namelist():
    if not name.endswith('.xml'):
        continue
    root = ET.fromstring(z.read(name))
    for r in root.iter(W + 'r'):
        tot += 1
        rf = r.find(W + 'rPr/' + W + 'rFonts')
        ea = rf.get(qn('w:eastAsia')) if rf is not None else None
        asc = rf.get(qn('w:ascii')) if rf is not None else None
        if ea != '宋体' or asc != '宋体':
            bad += 1
            key = (name, 'eastAsia=%s' % ea, 'ascii=%s' % asc)
            badmap[key] = badmap.get(key, 0) + 1

print('全包 w:r 总数 = %d，非宋体 = %d' % (tot, bad))
for k, v in sorted(badmap.items(), key=lambda x: -x[1])[:12]:
    print('   ', k, '->', v)

print()
allxml = ''.join(z.read(n).decode('utf-8', 'ignore')
                 for n in z.namelist() if n.endswith('.xml'))
for f in ['黑体', '微软雅黑', 'Calibri', 'Times New Roman', '等线', 'Cambria', '宋体']:
    print('%-18s 出现次数 = %d' % (f, allxml.count(f)))

print()
doc = ET.fromstring(z.read('word/document.xml'))
toc = doc.find('.//' + W + 'instrText')
if toc is not None and toc.text:
    print('目录域指令 =', toc.text.strip())

# 检查 TOC 是否已固化（有无真实条目文本）
texts = [t.text for t in doc.iter(W + 't') if t.text]
toc_hint = [t for t in texts if '更新域' in t]
entries = [t for t in texts if t.strip() in ('第一章  项目速览', '第三章  产品与解决方案',
                                             '附录 A  商业计划书章节对照表')]
print('目录占位提示残留 =', toc_hint if toc_hint else '无')
print('目录已含章节条目 =', entries if entries else '未找到')
print('文档总文本节点 =', len(texts))
