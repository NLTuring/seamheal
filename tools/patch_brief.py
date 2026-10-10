# -*- coding: utf-8 -*-
"""按锚点整块替换 build_brief.py 中的字符画，避免手工数框线字符出错。"""
import io

PATH = 'tools/build_brief.py'
src = io.open(PATH, encoding='utf-8').read()
lines = src.split('\n')


def find(pred, start=0, limit=None):
    end = len(lines) if limit is None else limit
    for i in range(start, end):
        if pred(lines[i]):
            return i
    raise SystemExit('锚点未找到')


patches = []  # (start, end_inclusive, new_lines)

# ---------- P1：4.2 四层技术架构（字符画 → 表格） ----------
i_h = find(lambda l: "H(doc, '4.2 四层技术架构', level=2)" in l)
i_code = i_h + 1
assert lines[i_code].strip() == 'CODE(doc,', 'P1 起点异常: ' + lines[i_code]
i_end = find(lambda l: l.strip().endswith(', size=8.5)'), i_code)
arch = """P(doc, '整条管线自上而下分为五层，数据逐层流动。', indent=False)
TABLE(doc,
      ['层级', '名称', '核心职责', '关键输出'],
      [['L0', '输入层',
        '接收 STL / OBJ / PLY / GLB / 3MF / 点云 / STEP 等格式',
        '标准化的网格与点云数据'],
       ['L1', '诊断层',
        '拓扑体检（孔洞、非流形、自交、法线朝向、退化面、孤立壳、薄壁），'
        '生成缺陷图谱并规划修复策略',
        '缺陷图谱 + 可执行的修复计划'],
       ['L2', '修复层',
        '小缺陷走拓扑手术（保形好），大破损走隐式场重建（成功率高）；'
        '全程执行纹理保持：UV 调和插值 + 纹理扩散补全 + 泊松融合',
        '水密、流形、纹理完好的网格'],
       ['L3', '接缝层',
        '(a) 几何接缝 G1/G2 连续化；(b) 纹理接缝的可见度加权缝位优化；'
        '(c) 制造接缝的应力感知分块与互锁接头自动生成',
        '接缝一致的模型与分块打印方案'],
       ['L4', '输出层',
        '输出打印就绪的多部件文件、装配图、切片预设，以及可追溯的修复报告',
        '打印就绪文件与可追溯报告']],
      widths=[1.3, 1.9, 7.4, 4.2], font_size=9.5)
P(doc, '架构的核心设计意图：L2 与 L3 之间不是依次执行的关系，而是共享同一个'
       '接缝场（Seam Field）数据结构，即“模型上哪些位置的属性是不连续的、'
       '不连续度是多少”。L2 修复时写入接缝场，L3 优化时读取并修改接缝场。'
       '这是把两个割裂的软件流程合成一个优化问题的工程实现方式。', size=11)"""
patches.append((i_code, i_end, arch.split('\n')))

# ---------- P2：4.1 公式第二行的对齐依赖 ----------
i_f1 = find(lambda l: 'w_m·‖Δσ‖²' in l)
i_f2 = i_f1 + 1
assert '几何法线不连续' in lines[i_f2], 'P2 次行异常: ' + lines[i_f2]
formula = """CODE(doc, 'E_seam(Γ) = ∫_Γ [ w_g·‖Δn‖² + w_p·‖Δx‖² + w_t·‖Δc‖² + w_m·‖Δσ‖² ] ds')
P(doc, '式中四项分别对应四个域的不连续度：', indent=False)
TABLE(doc,
      ['能量项', '物理含义', '对应域'],
      [['w_g · ‖Δn‖²', '接缝两侧法线方向的差异', '几何'],
       ['w_p · ‖Δx‖²', '接缝两侧位置坐标的差异', '几何'],
       ['w_t · ‖Δc‖²', '接缝两侧纹素颜色的差异', '纹理'],
       ['w_m · ‖Δσ‖²', '接缝两侧力学性能的差异', '力学']],
      widths=[3.2, 7.4, 3.0], font_size=9.5)"""
patches.append((i_f1, i_f2, formula.split('\n')))

# ---------- P3：8.4 增长飞轮（去掉右侧竖线对齐） ----------
i_h3 = find(lambda l: "H(doc, '8.4 增长飞轮（商业模式创新的得分点）', level=2)" in l)
i_code3 = i_h3 + 1
assert lines[i_code3].strip() == 'CODE(doc,', 'P3 起点异常: ' + lines[i_code3]
i_end3 = find(lambda l: l.strip().endswith(', size=10)'), i_code3)
fly = """CODE(doc,
     '① 免费插件触达创客，降低使用门槛\\n'
     '        ↓\\n'
     '② 用户上传破损模型，积累真实缺陷数据\\n'
     '        ↓\\n'
     '③ 数据反哺算法与模型迭代，修复效果持续提升\\n'
     '        ↓\\n'
     '④ 用户口碑传播，带来更多免费用户\\n'
     '        ↓\\n'
     '⑤ 回到第 ① 步，飞轮加速运转', size=10)"""
patches.append((i_code3, i_end3, fly.split('\n')))

# 自下而上应用，避免行号漂移
for start, end, new in sorted(patches, key=lambda p: -p[0]):
    print('替换 %d-%d 行（%d 行 → %d 行）' % (start + 1, end + 1, end - start + 1, len(new)))
    lines[start:end + 1] = new

io.open(PATH, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
print('补丁完成')
