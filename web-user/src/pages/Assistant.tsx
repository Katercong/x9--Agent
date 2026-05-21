import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, Sparkles } from 'lucide-react';
import { AsyncState } from '@/components/states/States';
import { useAssistantInfo, useAssistantChat } from '@/hooks/useApi';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
  ts: number;
}

export default function Assistant() {
  const info = useAssistantInfo();
  const chat = useAssistantChat();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  // 首次加载时若有 greeting,作为 AI 开场白
  useEffect(() => {
    if (info.data?.greeting && messages.length === 0) {
      setMessages([{ role: 'assistant', content: info.data.greeting, ts: Date.now() }]);
    }
  }, [info.data?.greeting]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = () => {
    const text = input.trim();
    if (!text || chat.isPending) return;
    const userMsg: Msg = { role: 'user', content: text, ts: Date.now() };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput('');
    chat.mutate(
      { message: text, history: messages.map((m) => ({ role: m.role, content: m.content })) },
      {
        onSuccess: (r) => {
          const reply = (r as any).reply || (r as any).message || (r as any).text || '(无回复)';
          setMessages((prev) => [...prev, { role: 'assistant', content: reply, ts: Date.now() }]);
        },
        onError: (err: any) => {
          setMessages((prev) => [...prev, { role: 'assistant', content: `❌ 错误:${err?.message || '未知错误'}`, ts: Date.now() }]);
        },
      },
    );
  };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const provider = info.data?.provider || '—';
  const model = info.data?.model || '—';

  return (
    <AsyncState loading={info.isLoading} error={info.error} height={400}>
      <div className="flex flex-col gap-3 h-[calc(100vh-120px)]">
        {/* Provider info bar */}
        <div className="card card-body !py-3 flex items-center gap-3">
          <div className="w-9 h-9 rounded-md flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #06b6d4 0%, #3b82f6 100%)' }}>
            <Sparkles size={16} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-semibold">X9 AI 助手</div>
            <div className="text-xxs text-muted">{provider} · {model}</div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <span className={`pill ${info.data?.ready === false ? 'pill-warn' : 'pill-good'}`}>
              {info.data?.ready === false ? '未就绪' : '在线'}
            </span>
            <button onClick={() => setMessages([])} className="btn btn-ghost text-xs">清空对话</button>
          </div>
        </div>

        {/* Messages */}
        <div className="card flex-1 overflow-hidden flex flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <div className="text-center py-12 text-muted text-xs">
                <Bot size={32} className="mx-auto mb-3 opacity-50" />
                输入问题开始对话 · 支持运维 / 数据查询 / 话术生成等
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0`}
                  style={{
                    background: m.role === 'user' ? 'rgb(var(--accent) / 0.2)' : 'rgb(var(--bg-elev-2))',
                  }}
                >
                  {m.role === 'user' ? <User size={13} className="text-accent" /> : <Bot size={13} className="text-muted" />}
                </div>
                <div
                  className={`max-w-[70%] rounded-lg px-3.5 py-2 text-sm whitespace-pre-wrap break-words ${m.role === 'user' ? 'text-text' : ''}`}
                  style={{
                    background: m.role === 'user'
                      ? 'rgb(var(--accent) / 0.18)'
                      : 'rgb(var(--bg-elev-2))',
                  }}
                >
                  {m.content}
                </div>
              </div>
            ))}
            {chat.isPending && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <Bot size={13} className="text-muted" />
                </div>
                <div className="rounded-lg px-3.5 py-2 flex items-center gap-2 text-xs text-muted" style={{ background: 'rgb(var(--bg-elev-2))' }}>
                  <Loader2 size={12} className="animate-spin" />
                  思考中...
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <div className="border-t border-border p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKey}
                placeholder="输入问题... (Enter 发送,Shift+Enter 换行)"
                rows={2}
                className="flex-1 px-3 py-2 rounded-md text-sm resize-none border border-border focus:outline-none focus:border-accent input-bare"
                style={{ background: 'rgb(var(--bg-elev-2))' }}
              />
              <button onClick={send} disabled={chat.isPending || !input.trim()} className="btn btn-primary !py-2 text-sm">
                <Send size={14} />发送
              </button>
            </div>
          </div>
        </div>
      </div>
    </AsyncState>
  );
}
