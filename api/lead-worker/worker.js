// Gurevic Real Estate — приём заявок с сайта → Notion «Website Leads» (+ Telegram).
//
// Cloudflare Worker (ES module). Секреты задаются через `wrangler secret put`:
//   NOTION_TOKEN        токен интеграции «website-leads» (только Insert content)
//   NOTION_LEADS_DB_ID  ID базы «Website Leads»
//   TELEGRAM_BOT_TOKEN  (необязательно) бот для уведомлений
//   TELEGRAM_CHAT_ID    (необязательно) чат, куда слать уведомления
// Переменная (wrangler.toml [vars]): ALLOWED_ORIGINS — через запятую.
//
// Формат запроса — docs/ARCHITECTURE.md §7, ключи полей — brief §E / docs/NOTION_SETUP.md.
// Персональные данные не логируются; в лог попадают только коды ошибок.

const NOTION_API = 'https://api.notion.com/v1';
const NOTION_VERSION = '2022-06-28';
const MAX_BODY_BYTES = 32 * 1024;
const MIN_ELAPSED_MS = 2500;
const SCHEMA_TTL_MS = 10 * 60 * 1000;
const RICH_TEXT_CHUNK = 2000;   // лимит Notion на один text-объект
const RICH_TEXT_MAX_PARTS = 100; // лимит Notion на массив rich_text

export const FORMS = {
  investor: 'Investor (private)',
  investor_company: 'Investor (company)',
  owner: 'Owner',
  contact: 'Contact',
  rent_request: 'Rent request',
  buy_request: 'Buy request',
  property_request: 'Property request',
  chat: 'Chat',
};

// Коды значений → человекочитаемые опции select в Notion
export const LABELS = {
  lang: { ru: 'Русский', en: 'English', de: 'Deutsch', fr: 'Français', pl: 'Polski', uk: 'Українська', he: 'עברית' },
  preferred_language: { ru: 'Русский', en: 'English', me: 'Crnogorski/Srpski', uk: 'Українська', other: 'Other' },
  contact_method: { email: 'E-mail', phone: 'Phone', whatsapp: 'WhatsApp', telegram: 'Telegram', video_call: 'Video call' },
  investment_type: {
    hotel: 'Hotel',
    development_land: 'Development land',
    restaurant_commercial: 'Restaurant / commercial',
    warehouse_logistics: 'Warehouse / logistics',
    development_partnership: 'Development partnership',
    other: 'Other',
  },
  budget: {
    lt_500k: '< €500K',
    '500k_2m': '€500K–2M',
    '2m_10m': '€2–10M',
    '10m_50m': '€10–50M',
    gt_50m: '> €50M',
    undisclosed: 'Not disclosed',
  },
  property_kind: {
    apartment: 'Apartment', house: 'House', land: 'Land',
    construction_project: 'Construction project', business: 'Business',
  },
  owner_type: { individual: 'Individual', company: 'Company' },
  interest: {
    buy: 'Buy', rent: 'Rent', invest: 'Invest', sell: 'Sell',
    rent_out: 'Rent out', management: 'Property management', other: 'Other',
  },
  rental_term: { off_season: 'Off-season', year: 'Full year', short_term: 'Short-term' },
};

// Поле payload → колонка Notion. Тип колонки берётся из схемы базы;
// значение пишется, только если тип совместим (иначе уходит строкой в Message).
const FIELD_COLUMNS = {
  email: 'Email',
  phone: 'Phone',
  telegram: 'Telegram',
  company: 'Company',
  position: 'Position',
  website: 'Website',
  jurisdiction: 'Jurisdiction',
  contact_method: 'Contact Method',
  preferred_language: 'Preferred Language',
  investment_type: 'Investment Type',
  budget: 'Budget',
  nda: 'NDA Requested',
  property_kind: 'Property Kind',
  owner_type: 'Owner Type',
  list_nepokretnosti: 'List Nepokretnosti',
  cadastral_municipality: 'KO',
  pd: 'PD',
  company_reg_no: 'Company Reg No',
  asking_price: 'Asking Price',
  interest: 'Interest',
  rental_term: 'Rental Term',
  move_in: 'Move-in',
  budget_month: 'Monthly Budget',
  bedrooms: 'Bedrooms',
  occupants: 'Occupants',
  pets: 'Pets',
  object_id: 'Object ID',
  listing_url: 'Listing URL',
  transcript: 'Transcript',
};

