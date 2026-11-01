const assert = require('node:assert/strict');

(async () => {
  const {renderMessage} = await import('../src/ai4s_demo/web/message.js');
  assert.equal(
    renderMessage('请指定参数：\n- 骨架：length / num_designs\n- 序列：sampling_temp\n\n确认后保存。',
      ['length', 'num_designs', 'sampling_temp']),
    '<p>请指定参数：</p><ul><li><span class="message-item-label">骨架：</span><span class="message-item-detail"><code>length</code> / <code>num_designs</code></span></li><li><span class="message-item-label">序列：</span><span class="message-item-detail"><code>sampling_temp</code></span></li></ul><p>确认后保存。</p>',
  );
  assert.equal(renderMessage('**步骤**\n\n1. 选择 `seed`\n2. 保存'),
    '<p><strong>步骤</strong></p><ol><li>选择 <code>seed</code></li><li>保存</li></ol>');
  assert.equal(renderMessage('```python\nprint("<test>")\n```'),
    '<pre><code>print(&quot;&lt;test&gt;&quot;)</code></pre>');
  const unsafe = renderMessage('<img src=x onerror=alert(1)>\n\n**<script>alert(1)</script>**\n\n[x](javascript:alert(1))');
  assert.ok(unsafe.includes('&lt;img'));
  assert.ok(unsafe.includes('&lt;script&gt;'));
  assert.ok(!/<(?:img|script|a)\b/.test(unsafe));
  console.log('PASS chat paragraphs, lists, parameter formatting, code blocks, and HTML escaping');
})().catch(error => { console.error(error); process.exitCode = 1; });
