const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const markdownit = require('../dashboard/static/vendor/markdown-it.min.js');
const katex = require('../dashboard/static/vendor/katex/katex.min.js');
const source = fs.readFileSync(path.join(__dirname, '../dashboard/static/app.js'), 'utf8');
const context = {md: markdownit({html: false, linkify: true, breaks: false})};
// Exercise the production helpers without booting the dashboard's router or API.
vm.runInNewContext(source.slice(source.indexOf('  function protectMath('), source.indexOf('  // [[目标')), context);

let checks = 0;
function check(label, input, expected, quoteCount = 0) {
  const {src, store} = context.protectMath(input);
  assert.deepEqual(Array.from(store), expected, label);
  const html = context.restoreMath(context.md.render(src), store);
  assert.equal((html.match(/<blockquote>/g) || []).length, quoteCount, label + ': quote framing');
  for (const math of store) {
    const display = math.startsWith('$$') || math.startsWith('\\[');
    const tex = math.slice(display || math.startsWith('\\(') ? 2 : 1, display || math.startsWith('\\(') ? -2 : -1);
    assert.doesNotThrow(() => katex.renderToString(tex, {displayMode: display, throwOnError:true}), label + ': valid TeX');
  }
  checks++;
}

check('reported energy with quote markers on continuation lines', String.raw`> **Toy model**
>
> $$E(\{p_i\})=\sum_{i=1}^N\frac{p_i^2}{2m_b}
> -\frac{\gamma}{2Nm_b}\sum_{i<j}(p_i-p_j)^2,
> \qquad 0\le\gamma<1.$$`, [String.raw`$$E(\{p_i\})=\sum_{i=1}^N\frac{p_i^2}{2m_b}
-\frac{\gamma}{2Nm_b}\sum_{i<j}(p_i-p_j)^2,
\qquad 0\le\gamma<1.$$`], 1);
check('aligned derivation', String.raw`> $$\begin{aligned}
> E&=a+b\\
> &=c.
> \end{aligned}$$`, [String.raw`$$\begin{aligned}
E&=a+b\\
&=c.
\end{aligned}$$`], 1);
check('real comparisons survive inside a quote', '> $$x > 0,\n> y > x,\n> > -1$$', ['$$x > 0,\ny > x,\n> -1$$'], 1);
check('real leading comparison outside a quote', '$$x\n> y$$', ['$$x\n> y$$']);
check('nested quotes and extra mathematical greater-than', '> > $$x > 0\n> > > -1$$', ['$$x > 0\n> -1$$'], 2);
check('compact nested quote markers', '>> $$x\n>> +y$$', ['$$x\n+y$$'], 2);
check('quote within a list item', '- > $$x\n  > +y$$', ['$$x\n+y$$'], 1);
check('list within a quote', '> - $$x\n>   +y$$', ['$$x\n  +y$$'], 1);
check('lazy continuation with no quote marker', '> $$x\n+y$$', ['$$x\n+y$$'], 1);
check('blank quoted line', '> $$x\n>\n> +y$$', ['$$x\n\n+y$$'], 1);
check('bracket delimiters', String.raw`> \[x
> +y\]`, [String.raw`\[x
+y\]`], 1);
check('parenthesis delimiters', String.raw`> \(x
> +y\)`, [String.raw`\(x
+y\)`], 1);
check('different delimiters keep correct source offsets', String.raw`$$a
+b$$

> \[c
> +d\]`, [String.raw`$$a
+b$$`, String.raw`\[c
+d\]`], 1);
check('inline comparisons and escaped dollars', String.raw`> $x>0$, $y<x$; \$5.`, ['$x>0$', '$y<x$'], 1);
check('single-line quoted display', '> $$x > 0$$', ['$$x > 0$$'], 1);

// Code examples must retain their literal quote markers. They are not rendered as math.
for (const code of ['```md\n> $$x\n> +y$$\n```', '> ```tex\n> $$x\n> +y$$\n> ```', '    > $$x\n    > +y$$']) {
  const {store} = context.protectMath(code);
  assert.match(store[0], /\n\s*> \+y/, 'code examples retain literal markers');
  checks++;
}
console.log(`Math rendering: ${checks} regression cases passed.`);
