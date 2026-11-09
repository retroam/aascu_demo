import test from 'node:test';
import assert from 'node:assert/strict';
import { renderChatMarkdown as render, renderChatTables, renderChatCharts } from './chat_charts.js';

test('renders common PDP answer formatting', () => {
  const html = render('# Schema\n\n**Cohort** and *course* fields use `student_id`.\n\n- Retention\n- Persistence\n\n1. Select a cohort\n2. Compare outcomes\n\n> Synthetic records');
  for (const part of ['<h3>Schema</h3>', '<strong>Cohort</strong>', '<em>course</em>', '<code>student_id</code>', '<ul>', '<ol>', '<blockquote>']) assert.ok(html.includes(part), part);
});
test('renders tables and fenced SQL without interpreting code', () => {
  const html = render('| Field | Meaning |\n| --- | --- |\n| `retention` | **Own institution** |\n\n```sql\nSELECT * FROM cohort_records;\n<img src=x onerror=alert(1)>\n```');
  assert.ok(html.includes('<th scope="col">Field</th>'));
  assert.ok(html.includes('<td><code>retention</code></td>'));
  assert.ok(html.includes('<pre tabindex="0"><code>SELECT *'));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!html.includes('<img'));
});
test('escapes model HTML and rejects executable link protocols', () => {
  const html = render('<script>alert(1)</script>\n[x](javascript:alert) [y](data:text/html,hi) [docs](https://example.com/?a=1&b=2)');
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('href="javascript:'));
  assert.ok(!html.includes('href="data:'));
  assert.ok(html.includes('href="https://example.com/?a=1&amp;b=2"'));
  assert.ok(html.includes('rel="noopener noreferrer"'));
});
test('handles incomplete Markdown and absent values', () => {
  assert.equal(render(null), '');
  assert.equal(render('```sql\nSELECT 1'), '<pre tabindex="0"><code>SELECT 1</code></pre>');
  assert.equal(render('A **partial'), '<p>A **partial</p>');
  assert.equal(render('`**literal**`'), '<p><code>**literal**</code></p>');
});


test('multiple sample tables coexist with charts and Markdown', () => {
  const tables = ['cohort_records', 'course_records', 'attribute_records'].map(title => ({title, columns:['student_id'], rows:[{student_id:'<synthetic>'}]}));
  const html = render('**Examples**') + renderChatTables(tables) + renderChatCharts([{type:'bar',title:'Retention',caption:'Computed',unit:'percent',points:[{label:'All',value:50,numerator:null,denominator:null,status:'ok'}]}]);
  assert.ok(html.includes('<strong>Examples</strong>'));
  assert.ok(html.includes('<h3>cohort_records</h3>'));
  assert.ok(html.includes('<h3>course_records</h3>'));
  assert.ok(html.includes('<h3>attribute_records</h3>'));
  assert.match(renderChatTables([...tables, tables[0]]), /unavailable/);
  assert.ok(html.includes('&lt;synthetic&gt;'));
  assert.ok(html.includes('<svg'));
  assert.ok(html.includes('evidence-bar'));
});
