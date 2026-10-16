from pathlib import Path
import html
import json
from publication_visual_utils import ROOT, Renderer, embedded

QA=ROOT/'qa/publication/Tenshi2_KR_Worklog_20261010_v3'

def main():
    QA.mkdir(parents=True,exist_ok=True)
    groups={
        'early_b4':list((ROOT/'translation/b4_debug_2026-08-23').rglob('*.png')),
        'josa':list((ROOT/'translation/b19_runtime').glob('bp_*.png'))[:12]+
            list((ROOT/'translation/b21_runtime').glob('bprobe_*.png'))[:6]+
            list((ROOT/'translation/b22_runtime').glob('bprobe_*.png'))[:10],
        'memo':[p for tag in ['b23','b24','b25'] for p in (ROOT/f'translation/{tag}_runtime').glob('userstate*/u_f090.png')]+
            [ROOT/'translation/b26_runtime/memonew/memo_list_full.png',ROOT/'translation/b17_runtime/memo_memo_item2_f02788.png'],
        'portrait':[ROOT/'translation/b13_fetch_trace'/name for name in ['t0.png','t120.png','t_end.png','portrait_b13_0.png','portrait_b13_300.png','portrait_b13_750.png']],
        'title':[ROOT/'translation/title_probe'/name for name in ['shot_f2700.png','shot_f3300.png','shot_f3900.png','mock_title_kr.png','logo_cells_matched.png','spr_sheet_pal0.png']]+[ROOT/'translation/b17_runtime/title_b17.png',ROOT/'translation/b17_runtime/title_b17_b.png'],
        'ui':[ROOT/f'translation/{tag}_runtime/smoke_diag_{kind}_150.png' for tag in ['b13_fetch_trace','b15','b16'] for kind in ['status','menu','memo'] if (ROOT/f'translation/{tag}_runtime/smoke_diag_{kind}_150.png').exists()]+
            [ROOT/'translation/b10_loadscreen_2026-08-29/walk_f03958.png',ROOT/'translation/b10v2_loadscreen_2026-08-29/walk_f03958.png'],
    }
    manifest={}
    renderer=Renderer(QA)
    try:
        for group,paths in groups.items():
            paths=[p for p in paths if p.exists()]
            manifest[group]=[str(p.relative_to(ROOT)) for p in paths]
            for offset in range(0,len(paths),12):
                cells=[]
                for p in paths[offset:offset+12]:
                    cells.append(f'<div><p>{html.escape(str(p.relative_to(ROOT)))}</p><img src="{embedded(p)}"></div>')
                text=f'<!doctype html><meta charset="utf-8"><style>*{{box-sizing:border-box}}body{{margin:0;padding:20px;font-family:"Malgun Gothic";background:#edf2f6}}h1{{margin:0 0 16px}}main{{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}}main div{{background:white;padding:10px}}p{{font-size:15px;overflow-wrap:anywhere;margin:0 0 8px}}img{{width:100%;height:265px;object-fit:contain;image-rendering:pixelated}}</style><h1>{group} {offset//12+1}</h1><main>{"".join(cells)}</main>'
                page=QA/f'contact_{group}_{offset//12+1}.html';page.write_text(text,encoding='utf-8')
                renderer.load(page,1440,1000)
                renderer.shot(page.with_suffix('.png'),True)
        (QA/'candidate_sources.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print({g:len(p) for g,p in groups.items()})
    finally:renderer.close()

if __name__=='__main__':main()