// Схема «Website Leads» из docs/NOTION_SETUP.md. Используется, когда интеграция
// не может прочитать схему базы (у интеграции только право Insert content → 403).
export const DEFAULT_SCHEMA = Object.fromEntries(Object.entries({
  Name: 'title', Form: 'select', Status: 'status', Language: 'select', 'Preferred Language': 'select',
  'Contact Method': 'select', Email: 'email', Phone: 'phone_number', Telegram: 'rich_text',
  Company: 'rich_text', Position: 'rich_text', Website: 'url', Jurisdiction: 'rich_text',
  'Investment Type': 'select', Budget: 'select', 'NDA Requested': 'checkbox', 'Property Kind': 'select',
  'Owner Type': 'select', 'List Nepokretnosti': 'rich_text', KO: 'rich_text', PD: 'rich_text',
  'Company Reg No': 'rich_text', 'Asking Price': 'number', Interest: 'select', 'Rental Term': 'select',
  'Move-in': 'date', 'Monthly Budget': 'number', Bedrooms: 'number', Occupants: 'rich_text',
  Pets: 'rich_text', 'Object ID': 'rich_text', 'Listing URL': 'url', Message: 'rich_text',
  Transcript: 'rich_text', Page: 'url', UTM: 'rich_text', Consent: 'checkbox',
  'Consent Version': 'rich_text',
}).map(([name, type]) => [name, { type, options: null }]));

// Максимальная длина полей (символы); остальные — DEFAULT_MAX
const FIELD_MAX = { name: 200, company: 200, email: 254, message: 5000, transcript: 20000, website: 500, listing_url: 1000 };
const DEFAULT_MAX = 500;
const EMAIL_RE = /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

// Не попадают в Telegram (кадастровые и регистрационные номера, контакты)
const TELEGRAM_FIELDS = ['company', 'contact_method', 'investment_type', 'budget', 'property_kind',
  'owner_type', 'interest', 'rental_term', 'object_id'];

let schemaCache = { dbId: null, at: 0, props: null };

/** Сброс кэша схемы (для тестов). */
export function _resetCache() {
  schemaCache = { dbId: null, at: 0, props: null };
}

class HttpError extends Error {
  constructor(status, code, upstreamStatus = 0) {
    super(code);
    this.status = status;
    this.code = code;
    this.upstreamStatus = upstreamStatus;
  }
}

function allowedOrigins(env) {
  return String(env.ALLOWED_ORIGINS || '')
    .split(',')
    .map((s) => s.trim().replace(/\/+$/, ''))
    .filter(Boolean);
}

function corsHeaders(origin) {
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
}

function json(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra },
  });
}

// ---------- валидация ----------

function cleanString(value, max, key) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'number' || typeof value === 'boolean') value = String(value);
  if (typeof value !== 'string') throw new HttpError(400, `invalid_field:${key}`);
  const s = value.replace(/\r\n?/g, '\n').replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, '').trim();
  if (s.length > max) throw new HttpError(400, `field_too_long:${key}`);
  return s;
}

function toNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  const s = value.replace(/[\s '€$]/g, '').replace(/,(?=\d{3}(\D|$))/g, '').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

function isHttpUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' || u.protocol === 'http:';
  } catch {
    return false;
  }
}

