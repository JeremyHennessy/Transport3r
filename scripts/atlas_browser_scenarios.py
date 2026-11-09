"""Synthetic Atlas lifecycle gates. No real-source or hosted acceptance implied."""
import json

# Observe the synthetic requests and deliberately delay replies when requested.
# The test does not suppress failed assertions or change application source data.
NETWORK_OBSERVER = r'''(() => {
  const fetcher=window.fetch;
  window.__atlasRequests=[];
  window.__atlasPending=0;
  window.__atlasHold=false;
  window.__atlasReleaseQueue=[];
  window.__releaseAtlasReplies=()=>{
    window.__atlasHold=false;
    for(const release of window.__atlasReleaseQueue.splice(0)) release();
  };
  window.fetch=async(input,options)=>{
    const url=String(input);
    if(!url.includes('data.transportation.gov/resource/')) return fetcher(input,options);
    window.__atlasRequests.push(url);
    window.__atlasPending++;
    try {
      const response=await fetcher(input,options);
      if(window.__atlasHold) await new Promise(resolve=>window.__atlasReleaseQueue.push(resolve));
      return response;
    } finally { window.__atlasPending--; }
  };
})();'''


def settle(page):
    # Poll application completion first, not the first request or a stale button.
    page.wait_for_function("document.querySelector('[data-testid=carrier-atlas]')?.dataset.loadState==='loaded' && window.__atlasPending===0")
    page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')


def exercise(page, output, width):
    try:
        settle(page)
        atlas=page.get_by_test_id('carrier-atlas')
        generation=int(atlas.get_attribute('data-load-generation'))
        before=page.evaluate('window.__atlasRequests.length')
        page.get_by_role('button',name='Load carrier map',exact=True).click()
        page.wait_for_function("(old)=>{const node=document.querySelector('[data-testid=carrier-atlas]');return Number(node?.dataset.loadGeneration)>old && node?.dataset.loadState==='loaded' && window.__atlasPending===0;}",arg=generation)
        settle(page)
        assert page.evaluate('window.__atlasRequests.length')>before
        assert '#/atlas?dot=3938496' in page.url
        before=page.evaluate('window.__atlasRequests.length')
        page.get_by_role('textbox',name='USDOT number',exact=True).fill('-1')
        page.get_by_role('button',name='Load carrier map',exact=True).click()
        page.get_by_text('Enter a valid positive USDOT number (up to ten digits).',exact=True).wait_for()
        page.wait_for_function("document.querySelector('[data-testid=carrier-atlas]')?.dataset.loadState==='invalid'")
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert page.locator('.t3-atlas-map-panel').count()==0
        assert page.evaluate('window.__atlasRequests.length')==before

        # Hold a valid refresh, then invalidate through the real form submit handler.
        # A form can be submitted programmatically even while its button is disabled.
        page.get_by_role('textbox',name='USDOT number',exact=True).fill('3938496')
        page.evaluate('window.__atlasHold=true')
        page.get_by_role('button',name='Load carrier map',exact=True).click()
        page.wait_for_function("window.__atlasReleaseQueue.length>0 && document.querySelector('[data-testid=carrier-atlas]')?.dataset.loadState==='loading'")
        page.get_by_role('textbox',name='USDOT number',exact=True).fill('-1')
        page.locator('form.t3-atlas-search').evaluate('(form)=>form.requestSubmit()')
        page.get_by_text('Enter a valid positive USDOT number (up to ten digits).',exact=True).wait_for()
        page.evaluate('window.__releaseAtlasReplies()')
        page.wait_for_function('window.__atlasPending===0')
        page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
        assert atlas.get_attribute('data-load-state')=='invalid'
        assert page.locator('.t3-atlas-map-panel').count()==0
        assert all('-1' not in url.split('$where=')[-1] for url in page.evaluate('window.__atlasRequests'))
        # Recover using ordinary valid input, retaining the same shareable carrier URL.
        page.get_by_role('textbox',name='USDOT number',exact=True).fill('3938496')
        page.get_by_role('button',name='Load carrier map',exact=True).click()
        settle(page)
        page.locator('.t3-atlas-map-panel').wait_for()
        page.screenshot(path=str(output/f'atlas-lifecycle-recovered-{width}.png'),animations='disabled')
    except Exception as error:
        diagnostic={'error':str(error),'viewport':width,'url':page.url,
                    'state':page.get_by_test_id('carrier-atlas').get_attribute('data-load-state'),
                    'requests':page.evaluate('window.__atlasRequests'),
                    'pending':page.evaluate('window.__atlasPending')}
        (output/f'atlas-lifecycle-failure-{width}.json').write_text(json.dumps(diagnostic,indent=2))
        (output/f'atlas-lifecycle-failure-{width}.html').write_text(page.content())
        page.screenshot(path=str(output/f'atlas-lifecycle-failure-{width}.png'),animations='disabled')
        raise
