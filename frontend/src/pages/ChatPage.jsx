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
        debug: m.debug || null,
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

    try {
      const res = await sendMessage(chatId, text);
      const agentId = Date.now() + 1;
      setMessages(prev => [
        ...prev,
        {
          role: 'agent',
          text: res.response,
          id: agentId,
          scene_slug: res.scene_slug,
          confidence: res.confidence,
          debug: {
            triage: res.triage,
            scene_slug: res.scene_slug,
            scene_name: res.scene_name,
            confidence: res.confidence,
            action: res.action,
            scene_decision: res.scene_decision,
            tools_results: res.tools_results,
            scene_data: res.scene_data,
            latency_ms: res.latency_ms,
            classifier_tokens: res.classifier_tokens,
            responder_tokens: res.responder_tokens,
            cost_usd: res.cost_usd,
            escalation_card: res.escalation_card,
          },
        },
      ]);
      setSelectedMsgId(agentId);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: 'agent', text: `Ошибка: ${err.message}`, id: Date.now() + 1 },
      ]);
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
    <div className="h-full flex">
      {/* Chat panel */}
      <div className="flex-1 flex flex-col">
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
            <div
              key={msg.id}
              className={`flex ${msg.role === 'client' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                onClick={() => msg.debug && setSelectedMsgId(msg.id)}
                className={`max-w-md px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap transition-all ${
                  msg.role === 'client'
                    ? 'bg-blue-600 text-white rounded-br-sm'
                    : `bg-white border text-gray-800 rounded-bl-sm ${
                        msg.debug ? 'cursor-pointer hover:shadow-md' : ''
                      } ${selectedMsgId === msg.id ? 'border-blue-400 ring-2 ring-blue-100' : 'border-gray-200'}`
                }`}
              >
                {msg.text}
                {msg.role === 'agent' && (
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
            </div>
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
        <div className="fixed inset-0 z-20 bg-gray-900 text-gray-100 overflow-y-auto sm:static sm:inset-auto sm:w-96 sm:border-l sm:border-gray-700 sm:shrink-0">
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
