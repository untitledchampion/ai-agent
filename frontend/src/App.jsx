import { useState } from 'react';
import ChatPage from './pages/ChatPage';
import KnowledgePage from './pages/KnowledgePage';
import ScenesPage from './pages/ScenesPage';
import ToolsPage from './pages/ToolsPage';
import TonePage from './pages/TonePage';
import SyncPage from './pages/SyncPage';

const TABS = [
  { id: 'chat', label: 'Чат', component: ChatPage },
  { id: 'knowledge', label: 'База знаний', component: KnowledgePage },
  { id: 'scenes', label: 'Сценарии', component: ScenesPage },
  { id: 'tools', label: 'Инструменты', component: ToolsPage },
  { id: 'tone', label: 'Тон', component: TonePage },
  { id: 'sync', label: 'Синхронизация', component: SyncPage },
];

export default function App() {
  const [tab, setTab] = useState('chat');
  const Active = TABS.find((t) => t.id === tab)?.component ?? ChatPage;

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="mx-auto w-full sm:max-w-2xl h-screen sm:h-[calc(100vh-2rem)] sm:my-4 bg-white sm:rounded-xl sm:shadow-lg sm:border sm:border-gray-200 flex flex-col overflow-hidden">
        <nav className="flex border-b border-gray-200 bg-white overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={
                'px-4 py-3 text-sm font-medium border-b-2 -mb-px transition whitespace-nowrap ' +
                (tab === t.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700')
              }
            >
              {t.label}
            </button>
          ))}
        </nav>
        <div className="flex-1 min-h-0 flex flex-col">
          <Active />
        </div>
      </div>
    </div>
  );
}
