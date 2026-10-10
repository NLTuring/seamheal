import { useEffect, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import { ImagePlus, LoaderCircle, Eraser, WandSparkles, ArrowDownToLine } from 'lucide-react';
import type { Artifact } from './types';
import './TexturePanel.css';

type Props={modelId:string;partId?:string;resultId?:string;disabled:boolean;onResult:(data:Artifact)=>void};
type Rect=[number,number,number,number];
export function TexturePanel({modelId,partId,resultId,disabled,onResult}:Props){
 const canvas=useRef<HTMLCanvasElement>(null),image=useRef<HTMLImageElement|null>(null),start=useRef<[number,number]|null>(null);
 const [rect,setRect]=useState<Rect|null>(null),[size,setSize]=useState<[number,number]|null>(null),[radius,setRadius]=useState(3);
 const [busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[error,setError]=useState('');
 const controller=useRef<AbortController|null>(null);
 useEffect(()=>{
  const abort=new AbortController();let url:string|undefined;
  const query=new URLSearchParams({model_id:modelId,...(partId?{part_id:partId}:{}),...(resultId?{result_id:resultId}:{})});
  setLoading(true);setError('');setRect(null);
  fetch('/api/texture?'+query,{signal:abort.signal}).then(async response=>{
   if(!response.ok){const data=await response.json();throw new Error(typeof data.detail==='string'?data.detail:'贴图无法读取。');}
   return response.blob();
  }).then(blob=>{
   if(abort.signal.aborted)return;url=URL.createObjectURL(blob);const img=new Image();
   img.onload=()=>{if(abort.signal.aborted)return;image.current=img;setSize([img.naturalWidth,img.naturalHeight]);setLoading(false);};
   img.onerror=()=>{if(!abort.signal.aborted){setError('贴图图像无法解码。');setLoading(false);}};img.src=url;
  }).catch(e=>{if(!abort.signal.aborted){setError(e.message);setLoading(false);}});
  return()=>{abort.abort();controller.current?.abort();if(url)URL.revokeObjectURL(url);};
 },[modelId,partId,resultId]);
 useEffect(()=>{
  const el=canvas.current,img=image.current;if(!el||!img||!size)return;
  el.width=size[0];el.height=size[1];const ctx=el.getContext('2d')!;ctx.drawImage(img,0,0);
  if(rect){ctx.fillStyle='#e881554a';ctx.fillRect(rect[0],rect[1],rect[2]-rect[0],rect[3]-rect[1]);ctx.strokeStyle='#f07b41';ctx.lineWidth=Math.max(2,size[0]/180);ctx.strokeRect(rect[0],rect[1],rect[2]-rect[0],rect[3]-rect[1]);}
 },[rect,size]);
 const point=(e:PointerEvent<HTMLCanvasElement>):[number,number]=>{const bounds=e.currentTarget.getBoundingClientRect();return [Math.round(Math.max(0,Math.min(size![0],(e.clientX-bounds.left)/bounds.width*size![0]))),Math.round(Math.max(0,Math.min(size![1],(e.clientY-bounds.top)/bounds.height*size![1])))];};
 const move=(e:PointerEvent<HTMLCanvasElement>)=>{if(!start.current||!size)return;const end=point(e);setRect([Math.min(start.current[0],end[0]),Math.min(start.current[1],end[1]),Math.max(start.current[0],end[0]),Math.max(start.current[1],end[1])]);};
 const pixels=rect?(rect[2]-rect[0])*(rect[3]-rect[1]):0;
 const fraction=size?pixels/(size[0]*size[1]):0;
 const submit=async()=>{
  if(!rect)return;setBusy(true);setError('');const abort=new AbortController();controller.current=abort;
  try{const response=await fetch('/api/texture/repair',{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({model_id:modelId,part_id:partId,result_id:resultId,rectangle:rect,radius})});const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'补全失败，请缩小选区后重试。');onResult(data);}
  catch(e){if(!abort.signal.aborted)setError((e as Error).message);}finally{if(!abort.signal.aborted)setBusy(false);}
 };
 return <div className="texture-panel"><div className="section-eyebrow">TEXTURE<span>纹理区域补全</span></div><h3><ImagePlus size={18}/>选择需要补全的区域</h3><p>在贴图上拖动框选。算法根据周围像素推测颜色，选区外像素保持不变。</p>
  {loading?<div className="texture-loading"><LoaderCircle className="spin" size={20}/>正在读取贴图…</div>:size&&<><div className="texture-canvas"><canvas ref={canvas} aria-label="框选纹理区域" onPointerDown={e=>{if(busy||disabled)return;e.currentTarget.setPointerCapture(e.pointerId);start.current=point(e);setRect(null);}} onPointerMove={move} onPointerUp={e=>{move(e);start.current=null;}} onPointerCancel={()=>{start.current=null;}}/></div><div className="texture-size">{size[0]} × {size[1]} px <span>已选 {(fraction*100).toFixed(1)}%</span></div><button className="outline-button" disabled={!rect||busy} onClick={()=>setRect(null)}><Eraser size={14}/>清除选区</button></>}
  <label className="texture-radius">补全半径 <output>{radius} px</output><input aria-label="纹理补全半径" type="range" min="1" max="15" value={radius} onChange={e=>setRadius(Number(e.target.value))}/></label>
  {fraction>.3||pixels>500000?<div className="inline-error">请缩小选区：不超过贴图 30%，且最多 50 万像素。</div>:null}
  {error&&<div className="inline-error" role="alert">{error}</div>}
  <button className="primary-button" disabled={disabled||busy||loading||pixels===0||fraction>.3||pixels>500000} onClick={()=>void submit()}>{busy?<LoaderCircle className="spin" size={16}/>:<WandSparkles size={16}/>}补全选中纹理</button><p className="texture-note">这是对缺失内容的预测，不能保证恢复原始花纹。透明通道保持原样；原文件保留，可随时切回。</p>
  {resultId&&<a className="report-link" href={'/outputs/'+resultId+'.zip'} download><ArrowDownToLine size={14}/>下载当前结果包</a>}
 </div>;
}
