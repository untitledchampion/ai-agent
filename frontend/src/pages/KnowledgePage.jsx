import { useEffect, useMemo, useRef, useState } from 'react';
import {
  listAliases,
  createAlias,
  updateAlias,
  deleteAlias,
  searchProductsForSelect,
} from '../api';

function ProductPicker({ value, onChange, autoFocus }) {
  const [q, setQ] = useState(value || '');
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    setQ(value || '');
  }, [value]);

  const handleChange = (v) => {
    setQ(v);
    onChange(v);
    setOpen(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      if (v.trim().length < 2) {
        setItems([]);
        return;
      }
      try {
        const res = await searchProductsForSelect(v);
        setItems(res.items || []);
      } catch (e) {
        setItems([]);
      }
    }, 200);
  };

  return (
    <div className="relative">
      <input
        autoFocus={autoFocus}
        value={q}
        onChange={(e) => handleChange(e.target.value)}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Название товара из прайса"
        className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
      />
      {open && items.length > 0 && (
        <div className="absolute z-10 left-0 right-0 bg-white border border-gray-200 rounded shadow-lg mt-1 max-h-64 overflow-y-auto">
          {items.map((p) => (
            <div
              key={p.id}
              onMouseDown={() => {
                setQ(p.name);
                onChange(p.name);
                setOpen(false);
              }}
              className="px-3 py-2 text-sm hover:bg-gray-50 cursor-pointer border-b border-gray-100 last:border-0"
            >
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-gray-500">
                {p.code} · {p.price_dealer ?? '—'} ₽
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AliasModal({ initial, onClose, onSaved }) {
  const [alias, setAlias] = useState(initial?.alias || '');
  const [productName, setProductName] = useState(initial?.product_name || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const isEdit = !!initial?.id;

  const save = async () => {
    setError(null);
    if (!alias.trim() || !productName.trim()) {
      setError('Заполните оба поля');
      return;
    }
    setSaving(true);
    try {
      if (isEdit) {
        await updateAlias(initial.id, { alias, product_name: productName });
      } else {
        await createAlias({ alias, product_name: productName });
      }
      onSaved();
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5">
        <h3 className="text-lg font-semibold mb-4">
          {isEdit ? 'Редактировать алиас' : 'Новый алиас'}
        </h3>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-gray-600 block mb-1">
              Как пишет клиент (алиас)
            </label>
            <input
              autoFocus={!isEdit}
              value={alias}
              onChange={(e) => setAlias(e.target.value)}
              placeholder='напр. "краб 2м"'
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-gray-600 block mb-1">
              Товар в прайсе
            </label>
            <ProductPicker value={productName} onChange={setProductName} />
          </div>
          {error && <div className="text-sm text-red-600">{error}</div>}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded border border-gray-300 hover:bg-gray-50"
          >
            Отмена
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Сохраняю…' : 'Сохранить'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(null); // null | {} | {id, alias, product_name}
  const timer = useRef(null);

  const load = async (query = q) => {
    setLoading(true);
    try {
      const res = await listAliases(query, 500);
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load('');
  }, []);

  const onSearch = (v) => {
    setQ(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => load(v), 250);
  };

  const remove = async (id) => {
    if (!confirm('Удалить алиас?')) return;
    await deleteAlias(id);
    load();
  };

  const broken = useMemo(() => items.filter((x) => !x.product_exists).length, [items]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-3">
        <input
          value={q}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Поиск по алиасу или товару…"
          className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm"
        />
        <button
          onClick={() => setModal({})}
          className="px-3 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 whitespace-nowrap"
        >
          + Добавить
        </button>
      </div>

      <div className="px-4 py-2 text-xs text-gray-500 flex gap-3 border-b border-gray-100">
        <span>Всего: {total}</span>
        {broken > 0 && (
          <span className="text-red-600">⚠ битых: {broken}</span>
        )}
        {loading && <span>загрузка…</span>}
      </div>

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr className="text-left text-xs text-gray-600">
              <th className="px-4 py-2 font-medium">Алиас</th>
              <th className="px-4 py-2 font-medium">Товар</th>
              <th className="px-4 py-2 font-medium w-20"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-4 py-2 font-mono">{it.alias}</td>
                <td className="px-4 py-2">
                  {!it.product_exists && (
                    <span className="text-red-600 mr-1" title="Товар не найден в прайсе">
                      ⚠
                    </span>
                  )}
                  {it.product_name}
                </td>
                <td className="px-4 py-2 text-right whitespace-nowrap">
                  <button
                    onClick={() => setModal(it)}
                    className="text-blue-600 hover:underline text-xs mr-2"
                  >
                    ред.
                  </button>
                  <button
                    onClick={() => remove(it.id)}
                    className="text-red-600 hover:underline text-xs"
                  >
                    удал.
                  </button>
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                  Ничего не найдено
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {modal && (
        <AliasModal
          initial={modal.id ? modal : null}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      )}
    </div>
  );
}