/** Разбор и проверка payload. Возвращает нормализованный объект или бросает HttpError. */
export function validatePayload(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) throw new HttpError(400, 'invalid_json');
  const form = typeof data.form === 'string' ? data.form : '';
  if (!Object.prototype.hasOwnProperty.call(FORMS, form)) throw new HttpError(400, 'invalid_form');
  if (data.consent !== true) throw new HttpError(400, 'consent_required');
  const elapsed = Number(data.elapsed_ms);
  if (!Number.isFinite(elapsed) || elapsed < MIN_ELAPSED_MS) throw new HttpError(400, 'too_fast');

  const rawFields = data.fields ?? {};
  if (typeof rawFields !== 'object' || Array.isArray(rawFields)) throw new HttpError(400, 'invalid_fields');
  const keys = Object.keys(rawFields);
  if (keys.length > 60) throw new HttpError(400, 'too_many_fields');

  const fields = {};
  for (const key of keys) {
    if (!/^[a-z][a-z0-9_]{0,40}$/.test(key)) throw new HttpError(400, 'invalid_field_name');
    const value = rawFields[key];
    if (key === 'nda') {
      fields.nda = value === true || value === 'true' || value === 'on' || value === '1';
      continue;
    }
    const s = cleanString(value, FIELD_MAX[key] || DEFAULT_MAX, key);
    if (s !== '') fields[key] = s;
  }

  if (fields.email && !EMAIL_RE.test(fields.email)) throw new HttpError(400, 'invalid_email');
  if (fields.move_in && !DATE_RE.test(fields.move_in)) throw new HttpError(400, 'invalid_date');
  if (form !== 'chat' && !fields.email && !fields.phone && !fields.telegram) {
    throw new HttpError(400, 'contact_required');
  }
  if (form === 'investor_company' && !fields.company) throw new HttpError(400, 'company_required');
  if (form === 'chat' && !fields.transcript && !fields.message) throw new HttpError(400, 'empty');

  const utmIn = data.utm && typeof data.utm === 'object' ? data.utm : {};
  const utm = {};
  for (const k of ['source', 'medium', 'campaign', 'term', 'content']) {
    const v = cleanString(typeof utmIn[k] === 'string' ? utmIn[k] : '', 200, `utm_${k}`);
    if (v) utm[k] = v;
  }

  const page = cleanString(typeof data.page === 'string' ? data.page : '', 1000, 'page');
  return {
    form,
    lang: cleanString(typeof data.lang === 'string' ? data.lang : '', 10, 'lang').toLowerCase(),
    page: isHttpUrl(page) ? page : '',
    consentVersion: cleanString(typeof data.consent_version === 'string' ? data.consent_version : '', 40, 'consent_version'),
    utm,
    fields,
  };
}

// ---------- Notion ----------

async function notionFetch(env, path, init = {}) {
  const res = await fetch(`${NOTION_API}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${env.NOTION_TOKEN}`,
      'Notion-Version': NOTION_VERSION,
      'Content-Type': 'application/json',
    },
  });
  if (!res.ok) {
    if (res.status !== 403 || init.method) {
      console.error(`notion ${init.method || 'GET'} ${path.split('/')[1]} failed: HTTP ${res.status}`);
    }
    throw new HttpError(502, 'upstream_error', res.status);
  }
  return res.json();
}

/** Схема базы {имя колонки: {type, options}} с кэшем на изолят. */
export async function getSchema(env, now = Date.now()) {
  if (schemaCache.props && schemaCache.dbId === env.NOTION_LEADS_DB_ID && now - schemaCache.at < SCHEMA_TTL_MS) {
    return schemaCache.props;
  }
  let props;
  try {
    const db = await notionFetch(env, `/databases/${encodeURIComponent(env.NOTION_LEADS_DB_ID)}`);
    props = {};
    for (const [name, p] of Object.entries(db.properties || {})) {
      const options = p[p.type]?.options?.map((o) => o.name) || null;
      props[name] = { type: p.type, options };
    }
  } catch (err) {
    // 403: у интеграции нет права Read content (рекомендуемая настройка) — пишем по
    // документированной схеме; несовпадения ловит повтор «минимальной» записью
    if (!(err instanceof HttpError) || err.upstreamStatus !== 403) throw err;
    props = DEFAULT_SCHEMA;
  }
  schemaCache = { dbId: env.NOTION_LEADS_DB_ID, at: now, props };
  return props;
}

export function chunkText(text, size = RICH_TEXT_CHUNK, maxParts = RICH_TEXT_MAX_PARTS) {
  const parts = [];
  const chars = Array.from(String(text)); // не режем суррогатные пары (эмодзи)
  for (let i = 0; i < chars.length && parts.length < maxParts; i += size) {
    parts.push({ type: 'text', text: { content: chars.slice(i, i + size).join('') } });
  }
  return parts;
}

function selectName(label) {
  // Notion: имя опции ≤ 100 символов и без запятых
  return String(label).replace(/,/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 100);
}

function labelFor(key, value) {
  const map = LABELS[key];
  if (map && Object.prototype.hasOwnProperty.call(map, value)) return map[value];
  return value;
}

/**
 * Значение → свойство Notion для колонки типа `type`. null — несовместимо.
 * `label` — человекочитаемая форма (для select/текста), `raw` — исходное значение.
 */
