import { useEffect, useMemo, useRef, useState } from 'react';
import {
  listAliases,
  createAlias,
  updateAlias,
  deleteAlias,
  bulkDeleteAliases,
  searchProductsForSelect,
} from '../api';

/** Searchable product picker — opens a popover, forces selection from results. */
function ProductPicker({ value, onPick, invalid }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);
  const reqSeq = useRef(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

  const runSearch = (v) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      if (v.trim().length < 2) {
        setItems([]);
        return;
      }
      const myReq = ++reqSeq.current;
      setLoading(true);
      try {
        const res = await searchProductsForSelect(v);
        if (myReq !== reqSeq.current) return;
        setItems(res.items || []);
      } finally {
        if (myReq === reqSeq.current) setLoading(false);
      }
    }, 200);
  };

  const pick = (p) => {
    onPick(p.name);
    setOpen(false);
    setQ('');
    setItems([]);
  };

  const highlight = (name) => {
    const t = q.trim();
    if (!t) return name;
    const i = name.toLowerCase().indexOf(t.toLowerCase());
    if (i < 0) return name;
    return (
      <>
        {name.slice(0, i)}
        <mark className="bg-yellow-200">{name.slice(i, i + t.length)}</mark>
        {name.slice(i + t.length)}
      </>
    );
  };

  return (
    <div className="relative">
      {value ? (
        <div
          className={
            'flex items-center gap-2 border rounded px-3 py-2 text-sm ' +
            (invalid ? 'border-red-400 bg-red-50' : 'border-gray-300 bg-gray-50')
          }
        >
          <span className="flex-1 break-words" title={value}>{value}</span>
          <button
            type="button"
            onClick={() => setOpen(true)}
            className="text-xs text-blue-600 hover:underline whitespace-nowrap"
          >
            сменить
          </button>
          <button
            type="button"
            onClick={() => onPick('')}
            className="text-xs text-gray-400 hover:text-red-600"
            title="Сбросить"
          >
            ✕
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full text-left border border-dashed border-gray-300 rounded px-3 py-2 text-sm text-gray-500 hover:border-blue-400 hover:text-blue-600"
        >
          + Выбрать товар из прайса…
        </button>
      )}

      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
          />
          <div className="absolute z-50 left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-xl overflow-hidden">
            <div className="p-2 border-b border-gray-100">
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  runSearch(e.target.value);
                }}
                placeholder="Поиск по названию или артикулу (мин. 2 символа)"
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:border-blue-400 focus:outline-none"
              />
            </div>
            <div className="max-h-72 overflow-y-auto">
              {loading && (
                <div className="px-3 py-2 text-xs text-gray-400">Ищу…</div>
              )}
              {!loading && q.trim().length < 2 && (
                <div className="px-3 py-6 text-xs text-gray-400 text-center">
                  Введите хотя бы 2 символа
                </div>
              )}
              {!loading && q.trim().length >= 2 && items.length === 0 && (
                <div className="px-3 py-6 text-xs text-gray-400 text-center">
                  Ничего не найдено
                </div>
              )}
              {items.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => pick(p)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50 border-b border-gray-50 last:border-0"
                >
                  <div className="font-medium">{highlight(p.name)}</div>
                  <div className="text-xs text-gray-500">
                    {p.code} · {p.price_dealer ?? '—'} ₽
                  </div>
                </button>
              ))}
            </div>
          </div>
        </>
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
  const brokenProduct = isEdit && initial?.product_exists === false;

  const canSave = alias.trim().length > 0 && productName.trim().length > 0 && !saving;

  const save = async () => {
    setError(null);
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
            <ProductPicker
              value={productName}
              onPick={setProductName}
              invalid={brokenProduct && productName === initial?.product_name}
            />
            {brokenProduct && productName === initial?.product_name && (
              <div className="text-xs text-red-600 mt-1">
                ⚠ этот товар больше не существует в прайсе — перевыберите
              </div>
            )}
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
            disabled={!canSave}
            className="px-4 py-2 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
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
  const [modal, setModal] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [page, setPage] = useState(1);
  const pageSize = 500;
  const timer = useRef(null);
  const reqSeq = useRef(0);

  const load = async (query, pageNum) => {
    const myReq = ++reqSeq.current;
    setLoading(true);
    try {
      const res = await listAliases(query, pageSize, (pageNum - 1) * pageSize);
      if (myReq !== reqSeq.current) return;
      setItems(res.items || []);
      setTotal(res.total || 0);
      setSelected(new Set());
    } catch (e) {
      if (myReq === reqSeq.current) console.error(e);
    } finally {
      if (myReq === reqSeq.current) setLoading(false);
    }
  };

  useEffect(() => {
    load(q, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  useEffect(() => {
    load('', 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onSearch = (v) => {
    setQ(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setPage(1);
      load(v, 1);
    }, 250);
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const remove = async (id) => {
    if (!confirm('Удалить алиас?')) return;
    await deleteAlias(id);
    load(q, page);
  };

  const toggleOne = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allVisibleIds = useMemo(() => items.map((i) => i.id), [items]);
  const allSelected = allVisibleIds.length > 0 && allVisibleIds.every((id) => selected.has(id));
  const someSelected = selected.size > 0 && !allSelected;

  const toggleAll = () => {
    setSelected((prev) => {
      if (allSelected) return new Set();
      const next = new Set(prev);
      allVisibleIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const bulkRemove = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!confirm(`Удалить ${ids.length} алиасов?`)) return;
    await bulkDeleteAliases(ids);
    load(q, page);
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

      {selected.size > 0 ? (
        <div className="px-4 py-2 text-sm flex items-center gap-3 border-b border-blue-200 bg-blue-50">
          <span className="font-medium text-blue-900">Выбрано: {selected.size}</span>
          <button
            onClick={bulkRemove}
            className="px-3 py-1 text-xs rounded bg-red-600 text-white hover:bg-red-700"
          >
            Удалить
          </button>
          <button
            onClick={() => setSelected(new Set())}
            className="px-3 py-1 text-xs rounded border border-gray-300 bg-white hover:bg-gray-50"
          >
            Снять выделение
          </button>
        </div>
      ) : (
        <div className="px-4 py-2 text-xs text-gray-500 flex gap-3 border-b border-gray-100">
          <span>Всего: {total}</span>
          {broken > 0 && <span className="text-red-600">⚠ битых: {broken}</span>}
          {loading && <span>загрузка…</span>}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr className="text-left text-xs text-gray-600">
              <th className="px-3 py-2 w-8">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someSelected;
                  }}
                  onChange={toggleAll}
                />
              </th>
              <th className="px-4 py-2 font-medium">Алиас</th>
              <th className="px-4 py-2 font-medium">Товар</th>
              <th className="px-4 py-2 font-medium w-20"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr
                key={it.id}
                className={
                  'border-b border-gray-100 hover:bg-gray-50 ' +
                  (selected.has(it.id) ? 'bg-blue-50' : '')
                }
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(it.id)}
                    onChange={() => toggleOne(it.id)}
                  />
                </td>
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
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  Ничего не найдено
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > pageSize && (
        <div className="px-4 py-2 border-t border-gray-200 bg-gray-50 flex items-center justify-between text-xs text-gray-600">
          <span>
            {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, total)} из {total}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(1)}
              disabled={page === 1}
              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              «
            </button>
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ←
            </button>
            <span className="px-2">
              стр. {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              →
            </button>
            <button
              onClick={() => setPage(totalPages)}
              disabled={page >= totalPages}
              className="px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              »
            </button>
          </div>
        </div>
      )}

      {modal && (
        <AliasModal
          key={modal.id || 'new'}
          initial={modal.id ? modal : null}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load(q, page);
          }}
        />
      )}
    </div>
  );
}
