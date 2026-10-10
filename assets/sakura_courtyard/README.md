# 樱庭 Sakura Courtyard 模型素材

本素材为愈缝 SeamHeal 的挑战杯演示制作。依据本次提供的樱花庭院截图重新构思并建模，包含三栋木构建筑、四棵樱花树、石质地台、庭园步道、小桥、溪流、灯笼与花枝彩绘墙板。几何与贴图均为本次新生成的资产，未从参考截图提取纹理或复原原始模型数据。

## 直接使用

| 文件 | 用途 |
| --- | --- |
| `sakura_courtyard_master.blend` | 可编辑的完整源场景；建筑构件、植物、地形分别组织，贴图已打包；含相机与灯光 |
| `sakura_courtyard_damaged.blend` | 屋面与墙板含真实缺口的场景；静态背景部件已合并，修复目标保留独立对象 |
| `exports/sakura_courtyard_intact.glb` | 浏览器展示用完整庭院，贴图内嵌 |
| `exports/sakura_courtyard_damaged.glb` | 同一庭院的可控破损版本，适合全景到局部的演示 |
| `exports/roof_intact.glb`、`roof_damaged.glb` | 独立的曲面瓦顶修复样本，连续 UV，可直接送入几何诊断和补洞流程 |
| `exports/panel_intact.glb`、`panel_damaged.glb` | 独立彩绘墙板样本，适合演示补洞时保留周边花纹与 UV |
| `exports/dovetail_assembled.glb`、`dovetail_exploded.glb` | 独立燕尾连接结构的组合与分离视图，用于解释互锁结构 |
| `textures/` | 可编辑的原创 PNG 贴图；完整 GLB 与 BLEND 使用时不依赖此文件夹 |
| `previews/` | 完整庭院、破损庭院、屋面与墙板局部、燕尾结构的渲染图 |
| `reports/asset_manifest.json` | 真实面数、尺寸、修复对象名称、破损面索引及源网格检测结果 |
| `reports/export_verification.json` | 导出后独立验证结果、文件哈希与几何/UV 一致性检查 |
| `source/` | 可重复生成资产的 Blender 建模脚本与贴图生成脚本 |

## 演示方式

浏览器工作台可以先加载完整庭院建立场景印象，再切换至破损版本并聚焦 `Roof_RepairTarget` 或 `Panel_RepairTarget`。模型对象上保留了 `repair_case_id` 与 `selectable_repair_target` 标记，便于定位。

建议最先接入独立的 `roof_damaged.glb` 和 `panel_damaged.glb` 跑通实际算法，再把处理后的对象放回庭院。全景中包含有意分离和相互搭接的建筑构件及装饰花瓣，因此诊断时应以选中的修复对象为范围。

完整版本是生成破损样本之前保存的几何基准，可用于验证修复结果。它不是已运行修复算法得到的输出。展示时使用“完整基准”“人为破损”等名称，避免把基准替换动画表述为真实修复计算。

燕尾连接样件是独立的结构示例，不是从庭院建筑上自动求解出的分块。未进行打印适配、受力计算或力学实验，不能据此展示强度保持率或承载数值。

## 本次检查

| 样本 | 完整版本 | 破损版本 |
| --- | --- | --- |
| 曲面瓦顶 | 9,048 个三角面，闭合，法向一致 | 缺失 704 个三角面，108 条边界边，2 个边界环 |
| 花枝彩绘墙板 | 4,096 个三角面，闭合，法向一致 | 缺失 324 个三角面，72 条边界边，2 个边界环 |
| 两块燕尾样件 | 各 28 个三角面，分别闭合 | 分离版本只改变位置 |

两组破损样本保留区域的顶点位置与 UV 坐标均与完整基准一致。GLB 已通过独立读入检查，图像全部内嵌，无外部贴图依赖。详细结果以 `reports/` 中的 JSON 为准。

完整庭院约 37.9 万个三角面，浏览器版有 19 个网格对象。场景采用米为单位，一个建模单位对应 20 mm；连同树冠的整体范围约 288 × 235 × 209 mm。此尺度用于展示与装配理解，整景尚未进行整体水密布尔合并、最小壁厚或实际打印验证。花朵使用真实花瓣几何，没有使用透明花叶卡片。

## 在本机打开与重新生成

本次使用 Blender 4.5.14 LTS 便携版，运行路径为：

```powershell
& 'D:\CodexTools\Blender\blender-4.5.14-windows-x64\blender.exe' 'D:\挑战杯项目\3D模型智能修复与接缝优化工具\assets\sakura_courtyard\sakura_courtyard_master.blend'
```

已附带贴图，重新生成模型只需 Blender。进入项目目录后运行：

```powershell
& 'D:\CodexTools\Blender\blender-4.5.14-windows-x64\blender.exe' --background --factory-startup --python 'assets\sakura_courtyard\source\build_scene.py' -- --all-views
```

`--draft` 可降低预览分辨率和采样；`--no-render` 只生成模型文件。纹理生成脚本额外使用 Pillow 和 NumPy；独立导出验证使用 trimesh 和 NumPy。生成脚本会覆盖本素材目录中同名的生成结果，手工编辑后的作品请另存文件。

Blender 安装包下载自清华大学开源软件镜像站，并按发布的 SHA-256 校验：`b9533d2397ac1984db4466fb23a7a4649391cca93f6e84209f9bcc60d071c8b9`。便携版放在项目外，未写入系统 PATH。