export function toProperty(type, raw, label = raw) {
  const text = typeof label === 'boolean' ? (label ? 'Yes' : 'No') : String(label ?? '');
  switch (type) {
    case 'title':
      return text ? { title: chunkText(text) } : null;
    case 'rich_text':
      return text ? { rich_text: chunkText(text) } : null;
    case 'select':
      return text ? { select: { name: selectName(text) } } : null;
    case 'multi_select':
      return text ? { multi_select: [{ name: selectName(text) }] } : null;
    case 'status':
      return text ? { status: { name: text } } : null;
    case 'email':
      return typeof raw === 'string' && EMAIL_RE.test(raw) ? { email: raw } : null;
    case 'phone_number':
      return text ? { phone_number: text.slice(0, 100) } : null;
    case 'url':
      return typeof raw === 'string' && isHttpUrl(raw) ? { url: raw.slice(0, 2000) } : null;
    case 'number': {
      const n = toNumber(raw);
      return n === null ? null : { number: n };
    }
    case 'checkbox':
      return typeof raw === 'boolean' ? { checkbox: raw } : null;
    case 'date':
      return typeof raw === 'string' && DATE_RE.test(raw) ? { date: { start: raw } } : null;
    default:
      return null;
  }
}

/** Собирает properties для POST /pages: только существующие колонки совместимого типа. */
export function buildProperties(lead, schema) {
  const props = {};
  const extra = []; // «key: value» для Message
  const put = (column, raw, label) => {
    const col = schema[column];
    if (!col) return false;
    const value = toProperty(col.type, raw, label);
    if (!value) return false;
    props[column] = value;
    return true;
  };
  const f = lead.fields;

  // заголовок — колонка типа title, как бы она ни называлась
  const titleCol = Object.keys(schema).find((k) => schema[k].type === 'title');
  if (titleCol) props[titleCol] = toProperty('title', f.name || f.company || 'Website lead');
  else if (f.name) extra.push(`name: ${f.name}`);

  put('Form', lead.form, FORMS[lead.form]) || extra.push(`form: ${FORMS[lead.form]}`);
  if (schema.Status && (!schema.Status.options || schema.Status.options.includes('New'))) put('Status', 'New');
  if (lead.lang) put('Language', lead.lang, labelFor('lang', lead.lang)) || extra.push(`lang: ${lead.lang}`);
  if (lead.page) put('Page', lead.page) || extra.push(`page: ${lead.page}`);
  const utm = Object.entries(lead.utm).map(([k, v]) => `${k}=${v}`).join('; ');
  if (utm) put('UTM', utm) || extra.push(`utm: ${utm}`);
  put('Consent', true);
  if (lead.consentVersion) put('Consent Version', lead.consentVersion) || extra.push(`consent_version: ${lead.consentVersion}`);

  for (const [key, value] of Object.entries(f)) {
    if (key === 'name' || key === 'message') continue;
    if (key === 'preferred_language_other') {
      extra.push(`preferred_language_other: ${value}`);
      continue;
    }
    const column = FIELD_COLUMNS[key];
    const label = labelFor(key, value);
    if (key === 'website' && !/^https?:\/\//i.test(value) && /^[\w-]+(\.[\w-]+)+(\/\S*)?$/.test(value)) {
      if (put(column, `https://${value}`)) continue;
    }
    if (column && put(column, value, label)) continue;
    extra.push(`${key}: ${typeof label === 'boolean' ? (label ? 'yes' : 'no') : label}`);
  }

  const message = [f.message, extra.length ? extra.join('\n') : ''].filter(Boolean).join('\n\n');
  if (message && !put('Message', message)) {
    // нет колонки Message — дописываем в Transcript, чтобы ничего не потерять
    if (!props.Transcript) put('Transcript', message);
  }
  return props;
}

/** Запасной вариант: только заголовок и Message (или Transcript) со всеми полями строками. */
export function buildMinimalProperties(lead, schema) {
  const props = {};
  const titleCol = Object.keys(schema).find((k) => schema[k].type === 'title');
  if (titleCol) props[titleCol] = toProperty('title', lead.fields.name || lead.fields.company || 'Website lead');
  const lines = [`form: ${FORMS[lead.form]}`, `lang: ${lead.lang}`, `page: ${lead.page}`];
  for (const [key, value] of Object.entries(lead.fields)) {
    const label = labelFor(key, value);
    lines.push(`${key}: ${typeof label === 'boolean' ? (label ? 'yes' : 'no') : label}`);
  }
  const textCol = ['Message', 'Transcript'].find((k) => schema[k] && schema[k].type === 'rich_text');
  if (textCol) props[textCol] = toProperty('rich_text', lines.join('\n'));
  return props;
}

