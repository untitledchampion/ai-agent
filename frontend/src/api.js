/**
 * API client for the agent backend.
 * All endpoints are proxied via Vite dev server to localhost:8000.
 */

const API = '/api';

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

// Chat
export const sendMessage = (chatId, message) =>
  request('/chat/send', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId, message }),
  });

export const getConversations = () => request('/chat/conversations');
export const getConversation = (chatId) => request(`/chat/conversations/${chatId}`);
export const deleteConversation = (chatId) =>
  request(`/chat/conversations/${chatId}`, { method: 'DELETE' });

// Scenes
export const getScenes = () => request('/scenes');
export const getScene = (slug) => request(`/scenes/${slug}`);
export const createScene = (data) =>
  request('/scenes', { method: 'POST', body: JSON.stringify(data) });
export const updateScene = (slug, data) =>
  request(`/scenes/${slug}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteScene = (slug) =>
  request(`/scenes/${slug}`, { method: 'DELETE' });

// Tools
export const getTools = () => request('/tools');
export const getTool = (slug) => request(`/tools/${slug}`);
export const createTool = (data) =>
  request('/tools', { method: 'POST', body: JSON.stringify(data) });
export const updateTool = (slug, data) =>
  request(`/tools/${slug}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteTool = (slug) =>
  request(`/tools/${slug}`, { method: 'DELETE' });

// Tone
export const getTone = () => request('/tone');
export const updateTone = (data) =>
  request('/tone', { method: 'PUT', body: JSON.stringify(data) });
export const previewTonePrompt = () => request('/tone/preview');

// Health
export const getHealth = () => request('/health');
