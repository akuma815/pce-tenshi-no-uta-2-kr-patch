"""Check every figure on desktop/mobile and keep document QA renders."""
import html
import json
from publication_visual_utils import Renderer,embedded
from build_publication_visuals_20261010_v3 import PUB,QA

def main():
    renderer=Renderer(QA);records=[]
    try:
        for device,width,mobile in [('desktop',1280,False),('mobile',390,True)]:
            renderer.load(PUB/'작업기.html',width,1700,mobile)
            metrics=renderer.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,headings:document.querySelectorAll("h2").length,figures:document.querySelectorAll("figure").length,loaded:Array.from(document.querySelectorAll("figure img")).every(i=>i.complete&&i.naturalWidth===1280),overflow:Array.from(document.querySelectorAll("main p,h2,figcaption,figure img")).filter(e=>e.getBoundingClientRect().right>innerWidth).length})')
            assert metrics['width']==width and metrics['scroll']<=width and metrics['headings']==15 and metrics['figures']==36 and metrics['loaded'] and metrics['overflow']==0,metrics
            for n in range(37):
                expr='window.scrollTo(0,0)' if n==0 else f'document.querySelector("#f{n:02}").scrollIntoView()'
                renderer.evaluate(expr)
                renderer.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
                path=QA/f'{device}_{"top" if n==0 else f"figure_{n:02}"}.png'
                renderer.shot(path)
                records.append(dict(path=path.name,device=device))
            for n in [1,10,31,35]:
                renderer.evaluate(f'document.querySelector("#f{n:02} .zoom").click()')
                renderer.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
                zoom=renderer.evaluate('({open:document.querySelector("dialog").open,img:document.querySelector("dialog img").getBoundingClientRect().width,body:document.documentElement.scrollWidth,window:innerWidth,dialog:document.querySelector("dialog").getBoundingClientRect().width,scroll:document.querySelector("dialog").scrollWidth})')
                assert zoom['open'] and zoom['img']==1280 and zoom['body']<=width and zoom['dialog']<=width,zoom
                renderer.shot(QA/f'{device}_zoom_{n:02}.png')
                renderer.evaluate('document.querySelector("dialog").scrollLeft=100;document.querySelector("dialog").scrollTop=100')
                if mobile:assert renderer.evaluate('document.querySelector("dialog").scrollLeft')>0
                renderer.call('Input.dispatchKeyEvent',dict(type='keyDown',key='Escape',code='Escape',windowsVirtualKeyCode=27))
                renderer.call('Input.dispatchKeyEvent',dict(type='keyUp',key='Escape',code='Escape',windowsVirtualKeyCode=27))
                assert not renderer.evaluate('document.querySelector("dialog").open')
        manifest=json.loads((QA/'visual_manifest.json').read_text(encoding='utf-8'))
        for start in range(0,36,6):
            cells=[]
            for b in manifest[start:start+6]:
                cells.append(f'<div><h2>{b["number"]:02} {html.escape(b["title"])}</h2><img src="{embedded(PUB/b["image"])}"></div>')
            page=QA/f'boards_review_{start//6+1}.html'
            page.write_text('<!doctype html><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;padding:15px;font:18px "Malgun Gothic";background:#eaf0f4}main{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}h2{font-size:18px;margin:8px 0}main>div{padding:10px;background:white}img{display:block;width:100%;height:auto}</style><main>'+''.join(cells)+'</main>',encoding='utf-8')
            renderer.load(page,1600,1200)
            renderer.shot(page.with_suffix('.png'),True)
        report=dict(status='PASS',method='isolated_headless_edge_cdp',desktop_width=1280,mobile_width=390,
            figure_renders=74,zoom_renders=8,board_review_sheets=6,figures_loaded=36,horizontal_overflow=False,
            natural_size_zoom_and_scroll='PASS',escape_close='PASS',records=records,
            scope='Publication document layout only; no game execution or gameplay QA.')
        (QA/'rendering.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in {'records','scope'}}))
    finally:renderer.close()

if __name__=='__main__':main()