// ---------- Telegram ----------

export function telegramText(lead, notionUrl) {
  const f = lead.fields;
  const lines = [`Новая заявка с сайта: ${FORMS[lead.form]}`];
  if (f.name) lines.push(`Имя: ${f.name}`);
  for (const key of TELEGRAM_FIELDS) {
    if (f[key] !== undefined && f[key] !== '' && key !== 'nda') lines.push(`${key}: ${labelFor(key, f[key])}`);
  }
  if (f.nda) lines.push('NDA: да');
  if (lead.lang) lines.push(`Язык сайта: ${lead.lang}`);
  if (notionUrl) lines.push(notionUrl);
  return lines.join('\n').slice(0, 3500);
}

async function notifyTelegram(env, lead, notionUrl) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return;
  try {
    const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: env.TELEGRAM_CHAT_ID,
        text: telegramText(lead, notionUrl),
        disable_web_page_preview: true,
      }),
    });
    if (!res.ok) console.error(`telegram failed: HTTP ${res.status}`);
  } catch {
    console.error('telegram failed: network');
  }
}

// ---------- обработчик ----------

async function readBody(request) {
  const len = Number(request.headers.get('Content-Length') || 0);
  if (len > MAX_BODY_BYTES) throw new HttpError(413, 'too_large');
  const buf = await request.arrayBuffer();
  if (buf.byteLength > MAX_BODY_BYTES) throw new HttpError(413, 'too_large');
  try {
    return JSON.parse(new TextDecoder().decode(buf));
  } catch {
    throw new HttpError(400, 'invalid_json');
  }
}

async function handle(request, env, ctx) {
  const origin = (request.headers.get('Origin') || '').replace(/\/+$/, '');
  if (!origin || !allowedOrigins(env).includes(origin)) {
    return json(403, { ok: false, error: 'origin_not_allowed' });
  }
  const cors = corsHeaders(origin);

  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
  if (request.method !== 'POST') return json(405, { ok: false, error: 'method_not_allowed' }, { ...cors, Allow: 'POST, OPTIONS' });

  const ctype = (request.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase();
  if (ctype !== 'text/plain' && ctype !== 'application/json') {
    return json(415, { ok: false, error: 'unsupported_media_type' }, cors);
  }
  if (!env.NOTION_TOKEN || !env.NOTION_LEADS_DB_ID) {
    console.error('config: NOTION_TOKEN / NOTION_LEADS_DB_ID not set');
    return json(503, { ok: false, error: 'not_configured' }, cors);
  }

  try {
    const data = await readBody(request);
    // ловушка для ботов: делаем вид, что всё хорошо, но ничего не пишем
    if (data && typeof data === 'object' && typeof data.hp === 'string' && data.hp.trim() !== '') {
      return json(200, { ok: true }, cors);
    }
    if (data && typeof data === 'object' && data.hp !== undefined && typeof data.hp !== 'string') {
      throw new HttpError(400, 'invalid_json');
    }
    const lead = validatePayload(data);
    const schema = await getSchema(env);
    const create = (properties) => notionFetch(env, '/pages', {
      method: 'POST',
      body: JSON.stringify({ parent: { database_id: env.NOTION_LEADS_DB_ID }, properties }),
    });
    let created;
    try {
      created = await create(buildProperties(lead, schema));
    } catch (err) {
      // 400 = Notion не принял какое-то значение (напр. переименовали опцию) —
      // повторяем «минимальной» записью: заголовок + всё остальное текстом
      if (!(err instanceof HttpError) || err.upstreamStatus !== 400) throw err;
      created = await create(buildMinimalProperties(lead, schema));
    }
    const task = notifyTelegram(env, lead, created && created.url);
    if (ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(task);
    else await task;
    return json(200, { ok: true }, cors);
  } catch (err) {
    if (err instanceof HttpError) return json(err.status, { ok: false, error: err.code }, cors);
    console.error(`unexpected: ${err && err.name}`);
    return json(500, { ok: false, error: 'internal_error' }, cors);
  }
}

export default {
  fetch: handle,
};
