// Тесты lead-worker: node --test api/lead-worker/test
// fetch к Notion/Telegram подменяется моком; сеть не используется.
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import worker, { _resetCache, chunkText, toProperty, buildProperties, LABELS, telegramText, DEFAULT_SCHEMA } from '../worker.js';

const ORIGIN = 'https://re6al.github.io';
const DB_ID = '0123456789abcdef0123456789abcdef';
const ENV = {
  ALLOWED_ORIGINS: 'https://re6al.github.io,http://localhost:8768',
  NOTION_TOKEN: 'ntn_test_secret_value',
  NOTION_LEADS_DB_ID: DB_ID,
};

// Схема «Website Leads» как в docs/NOTION_SETUP.md
const SCHEMA = {
  Name: 'title', Form: 'select', Status: 'status', Language: 'select', 'Preferred Language': 'select',
  'Contact Method': 'select', Email: 'email', Phone: 'phone_number', Telegram: 'rich_text',
  Company: 'rich_text', Position: 'rich_text', Website: 'url', Jurisdiction: 'rich_text',
  'Investment Type': 'select', Budget: 'select', 'NDA Requested': 'checkbox', 'Property Kind': 'select',
  'Owner Type': 'select', 'List Nepokretnosti': 'rich_text', KO: 'rich_text', PD: 'rich_text',
  'Company Reg No': 'rich_text', 'Asking Price': 'number', Interest: 'select', 'Rental Term': 'select',
  'Move-in': 'date', 'Monthly Budget': 'number', Bedrooms: 'number', Occupants: 'rich_text',
  Pets: 'rich_text', 'Object ID': 'rich_text', 'Listing URL': 'url', Message: 'rich_text',
  Transcript: 'rich_text', Page: 'url', UTM: 'rich_text', Consent: 'checkbox',
  'Consent Version': 'rich_text', Received: 'created_time',
};

function schemaResponse(types = SCHEMA) {
  const properties = {};
  for (const [name, type] of Object.entries(types)) {
    properties[name] = { id: name, name, type, [type]: type === 'status' ? { options: [{ name: 'New' }, { name: 'Spam' }] } : {} };
  }
  return { object: 'database', id: DB_ID, properties };
}

let calls;
let responder;
const realFetch = globalThis.fetch;

