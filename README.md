# 愈缝 SeamHeal · 面向数字制造的 3D 模型修复与接缝优化工作台

![Python](https://img.shields.io/badge/Backend-Python%203.11%2B%20%2F%20FastAPI-3776AB?logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/Vision-OpenCV%20Inpainting-5C3EE8?logo=opencv&logoColor=white)
![WebGL](https://img.shields.io/badge/3D%20Viewport-Three.js%20WebGL-000000?logo=threedotjs&logoColor=white)
![Manufacturing](https://img.shields.io/badge/Domain-3D%20Printing%20%26%20Mesh%20Repair-E65100)

> 打通从三维扫描/AIGC 生成到 3D 打印制造的“接缝断点”，一站式完成网格诊断、局部曲面补洞、二面角接缝优化与 PBR 纹理补全。

**愈缝（SeamHeal）** 是一套本地运行的 3D 数字制造预处理工作台。针对三维扫描拼接或生成式 3D 模型常见的破洞、非流形边、接缝折痕与贴图缺失问题，提供**几何拓扑修复 + 二面角与 UV 各向异性优化 + OpenCV 局部纹理插值 + 打印切片前几何检查**的完整流水线。

---

## 已实现的核心能力 (`workbench/`)

| 模块 | 工程实现细节 |
| --- | --- |
| **多格式导入与多构件场景** | 支持 `GLB`、`STL`、`OBJ`、`PLY` 导入与持久化管理；支持整景诊断或勾选局部子构件批量修复，保留世界坐标变换与未选中构件原始拓扑 |
| **网格拓扑诊断与清理** | 自动检测开放边界孔洞、退化面（Degenerate Faces）、非流形边（Non-manifold Edges）与法线朝向不一致；一键清除重复/退化面并统一绕序 |
| **局部曲面补洞与接缝优化** | 针对孔洞生成局部补片并插值新 UV；计算原网格与补片交界处的**二面角（Dihedral Angle）**及 UV 各向异性畸变，仅迭代微调新增顶点，且通过定量改善判定后才提交结果 |
| **交互式纹理选区补全** | 支持在 BaseColor 贴图上框选缺陷区域，后端调用 OpenCV 局部插值算法补全缺失像素，严格保护选区外像素、Alpha 通道及其他 PBR 贴图层 |
| **双向点云采样基准测量** | 内置固定随机种子的双向表面采样距离（Chamfer / Hausdorff 近似）对比，支持双视口同步旋转、线框叠加、孔洞轮廓与补片接缝高亮 |
| **3D 打印制造准备检查** | 检测水密性（Watertightness）、悬挑特征、壁厚风险与支撑需求，支持分块装配预览、多格式导出与操作历史栈回退 |

---

## 快速启动

环境要求：Python 3.11+、Node.js 22.12+、Git LFS（用于拉取示例 GLB/BLEND 模型资产）。

```powershell
git lfs install
git clone https://github.com/NLTuring/seamheal.git
cd seamheal
git lfs pull
.\workbench\start.ps1
```

启动后浏览器自动打开 `http://127.0.0.1:8765`。如需在前台运行服务端：

```powershell
cd workbench
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8765
```

详细操作说明见 [workbench/README.md](workbench/README.md)。

---

## 目录结构

```text
seamheal/
├── workbench/      # 本地 3D 修复工作台前后端源码（FastAPI 几何处理服务端 + 三维交互前端）
├── assets/         # 测试与演示用三维网格模型资产
├── docs/           # 接缝优化算法原理与系统架构文档
└── tools/          # 工程辅助脚本
```
