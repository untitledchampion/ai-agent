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

// Knowledge (product aliases)
export const listAliases = (q = '', limit = 500) =>
  request(`/knowledge/aliases?q=${encodeURIComponent(q)}&limit=${limit}`);
export const createAlias = (data) =>
  request('/knowledge/aliases', { method: 'POST', body: JSON.stringify(data) });
export const updateAlias = (id, data) =>
  request(`/knowledge/aliases/${id}`, { method: 'PUT', body: JSON.stringify(data) });
export const deleteAlias = (id) =>
  request(`/knowledge/aliases/${id}`, { method: 'DELETE' });
export const bulkDeleteAliases = (ids) =>
  request('/knowledge/aliases/bulk_delete', {
    method: 'POST',
    body: JSON.stringify({ ids }),
  });
export const searchProductsForSelect = (q) =>
  request(`/knowledge/products/search?q=${encodeURIComponent(q)}`);

// Health
export const getHealth = () => request('/health');
