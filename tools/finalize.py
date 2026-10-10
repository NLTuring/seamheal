# -*- coding: utf-8 -*-
"""收尾处理：重新开启 updateFields，并核查标题大纲级别与目录条目。"""
import os
import zipfile
import lxml.etree as ET
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')

doc = Document(PATH)

# 1) 重新开启 updateFields，让 Word 打开时按需刷新页码
settings = doc.settings.element
uf = settings.find(W + 'updateFields')
if uf is None:
    uf = OxmlElement('w:updateFields')
    settings.append(uf)
uf.set(qn('w:val'), 'true')
print('updateFields 已设为 true')

doc.save(PATH)

# 2) 核查：带大纲级别的段落数 + 目录条目
z = zipfile.ZipFile(PATH)
styles = ET.fromstring(z.read('word/styles.xml'))
outline = {}
for st in styles.iter(W + 'style'):
    sid = st.get(qn('w:styleId'))
    lvl = st.find(W + 'pPr/' + W + 'outlineLvl')
    if lvl is not None:
        outline[sid] = lvl.get(qn('w:val'))
print('带大纲级别的样式 =', outline)

used = {}
d = ET.fromstring(z.read('word/document.xml'))
for p in d.iter(W + 'p'):
    ps = p.find(W + 'pPr/' + W + 'pStyle')
    if ps is not None:
        v = ps.get(qn('w:val'))
        if v in outline:
            used[v] = used.get(v, 0) + 1
print('正文中使用的标题样式计数 =', used)

instr = [t.text for t in d.iter(W + 'instrText') if t.text]
print('域指令 =', instr)

ents = [t.text for t in d.iter(W + 't') if t.text and t.text.startswith('第') and '章' in t.text]
print('目录/正文中的章标题样本 =', ents[:6])
print('总页数引用（应为空，由 Word 计算）')
