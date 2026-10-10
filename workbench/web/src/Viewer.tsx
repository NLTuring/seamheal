import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { LoaderCircle, TriangleAlert } from 'lucide-react';
import type { Segment } from './types';

type Props = {url:string; sampleId:string; wireframe:boolean; boundaries:Segment[]; showBoundary:boolean; resetKey:number; label:string};
type Loaded = {model:THREE.Object3D; controls:OrbitControls; reset:()=>void; lines?:THREE.LineSegments; meshes:THREE.Mesh[]};

export function Viewer({url,sampleId,wireframe,boundaries,showBoundary,resetKey,label}:Props){
  const container=useRef<HTMLDivElement>(null);
  const loaded=useRef<Loaded|null>(null);
  const [status,setStatus]=useState<'loading'|'ready'|'error'>('loading');
  const [error,setError]=useState('');
  const [version,setVersion]=useState(0);
  useEffect(()=>{
    const el=container.current!;
    let disposed=false, frame=0;
    setStatus('loading'); setError('');
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}
    catch{setError('无法初始化 3D 视图，请使用支持 WebGL 的浏览器。');setStatus('error');return;}
    renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
    renderer.outputColorSpace=THREE.SRGBColorSpace;
    renderer.toneMapping=THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure=1.12;
    renderer.setClearColor('#edf0eb');
    renderer.domElement.setAttribute('aria-label',label+'三维视图');
    el.appendChild(renderer.domElement);
    const scene=new THREE.Scene();
    const camera=new THREE.PerspectiveCamera(38,1,.01,100);
    camera.position.set(...(sampleId==='panel'?[.6,.4,5.2]:sampleId==='roof'?[2.4,2.3,4.2]:[3.8,2.7,4.8]) as [number,number,number]);
    const initialDirection=camera.position.clone().normalize(),initialDistance=camera.position.length();
    const controls=new OrbitControls(camera,renderer.domElement);
    controls.enableDamping=true; controls.dampingFactor=.09; controls.minDistance=1; controls.maxDistance=14;
    controls.saveState();
    scene.add(new THREE.HemisphereLight('#ffffff','#a5afa1',2.8));
    const light=new THREE.DirectionalLight('#fff6e8',3.1);light.position.set(4,6,5);scene.add(light);
    const fill=new THREE.DirectionalLight('#e3efff',1);fill.position.set(-4,2,-2);scene.add(fill);
    const group=new THREE.Group();scene.add(group);
    const grid=new THREE.GridHelper(12,40,'#b9c9bd','#d1dbd0');
    (grid.material as THREE.Material).transparent=true;(grid.material as THREE.Material).opacity=.5;
    scene.add(grid);
    const fitView=()=>{const distance=Math.max(initialDistance,1.7/(Math.tan(THREE.MathUtils.degToRad(camera.fov/2))*Math.min(camera.aspect,1)));camera.position.copy(initialDirection).multiplyScalar(distance);controls.target.set(0,0,0);controls.update();};
    const resize=()=>{const w=el.clientWidth,h=el.clientHeight;if(!w||!h)return;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);fitView();};
    const observer=new ResizeObserver(resize);observer.observe(el);resize();
    const disposeObject=(object:THREE.Object3D)=>object.traverse(child=>{
      if(child instanceof THREE.Mesh || child instanceof THREE.LineSegments){
        child.geometry.dispose();
        const materials=Array.isArray(child.material)?child.material:[child.material];
        for(const material of materials){for(const value of Object.values(material)) if(value instanceof THREE.Texture)value.dispose();material.dispose();}
      }
    });
    new GLTFLoader().load(url,gltf=>{
      if(disposed){disposeObject(gltf.scene);return;}
      const model=gltf.scene;group.add(model);model.updateMatrixWorld(true);
      const box=new THREE.Box3().setFromObject(model);
      if(box.isEmpty()){setError('模型中没有可显示的几何体。');setStatus('error');return;}
      const center=box.getCenter(new THREE.Vector3()),size=box.getSize(new THREE.Vector3());
      const scale=3/Math.max(size.x,size.y,size.z,.001);
      group.scale.setScalar(scale);group.position.copy(center).multiplyScalar(-scale);
      grid.position.y=(box.min.y-center.y)*scale-.055;
      const meshes:THREE.Mesh[]=[];
      model.traverse(child=>{if(child instanceof THREE.Mesh)meshes.push(child);});
      loaded.current={model,controls,meshes,reset:fitView};
      renderer.domElement.dataset.loaded='true';
      setStatus('ready');setVersion(v=>v+1);
    },undefined,()=>{if(!disposed){setError('模型加载失败，请检查本地服务或重新导入文件。');setStatus('error');}});
    const render=()=>{if(disposed)return;controls.update();renderer.render(scene,camera);frame=requestAnimationFrame(render);};render();
    return()=>{disposed=true;cancelAnimationFrame(frame);observer.disconnect();controls.dispose();loaded.current=null;disposeObject(group);grid.geometry.dispose();(grid.material as THREE.Material).dispose();renderer.dispose();renderer.forceContextLoss();renderer.domElement.remove();};
  },[url,sampleId]);
  useEffect(()=>{
    if(!loaded.current)return;
    for(const mesh of loaded.current.meshes){
      const materials=Array.isArray(mesh.material)?mesh.material:[mesh.material];
      for(const material of materials) if('wireframe' in material) material.wireframe=wireframe;
    }
  },[wireframe,version]);
  useEffect(()=>{
    const state=loaded.current;if(!state)return;
    if(state.lines){state.lines.removeFromParent();state.lines.geometry.dispose();(state.lines.material as THREE.Material).dispose();state.lines=undefined;}
    if(!showBoundary || !boundaries.length || !state.meshes.length)return;
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(boundaries.flat(2),3));
    const lines=new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:'#e46c3f',depthTest:false,transparent:true,opacity:.95}));
    lines.renderOrder=10;state.meshes[0].add(lines);state.lines=lines;
  },[boundaries,showBoundary,version]);
  useEffect(()=>{loaded.current?.reset();},[resetKey]);
  return <div className="viewer-wrap"><div className="three-view" ref={container}/><span className="view-tag"><span/>{label}</span>{status==='loading'&&<div className="view-message"><LoaderCircle className="spin" size={25}/><b>正在加载模型</b><span>读取几何与内嵌贴图…</span></div>}{status==='error'&&<div className="view-message error"><TriangleAlert size={25}/><b>暂时无法显示</b><span>{error}</span></div>}</div>;
}
