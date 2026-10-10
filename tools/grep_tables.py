# -*- coding: utf-8 -*-
"""定位第十二章风险表与第十三章成果表的 widths/font_size 参数。"""
import io

lines = io.open('tools/build_brief.py', encoding='utf-8').read().split('\n')
ANCHORS = ['风险类别', '成果类型', '时间', '资源类型']
for a in ANCHORS:
    for i, l in enumerate(lines, 1):
        if a in l:
            print('锚点 “%s” 在第 %d 行：%s' % (a, i, l.strip()[:90]))
            # 向下找 widths/font_size
            for j in range(i, min(i + 40, len(lines))):
                if 'widths=' in lines[j]:
                    print('    %5d| %s' % (j + 1, lines[j].strip()[:110]))
                    break
            print()
