import {query, readInput, encodeInput} from './api.js';
import {el, evidence, table} from './table.js';

const byId = id => document.getElementById(id);
const settings = JSON.parse(byId('settings').textContent);
const links = [...document.querySelectorAll('[data-module]')];
const body = byId('grid-data');
const alert = byId('notice');
const live = byId('state');
const action = document.querySelector('#source button[type=submit]');
const topExport = byId('export');
let selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
let result = null;
let inputs = {};
let reviewVersion = 0;
let renderEpoch = 0;
let activeView = null;
const filter = byId('filter');
const differences = byId('differences');

function filterTable() {
  if (!activeView) return;
  const {columns, rows, stage} = activeView;
  const query = filter.value.trim().toLocaleLowerCase();
  const selected = rows.filter(row => {
    if (stage === 'reconcile' && differences.checked && row.code === 'MATCH') return false;
    return !query || [row.key,row.id,row.line,row.code,settings.reasons[row.code],row.detail,row.note,row.kind]
      .some(value => String(value ?? '').toLocaleLowerCase().includes(query));
  });
  byId('shown').textContent = `${selected.length} / ${rows.length}`;
  table(body, columns, selected);
}
filter.addEventListener('input', filterTable);
differences.addEventListener('change', filterTable);
const uploaded = new Map();

function notice(message, error = false) {
  alert.value = message;
  alert.classList.toggle('problem', error);
}

function tag(code) {
  return el('span', settings.reasons[code] || code, code === 'MATCH' ? 'state' : 'state problem');
}


function showEvidence(row) {
  const panel = byId('evidence-panel');
  const record = byId('evidence-key');
  const details = byId('signal');
  if (!row) {
    record.textContent = '';
    details.replaceChildren(el('p', '本批没有可采信记录', 'empty'));
    return;
  }
  record.textContent = row.key;
  const content = el('ol', undefined, panel.dataset.instrument);
  for (const item of row.proof) {
    const line = el('li');
    line.append(el('span', item.metric));
    line.append(el('strong', item.unit ? `${item.value} ${item.unit}` : item.value, 'measure'));
    content.append(line);
  }
  details.replaceChildren(content);
}

function inspect(row) {
  const button = el('button', '查看依据', 'btn');
  button.type = 'button';
  button.addEventListener('click', () => showEvidence(row));
  const raw = evidence('原始字段', row.raw);
  const cell = el('div');
  cell.append(button, raw);
  return cell;
}

function setRun(report) {
  result = report;
  byId('created').textContent = `${report.manifest.created.slice(0, 19).replace('T', ' ')} UTC`;
  showEvidence(report.accepted[0]);
  const id = result.manifest.run_id;
  byId('run-id').textContent = id.slice(0, 9);
  byId('run-id').title = id;
  topExport.hidden = false;
  topExport.href = `/api/export/${id}`;
  const values = {...result.counts, delta: result.book.delta, mismatched: result.book.mismatched};
  for (const cell of document.querySelectorAll('[data-count]')) cell.textContent = values[cell.dataset.count];
  live.textContent = `批次 ${id.slice(0, 9)} · ${result.balanced ? '记录已对齐' : '记录数不符'}`;
}

const TAIL_STATES = {'在库': ['在库可领', 'state'], '预占': ['预占留批', 'state hold'],
                     '借出': ['借出未还', 'state problem'], '已领用': ['已领用', '']};

function tailActions(row) {
  const wrap = el('div', undefined, 'actions');
  const run = async (button, task) => {
    button.disabled = true;
    try { notice(await task()); await render(); }
    catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
  };
  const button = (label, task) => {
    const control = el('button', label, 'btn');
    control.type = 'button';
    control.addEventListener('click', () => run(control, task));
    return control;
  };
  const field = (placeholder, value = '') => {
    const input = el('input');
    input.placeholder = placeholder;
    input.value = value;
    input.maxLength = 64;
    return input;
  };
  if (row.state === '在库' || row.state === '预占') {
    const claimId = field('领料单号', `L-${row.id}`);
    wrap.append(claimId, button('领用', async () => {
      const request = claimId.value.trim();
      if (!request) throw Error('填写领料单号');
      const outcome = await query('/api/claims', {request, tail: row.id, batch: row.home});
      return outcome.deduplicated ? `领料单 ${request} 已入账，未重复扣减`
                                  : `已领用 ${row.id}，扣减 ${outcome.claim.length} 毫米`;
    }));
  }
  if (row.state === '在库') {
    const borrower = field('急单号');
    wrap.append(button('预占', async () => { await query(`/api/tails/${row.id}/reserve`, {}); return `已预占留给 ${row.home}`; }),
                borrower, button('借出', async () => {
      const who = borrower.value.trim();
      if (!who) throw Error('填写急单号');
      await query(`/api/tails/${row.id}/lend`, {borrower: who});
      return `已借给 ${who}`;
    }));
  } else if (row.state === '预占') {
    wrap.append(button('取消预占', async () => { await query(`/api/tails/${row.id}/unreserve`, {}); return '已取消预占，回到在库'; }));
  } else if (row.state === '借出') {
    wrap.append(button('归还', async () => {
      const outcome = await query(`/api/loans/${row.loan}/return`, {});
      return outcome.restored ? '已归还回库，恢复原批可领' : '该借出单已归还过，未重复恢复';
    }));
  }
  return wrap;
}