beforeEach(() => {
  _resetCache();
  calls = [];
  responder = defaultResponder();
  globalThis.fetch = async (url, init = {}) => {
    const call = { url: String(url), method: init.method || 'GET', headers: init.headers || {}, body: init.body ? JSON.parse(init.body) : null };
    calls.push(call);
    return responder(call);
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function defaultResponder(types = SCHEMA) {
  return (call) => {
    if (call.url.includes('/v1/databases/')) return jsonResponse(200, schemaResponse(types));
    if (call.url.endsWith('/v1/pages')) return jsonResponse(200, { object: 'page', id: 'p1', url: 'https://www.notion.so/p1' });
    if (call.url.includes('api.telegram.org')) return jsonResponse(200, { ok: true });
    return jsonResponse(404, {});
  };
}

function payload(over = {}, fields = {}) {
  return {
    form: 'investor',
    lang: 'en',
    page: 'https://re6al.github.io/gurevic-real-estate/en/invest/',
    ts: '2026-10-13T10:00:00Z',
    elapsed_ms: 12000,
    hp: '',
    consent: true,
    consent_version: '2026-10',
    utm: { source: 'google', medium: 'cpc', campaign: 'invest' },
    fields: {
      name: 'Jane Investor',
      email: 'jane@fund.example',
      contact_method: 'email',
      investment_type: 'hotel',
      budget: '2m_10m',
      nda: true,
      message: 'Looking for a boutique hotel.',
      ...fields,
    },
    ...over,
  };
}

function request(body, { method = 'POST', origin = ORIGIN, ctype = 'text/plain;charset=UTF-8', raw } = {}) {
  const headers = {};
  if (origin) headers.Origin = origin;
  if (ctype) headers['Content-Type'] = ctype;
  const init = { method, headers };
  if (method !== 'GET' && method !== 'OPTIONS') init.body = raw !== undefined ? raw : JSON.stringify(body);
  return new Request('https://leads.example.workers.dev/', init);
}

async function send(body, opts, env = ENV, ctx) {
  const res = await worker.fetch(request(body, opts), env, ctx);
  return { res, data: res.status === 204 ? null : await res.json() };
}

const notionPageCalls = () => calls.filter((c) => c.url.endsWith('/v1/pages'));
const createdProps = () => notionPageCalls().at(-1).body.properties;
const plain = (prop) => prop.rich_text.map((t) => t.text.content).join('');

// ---------- CORS ----------

test('OPTIONS preflight from an allowed origin', async () => {
  const res = await worker.fetch(request(null, { method: 'OPTIONS' }), ENV);
  assert.equal(res.status, 204);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), ORIGIN);
  assert.match(res.headers.get('Access-Control-Allow-Methods'), /POST/);
  assert.equal(res.headers.get('Vary'), 'Origin');
});

test('localhost origin is allowed', async () => {
  const { res } = await send(payload(), { origin: 'http://localhost:8768' });
  assert.equal(res.status, 200);
  assert.equal(res.headers.get('Access-Control-Allow-Origin'), 'http://localhost:8768');
});

test('foreign or missing origin is rejected without touching Notion', async () => {
  for (const origin of ['https://evil.example', null]) {
    const { res, data } = await send(payload(), { origin });
    assert.equal(res.status, 403);
    assert.deepEqual(data, { ok: false, error: 'origin_not_allowed' });
    assert.equal(res.headers.get('Access-Control-Allow-Origin'), null);
  }
  assert.equal(calls.length, 0);
});

test('only POST is accepted', async () => {
  const { res, data } = await send(null, { method: 'GET' });
  assert.equal(res.status, 405);
  assert.equal(data.error, 'method_not_allowed');
});

test('unsupported content type → 415; application/json is accepted', async () => {
  let r = await send(payload(), { ctype: 'application/x-www-form-urlencoded' });
  assert.equal(r.res.status, 415);
  r = await send(payload(), { ctype: 'application/json' });
  assert.equal(r.res.status, 200);
});

// ---------- защита от спама и валидация ----------

test('honeypot: pretends success, writes nothing', async () => {
  const { res, data } = await send(payload({ hp: 'http://spam' }));
  assert.equal(res.status, 200);
  assert.deepEqual(data, { ok: true });
  assert.equal(calls.length, 0);
});

test('too fast submission is rejected', async () => {
  const { res, data } = await send(payload({ elapsed_ms: 900 }));
  assert.equal(res.status, 400);
  assert.equal(data.error, 'too_fast');
  assert.equal(calls.length, 0);
});

test('consent must be exactly true', async () => {
  for (const consent of [false, 'true', undefined]) {
    const { res, data } = await send(payload({ consent }));
    assert.equal(res.status, 400);
    assert.equal(data.error, 'consent_required');
  }
});

test('invalid form type, email, json, size, field length', async () => {
  let r = await send(payload({ form: 'newsletter' }));
  assert.equal(r.data.error, 'invalid_form');
  r = await send(payload({}, { email: 'not-an-email' }));
  assert.equal(r.data.error, 'invalid_email');
  r = await send(null, { raw: '{not json' });
  assert.equal(r.data.error, 'invalid_json');
  r = await send(null, { raw: JSON.stringify(payload({ pad: 'x'.repeat(33 * 1024) })) });
  assert.equal(r.res.status, 413);
  r = await send(payload({}, { name: 'n'.repeat(201) }));
  assert.equal(r.data.error, 'field_too_long:name');
  r = await send(payload({}, { email: '', phone: '', telegram: '' }));
  assert.equal(r.data.error, 'contact_required');
  r = await send(payload({ form: 'investor_company' }));
  assert.equal(r.data.error, 'company_required');
  r = await send(payload({}, { move_in: '13.10.2026' }));
  assert.equal(r.data.error, 'invalid_date');
  assert.equal(notionPageCalls().length, 0);
});

test('missing secrets → 503 not_configured', async () => {
  const { res, data } = await send(payload(), {}, { ALLOWED_ORIGINS: ENV.ALLOWED_ORIGINS });
  assert.equal(res.status, 503);
  assert.equal(data.error, 'not_configured');
});

// ---------- запись в Notion ----------

test('happy path: labels, types, headers, no secret echo', async () => {
  const { res, data } = await send(payload({ form: 'investor_company' }, {
    company: 'Adriatic Capital, LLC', position: 'Partner', website: 'adriatic.example',
    jurisdiction: 'Cyprus', phone: '+382 69 000 000', preferred_language: 'en',
  }));
  assert.equal(res.status, 200);
  assert.deepEqual(data, { ok: true });
  assert.ok(!JSON.stringify(data).includes(ENV.NOTION_TOKEN));

  const [schemaCall, pageCall] = calls;
  assert.equal(schemaCall.method, 'GET');
  assert.ok(schemaCall.url.endsWith(`/v1/databases/${DB_ID}`));
  assert.equal(pageCall.headers.Authorization, `Bearer ${ENV.NOTION_TOKEN}`);
  assert.equal(pageCall.headers['Notion-Version'], '2022-06-28');
  assert.deepEqual(pageCall.body.parent, { database_id: DB_ID });

  const p = createdProps();
  assert.equal(p.Name.title[0].text.content, 'Jane Investor');
  assert.equal(p.Form.select.name, 'Investor (company)');
  assert.equal(p.Status.status.name, 'New');
  assert.equal(p.Language.select.name, 'English');
  assert.equal(p['Investment Type'].select.name, 'Hotel');
  assert.equal(p.Budget.select.name, '€2–10M');
  assert.equal(p['Contact Method'].select.name, 'E-mail');
  assert.equal(p['Preferred Language'].select.name, 'English');
  assert.equal(p['NDA Requested'].checkbox, true);
  assert.equal(p.Email.email, 'jane@fund.example');
  assert.equal(p.Phone.phone_number, '+382 69 000 000');
  assert.equal(plain(p.Company), 'Adriatic Capital, LLC');
  assert.equal(p.Website.url, 'https://adriatic.example');
  assert.equal(p.Page.url, 'https://re6al.github.io/gurevic-real-estate/en/invest/');
  assert.equal(plain(p.UTM), 'source=google; medium=cpc; campaign=invest');
  assert.equal(p.Consent.checkbox, true);
  assert.equal(plain(p['Consent Version']), '2026-10');
  assert.equal(plain(p.Message), 'Looking for a boutique hotel.');
  assert.equal(p.Received, undefined); // created_time заполняет Notion
});

test('select labels never contain commas (Notion restriction)', () => {
  assert.equal(toProperty('select', 'a,b', 'Restaurant, commercial').select.name, 'Restaurant commercial');
});

test('label maps cover every code of brief §E', () => {
  assert.deepEqual(Object.keys(LABELS.budget), ['lt_500k', '500k_2m', '2m_10m', '10m_50m', 'gt_50m', 'undisclosed']);
  assert.deepEqual(Object.keys(LABELS.investment_type),
    ['hotel', 'development_land', 'restaurant_commercial', 'warehouse_logistics', 'development_partnership', 'other']);
  assert.deepEqual(Object.keys(LABELS.contact_method), ['email', 'phone', 'whatsapp', 'telegram', 'video_call']);
  assert.deepEqual(Object.keys(LABELS.preferred_language), ['ru', 'en', 'me', 'uk', 'other']);
  assert.deepEqual(Object.keys(LABELS.property_kind), ['apartment', 'house', 'land', 'construction_project', 'business']);
  assert.deepEqual(Object.keys(LABELS.interest), ['buy', 'rent', 'invest', 'sell', 'rent_out', 'management', 'other']);
  assert.deepEqual(Object.keys(LABELS.rental_term), ['off_season', 'year', 'short_term']);
});

test('schema filtering: missing columns and wrong types go to Message', async () => {
  const partial = { ...SCHEMA };
  delete partial.Budget;               // колонки нет
  partial['Asking Price'] = 'number';
  partial.Bedrooms = 'checkbox';       // несовместимый тип
  responder = defaultResponder(partial);
  const { res } = await send(payload({ form: 'owner' }, {
    budget: 'gt_50m', asking_price: '350 000 €', bedrooms: '3', property_kind: 'apartment',
    owner_type: 'individual', list_nepokretnosti: '1234', cadastral_municipality: 'Budva', pd: '7',
    preferred_language: 'other', preferred_language_other: 'Italiano', unknown_key: 'hello',
  }));
  assert.equal(res.status, 200);
  const p = createdProps();
  assert.equal(p.Budget, undefined);
  assert.equal(p.Bedrooms, undefined);
  assert.equal(p['Asking Price'].number, 350000);
  assert.equal(p['Property Kind'].select.name, 'Apartment');
  assert.equal(p['Owner Type'].select.name, 'Individual');
  assert.equal(plain(p['List Nepokretnosti']), '1234');
  assert.equal(plain(p.KO), 'Budva');
  assert.equal(p['Preferred Language'].select.name, 'Other');
  const msg = plain(p.Message);
  assert.match(msg, /^Looking for a boutique hotel\.\n\n/);
  assert.match(msg, /budget: > €50M/);
  assert.match(msg, /bedrooms: 3/);
  assert.match(msg, /preferred_language_other: Italiano/);
  assert.match(msg, /unknown_key: hello/);
  for (const name of Object.keys(p)) assert.ok(name in partial, `unexpected column ${name}`);
});

test('insert-only integration (schema GET → 403) falls back to the documented schema', async () => {
  const base = defaultResponder();
  responder = (call) => (call.url.includes('/v1/databases/') ? jsonResponse(403, { code: 'restricted_resource' }) : base(call));
  const { res } = await send(payload());
  assert.equal(res.status, 200);
  const p = createdProps();
  assert.equal(p.Budget.select.name, '€2–10M');
  assert.equal(p.Status.status.name, 'New');
  assert.deepEqual(Object.keys(DEFAULT_SCHEMA).sort(), Object.keys(SCHEMA).filter((k) => k !== 'Received').sort());
  await send(payload());
  assert.equal(calls.filter((c) => c.url.includes('/v1/databases/')).length, 1); // 403 тоже кэшируется
});

test('schema GET 401 (bad token) → 502', async () => {
  responder = () => jsonResponse(401, {});
  const { res, data } = await send(payload());
  assert.equal(res.status, 502);
  assert.equal(data.error, 'upstream_error');
});

test('schema is cached per isolate', async () => {
  await send(payload());
  await send(payload());
  assert.equal(calls.filter((c) => c.url.includes('/v1/databases/')).length, 1);
  assert.equal(notionPageCalls().length, 2);
});

test('rich text is split into ≤2000-char chunks', async () => {
  const transcript = 'a'.repeat(4500);
  const { res } = await send(payload({ form: 'chat' }, { transcript, email: '' }));
  assert.equal(res.status, 200);
  const parts = createdProps().Transcript.rich_text;
  assert.deepEqual(parts.map((x) => x.text.content.length), [2000, 2000, 500]);
  assert.equal(chunkText('x'.repeat(10), 3, 2).length, 2);
  assert.equal(Array.from(chunkText('😀'.repeat(3), 2)[0].text.content).length, 2);
});

test('title falls back to company, then to "Website lead"', () => {
  const lead = { form: 'contact', lang: '', page: '', consentVersion: '', utm: {}, fields: { company: 'ACME' } };
  assert.equal(buildProperties(lead, { Name: { type: 'title' } }).Name.title[0].text.content, 'ACME');
  lead.fields = { phone: '+1' };
  assert.equal(buildProperties(lead, { Lead: { type: 'title' } }).Lead.title[0].text.content, 'Website lead');
});

test('rent request: date, numbers, labels', async () => {
  const { res } = await send(payload({ form: 'rent_request' }, {
    rental_term: 'off_season', move_in: '2026-11-01', budget_month: 900, bedrooms: 2,
    object_id: 'RN-26-001', listing_url: 'https://re6al.github.io/gurevic-real-estate/rent/rn-26-001/',
  }));
  assert.equal(res.status, 200);
  const p = createdProps();
  assert.equal(p['Rental Term'].select.name, 'Off-season');
  assert.deepEqual(p['Move-in'].date, { start: '2026-11-01' });
  assert.equal(p['Monthly Budget'].number, 900);
  assert.equal(p.Bedrooms.number, 2);
  assert.equal(plain(p['Object ID']), 'RN-26-001');
  assert.ok(p['Listing URL'].url.endsWith('/rent/rn-26-001/'));
});

test('Notion 400 → retried as a minimal record; other errors → 502', async () => {
  let attempt = 0;
  responder = (call) => {
    if (call.url.includes('/v1/databases/')) return jsonResponse(200, schemaResponse());
    if (call.url.endsWith('/v1/pages')) {
      attempt += 1;
      return attempt === 1 ? jsonResponse(400, { message: 'validation_error' }) : jsonResponse(200, { url: 'u' });
    }
    return jsonResponse(404, {});
  };
  let r = await send(payload());
  assert.equal(r.res.status, 200);
  const minimal = createdProps();
  assert.deepEqual(Object.keys(minimal).sort(), ['Message', 'Name']);
  assert.match(plain(minimal.Message), /budget: €2–10M/);

  responder = (call) => (call.url.includes('/v1/databases/')
    ? jsonResponse(200, schemaResponse()) : jsonResponse(500, {}));
  _resetCache();
  r = await send(payload());
  assert.equal(r.res.status, 502);
  assert.deepEqual(r.data, { ok: false, error: 'upstream_error' });
});

// ---------- Telegram ----------

test('Telegram is optional', async () => {
  await send(payload());
  assert.equal(calls.filter((c) => c.url.includes('telegram')).length, 0);
});

test('Telegram summary is sent when configured and omits sensitive numbers', async () => {
  const env = { ...ENV, TELEGRAM_BOT_TOKEN: '123:abc', TELEGRAM_CHAT_ID: '-100500' };
  const pending = [];
  const ctx = { waitUntil: (p) => pending.push(p) };
  const { res } = await send(payload({ form: 'owner' }, {
    property_kind: 'land', list_nepokretnosti: 'LN-98765', cadastral_municipality: 'KO-SECRET',
    pd: 'PD-55', company_reg_no: 'REG-777', phone: '+382 67 123 456',
  }), {}, env, ctx);
  assert.equal(res.status, 200);
  await Promise.all(pending);
  const tg = calls.find((c) => c.url.includes('api.telegram.org'));
  assert.ok(tg, 'telegram call expected');
  assert.ok(tg.url.endsWith('/bot123:abc/sendMessage'));
  assert.equal(tg.body.chat_id, '-100500');
  const text = tg.body.text;
  assert.match(text, /Owner/);
  assert.match(text, /Jane Investor/);
  assert.match(text, /https:\/\/www\.notion\.so\/p1/);
  for (const secret of ['LN-98765', 'KO-SECRET', 'PD-55', 'REG-777', '+382 67 123 456', 'jane@fund.example']) {
    assert.ok(!text.includes(secret), `telegram leaked ${secret}`);
  }
});

test('Telegram failure does not fail the request', async () => {
  const env = { ...ENV, TELEGRAM_BOT_TOKEN: '1:x', TELEGRAM_CHAT_ID: '1' };
  const base = defaultResponder();
  responder = (call) => (call.url.includes('telegram') ? jsonResponse(500, {}) : base(call));
  const errors = [];
  const origError = console.error;
  console.error = (m) => errors.push(String(m));
  try {
    const { res } = await send(payload(), {}, env);
    assert.equal(res.status, 200);
  } finally {
    console.error = origError;
  }
  assert.ok(errors.some((e) => e.includes('telegram failed')));
  assert.ok(errors.every((e) => !e.includes('jane@fund.example')));
});

test('telegramText helper is short', () => {
  const lead = { form: 'investor', lang: 'ru', fields: { name: 'X', budget: 'undisclosed', nda: true } };
  const text = telegramText(lead, '');
  assert.match(text, /Not disclosed/);
  assert.match(text, /NDA: да/);
  assert.ok(text.length < 3500);
});
