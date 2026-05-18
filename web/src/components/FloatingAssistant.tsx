import { useEffect, useRef, useState } from 'react';
import { Bot, X, Send, Trash2, Loader2 } from 'lucide-react';
import { endpoints } from '@/api/endpoints';

type Msg = { role: 'user' | 'assistant'; content: string };

/**
 * Global floating AI assistant — mounted once in AppShell so it is
 * available on every page. Talks to the core agent through the desktop
 * /api/v1 reverse-proxy (loopback, auth-free after the auth fix).
 */
export default function FloatingAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, open]);

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    const next = [...messages, { role: 'user' as const, content: text }];
    setMessages(next);
    setSending(true);
    try {
      const res = await endpoints.agentChat(next);
      setMessages([...next, { role: 'assistant', content: res.answer || '(空回复)' }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessages([...next, { role: 'assistant', content: `出错了：${msg}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          title="AI 助手"
          aria-label="AI 助手"
          className="fixed bottom-5 right-5 z-[9000] flex h-14 w-14 items-center justify-center rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/40 transition hover:scale-105 hover:bg-blue-700"
        >
          <Bot size={24} />
        </button>
      )}

      {open && (
        <section
          aria-label="AI 助手"
          className="fixed bottom-5 right-5 z-[9001] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-2xl"
          style={{ height: '560px', maxHeight: 'calc(100vh - 7rem)' }}
        >
          <header className="flex items-center gap-2 bg-blue-600 px-4 py-3 text-white">
            <Bot size={18} />
            <span className="flex-1 text-sm font-semibold">AI 项目助手</span>
            <button
              type="button"
              onClick={() => setMessages([])}
              title="清空对话"
              className="rounded p-1 hover:bg-white/20"
            >
              <Trash2 size={15} />
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              title="关闭"
              className="rounded p-1 hover:bg-white/20"
            >
              <X size={16} />
            </button>
          </header>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-gray-50 p-3">
            {messages.length === 0 && (
              <div className="rounded-lg bg-white p-3 text-xs text-muted shadow-sm">
                你好，我可以帮你了解这个系统：数据 schema、命名查询、业务/线索/建联流程、操作引导等。问我任何事。
              </div>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={
                  m.role === 'user'
                    ? 'ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-blue-600 px-3 py-2 text-sm text-white'
                    : 'mr-auto max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm text-gray-800 shadow-sm'
                }
              >
                {m.content}
              </div>
            ))}
            {sending && (
              <div className="mr-auto flex items-center gap-2 rounded-2xl rounded-bl-sm bg-white px-3 py-2 text-sm text-muted shadow-sm">
                <Loader2 size={14} className="animate-spin" /> 思考中…
              </div>
            )}
          </div>

          <div className="flex items-end gap-2 border-t border-gray-200 p-2.5">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={1}
              placeholder="问任何关于系统的事… (Ctrl/⌘+Enter 发送)"
              className="max-h-28 min-h-[40px] flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
            />
            <button
              type="button"
              onClick={send}
              disabled={sending || !input.trim()}
              className="flex h-10 items-center gap-1.5 rounded-lg bg-blue-600 px-3 text-sm text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Send size={15} />
            </button>
          </div>
        </section>
      )}
    </>
  );
}
