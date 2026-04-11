import { useState, useEffect } from 'react';
import { getTone, updateTone, previewTonePrompt } from '../api';

export default function TonePage() {
  const [tone, setTone] = useState(null);
  const [preview, setPreview] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => { load(); }, []);

  async function load() {
    const data = await getTone();
    setTone(data);
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateTone(tone);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
    setSaving(false);
  }

  async function handlePreview() {
    const data = await previewTonePrompt();
    setPreview(data.prompt_block);
  }

  if (!tone) return <div className="p-8 text-gray-500">Загрузка...</div>;

  const params = tone.parameters || {};

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Настройка тона</h2>
          <p className="text-sm text-gray-500">Как агент разговаривает с клиентами</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handlePreview}
            className="px-4 py-2 text-sm bg-gray-100 hover:bg-gray-200 rounded text-gray-600"
          >
            Предпросмотр промпта
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {saved ? '✓ Сохранено' : saving ? '...' : 'Сохранить'}
          </button>
        </div>
      </div>

      <div className="space-y-6">
        {/* Persona */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <label className="text-sm font-medium text-gray-700 block mb-2">Персона</label>
          <input
            className="input"
            value={tone.persona}
            onChange={e => setTone({...tone, persona: e.target.value})}
            placeholder="Менеджер отдела продаж..."
          />
        </div>

        {/* Parameters */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-4">Параметры стиля</h3>
          <div className="space-y-4">
            <SliderParam
              label="Формальность"
              left="разговорный" right="формальный"
              value={params.formality || 2}
              onChange={v => setTone({...tone, parameters: {...params, formality: v}})}
            />
            <SliderParam
              label="Краткость"
              left="подробный" right="краткий"
              value={params.brevity || 4}
              onChange={v => setTone({...tone, parameters: {...params, brevity: v}})}
            />
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox" checked={params.emoji || false}
                  onChange={e => setTone({...tone, parameters: {...params, emoji: e.target.checked}})}
                  className="rounded"
                />
                Эмодзи
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-600">
                <input
                  type="checkbox" checked={params.signature || false}
                  onChange={e => setTone({...tone, parameters: {...params, signature: e.target.checked}})}
                  className="rounded"
                />
                Подпись
              </label>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Обращение</label>
              <select
                className="input w-48"
                value={params.address || 'ты/вы по контексту'}
                onChange={e => setTone({...tone, parameters: {...params, address: e.target.value}})}
              >
                <option>на ты</option>
                <option>на вы</option>
                <option>ты/вы по контексту</option>
              </select>
            </div>
          </div>
        </div>

        {/* Rules */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Правила</h3>
          <ListEditor
            items={tone.rules || []}
            onChange={rules => setTone({...tone, rules})}
            placeholder="Новое правило..."
          />
        </div>

        {/* Examples */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Примеры эталонных ответов</h3>
          {(tone.examples || []).map((ex, i) => (
            <div key={i} className="flex gap-2 mb-3 items-start">
              <div className="flex-1 space-y-1">
                <input
                  className="input text-xs"
                  value={ex.client}
                  onChange={e => {
                    const examples = [...tone.examples];
                    examples[i] = {...ex, client: e.target.value};
                    setTone({...tone, examples});
                  }}
                  placeholder="Клиент:"
                />
                <input
                  className="input text-xs"
                  value={ex.agent}
                  onChange={e => {
                    const examples = [...tone.examples];
                    examples[i] = {...ex, agent: e.target.value};
                    setTone({...tone, examples});
                  }}
                  placeholder="Ответ:"
                />
              </div>
              <button
                onClick={() => {
                  const examples = tone.examples.filter((_, j) => j !== i);
                  setTone({...tone, examples});
                }}
                className="text-red-400 hover:text-red-600 text-xs mt-1"
              >
                x
              </button>
            </div>
          ))}
          <button
            onClick={() => setTone({...tone, examples: [...(tone.examples || []), {client: '', agent: ''}]})}
            className="text-xs text-blue-600 hover:text-blue-800"
          >
            + Добавить пример
          </button>
        </div>

        {/* Forbidden phrases */}
        <div className="bg-white rounded-lg border border-gray-200 p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Запретные фразы</h3>
          <ListEditor
            items={tone.forbidden_phrases || []}
            onChange={forbidden_phrases => setTone({...tone, forbidden_phrases})}
            placeholder="Новая запретная фраза..."
          />
        </div>
      </div>

      {/* Preview modal */}
      {preview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setPreview('')}>
          <div className="bg-gray-900 text-gray-100 rounded-lg p-6 max-w-2xl max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="font-semibold mb-3">Блок тона в промпте LLM</h3>
            <pre className="text-xs font-mono whitespace-pre-wrap">{preview}</pre>
            <button onClick={() => setPreview('')} className="mt-4 px-4 py-2 bg-gray-700 rounded text-sm hover:bg-gray-600">
              Закрыть
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SliderParam({ label, left, right, value, onChange }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 mb-1">
        <span>{label}</span>
        <span>{value}/5</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-400 w-20 text-right">{left}</span>
        <input
          type="range" min={1} max={5} value={value}
          onChange={e => onChange(parseInt(e.target.value))}
          className="flex-1"
        />
        <span className="text-xs text-gray-400 w-20">{right}</span>
      </div>
    </div>
  );
}

function ListEditor({ items, onChange, placeholder }) {
  const [newItem, setNewItem] = useState('');
  return (
    <div>
      {items.map((item, i) => (
        <div key={i} className="flex items-center gap-2 mb-1">
          <span className="text-sm text-gray-600 flex-1">{item}</span>
          <button
            onClick={() => onChange(items.filter((_, j) => j !== i))}
            className="text-red-400 hover:text-red-600 text-xs"
          >
            x
          </button>
        </div>
      ))}
      <div className="flex gap-2 mt-2">
        <input
          className="input text-xs flex-1"
          value={newItem}
          onChange={e => setNewItem(e.target.value)}
          placeholder={placeholder}
          onKeyDown={e => {
            if (e.key === 'Enter' && newItem.trim()) {
              onChange([...items, newItem.trim()]);
              setNewItem('');
            }
          }}
        />
        <button
          onClick={() => { if (newItem.trim()) { onChange([...items, newItem.trim()]); setNewItem(''); } }}
          className="text-xs text-blue-600 hover:text-blue-800"
        >
          +
        </button>
      </div>
    </div>
  );
}
