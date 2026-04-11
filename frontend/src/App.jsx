import ChatPage from './pages/ChatPage';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      <div className="mx-auto w-full sm:max-w-2xl h-screen sm:h-[calc(100vh-2rem)] sm:my-4 bg-white sm:rounded-xl sm:shadow-lg sm:border sm:border-gray-200 flex flex-col overflow-hidden">
        <ChatPage />
      </div>
    </div>
  );
}
