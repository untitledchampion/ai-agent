import { useState, useEffect } from 'react';
import { getScenes, updateScene, createScene, deleteScene } from '../api';

export default function ScenesPage() {
  const [scenes, setScenes] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState(null);
  const [isNew, setIsNew] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try {
      const data = await getScenes();
      setScenes(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  }

  async function toggleActive(e, scene) {
    e.stopPropagation();
    await updateScene(scene.slug, { active: !scene.active });
    load();
  }

  function startNew() {
    setSelectedSlug(null);
    setIsNew(true);
  }

  function selectScene(slug) {
    setSelectedSlug(slug);
    setIsNew(false);
  }

  const selected = scenes.find(s => s.slug === selectedSlug) || null;

  if (loading) return <div className="flex items-center justify-center h-full text-gray-400">Загрузка...</div>;

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-72 min-w-[18rem] border-r border-gray-200 bg-gray-50 flex flex-col">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">Сценарии</h2>
          <button onClick={startNew} className="px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-opacity">
            + Добавить
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {scenes.length === 0 && (
            <p className="text-center text-gray-400 text-sm py-8">Нет сценариев</p>
          )}
          {scenes.map(s => (
            <div
              key={s.slug}
              onClick={() => selectScene(s.slug)}
              className={`px-4 py-3 border-b border-gray-100 cursor-pointer transition-colors ${
                selectedSlug === s.slug ? 'bg-blue-50' : 'hover:bg-gray-100'
              } ${!s.active ? 'opacity-40' : ''}`}
            >
              <div className="flex items-center justify-between gap-2 mb-0.5">
                <span className="font-medium text-gray-800 truncate">{s.name}</span>
                <button
                  onClick={(e) => toggleActive(e, s)}
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0 transition-colors ${
                    s.active
                      ? 'bg-green-50 text-green-600 hover:bg-green-100'
                      : 'bg-red-50 text-red-500 hover:bg-red-100'
                  }`}
                >
                  {s.active ? 'Вкл' : 'Выкл'}
                </button>
              </div>
              <div className="flex items-center gap-2">
                {s.auto_reply && (
                  <span className="text-[10px] bg-purple-50 text-purple-600 px-1.5 py-0.5 rounded-full">AI</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* Editor */}
      {(isNew || selected) ? (
        <SceneEditor
          key={isNew ? '__new__' : selectedSlug}
          scene={isNew ? null : selected}
          onSave={async (data) => {
            if (isNew) {
              await createScene(data);
              setIsNew(false);
            } else {
              await updateScene(data.slug, data);
            }
            load();
          }}
          onDelete={async (slug) => {
            if (!confirm(`Удалить сценарий "${slug}"?`)) return;
            await deleteScene(slug);
            setSelectedSlug(null);
            load();
          }}
        />
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
          Выберите сценарий или создайте новый
        </div>
      )}
    </div>
  );
}


function SceneEditor({ scene, onSave, onDelete }) {
  const isNew = !scene;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const [slug, setSlug] = useState(scene?.slug || '');
  const [slugManual, setSlugManual] = useState(false);
  const [name, setName] = useState(scene?.name || '');
  const [active, setActive] = useState(scene?.active !== false);
  const [autoReply, setAutoReply] = useState(scene?.auto_reply !== false);
  const [description, setDescription] = useState(scene?.trigger?.description || '');
  const [examples, setExamples] = useState((scene?.trigger?.examples || []).join('\n'));
  const [responseTemplate, setResponseTemplate] = useState(scene?.response_template || '');
  const [escalateWhen, setEscalateWhen] = useState((scene?.escalate_when || []).join('\n'));
  const [fields, setFields] = useState(scene?.fields || []);
  const [tools, setTools] = useState(scene?.tools || []);
  const [knowledge, setKnowledge] = useState(scene?.knowledge || []);

  async function handleSave() {
    if (!name) { setError('Укажите название'); return; }
    if (isNew && !slug) { setError('Укажите Slug (ID)'); return; }
    if (isNew && !/^[a-z0-9_-]+$/.test(slug)) { setError('Slug может содержать только латиницу, цифры, дефис и _'); return; }
    setError('');
    setSaving(true);
    try {
      await onSave({
        slug: isNew ? slug : scene.slug,
        name,
        active,
        auto_reply: autoReply,
        trigger: {
          description,
          examples: examples.split('\n').map(s => s.trim()).filter(Boolean),
        },
        fields,
        tools,
        knowledge,
        response_template: responseTemplate,
        escalate_when: escalateWhen.split('\n').map(s => s.trim()).filter(Boolean),
      });
      setError('');
    } catch (err) {
      const msg = err.message || String(err);
      if (msg.includes('409')) {
        setError(`Сценарий с slug "${slug}" уже существует`);
      } else {
        setError(`Ошибка сохранения: ${msg}`);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="flex-1 overflow-y-auto p-6">
      <h3 className="text-lg font-semibold text-gray-800 mb-5">
        {isNew ? 'Новый сценарий' : 'Редактирование'}
      </h3>

      <div className="max-w-2xl space-y-5">
        {/* Name & Slug */}
        <div className="grid grid-cols-2 gap-4">
          <FormRow label="Название">
            <input
              className="input"
              value={name}
              onChange={e => {
                setName(e.target.value);
                if (isNew && !slugManual) {
                  setSlug(transliterate(e.target.value));
                }
              }}
              placeholder="Оформление заказа"
            />
          </FormRow>
          <FormRow label="Slug (ID)">
            {isNew ? (
              <input
                className="input font-mono"
                value={slug}
                onChange={e => { setSlug(e.target.value); setSlugManual(true); }}
                placeholder="автоматически из названия"
              />
            ) : (
              <div className="input font-mono bg-gray-50 text-gray-500 cursor-not-allowed select-all">{scene.slug}</div>
            )}
          </FormRow>
        </div>

        {/* Toggles */}
        <div className="flex gap-6">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input type="checkbox" className="accent-blue-600 w-4 h-4" checked={active} onChange={e => setActive(e.target.checked)} />
            <span>Включён</span>
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input type="checkbox" className="accent-blue-600 w-4 h-4" checked={autoReply} onChange={e => setAutoReply(e.target.checked)} />
            <span>AI автоответ</span>
            <span className="text-xs text-gray-400">(без участия менеджера)</span>
          </label>
        </div>

        {/* Activation */}
        <FormRow label="Условия активации">
          <textarea
            className="input" rows={3} value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Клиент присылает список товаров с количествами или просит оформить заказ"
          />
        </FormRow>

        {/* Examples */}
        <FormRow label="Примеры сообщений">
          <textarea
            className="input" rows={3} value={examples}
            onChange={e => setExamples(e.target.value)}
            placeholder={"ПК14 3.2м, гарпун тандем 5м\nЗапустите бауф чёрный\nНужен профиль 80 метров"}
          />
        </FormRow>

        {/* Instructions for agent */}
        <FormRow label="Инструкции для агента">
          <textarea
            className="input" rows={4} value={responseTemplate}
            onChange={e => setResponseTemplate(e.target.value)}
            placeholder="Подтверди каждую позицию с ценой и наличием. Назови итоговую сумму."
          />
        </FormRow>

        {/* Escalation conditions */}
        <FormRow label="Условия эскалации">
          <textarea
            className="input" rows={3} value={escalateWhen}
            onChange={e => setEscalateWhen(e.target.value)}
            placeholder={"Клиент просит скидку\nТовара нет ни на одном складе\nКлиент недоволен"}
          />
        </FormRow>

        {/* Fields */}
        <Section
          title="Поля для сбора"
          count={fields.length}
          onAdd={() => setFields([...fields, { name: '', type: 'string', required: true, prompt: '' }])}
          emptyText="Нет полей. Агент не будет собирать данные."
        >
          {fields.map((f, i) => (
            <div key={i} className="border border-gray-200 rounded-lg p-3 bg-white">
              <div className="flex items-start gap-2">
                <div className="flex-1 space-y-2">
                  <div className="grid grid-cols-3 gap-2">
                    <input
                      className="input text-sm" placeholder="Имя (name)"
                      value={f.name}
                      onChange={e => updateAt(fields, setFields, i, 'name', e.target.value)}
                    />
                    <select
                      className="input text-sm" value={f.type || 'string'}
                      onChange={e => updateAt(fields, setFields, i, 'type', e.target.value)}
                    >
                      <option value="string">string</option>
                      <option value="number">number</option>
                      <option value="enum">enum</option>
                      <option value="phone">phone</option>
                      <option value="email">email</option>
                      <option value="address">address</option>
                      <option value="array">array</option>
                      <option value="text">text</option>
                      <option value="product_list">product_list</option>
                    </select>
                    <label className="flex items-center gap-1.5 text-xs text-gray-600">
                      <input type="checkbox" checked={f.required !== false}
                        onChange={e => updateAt(fields, setFields, i, 'required', e.target.checked)}
                      />
                      Обязательное
                    </label>
                  </div>
                  <input
                    className="input w-full text-sm" placeholder="Подсказка: Как вас зовут?"
                    value={f.prompt || ''}
                    onChange={e => updateAt(fields, setFields, i, 'prompt', e.target.value)}
                  />
                  {f.type === 'enum' && (
                    <input
                      className="input w-full text-sm"
                      placeholder="Варианты: монтажник, дилер, магазин"
                      value={(f.options || []).join(', ')}
                      onChange={e => updateAt(fields, setFields, i, 'options', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                    />
                  )}
                </div>
                <button onClick={() => removeAt(fields, setFields, i)} className="text-red-400 hover:text-red-600 text-xs mt-1">X</button>
              </div>
            </div>
          ))}
        </Section>

        {/* Tools */}
        <Section
          title="Инструменты"
          count={tools.length}
          onAdd={() => setTools([...tools, { tool: '', when: 'all_fields_collected', args: {} }])}
          emptyText="Нет инструментов. Агент ответит только из базы знаний."
        >
          {tools.map((t, i) => (
            <div key={i} className="border border-gray-200 rounded-lg p-3 bg-white">
              <div className="flex items-start gap-2">
                <div className="flex-1 space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      className="input text-sm" placeholder="Slug (check_stock)"
                      value={t.tool}
                      onChange={e => updateAt(tools, setTools, i, 'tool', e.target.value)}
                    />
                    <select
                      className="input text-sm" value={t.when || 'all_fields_collected'}
                      onChange={e => updateAt(tools, setTools, i, 'when', e.target.value)}
                    >
                      <option value="all_fields_collected">Когда все поля собраны</option>
                      <option value="always">Всегда</option>
                      <option value="on_demand">По запросу</option>
                    </select>
                  </div>
                  <input
                    className="input w-full text-sm font-mono"
                    placeholder='Аргументы: {"items": "$items"}'
                    value={typeof t.args === 'object' ? JSON.stringify(t.args) : t.args || ''}
                    onChange={e => {
                      const updated = [...tools];
                      try { updated[i] = { ...updated[i], args: JSON.parse(e.target.value) }; }
                      catch { updated[i] = { ...updated[i], args: e.target.value }; }
                      setTools(updated);
                    }}
                  />
                </div>
                <button onClick={() => removeAt(tools, setTools, i)} className="text-red-400 hover:text-red-600 text-xs mt-1">X</button>
              </div>
            </div>
          ))}
        </Section>

        {/* Knowledge base */}
        <Section
          title="База знаний"
          count={knowledge.length}
          onAdd={() => setKnowledge([...knowledge, { question: '', answer: '' }])}
          emptyText="Нет записей. Добавьте вручную."
        >
          {knowledge.map((entry, i) => (
            <div key={i} className="border border-gray-200 rounded-lg p-3 bg-white">
              <div className="flex items-start gap-2">
                <div className="flex-1 space-y-2">
                  <input
                    className="input w-full text-sm" placeholder="Вопрос клиента..."
                    value={entry.question}
                    onChange={e => updateAt(knowledge, setKnowledge, i, 'question', e.target.value)}
                  />
                  <textarea
                    className="input w-full text-sm" rows={3} placeholder="Ответ..."
                    value={entry.answer}
                    onChange={e => updateAt(knowledge, setKnowledge, i, 'answer', e.target.value)}
                  />
                </div>
                <button onClick={() => removeAt(knowledge, setKnowledge, i)} className="text-red-400 hover:text-red-600 text-xs mt-1">X</button>
              </div>
            </div>
          ))}
        </Section>

        {/* Actions */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2.5 rounded-lg text-sm">
            {error}
          </div>
        )}
        <div className="flex gap-3 pt-2">
          <button
            onClick={handleSave}
            disabled={saving || !name || (isNew && !slug)}
            className="px-6 py-2.5 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-opacity"
          >
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
          {!isNew && (
            <button
              onClick={() => onDelete(scene.slug)}
              className="px-6 py-2.5 text-red-500 border border-red-300 rounded-lg hover:bg-red-50 transition-colors"
            >
              Удалить
            </button>
          )}
        </div>
      </div>
    </main>
  );
}


/* ── Helpers ───────────────────────────────────────── */

const TRANSLIT_MAP = {
  'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i',
  'й':'y','к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t',
  'у':'u','ф':'f','х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'',
  'э':'e','ю':'yu','я':'ya',
};

function transliterate(text) {
  return text
    .toLowerCase()
    .split('')
    .map(ch => TRANSLIT_MAP[ch] ?? (ch === ' ' ? '_' : ch))
    .join('')
    .replace(/[^a-z0-9_-]/g, '')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}

function updateAt(arr, setArr, i, key, value) {
  const updated = [...arr];
  updated[i] = { ...updated[i], [key]: value };
  setArr(updated);
}

function removeAt(arr, setArr, i) {
  setArr(arr.filter((_, j) => j !== i));
}

function FormRow({ label, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</label>
      {children}
    </div>
  );
}

function Section({ title, count, onAdd, emptyText, children }) {
  return (
    <div className="border-t border-gray-200 pt-5">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold text-gray-700">{title} ({count})</h4>
        <button onClick={onAdd} className="text-xs text-blue-600 hover:text-blue-800 font-medium">+ Добавить</button>
      </div>
      {count === 0 && <p className="text-sm text-gray-400 text-center py-4">{emptyText}</p>}
      <div className="space-y-3">{children}</div>
    </div>
  );
}
