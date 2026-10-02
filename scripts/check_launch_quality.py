"""Visual, mobile and cold/warm lab evidence. Public GETs only when --base-url is set."""
import argparse
import json
from contextlib import nullcontext
from pathlib import Path
from playwright.sync_api import sync_playwright
from shoot import DevServer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '.shots/launch-quality'
INIT = """window.__quality={lcp:0,cls:0,longTasks:[]};
new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__quality.lcp=e.startTime)).observe({type:'largest-contentful-paint',buffered:true});
new PerformanceObserver(l=>l.getEntries().forEach(e=>{if(!e.hadRecentInput)window.__quality.cls+=e.value})).observe({type:'layout-shift',buffered:true});
new PerformanceObserver(l=>l.getEntries().forEach(e=>window.__quality.longTasks.push(e.duration))).observe({type:'longtask',buffered:true});
const timer=setInterval(()=>{const el=document.getElementById('esta-preloader');if(document.querySelector('h1')&&document.documentElement.dataset.siteReady==='true'&&!document.documentElement.classList.contains('esta-pre-lock')&&(!el||Number(getComputedStyle(el).opacity)<.1||getComputedStyle(el).visibility==='hidden')){window.__quality.uncovered=performance.now();clearInterval(timer)}},25);"""


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url', default='')
    parser.add_argument('--engine', default='chromium')
    parser.add_argument('--perf-only', action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    base=args.base_url or 'http://127.0.0.1:8884'
    result=[]
    with (nullcontext() if args.base_url else DevServer(8884)), sync_playwright() as pw:
        browser=getattr(pw,args.engine).launch()
        if not args.perf_only:
            for width in (320,390,768,1440):
                context=browser.new_context(viewport={'width':width,'height':844},device_scale_factor=1)
                page=context.new_page(); errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                for path in ('/','/recruit/#hardware','/resources/','/recruitment/','/accounts/register/'):
                    response=page.goto(base+path,wait_until='load')
                    assert response.status==200,(path,response.status)
                    page.wait_for_function("!document.documentElement.classList.contains('esta-pre-lock')")
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,path,'overflow')
                    if path=='/':
                        page.wait_for_timeout(800)
                        page.screenshot(path=str(OUT/f'{args.engine}-{width}-hero.png'))
                        page.locator('#nf-forge').scroll_into_view_if_needed()
                        page.wait_for_selector('#nf-forge-stage.is-3d',timeout=25000)
                        page.evaluate("window.ESTA.motion.lenis ? window.ESTA.motion.lenis.scrollTo(document.querySelector('#nf-forge').offsetTop+500,{immediate:true}) : scrollTo(0,document.querySelector('#nf-forge').offsetTop+500)")
                        page.wait_for_timeout(600)
                        page.screenshot(path=str(OUT/f'{args.engine}-{width}-forge.png'))
                    elif path.startswith('/recruit/#'):
                        assert page.locator('#hardware > .rg-details').get_attribute('open') is not None
                    else:
                        page.screenshot(path=str(OUT/f'{args.engine}-{width}-{path.strip("/").replace("/","-")}.png'))
                assert not errors,errors
                print(args.engine,width,'layout, chapter deep link and full 3D passed',flush=True)
                context.close()
        if args.engine=='chromium':
            context=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1,is_mobile=True,has_touch=True)
            page=context.new_page();page.add_init_script(INIT)
            dev=context.new_cdp_session(page);dev.send('Network.enable')
            dev.send('Network.emulateNetworkConditions',{'offline':False,'latency':150,'downloadThroughput':200000,'uploadThroughput':93750,'connectionType':'cellular4g'})
            dev.send('Emulation.setCPUThrottlingRate',{'rate':4})
            for mode in ('cold','warm'):
                page.goto(base+'/',wait_until='domcontentloaded',timeout=55000)
                page.wait_for_function('window.__quality.uncovered>0',timeout=20000)
                early=page.evaluate("()=>({bytes:performance.getEntriesByType('resource').reduce((s,r)=>s+r.transferSize,0),uncovered:window.__quality.uncovered})")
                page.wait_for_load_state('load',timeout=55000);page.wait_for_timeout(1000)
                data=page.evaluate("()=>({...window.__quality,navigation:performance.getEntriesByType('navigation')[0].toJSON(),load:performance.getEntriesByType('navigation')[0].loadEventEnd,ttfb:performance.getEntriesByType('navigation')[0].responseStart,resources:performance.getEntriesByType('resource').map(r=>({name:r.name,bytes:r.transferSize,start:r.startTime,end:r.responseEnd,duration:r.duration})),renderer:document.querySelector('#hero-canvas').dataset.renderer})")
                data.update(mode=mode,early=early,base=base);result.append(data)
                print(mode,json.dumps({k:data[k] for k in ('early','lcp','cls','load','renderer')},ensure_ascii=False),flush=True)
            context.close()
        browser.close()
    (OUT/f'{args.engine}-metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
