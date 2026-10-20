const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const {chromium} = require('playwright');

(async () => {
  const root = path.resolve(process.argv[2]);
  const browser = await chromium.launch({
    channel: process.env.RALLYCUT_BROWSER_CHANNEL || (process.platform === 'win32' ? 'msedge' : undefined),
    headless: true, args: ['--allow-file-access-from-files']
  });
  const page = await browser.newPage({viewport: {width:1280,height:1000}});
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const checks = [];
  try {
    await page.goto(pathToFileURL(path.join(root,'review.html')).href);
    const caseCount = await page.locator('#case option').count();
    if (!caseCount) throw new Error('No comparison videos');
    for (let i=0;i<caseCount;i++) {
      await page.locator('#case').selectOption(String(i));
      await page.waitForFunction(() => {
        const v=document.querySelector('video');
        return v.readyState>=2 && v.videoWidth>0;
      });
      const info = await page.evaluate(async () => {
        const v=document.querySelector('video');
        await new Promise(resolve => {
          v.addEventListener('seeked',resolve,{once:true});
          v.currentTime=Math.min(12,v.duration/2);
        });
        await v.play();
        return {duration:v.duration,width:v.videoWidth,src:v.currentSrc};
      });
      await page.waitForTimeout(500);
      await page.evaluate(()=>document.querySelector('video').pause());
      const expected = await page.evaluate(index=>cases[index], i);
      if(Math.abs(info.duration-expected.duration)>.3) throw new Error('Wrong video duration');
      if(!info.src.endsWith(expected.src.split('/').pop())) throw new Error('Wrong video source');
      checks.push({case:i,...info});
    }
    await page.locator('#case').selectOption('0');
    await page.waitForFunction(()=>document.querySelector('video').readyState>=2);
    await page.screenshot({path:path.join(root,'review_desktop.png'),fullPage:true});
    const expectedNext = await page.evaluate(() => {
      const d=cases[0], t=document.querySelector('video').currentTime;
      const events=[...d.teacher,...d.fast].flatMap(r=>[r.start_seconds,r.end_seconds]).sort((a,b)=>a-b);
      const next=events.find(s=>s>t+.3&&
        ((active(d.teacher,s+.08)<0)!==(active(d.fast,s+.08)<0)||
         (active(d.teacher,s-.08)<0)!==(active(d.fast,s-.08)<0)));
      return next===undefined?t:Math.max(0,next-.1);
    });
    await page.locator('#next').click();
    const nextTime=await page.evaluate(()=>document.querySelector('video').currentTime);
    if(Math.abs(nextTime-expectedNext)>.05) throw new Error('Difference navigation failed');
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:path.join(root,'review_mobile.png'),fullPage:true});
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    if(overflow) throw new Error('Mobile horizontal overflow');
    if(errors.length) throw new Error(errors.join('\n'));
    fs.writeFileSync(path.join(root,'review_qa.json'),JSON.stringify({checks,errors,nextTime,overflow},null,2));
    console.log(JSON.stringify({videos:checks.length,errors,nextTime,overflow}));
  } finally {
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exit(1)});
