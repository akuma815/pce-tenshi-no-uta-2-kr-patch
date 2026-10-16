"""Render HTML document layouts with unchanged embedded source bitmaps."""
from pathlib import Path
import base64
import json
import subprocess
import time
import urllib.request
import websocket

ROOT = Path(__file__).resolve().parents[1]
EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

def embedded(path):
    return 'data:image/png;base64,' + base64.b64encode(Path(path).read_bytes()).decode('ascii')

class Renderer:
    def __init__(self, qa):
        self.profile = Path(qa) / ('edge_' + str(time.time_ns()))
        self.proc = subprocess.Popen([EDGE, '--headless=new', '--disable-gpu', '--no-first-run',
            '--no-default-browser-check', '--remote-debugging-port=0', '--remote-allow-origins=*',
            f'--user-data-dir={self.profile}', 'about:blank'], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic()+20
        while not (self.profile/'DevToolsActivePort').is_file():
            assert time.monotonic()<deadline
            time.sleep(.15)
        port = (self.profile/'DevToolsActivePort').read_text().splitlines()[0]
        tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list'))
        target = next(t for t in tabs if t['type']=='page')
        self.ws = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30)
        self.seq=0
        self.call('Page.enable')

    def call(self, method, params=None):
        self.seq+=1
        self.ws.send(json.dumps(dict(id=self.seq,method=method,params=params or {})))
        while True:
            result=json.loads(self.ws.recv())
            if result.get('id')==self.seq:
                assert 'error' not in result,result
                return result.get('result',{})

    def evaluate(self, code):
        result=self.call('Runtime.evaluate',dict(expression=code,returnByValue=True,awaitPromise=True))
        assert 'exceptionDetails' not in result,result
        return result['result'].get('value')

    def load(self,path,width=1440,height=1200,mobile=False):
        self.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=mobile))
        self.call('Page.navigate',dict(url=Path(path).as_uri()))
        for _ in range(100):
            if self.evaluate('document.readyState')=='complete':break
            time.sleep(.05)
        self.evaluate('document.fonts.ready.then(()=>true)')
        self.evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
        assert self.evaluate('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')
        assert self.evaluate('document.documentElement.scrollWidth<=innerWidth')

    def shot(self,path,full=False):
        params=dict(format='png',captureBeyondViewport=full)
        if full:
            size=self.evaluate('({width:innerWidth,height:document.documentElement.scrollHeight})')
            params['clip']=dict(x=0,y=0,width=size['width'],height=size['height'],scale=1)
        result=self.call('Page.captureScreenshot',params)
        Path(path).write_bytes(base64.b64decode(result['data']))

    def close(self):
        try:self.call('Browser.close')
        except Exception:pass
        self.ws.close()
        if self.proc.poll() is None:self.proc.wait(timeout=10)

