const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const markdownit = require('../dashboard/static/vendor/markdown-it.min.js');
const source = fs.readFileSync(path.join(__dirname, '../dashboard/static/reading-mode.js'), 'utf8');
async function readingMode(lang) {
  const catalog = {enabled:true, documents:{'labs/test/report.md':{
    title:'Test', state:'current', body:'## Current answer (preliminary)\n\nPreliminary evidence.\n\n## Evidence\n\n![L3 result](fig/main.png)\n\n![L6 result for $J \\in [3,4]$](fig/L6/main.png)'
  },'labs/test/DATA.md':{title:'',body:'# Data inventory',state:'current'}}, captions:{'labs/test/fig/multiL/main.png':{text:'Combined sizes', state:'current'}}};
  const document = {body:{classList:{toggle(){}},querySelectorAll(){return []}}, documentElement:{}, querySelector(){return null}, querySelectorAll(){return []}, createTreeWalker(){return {nextNode(){return false}}}};
  const ctx = {window:{markdownit}, document, location:{search:'?lang='+lang, href:'http://test/?lang='+lang},
    URL, URLSearchParams, NodeFilter:{SHOW_TEXT:4}, MutationObserver:class {observe(){}}, queueMicrotask,
    fetch:async()=>({ok:true,json:async()=>catalog})};
  vm.runInNewContext(source,ctx);
  await ctx.window.ReadingMode.refresh();
  return ctx.window.ReadingMode;
}
(async()=>{
  const original = {id:'test', path:'labs/test/brief.md', title:'中文', report:{path:'labs/test/report.md',body:'中文报告'}, images:[
    {path:'labs/test/fig/main.png',caption:'L3 中文'}, {path:'labs/test/fig/L6/main.png',caption:'L6 中文'},
    {path:'labs/test/fig/multiL/main.png',caption:'多尺寸'}, {path:'labs/test/fig/L9/main.png',caption:''}
  ]};
  const en=await readingMode('en');
  assert.equal(en.t('机器：pod（studio 只做后处理与画图）'),'Machine: pod (postprocessing and plotting on studio)');
  const result=en.overlay('/api/labs/test',original);
  assert.equal(result.answer,'Preliminary evidence.');
  assert.equal(result.images[0].caption,'L3 result');
  assert.equal(result.images[1].caption,'L6 result for $J \\in [3,4]$');
  assert.equal(result.images[2].caption,'Combined sizes');
  assert.notEqual(result.images[3].caption,'L3 result');
  assert.equal(original.images[0].caption,'L3 中文');
  assert.equal(en.overlay('/api/raw?path=labs/test/DATA.md',{path:'labs/test/DATA.md',title:'DATA.md',body:'数据'}).title,'DATA.md');
  const zh=await readingMode('zh');
  assert.equal(zh.t('机器：pod（studio 只做后处理与画图）'),'机器：pod（studio 只做后处理与画图）');
  assert.equal(zh.overlay('/api/labs/test',original),original);
  console.log('Reading mode: qualified summary, full-path captions, and Chinese preservation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
