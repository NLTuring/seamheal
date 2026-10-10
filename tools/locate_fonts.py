# -*- coding: utf-8 -*-
"""定位非宋体字体名的具体位置，确认是否影响可见内容。"""
import os
import zipfile
import lxml.etree as ET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')

TARGETS = ['黑体', 'Calibri', 'Times New Roman', 'Cambria', '等线']

z = zipfile.ZipFile(PATH)
for name in sorted(z.namelist()):
    if not name.endswith('.xml'):
        continue
    raw = z.read(name)
    hit = [t for t in TARGETS if t.encode('utf-8') in raw]
    if not hit:
        continue
    print('=== %s ===' % name)
    root = ET.fromstring(raw)
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    # 样式表中的字体定义
    for f in root.iter(W + 'rFonts'):
        vals = {k.split('}')[-1]: v for k, v in f.attrib.items()}
        names = set(vals.values())
        if names & set(TARGETS):
            print('   rFonts:', vals)
    # 文本内容
    for t in root.iter(W + 't'):
        if t.text and any(x in t.text for x in TARGETS):
            print('   文本包含字体名:', t.text[:80])
    print()
