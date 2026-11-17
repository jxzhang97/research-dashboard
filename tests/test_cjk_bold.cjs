// 中文标点旁的加粗（app.js fixCjkBold 用的 CJK_BOLD）：markdown 没认出来的 **…** 补成加粗，x**2 这类不动
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const src = fs.readFileSync(path.join(__dirname, '../dashboard/static/app.js'), 'utf8');
const line = src.split('\n').find((l) => l.includes('const CJK_BOLD ='));
const CJK_BOLD = eval(line.slice(line.indexOf('=') + 1).trim().replace(/;$/, ''));
const parts = (t) => t.split(new RegExp(CJK_BOLD.source, 'g'));
assert.deepEqual(parts('这里的**随机试验（random experiment）**就是抽卡'), ['这里的', '随机试验（random experiment）', '就是抽卡']);
assert.deepEqual(parts('**事件（event）**是其中一批'), ['', '事件（event）', '是其中一批']);
assert.deepEqual(parts('有效质量 **$m^*$ 变大**，所以'), ['有效质量 ', '$m^*$ 变大', '，所以']);
assert.deepEqual(parts('计算 x**2 和 y**3'), ['计算 x**2 和 y**3']);
assert.deepEqual(parts('两个星号 ** 中间有空格 ** 不算'), ['两个星号 ** 中间有空格 ** 不算']);
console.log('cjk bold: 5 checks passed');
