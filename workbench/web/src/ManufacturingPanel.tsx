import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowDownToLine, Box, Check, ChevronDown, Eye, FileJson, LoaderCircle, Ruler, Scissors, TriangleAlert } from 'lucide-react';
import './ManufacturingPanel.css';

type PrintReport = {
  dimensions_mm: number[];
  volume_mm3: number | null;
  watertight: boolean;
  winding_consistent: boolean;
  outward_normals: boolean;
  fits_build_volume: boolean;
  fits_with_axis_rotation: boolean;
  passes_checked_constraints: boolean;
  self_intersection: {status:string;intersection_pairs:number;scope:string};
  overhang: { area_ratio: number; angle_deg: number };
  wall_thickness: {
    status: string;
    samples: number;
    sampled_min_mm: number | null;
    below_minimum_samples: number;
    limitation: string;
    reason?: string;
  };
  warnings: string[];
};

type Assembly = {
  result_id: string;
  result_url: string;
  report_url: string;
  bundle_url: string;
  stl_urls: { name: string; url: string }[];
  report: {
    joint: 'none' | 'dovetail';
    measured_gap_mm: number;
    angle_deg: number;
    assembly_axis: string;
    removed_volume_mm3: number;
    parts: { name: string; watertight: boolean; volume_mm3: number }[];
    warnings: string[];
  };
};

export type ManufacturingPanelProps = {
  modelId: string;
  partId?: string;
  resultId?: string;
  disabled: boolean;
  onPreview: (url: string, label: string) => void;
};

const format = (value: number, digits = 2) => value.toLocaleString('zh-CN', {
  maximumFractionDigits: digits,
});

