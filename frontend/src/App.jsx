import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import ChatPage from './pages/ChatPage';
import ScenesPage from './pages/ScenesPage';
import TonePage from './pages/TonePage';
import ToolsPage from './pages/ToolsPage';
const navItems = [
  { to: '/', label: 'Чат', icon: '💬' },
  { to: '/scenes', label: 'Сценарии', icon: '🎬' },
  { to: '/tone', label: 'Тон', icon: '🎤' },
  { to: '/tools', label: 'Инструменты', icon: '🔧' },
];

export default function App() {
  return (
    <BrowserRouter>
      <div className="h-screen bg-gray-50 flex">
        {/* Sidebar */}
        <nav className="w-56 bg-white border-r border-gray-200 flex flex-col shrink-0">
          <div className="p-4 border-b border-gray-200">
            <h1 className="text-lg font-bold text-gray-800">OptCeiling</h1>
            <p className="text-xs text-gray-500">AI Agent Panel</p>
          </div>
          <div className="flex-1 py-2">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-blue-50 text-blue-700 font-medium border-r-2 border-blue-700'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`
                }
              >
                <span>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
          <div className="p-4 border-t border-gray-200 text-xs text-gray-400">
            v0.1.0 MVP
          </div>
        </nav>

        {/* Main content */}
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/scenes" element={<ScenesPage />} />
            <Route path="/tone" element={<TonePage />} />
            <Route path="/tools" element={<ToolsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
