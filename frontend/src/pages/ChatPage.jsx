import { useState, useRef, useEffect } from 'react';
import { sendMessage, getConversation, deleteConversation } from '../api';

export default function ChatPage() {
  const [chatId, setChatId] = useState('test-chat-1');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedMsgId, setSelectedMsgId] = useState(null);
  const [showDebug, setShowDebug] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => { loadHistory(); }, [chatId]);
  useEffect(() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  async function loadHistory() {
    try {
      const data = await getConversation(chatId);
      const msgs = (data.messages || []).map(m => ({
        id: m.id,
        role: m.role,
        text: m.text,
        scene_slug: m.scene_slug,
        confidence: m.confidence,
        debug: m.debug
          ? { ...m.debug, tools_results: m.tools_called || [] }
          : null,
      }));
      setMessages(msgs);
      // Select last agent message
      const lastAgent = [...msgs].reverse().find(m => m.role === 'agent');
      if (lastAgent) setSelectedMsgId(lastAgent.id);
    } catch {
      setMessages([]);
    }
  }

  async function handleSend(e) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const text = input.trim();
    setInput('');
    const tempId = Date.now();
    setMessages(prev => [...prev, { role: 'client', text, id: tempId }]);
    setLoading(true);
    setSelectedMsgId(null);

    const agentId = Date.now() + 1;
    // Placeholder "thinking" message — narrative lines accumulate as events arrive
    setMessages(prev => [
      ...prev,
      { role: 'agent', text: '', id: agentId, streaming: true, debug: {}, thinking: ['⋯ Думаю над вашим запросом…'] },
    ]);
    setSelectedMsgId(agentId);

    const updateAgent = (patch) => {
      setMessages(prev => prev.map(m => m.id === agentId ? { ...m, ...patch, debug: { ...(m.debug || {}), ...(patch.debug || {}) } } : m));
    };

    const fmtItems = (items) => {
      if (!items || !Array.isArray(items) || items.length === 0) return null;
      return items.map(it => {
        const name = it.name || it.query_name || '';
        const qty = it.qty || it.quantity;
        return qty ? `${name} (${qty})` : name;
      }).join('; ');
    };

    try {
      const resp = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: chatId, message: text }),
      });
      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split('\n\n');
        buf = parts.pop();
        for (const chunk of parts) {
          const line = chunk.split('\n').find(l => l.startsWith('data: '));
          if (!line) continue;
          const ev = JSON.parse(line.slice(6));
          if (ev.type === 'triage') {
            const items = ev.triage?.extracted?.items || ev.triage?.extracted?.positions;
            const summary = fmtItems(items) || ev.triage?.scene || 'нет позиций';
            updateAgent({
              scene_slug: ev.triage?.scene,
              confidence: ev.triage?.confidence,
              thinking: [
                `✓ Разобрано: ${summary}`,
                '⋯ Ищу в прайсе…',
              ],
              debug: { triage: ev.triage, scene_decision: ev.scene_decision, classifier_tokens: ev.classifier_tokens },
            });
          } else if (ev.type === 'tools') {
            const search = (ev.tools_results || []).find(t => t.tool_slug === 'search_products');
            const nItems = search?.data?.items?.length || 0;
            const totalCands = (search?.data?.items || []).reduce((s, it) => s + (it.candidates?.length || 0), 0);
            setMessages(prev => prev.map(m => {
              if (m.id !== agentId) return m;
              const kept = (m.thinking || []).filter(l => l.startsWith('✓'));
              return {
                ...m,
                scene_slug: ev.scene_slug,
                debug: { ...(m.debug || {}), tools_results: ev.tools_results, scene_name: ev.scene_name, scene_data: ev.scene_data },
                thinking: [
                  ...kept,
                  `✓ Найдено ${nItems} позиций${totalCands ? ` (${totalCands} кандидатов)` : ''}`,
                  '⋯ Формулирую ответ…',
                ],
              };
            }));
          } else if (ev.type === 'done') {
            updateAgent({
              text: ev.response,
              streaming: false,
              thinking: undefined,
              scene_slug: ev.scene_slug,
              confidence: ev.confidence,
              debug: {
                triage: ev.triage,
                scene_slug: ev.scene_slug,
                scene_name: ev.scene_name,
                confidence: ev.confidence,
                action: ev.action,
                scene_decision: ev.scene_decision,
                tools_results: ev.tools_results,
                scene_data: ev.scene_data,
                latency_ms: ev.latency_ms,
                classifier_tokens: ev.classifier_tokens,
                responder_tokens: ev.responder_tokens,
                cost_usd: ev.cost_usd,
                escalation_card: ev.escalation_card,
              },
            });
          } else if (ev.type === 'error') {
            updateAgent({ text: `Ошибка: ${ev.error}`, streaming: false });
          }
        }
      }
    } catch (err) {
      updateAgent({ text: `Ошибка: ${err.message}`, streaming: false });
    } finally {
      setLoading(false);
    }
  }

  async function handleReset() {
    if (!confirm('Сбросить чат?')) return;
    try { await deleteConversation(chatId); } catch {}
    setMessages([]);
    setSelectedMsgId(null);
  }

  const selectedDebug = messages.find(m => m.id === selectedMsgId)?.debug || null;

  return (
    <>
      {/* Chat panel */}
      <div className="flex-1 flex flex-col min-h-0">
        <div className="p-4 border-b border-gray-200 bg-white flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-800">Тестовый чат</h2>
            <p className="text-xs text-gray-500">ID: {chatId}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setShowDebug(!showDebug)}
              className="px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 rounded text-gray-600"
            >
              {showDebug ? 'Скрыть отладку' : 'Отладка'}
            </button>
            <button
              onClick={handleReset}
              className="px-3 py-1.5 text-xs bg-red-50 hover:bg-red-100 rounded text-red-600"
            >
              Сбросить чат
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-center text-gray-400 mt-20">
              <p className="text-4xl mb-3">💬</p>
              <p>Напишите сообщение как клиент</p>
              <p className="text-xs mt-1">Например: "ПК14 3.2м есть на востоке?"</p>
            </div>
          )}
          {messages.map((msg) => (
            <AgentMessage
              key={msg.id}
              msg={msg}
              selected={selectedMsgId === msg.id}
              onSelect={() => msg.debug && setSelectedMsgId(msg.id)}
            />
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-white border border-gray-200 px-4 py-2.5 rounded-2xl rounded-bl-sm">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.1s]" />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                </div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <form onSubmit={handleSend} className="p-4 bg-white border-t border-gray-200">
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Напишите как клиент..."
              className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="px-5 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Отправить
            </button>
          </div>
        </form>
      </div>

      {/* Debug panel */}
      {showDebug && (
        <div className="fixed inset-0 z-20 bg-gray-900 text-gray-100 overflow-y-auto">
          <div className="p-4 border-b border-gray-700 flex items-center justify-between">
            <h3 className="font-semibold text-sm">Отладка</h3>
            <button
              onClick={() => setShowDebug(false)}
              className="text-gray-400 hover:text-white text-lg leading-none px-2"
              aria-label="Закрыть"
            >×</button>
          </div>
          {selectedDebug ? (
            <div className="p-4 space-y-4 text-xs font-mono">
              <DebugSection title="Triage">
                <Row label="action" value={selectedDebug.triage?.action} color="text-cyan-400" />
                <Row label="сценарий" value={selectedDebug.scene_slug || selectedDebug.triage?.scene} color="text-green-400" />
                <Row label="confidence" value={selectedDebug.confidence?.toFixed?.(2) || selectedDebug.confidence} color="text-yellow-400" />
                <Row label="action result" value={selectedDebug.action} color={
                  selectedDebug.action === 'auto_reply' ? 'text-green-400' :
                  selectedDebug.action === 'escalation' ? 'text-orange-400' : 'text-blue-400'
                } />
                <div className="mt-1 text-gray-400">{selectedDebug.triage?.reason}</div>
                {selectedDebug.triage?.extracted && Object.keys(selectedDebug.triage.extracted).length > 0 && (
                  <pre className="mt-1 text-gray-500 whitespace-pre-wrap text-[10px]">
                    {JSON.stringify(selectedDebug.triage.extracted, null, 2)}
                  </pre>
                )}
              </DebugSection>

              {selectedDebug.tools_results?.length > 0 && (
                <DebugSection title="Tools">
                  {selectedDebug.tools_results.map((t, i) => (
                    <div key={i} className="mb-2">
                      <div>{t.success ? '✅' : '❌'} {t.tool_slug} <span className="text-gray-500">({t.latency_ms}ms)</span></div>
                      <pre className="text-gray-500 whitespace-pre-wrap text-[10px] mt-0.5">
                        {JSON.stringify(t.data, null, 2)}
                      </pre>
                    </div>
                  ))}
                </DebugSection>
              )}

              {selectedDebug.scene_data && Object.keys(selectedDebug.scene_data).length > 0 && (
                <DebugSection title="Extracted Data">
                  <pre className="text-gray-400 whitespace-pre-wrap text-[10px]">
                    {JSON.stringify(selectedDebug.scene_data, null, 2)}
                  </pre>
                </DebugSection>
              )}

              <DebugSection title="Metrics">
                <Row label="latency" value={`${selectedDebug.latency_ms}ms`} />
                <Row label="triage tokens" value={selectedDebug.classifier_tokens} />
                <Row label="responder tokens" value={selectedDebug.responder_tokens} />
                <Row label="cost" value={`$${selectedDebug.cost_usd?.toFixed?.(5) || '0'}`} />
              </DebugSection>

              {selectedDebug.escalation_card && (
                <DebugSection title="Escalation">
                  <pre className="text-orange-300 whitespace-pre-wrap text-[10px]">
                    {selectedDebug.escalation_card}
                  </pre>
                </DebugSection>
              )}
            </div>
          ) : (
            <div className="p-4 text-gray-500 text-sm">
              {messages.length === 0
                ? 'Отправьте сообщение чтобы увидеть отладку'
                : 'Кликните на ответ агента чтобы увидеть отладку'}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function AgentMessage({ msg, selected, onSelect }) {
  const [expanded, setExpanded] = useState(false);

  if (msg.role === 'client') {
    return (
      <div className="flex justify-end">
        <div className="max-w-md px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap bg-blue-600 text-white rounded-br-sm">
          {msg.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <div
        onClick={onSelect}
        className={`max-w-md px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm whitespace-pre-wrap transition-all bg-white border text-gray-800 ${
          msg.debug ? 'cursor-pointer hover:shadow-md' : ''
        } ${selected ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'}`}
      >
        {msg.text ? msg.text : msg.streaming ? (
          <div className="text-gray-400 italic text-[13px] space-y-0.5">
            {(msg.thinking || []).map((line, i) => (
              <div key={i} className={line.startsWith('⋯') ? 'animate-pulse' : ''}>{line}</div>
            ))}
          </div>
        ) : null}
        {msg.debug && !msg.streaming && (
          <div className="mt-1.5 flex items-center gap-2 text-xs opacity-50">
            {msg.scene_slug && <span>{msg.scene_slug}</span>}
            {msg.confidence > 0 && <span>{(msg.confidence * 100).toFixed(0)}%</span>}
            {msg.debug?.action && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                msg.debug.action === 'auto_reply' ? 'bg-green-50 text-green-600' :
                msg.debug.action === 'escalation' ? 'bg-orange-50 text-orange-600' :
                msg.debug.action === 'resolved' ? 'bg-blue-50 text-blue-600' : ''
              }`}>
                {msg.debug.action}
              </span>
            )}
          </div>
        )}
      </div>
      {msg.debug && !msg.streaming && (
        <>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[10px] text-gray-400 hover:text-gray-600 px-2 py-0.5 rounded"
          >
            {expanded ? '▾ Скрыть отладку' : '▸ Отладка'}
          </button>
          {expanded && <InlineDebug debug={msg.debug} />}
        </>
      )}
    </div>
  );
}

function InlineDebug({ debug, streaming }) {
  const extracted = debug.triage?.extracted || {};
  const items = extracted.items || extracted.positions || null;
  const searchResult = (debug.tools_results || []).find(t => t.tool_slug === 'search_products');
  const searchItems = searchResult?.data?.items || [];

  const triageReady = !!debug.triage;
  const toolsReady = !!searchResult || (debug.tools_results && debug.tools_results.length > 0);
  const responderReady = !streaming;

  return (
    <div className="max-w-2xl w-full bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs space-y-3">
      {/* Stage 1: Triage */}
      <Stage
        num={1}
        title="Разбор сообщения (Triage LLM)"
        meta={triageReady ? `${debug.triage?.action || '—'} · ${debug.scene_slug || '—'} · ${((debug.confidence || 0) * 100).toFixed(0)}%` : 'ожидание…'}
        dim={!triageReady}
      >
        {debug.triage?.reason && (
          <div className="text-gray-500 italic mb-1.5">{debug.triage.reason}</div>
        )}
        {items && Array.isArray(items) && items.length > 0 ? (
          <table className="w-full text-[11px] font-mono border-collapse">
            <thead>
              <tr className="text-gray-400 text-left border-b border-gray-200">
                <th className="py-1 pr-2 w-6 font-normal">#</th>
                <th className="py-1 pr-2 font-normal">Название</th>
                <th className="py-1 pr-2 w-24 font-normal">Кол-во</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => {
                const qty = it.qty || it.quantity;
                return (
                  <tr key={i} className="border-b border-gray-100 last:border-0">
                    <td className="py-1 pr-2 text-gray-400">{i + 1}</td>
                    <td className="py-1 pr-2 text-gray-800">{it.name || it.query_name || JSON.stringify(it)}</td>
                    <td className="py-1 pr-2 text-gray-600">{qty || <span className="text-gray-300">—</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : Object.keys(extracted).length > 0 ? (
          <pre className="font-mono text-[10px] text-gray-700 whitespace-pre-wrap">
            {JSON.stringify(extracted, null, 2)}
          </pre>
        ) : (
          <div className="text-gray-400">— нет извлечённых данных</div>
        )}
      </Stage>

      {/* Stage 2: Search */}
      {(searchResult || streaming) && (
        <Stage
          num={2}
          title="Результаты поиска по прайсу"
          meta={searchResult ? `${searchResult.success ? '✓' : '✗'} ${searchItems.length} позиций · ${searchResult.latency_ms}ms` : 'ожидание…'}
          dim={!toolsReady}
        >
          {searchItems.length > 0 ? (
            <div className="space-y-2">
              {searchItems.map((item, i) => (
                <div key={i} className="border-l-2 border-gray-300 pl-2">
                  <div className="font-medium text-gray-800">
                    «{item.query_name}» {item.qty && <span className="text-gray-500">· {item.qty}</span>}
                    {item.ambiguous && <span className="ml-2 text-orange-600 text-[10px]">AMBIGUOUS ({item.close_count})</span>}
                  </div>
                  {item.candidates && item.candidates.length > 0 ? (
                    <div className="mt-1 space-y-0.5">
                      {item.candidates.slice(0, 5).map((c, j) => (
                        <div key={j} className="font-mono text-[10px] text-gray-600 flex items-baseline gap-2">
                          <span className="text-gray-400 w-8">{c.distance?.toFixed?.(3) || '—'}</span>
                          <span className="flex-1">{c.name}</span>
                          {c.price_dealer != null && <span className="text-gray-500">{c.price_dealer}₽</span>}
                        </div>
                      ))}
                      {item.candidates.length > 5 && (
                        <div className="text-[10px] text-gray-400">…и ещё {item.candidates.length - 5}</div>
                      )}
                    </div>
                  ) : (
                    <div className="text-gray-400 text-[10px] mt-0.5">нет кандидатов</div>
                  )}
                  {item.computed && (
                    <div className="text-[10px] text-green-700 mt-0.5">
                      готовый расчёт: {item.computed.pieces} {item.computed.unit_label} × {item.computed.unit_price}₽ = {item.computed.total_price}₽
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-400">— нет результатов</div>
          )}
        </Stage>
      )}

      {/* Stage 3: Responder */}
      <Stage
        num={3}
        title="Ответ Responder LLM"
        meta={responderReady ? `${debug.responder_tokens || 0} токенов · $${(debug.cost_usd || 0).toFixed(5)} · ${debug.latency_ms}ms` : 'генерация…'}
        dim={!responderReady}
      >
        <div className="text-gray-500 text-[10px]">
          Итоговый ответ клиенту показан в сообщении выше. Здесь — что LLM выбрала из кандидатов.
        </div>
        {debug.escalation_card && (
          <pre className="mt-2 p-2 bg-orange-50 text-orange-800 whitespace-pre-wrap text-[10px] rounded">
            {debug.escalation_card}
          </pre>
        )}
      </Stage>
    </div>
  );
}

function Stage({ num, title, meta, children, dim }) {
  return (
    <div className={dim ? 'opacity-40' : ''}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-white text-[10px] font-semibold ${dim ? 'bg-gray-400' : 'bg-blue-600'}`}>{num}</span>
          <span className="font-medium text-gray-700">{title}</span>
        </div>
        {meta && <span className="text-[10px] text-gray-500 font-mono">{meta}</span>}
      </div>
      <div className="pl-6">{children}</div>
    </div>
  );
}

function DebugSection({ title, children }) {
  return (
    <div>
      <div className="text-gray-500 uppercase tracking-wider mb-1 text-[10px]">{title}</div>
      <div className="bg-gray-800 rounded p-2.5">{children}</div>
    </div>
  );
}

function Row({ label, value, color = 'text-gray-300' }) {
  if (value === undefined || value === null) return null;
  return (
    <div>
      <span className="text-gray-500">{label}: </span>
      <span className={color}>{value}</span>
    </div>
  );
}
