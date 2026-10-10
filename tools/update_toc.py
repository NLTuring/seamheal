# -*- coding: utf-8 -*-
"""打开生成的 DOCX，更新目录域并将结果固化保存，使目录直接显示条目与页码。"""
import os
import win32com.client as wc

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCX = os.path.join(BASE, '愈缝SeamHeal-项目简介文档.docx')

app = wc.Dispatch('Word.Application')
app.Visible = False
app.DisplayAlerts = 0

doc = app.Documents.Open(DOCX, False, False)

try:
    n = doc.TablesOfContents.Count
    print('目录域数量 =', n)
    for i in range(1, n + 1):
        doc.TablesOfContents(i).Update()
        print('已更新目录', i)
except Exception as e:
    print('更新目录失败:', str(e)[:150])

try:
    doc.Fields.Update()
    print('全部域已更新')
except Exception as e:
    print('更新全部域失败:', str(e)[:150])

doc.Repaginate()
print('总页数 =', doc.ComputeStatistics(2))

doc.Save()
print('目录已保存')
try:
    doc.Close(0)
except Exception as e:
    print('关闭文档异常（可忽略）:', str(e)[:80])
try:
    app.Quit()
except Exception as e:
    print('退出 Word 异常（可忽略）:', str(e)[:80])
print('完成')
