"""Render the offline article with an isolated, headless Edge profile."""
from pathlib import Path
import base64
import json
import subprocess
import time
import urllib.request
import websocket

ROOT = Path(__file__).resolve().parents[1]
NAME = 'Tenshi2_KR_Worklog_20261010'
QA = ROOT / 'qa' / 'publication' / NAME
PAGE = ROOT / 'workspace' / 'publication' / NAME / '작업기.html'
EDGE = Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')

def main():
    profile = QA / ('edge_cdp_' + str(time.time_ns()))
    proc = subprocess.Popen([str(EDGE), '--headless=new', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--remote-debugging-port=0', '--remote-allow-origins=*',
        f'--user-data-dir={profile}', 'about:blank'], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    deadline = time.monotonic() + 20
    while not (profile / 'DevToolsActivePort').is_file():
        assert time.monotonic() < deadline, 'DevTools startup timeout'
        time.sleep(.2)
    port = (profile / 'DevToolsActivePort').read_text().splitlines()[0]
    tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list'))
    target = next(t for t in tabs if t['type'] == 'page')
    ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=15)
    seq = 0
    def call(method, params=None):
        nonlocal seq
        seq += 1
        ws.send(json.dumps({'id': seq, 'method': method, 'params': params or {}}))
        while True:
            result = json.loads(ws.recv())
            if result.get('id') == seq:
                assert 'error' not in result, result
                return result.get('result', {})
    def evaluate(expression):
        r = call('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
                                    'awaitPromise': True})
        assert 'exceptionDetails' not in r, r
        return r['result'].get('value')
    results = []
    call('Page.enable')
    call('Page.navigate', {'url': PAGE.as_uri()})
    for _ in range(60):
        if evaluate('document.readyState') == 'complete':
            break
        time.sleep(.1)
    evaluate('document.fonts.ready.then(()=>true)')
    for device, width, height, mobile in [('desktop', 1280, 1700, False), ('mobile', 390, 1700, True)]:
        call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
            'deviceScaleFactor': 1, 'mobile': mobile})
        evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
        metrics = evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,headings:document.querySelectorAll("h2").length,images:Array.from(document.querySelectorAll("figure img"),i=>({loaded:i.complete&&i.naturalWidth>0,width:i.getBoundingClientRect().width}))})')
        assert metrics['width'] == width and metrics['scroll'] <= width, metrics
        assert metrics['headings'] == 15 and all(i['loaded'] and i['width'] <= width for i in metrics['images']), metrics
        for part, expr in [('top', 'window.scrollTo(0,0)'), ('portrait', 'document.querySelector("#s10").scrollIntoView()')]:
            evaluate(expr)
            evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
            shot = call('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': False})
            output = QA / f'{device}_{part}.png'
            output.write_bytes(base64.b64decode(shot['data']))
            results.append({'image': output.name, 'width': width, 'height': height, 'metrics': metrics})
        evaluate('document.querySelector(".zoom").click()')
        assert evaluate('document.querySelector("dialog").open')
        call('Input.dispatchKeyEvent', {'type': 'keyDown', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
        call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'Escape', 'code': 'Escape', 'windowsVirtualKeyCode': 27})
        assert not evaluate('document.querySelector("dialog").open')
    (QA / 'rendering.json').write_text(json.dumps({'method': 'isolated_headless_edge_cdp',
        'status': 'PASS', 'renders': results, 'dialog_open_and_escape': 'PASS',
        'scope': 'DOM/layout checks across article; screenshots at top and portrait section for desktop/mobile; visual inspection in handoff'},
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'screenshots': len(results), 'no_horizontal_overflow': True,
                      'all_images_loaded': True, 'dialog_open_and_escape': True}))
    try:
        call('Browser.close')
    except Exception:
        pass
    ws.close()
    if proc.poll() is None:
        proc.wait(timeout=10)

if __name__ == '__main__':
    main()