function paintTails(view) {
  const root = el('div', undefined, 'tails');
  const form = el('form', undefined, 'ledger-form');
  const inputs = {};
  for (const [name, label] of [['tail', '料尾编号'], ['length', '长度毫米'], ['home', '原签批批次']]) {
    const input = el('input');
    input.required = true;
    input.maxLength = 40;
    const item = el('label');
    item.append(label, input);
    inputs[name] = input;
    form.append(item);
  }
  const submit = el('button', '登记退料', 'btn btn--primary');
  submit.type = 'submit';
  form.append(submit);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const length = Number(inputs.length.value);
    if (!Number.isInteger(length) || length <= 0) { notice('长度须为正整数毫米', true); return; }
    submit.disabled = true;
    try {
      const outcome = await query('/api/tails', {tail: inputs.tail.value.trim(), length, home: inputs.home.value.trim()});
      notice(outcome.deduplicated ? `料尾 ${outcome.id} 已登记过，未重复入账` : `料尾 ${outcome.id} 已登记在库`);
      form.reset();
      await render();
    } catch (error) { notice(error.message, true); }
    finally { submit.disabled = false; }
  });
  const batches = el('div');
  table(batches, [['原签批批次', 'batch'], [`还能领 · ${settings.unit}`, 'claimable', 'num'], ['可领截数', 'pieces', 'num'],
                  ['其中预占', 'reserved', 'num'], ['在库未占', 'on_hand', 'num'],
                  ['借出未还', 'lent', 'num'], ['已领用', 'claimed', 'num']], view.batches);
  const list = el('div');
  table(list, [['料尾', 'id'], [`长度 · ${settings.unit}`, 'length', 'num'], ['原批次', 'home'],
               ['状态', row => { const [label, tone] = TAIL_STATES[row.state]; return el('span', label, tone || undefined); }],
               ['持有 / 归还去向', row => {
                 const cell = el('div');
                 const where = {'在库': '库房在库', '预占': `留给 ${row.holder}`, '借出': `借给 ${row.holder}`, '已领用': `${row.holder} 已领`};
                 cell.append(el('span', where[row.state]));
                 if (row.loans.length) {
                   cell.append(evidence('借还去向', row.loans.map(loan =>
                     `借出单#${loan.id} → ${loan.borrower} · ${loan.lent.slice(0, 10)} 借` +
                     (loan.returned ? ` · ${loan.returned.slice(0, 10)} 还回在库` : ' · 未还'))));
                 }
                 return cell;
               }],
               ['更新 UTC', row => row.updated.slice(0, 19).replace('T', ' '), 'num'],
               ['操作', tailActions]], view.tails);
  root.append(form, el('h3', '原签批批次可领汇总'), batches, el('h3', '料尾明细'), list);
  body.replaceChildren(root);
  live.textContent = `料尾台账 · ${view.tails.length} 截登记`;
}

