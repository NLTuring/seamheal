"""Build a labeled preview sheet and a self-contained shareable asset ZIP."""
from pathlib import Path
import json
import hashlib
import zipfile
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]


def font(size,bold=False):
    name='msyhbd.ttc' if bold else 'msyh.ttc'
    return ImageFont.truetype('C:/Windows/Fonts/'+name,size)


def contact_sheet():
    canvas=Image.new('RGB',(1720,1640),'#F5F1E9');d=ImageDraw.Draw(canvas)
    d.text((60,35),'樱庭 · 修复演示素材',font=font(40,True),fill='#303632')
    d.text((62,92),'真实几何缺口  /  原创 UV 贴图  /  完整基准对照',font=font(21),fill='#77766E')
    d.line((60,138,1660,138),fill='#B39761',width=2)
    for row,(key,title,note) in enumerate([
            ('roof','曲面瓦顶','破损版缺失 704 个三角面 · 108 条边界边'),
            ('panel','花枝彩绘墙板','破损版缺失 324 个三角面 · 72 条边界边')]):
        y=170+row*700
        d.text((60,y),title,font=font(27,True),fill='#353B37')
        d.text((1660,y+7),note,font=font(19),fill='#77766E',anchor='ra')
        for col,(variant,label) in enumerate([('damaged','人为破损'),('intact','完整基准')]):
            x=60+col*815
            d.text((x,y+49),label,font=font(20),fill='#947844')
            im=Image.open(ROOT/'previews'/f'{key}_{variant}_detail.png').convert('RGB')
            im=im.resize((785,589),Image.Resampling.LANCZOS)
            canvas.paste(im,(x,y+82))
    d.rectangle((0,1585,1720,1640),fill='#EEE8DB')
    d.text((60,1600),'完整版本是人为破损前保存的建模基准；后续算法结果应与该基准比较。',font=font(19),fill='#77766E')
    canvas.save(ROOT/'previews'/'repair_comparison.png')


def package():
    verification=json.loads((ROOT/'reports'/'export_verification.json').read_text(encoding='utf-8'))
    for name,record in verification['files'].items():
        digest=hashlib.sha256((ROOT/'exports'/name).read_bytes()).hexdigest()
        assert digest==record['sha256'],f'Export changed after verification: {name}'
    archive=ROOT.parent/'sakura_courtyard_asset_pack.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in ('.log','.pyc','.blend1'):
                continue
            z.write(path,Path('sakura_courtyard')/path.relative_to(ROOT))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        count=len(z.namelist())
    print(json.dumps({'zip':str(archive),'bytes':archive.stat().st_size,'files':count},ensure_ascii=False))


if __name__=='__main__':
    contact_sheet();package()
