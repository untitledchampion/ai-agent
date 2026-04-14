import { useState } from 'react';

export default function SyncPage() {
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setError(null);
    setRunning(true);
    try {
      const res = await fetch('/api/sync/products', { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
      setReport(await res.json());
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <h2 className="text-xl font-semibold mb-4">Синхронизация с 1С</h2>

      <div className="border border-gray-200 rounded-lg p-4 mb-4">
        <p className="text-sm text-gray-600 mb-3">
          Подтягивает номенклатуру из 1С УНФ (<code>Catalog_Номенклатура</code>),
          обновляет локальную базу товаров и пересчитывает эмбеддинги для поиска.
        </p>
        <button
          onClick={run}
          disabled={running}
          className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {running ? 'Синхронизирую…' : 'Синхронизировать сейчас'}
        </button>
        {error && (
          <div className="mt-3 text-sm text-red-600 whitespace-pre-wrap">{error}</div>
        )}
      </div>

      {report && (
        <div className="border border-gray-200 rounded-lg p-4 space-y-2 text-sm">
          <h3 className="font-semibold">Результат:</h3>
          <div>Всего в 1С: <b>{report.total_1c}</b></div>
          <div className="text-green-700">✓ Обновлено: <b>{report.updated}</b></div>
          <div className="text-green-700">✓ Добавлено: <b>{report.added}</b></div>
          <div className="text-amber-700">⚠ Осиротело (нет в 1С): <b>{report.orphaned}</b></div>
          {report.orphaned_aliases > 0 && (
            <div className="text-red-700">
              ⚠ Алиасов к осиротевшим товарам: <b>{report.orphaned_aliases}</b>
              <span className="text-gray-500 ml-2">
                (перемапить во вкладке «База знаний»)
              </span>
            </div>
          )}
          <div className="text-gray-500 text-xs pt-2">
            Время: {report.duration_sec}с
          </div>
        </div>
      )}
    </div>
  );
}