async function render() {
  const ticket = ++renderEpoch;
  const stage = selected;
  byId('phase').textContent = settings.tabs[stage];
  byId('review').hidden = true;
  for (const link of links) {
    if (link.dataset.module === stage) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  if (stage === 'tails') {
    byId('tools').hidden = true;
    try {
      const view = await query('/api/tails');
      if (ticket === renderEpoch) paintTails(view);
    } catch (error) {
      if (ticket === renderEpoch) notice(error.message, true);
    }
    return;
  }
  if (!result) return;
  const id = result.manifest.run_id;
  const raw = row => evidence('来源字段', row.raw);
  const key = [settings.key, 'key'];
  const line = ['行号', 'line', 'num'];
  try {
    let view, rows;
    if (stage === 'domain') {
      view = [key, [`新棒长度 · ${settings.unit}`, 'amount', 'num'], line, ['明细依据', inspect]];
      rows = result.accepted;
    } else if (stage === 'quality') {
      view = [key, line, ['判定', row => tag(row.code)], ['说明', 'detail'], ['字段', raw]];
      rows = [...result.quarantine, ...result.suppressed].sort((a,b) => a.line-b.line);
    } else if (stage === 'reconcile') {
      view = [key, ['实际', 'amount', 'num'], ['外部账', 'reference', 'num'], ['差值', 'delta', 'num'], ['外部行', 'book_line', 'num'], ['结论', row => tag(row.code)]];
      rows = [...result.book.rows].sort((a,b) => Number(a.code === 'MATCH') - Number(b.code === 'MATCH'));
    } else if (stage === 'intake') {
      const intake = await query('/api/intake', inputs);
      view = [line, ['分类', 'kind'], ['字段', raw]];
      rows = [...intake.rows.map(row => ({...row,kind:'完整记录'})), ...intake.rejected.map(row => ({...row,kind:'坏行'})),
              ...intake.blank_lines.map(line => ({line,kind:'空白行',raw:[]})),
              ...intake.header_lines.map(line => ({line,kind:'重复表头',raw:[]}))].sort((a,b) => a.line-b.line);
    } else if (stage === 'contract') {
      const contract = await query('/api/contract', inputs);
      view = [key, line, ['修订', 'revision', 'num'], ['来源时刻 UTC', 'time'], ['字段', row => evidence('归一值', Object.entries(row.fields).map(([k,v]) => `${k} · ${v}`))]];
      rows = contract.accepted;
    } else if (stage === 'runs') {
      const runs = await query('/api/runs');
      view = [['指纹','id'], ['创建 UTC','created'], ['操作', row => {
        const current = row.id === id;
        const button = el('button',current ? '复算当前批' : '打开此批','btn');
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            if (current) {
              setRun(await query(`/api/runs/${id}/replay`, {}));
              notice('复算已核对');
            } else {
              const [past, original] = await Promise.all([
                query(`/api/runs/${row.id}`), query(`/api/runs/${row.id}/source`),
              ]);
              inputs = original;
              setRun(past);
              notice('已打开历史批次');
              await render();
            }
          }
          catch (error) { notice(error.message, true); }
          finally { button.disabled = false; }
        });
        return button;
      }]];
      rows = runs;
    } else {
      const timeline = await query(`/api/review/${id}`);
      view = [['版本','version','num'], ['结论','decision'], ['复核意见','note'], ['登记 UTC','changed']];
      rows = timeline;
      if (ticket === renderEpoch) {
        reviewVersion = timeline[0]?.version || 0;
        byId('review').hidden = false;
      }
    }
    if (ticket === renderEpoch) {
      if (activeView?.stage !== stage) filter.value = '';
      activeView = {stage, columns: view, rows};
      byId('tools').hidden = false;
      byId('only-differences').hidden = stage !== 'reconcile';
      filterTable();
    }
  } catch (error) {
    if (ticket === renderEpoch) notice(error.message, true);
  }
}

window.addEventListener('hashchange', () => {
  selected = Object.hasOwn(settings.tabs, location.hash.slice(1)) ? location.hash.slice(1) : 'domain';
  render();
});
byId('sample').addEventListener('click', async () => {
  const paths = ['shift', 'external'];
  try {
    const responses = await Promise.all(paths.map(name => fetch(`/api/samples/${name}`)));
    if (responses.some(item => !item.ok)) throw Error('样例暂时不可用');
    const files = await Promise.all(responses.map(item => item.arrayBuffer()));
    for (const [index,name] of ['source','book'].entries()) {
      const decoded = new TextDecoder('utf-8').decode(files[index]);
      byId(`${name}-csv`).value = decoded;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes:files[index]});
    }
    byId('source-file').value = '';
    byId('book-file').value = '';
    document.querySelector('#source details').open = true;
    notice('样例已载入');
  } catch (error) { notice(error.message, true); }
});
for (const name of ['source','book']) {
  byId(`${name}-file`).addEventListener('change', async event => {
    const file = event.target.files[0];
    if (!file) return;
    action.disabled = true;
    try {
      const [text,bytes] = await readInput(file);
      byId(`${name}-csv`).value = text;
      uploaded.set(name,{text:byId(`${name}-csv`).value,bytes});
      notice(`已读取 ${file.name}`);
    } catch (error) {
      event.target.value = '';
      notice(error.message, true);
    } finally { action.disabled = false; }
  });
}
byId('source').addEventListener('submit', async event => {
  event.preventDefault();
  const candidate = {};
  for (const [control,name] of [['source','data'],['book','book']]) {
    const text = byId(`${control}-csv`).value;
    const original = uploaded.get(control);
    if (original && text === original.text) candidate[`${name}_base64`] = encodeInput(original.bytes);
    else if (text.length || original) candidate[name] = text;
  }
  action.disabled = true;
  ++renderEpoch;
  notice('计算中');
  try {
    const report = await query('/api/runs', candidate);
    inputs = candidate;
    setRun(report);
    notice('批次已计算');
    await render();
  } catch (error) { notice(error.message, true); }
  finally { action.disabled = false; }
});
byId('review').addEventListener('submit', async event => {
  event.preventDefault();
  const id = result.manifest.run_id;
  const note = byId('review-note');
  try {
    await query(`/api/review/${id}`, {version: reviewVersion, decision: byId('decision').value, note: note.value});
    notice('复核已登记');
    note.value = '';
    await render();
  } catch (error) {
    notice(error.message, true);
    if (error.status === 409) await render();
  }
});
render();
