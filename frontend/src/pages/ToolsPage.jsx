import { useState, useEffect } from 'react';
import { getTools, updateTool, createTool, deleteTool } from '../api';

export default function ToolsPage() {
  const [tools, setTools] = useState([]);
  const [editing, setEditing] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    try { setTools(await getTools()); } catch (e) { console.error(e); }
    setLoading(false);
  }

  async function toggleActive(tool) {
    await updateTool(tool.slug, { active: !tool.active });
    load();
  }

  async function handleDelete(slug) {
    if (!confirm(`Удалить инструмент "${slug}"?`)) return;
    await deleteTool(slug);
    load();
  }

  if (loading) return <div className="p-8 text-gray-500">Загрузка...</div>;

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-800">Инструменты</h2>
          <p className="text-sm text-gray-500">Внешние API и сервисы, которые агент может вызывать</p>
        </div>
        <button
          onClick={() => setEditing({ slug: '', name: '', description: '', active: true, request: {}, response_mapping: {}, fallback_message: '', timeout_ms: 5000, retry_count: 1, _isNew: true })}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
        >
          + Новый инструмент
        </button>
      </div>

      {editing && (
        <ToolEditor
          tool={editing}
          onSave={async (data) => {
            if (data._isNew) {
              const { _isNew, ...rest } = data;
              await createTool(rest);
            } else {
              await updateTool(data.slug, data);
            }
            setEditing(null);
            load();
          }}
          onCancel={() => setEditing(null)}
        />
      )}

      <div className="space-y-3">
        {tools.map((tool) => (
          <div
            key={tool.slug}
            className={`bg-white rounded-lg border p-4 ${tool.active ? 'border-gray-200' : 'border-gray-100 opacity-60'}`}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-gray-800">{tool.name}</h3>
                  <span className="text-xs text-gray-400 font-mono">{tool.slug}</span>
                </div>
                <p className="text-sm text-gray-500 mt-1">{tool.description}</p>
                <div className="flex gap-4 mt-2 text-xs text-gray-400">
                  {tool.request?.url && (
                    <span>{tool.request.method || 'GET'} {tool.request.url}</span>
                  )}
                  {!tool.request?.url && <span>Встроенный (мок)</span>}
                  <span>Timeout: {tool.timeout_ms}ms</span>
                  <span>Retry: {tool.retry_count}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 ml-4">
                <button
                  onClick={() => toggleActive(tool)}
                  className={`px-3 py-1 text-xs rounded ${tool.active ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-500'}`}
                >
                  {tool.active ? 'Вкл' : 'Выкл'}
                </button>
                <button
                  onClick={() => setEditing(tool)}
                  className="px-3 py-1 text-xs bg-gray-100 hover:bg-gray-200 rounded text-gray-600"
                >
                  Править
                </button>
                <button
                  onClick={() => handleDelete(tool.slug)}
                  className="px-3 py-1 text-xs bg-red-50 hover:bg-red-100 rounded text-red-500"
                >
                  X
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ToolEditor({ tool, onSave, onCancel }) {
  const [data, setData] = useState({ ...tool });
  const [requestJson, setRequestJson] = useState(JSON.stringify(tool.request || {}, null, 2));
  const [mappingJson, setMappingJson] = useState(JSON.stringify(tool.response_mapping || {}, null, 2));

  function handleSave() {
    let request, response_mapping;
    try { request = JSON.parse(requestJson); } catch { alert('Невалидный JSON запроса'); return; }
    try { response_mapping = JSON.parse(mappingJson); } catch { alert('Невалидный JSON маппинга'); return; }
    onSave({ ...data, request, response_mapping });
  }

  return (
    <div className="bg-white rounded-lg border border-blue-200 p-6 mb-6 shadow-sm">
      <h3 className="font-semibold text-gray-800 mb-4">
        {data._isNew ? 'Новый инструмент' : `Редактирование: ${data.name}`}
      </h3>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {data._isNew && (
          <Field label="Slug (id)">
            <input className="input" value={data.slug} onChange={e => setData({...data, slug: e.target.value})} />
          </Field>
        )}
        <Field label="Название">
          <input className="input" value={data.name} onChange={e => setData({...data, name: e.target.value})} />
        </Field>
      </div>

      <Field label="Описание" className="mb-4">
        <textarea className="input h-16" value={data.description} onChange={e => setData({...data, description: e.target.value})} />
      </Field>

      <Field label="HTTP запрос (JSON)" className="mb-4">
        <textarea className="input h-32 font-mono text-xs" value={requestJson} onChange={e => setRequestJson(e.target.value)} />
      </Field>

      <Field label="Маппинг ответа (JSON)" className="mb-4">
        <textarea className="input h-20 font-mono text-xs" value={mappingJson} onChange={e => setMappingJson(e.target.value)} />
      </Field>

      <Field label="Fallback сообщение" className="mb-4">
        <input className="input" value={data.fallback_message} onChange={e => setData({...data, fallback_message: e.target.value})} />
      </Field>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <Field label="Timeout (ms)">
          <input className="input" type="number" value={data.timeout_ms} onChange={e => setData({...data, timeout_ms: parseInt(e.target.value)})} />
        </Field>
        <Field label="Retries">
          <input className="input" type="number" value={data.retry_count} onChange={e => setData({...data, retry_count: parseInt(e.target.value)})} />
        </Field>
      </div>

      <div className="flex gap-2 justify-end">
        <button onClick={onCancel} className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded">Отмена</button>
        <button onClick={handleSave} className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700">Сохранить</button>
      </div>
    </div>
  );
}

function Field({ label, className = '', children }) {
  return (
    <label className={`block ${className}`}>
      <span className="text-xs font-medium text-gray-600 block mb-1">{label}</span>
      {children}
    </label>
  );
}