async function post<T>(endpoint: string, payload: object, signal: AbortSignal): Promise<T> {
  const response = await fetch(`/api/manufacturing/${endpoint}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal,
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('服务返回了无法读取的结果，请稍后重试。');
  }
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : '参数或模型不符合要求，请调整后重试。');
  }
  return data as T;
}

function CheckRow({ label, passed, warning = '需复核' }: { label: string; passed: boolean; warning?: string }) {
  return <div className="mfg-check-row"><span>{label}</span>
    <strong className={passed ? 'mfg-pass' : 'mfg-warning'}>
      {passed ? <Check size={12} /> : <TriangleAlert size={12} />}{passed ? '通过' : warning}
    </strong>
  </div>;
}

function AssemblyResult({ data, label, onPreview }: {
  data: Assembly; label: string; onPreview: ManufacturingPanelProps['onPreview'];
}) {
  return <div className="mfg-assembly-result" aria-label={label}>
    <div className="mfg-result-title"><Check size={14} /><strong>{label}已生成</strong><span>{data.report.parts.length} 件</span></div>
    <dl className="mfg-metrics">
      <div><dt>测得装配间隙</dt><dd>{format(data.report.measured_gap_mm, 3)} mm</dd></div>
      <div><dt>部件闭合</dt><dd>{data.report.parts.every(part => part.watertight) ? '全部通过' : '需复核'}</dd></div>
      {data.report.joint === 'dovetail' && <div><dt>滑入方向 / 燕尾角</dt><dd>{data.report.assembly_axis.toUpperCase()} / {format(data.report.angle_deg)}°</dd></div>}
    </dl>
    <button type="button" className="mfg-secondary" onClick={() => onPreview(data.result_url, label)}><Eye size={14} />查看装配模型</button>
    <a className="mfg-download" href={data.bundle_url} download><ArrowDownToLine size={14} />下载完整装配包<span>ZIP</span></a>
    <div className="mfg-file-links">
      <a href={data.result_url} download>GLB 模型</a>
      <a href={data.report_url} download><FileJson size={12} />参数报告</a>
      {data.stl_urls.map((part, index) => <a key={part.url} href={part.url} download title={part.name}>部件 {index + 1} · STL</a>)}
    </div>
    <details className="mfg-details mfg-output-notes"><summary>装配说明与适用范围<ChevronDown size={12} /></summary>
      <ul>{data.report.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
    </details>
  </div>;
}

export function ManufacturingPanel({ modelId, partId, resultId, disabled, onPreview }: ManufacturingPanelProps) {
  const [minimumWall, setMinimumWall] = useState('1');
  const [buildVolume, setBuildVolume] = useState(['220', '220', '250']);
  const [axis, setAxis] = useState('x');
  const [fraction, setFraction] = useState(.5);
  const [joint, setJoint] = useState<'dovetail' | 'none'>('dovetail');
  const [clearance, setClearance] = useState('0.2');
  const [sampleDimensions, setSampleDimensions] = useState(['60', '30', '12']);
  const [sampleClearance, setSampleClearance] = useState('0.2');
  const [angle, setAngle] = useState('12');
  const [check, setCheck] = useState<PrintReport | null>(null);
  const [split, setSplit] = useState<Assembly | null>(null);
  const [sample, setSample] = useState<Assembly | null>(null);
  const [busy, setBusy] = useState<'check' | 'split' | 'sample' | null>(null);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  const blocked = disabled || busy !== null;
  const reference = { model_id: modelId, ...(partId ? { part_id: partId } : {}), ...(resultId ? { result_id: resultId } : {}) };
  const run = async (kind: 'check' | 'split' | 'sample', payload: object) => {
    if (busy || (kind !== 'sample' && (disabled || !modelId))) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(kind);
    setError('');
    try {
      if (kind === 'check') {
        setCheck(null);
        const report = await post<PrintReport>(kind, payload, request.signal);
        if (!request.signal.aborted) setCheck(report);
      } else {
        if (kind === 'split') setSplit(null); else setSample(null);
        const result = await post<Assembly>(kind, payload, request.signal);
        if (!request.signal.aborted) {
          if (kind === 'split') setSplit(result); else setSample(result);
          onPreview(result.result_url, kind === 'split' ? '分块装配结果' : '参数化燕尾试件');
        }
      }
    } catch (cause) {
      if (!request.signal.aborted) setError(cause instanceof Error ? cause.message : '操作失败，请重试。');
    } finally {
      if (!request.signal.aborted) setBusy(null);
    }
  };
  const submitCheck = (event: FormEvent) => {
    event.preventDefault();
    void run('check', { ...reference, minimum_wall_mm: Number(minimumWall), build_volume_mm: buildVolume.map(Number) });
  };
  const submitSplit = (event: FormEvent) => {
    event.preventDefault();
    void run('split', { ...reference, axis, fraction, joint, clearance_mm: Number(clearance) });
  };
  const submitSample = (event: FormEvent) => {
    event.preventDefault();
    void run('sample', { width_mm: Number(sampleDimensions[0]), depth_mm: Number(sampleDimensions[1]),
      height_mm: Number(sampleDimensions[2]), clearance_mm: Number(sampleClearance), angle_deg: Number(angle) });
  };

  return <section className="manufacturing-panel" aria-label="制造与装配" aria-busy={busy !== null}>
    <div className="mfg-panel-heading"><Ruler size={16} /><h2>制造与装配</h2><span>mm</span></div>
    <p className="mfg-context">{resultId ? '检查与分块使用当前修复结果。' : '检查与分块使用当前选中部件。'}尺寸以毫米显示。</p>
    {error && <div className="mfg-error" role="alert"><TriangleAlert size={14} /><span>{error}</span></div>}
    {busy && <p className="mfg-busy" role="status"><LoaderCircle size={13} className="spin" />{busy === 'check' ? '正在测量尺寸、壁厚与悬垂…' : '正在构建闭合部件并校验间隙…'}</p>}

    <section className="mfg-section" aria-label="打印几何检查">
      <h3><Ruler size={14} />打印几何检查</h3>
      <form onSubmit={submitCheck}>
        <fieldset disabled={blocked || !modelId}>
          <label className="mfg-field">最小壁厚 <span>mm</span><input type="number" aria-label="最小壁厚" min="0.01" max="100" step="any" required value={minimumWall} onChange={event => { setMinimumWall(event.target.value); setCheck(null); }} /></label>
          <div className="mfg-field-label">打印空间 <span>mm · X / Y / Z</span></div>
          <div className="mfg-three-inputs">{buildVolume.map((value, index) => <label key={index}>
            <span>{'XYZ'[index]}</span><input type="number" aria-label={`打印空间 ${'XYZ'[index]}`} min="1" max="100000" step="any" required value={value} onChange={event => { setBuildVolume(previous => previous.map((item, at) => at === index ? event.target.value : item)); setCheck(null); }} />
          </label>)}</div>
          <button type="submit" className="mfg-action"><Ruler size={14} />{busy === 'check' ? '正在检查…' : '运行打印检查'}</button>
        </fieldset>
      </form>
      {check && <div className="mfg-print-result" aria-live="polite">
        <div className={`mfg-status ${check.passes_checked_constraints ? 'mfg-pass' : 'mfg-warning'}`}>
          {check.passes_checked_constraints ? <Check size={14} /> : <TriangleAlert size={14} />}
          {check.passes_checked_constraints ? '已检查项通过' : '检查结果需复核'}
        </div>
        <dl className="mfg-metrics">
          <div className="mfg-dimensions"><dt>外形尺寸 · mm</dt><dd>{check.dimensions_mm.map(value => format(value)).join(' × ')}</dd></div>
          <div><dt>实体体积</dt><dd>{check.volume_mm3 === null ? '不可计算' : `${format(check.volume_mm3 / 1000)} cm³`}</dd></div>
        </dl>
        <CheckRow label="封闭性" passed={check.watertight} />
        <CheckRow label="面朝向" passed={check.winding_consistent && check.outward_normals} />
        <CheckRow label="非相邻面自交" passed={check.self_intersection.status === 'checked' && check.self_intersection.intersection_pairs === 0} warning={check.self_intersection.intersection_pairs ? `${check.self_intersection.intersection_pairs} 对相交` : check.self_intersection.status === 'partial' ? '部分检查' : '未检查'} />
        <CheckRow label="当前朝向适配打印空间" passed={check.fits_build_volume} warning={check.fits_with_axis_rotation ? '可尝试旋转' : '超出空间'} />
        <dl className="mfg-metrics mfg-estimates">
          <div><dt>抽样最小壁厚</dt><dd className={check.wall_thickness.below_minimum_samples ? 'mfg-warning' : ''}>{check.wall_thickness.sampled_min_mm === null ? '未检查' : `${format(check.wall_thickness.sampled_min_mm, 3)} mm`}</dd></div>
          <div><dt>悬垂面积占比</dt><dd>{format(check.overhang.area_ratio * 100)}%</dd></div>
        </dl>
        <p className="mfg-note">壁厚已取样 {check.wall_thickness.samples} 处{check.wall_thickness.below_minimum_samples ? `，${check.wall_thickness.below_minimum_samples} 处低于阈值` : ''}。悬垂按 +Z 朝向、{check.overhang.angle_deg}° 阈值计算，排除底面。</p>
        <details className="mfg-details"><summary>查看检查范围与建议<ChevronDown size={12} /></summary>
          <p>{check.wall_thickness.reason || check.wall_thickness.limitation}</p>
          <ul>{check.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
        </details>
      </div>}
      <p className="mfg-note">壁厚采用射线抽样估计。自交检查设有规模与时间上限，不含共享顶点的相邻面重叠。制造强度未标定。</p>
    </section>

    <section className="mfg-section" aria-label="模型分块装配">
      <h3><Scissors size={14} />模型分块装配</h3>
      <form onSubmit={submitSplit}>
        <fieldset disabled={blocked || !modelId}>
          <div className="mfg-two-inputs">
            <label className="mfg-field">切分轴<select aria-label="切分轴" value={axis} onChange={event => setAxis(event.target.value)}><option value="x">X 轴</option><option value="y">Y 轴</option><option value="z">Z 轴</option></select></label>
            <label className="mfg-field">连接方式<select aria-label="连接方式" value={joint} onChange={event => setJoint(event.target.value as 'dovetail' | 'none')}><option value="dovetail">滑入式燕尾</option><option value="none">平面分块</option></select></label>
          </div>
          <label className="mfg-range">切分位置 <strong>{Math.round(fraction * 100)}%</strong><input type="range" aria-label="切分位置" min="0.1" max="0.9" step="0.05" value={fraction} onChange={event => setFraction(Number(event.target.value))} /></label>
          <label className="mfg-field">装配间隙 <span>mm</span><input type="number" aria-label="分块装配间隙" min="0" max="2" step="0.05" required value={clearance} onChange={event => setClearance(event.target.value)} /></label>
          <button type="submit" className="mfg-action"><Scissors size={14} />{busy === 'split' ? '正在生成分块…' : '生成分块与装配'}</button>
        </fieldset>
      </form>
      <p className="mfg-note">适用于单个封闭实体。燕尾需贯穿的实体安装区，薄壁与曲面可先尝试平面分块。输出使用部件颜色。</p>
      {split && <AssemblyResult data={split} label="分块装配结果" onPreview={onPreview} />}
    </section>

    <details className="mfg-section mfg-details mfg-sample">
      <summary><Box size={14} /><strong>参数化燕尾试件</strong><ChevronDown size={13} /></summary>
      <p className="mfg-note">生成独立公母试件，用于比较配合间隙与打印试装。</p>
      <form onSubmit={submitSample}>
        <fieldset disabled={busy !== null}>
          <div className="mfg-field-label">试件尺寸 <span>mm</span></div>
          <div className="mfg-three-inputs">{sampleDimensions.map((value, index) => <label key={index}>
            <span>{['宽', '深', '高'][index]}</span><input type="number" aria-label={`试件${['宽度', '深度', '高度'][index]}`} min={index === 2 ? 2 : 10} max="1000" step="any" required value={value} onChange={event => setSampleDimensions(previous => previous.map((item, at) => at === index ? event.target.value : item))} />
          </label>)}</div>
          <div className="mfg-two-inputs">
            <label className="mfg-field">间隙 <span>mm</span><input type="number" aria-label="试件装配间隙" min="0" max="2" step="0.05" required value={sampleClearance} onChange={event => setSampleClearance(event.target.value)} /></label>
            <label className="mfg-field">燕尾角 <span>°</span><input type="number" aria-label="试件燕尾角" min="3" max="30" step="1" required value={angle} onChange={event => setAngle(event.target.value)} /></label>
          </div>
          <button type="submit" className="mfg-secondary"><Box size={14} />{busy === 'sample' ? '正在生成试件…' : '生成燕尾试件'}</button>
        </fieldset>
      </form>
      {sample && <AssemblyResult data={sample} label="参数化燕尾试件" onPreview={onPreview} />}
    </details>
  </section>;
}
