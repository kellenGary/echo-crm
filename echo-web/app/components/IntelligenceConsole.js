import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Bot, User, Loader2, Sparkles } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

export function IntelligenceConsole() {
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Intelligence Console active. Ask me anything about your contacts or their message history.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: userMessage }),
      });

      const data = await response.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.answer || "I couldn't generate an answer." }]);
    } catch (error) {
      setMessages(prev => [...prev, { role: 'assistant', content: "Error connecting to the intelligence engine." }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background/95">
      <div className="foundry-header border-b px-8 py-8 h-auto flex flex-col items-start gap-4">
        <div className="flex items-center gap-3">
          <div className="size-10 bg-primary rounded flex items-center justify-center">
            <MessageSquare className="size-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Intelligence Console</h1>
            <div className="text-xs text-muted-foreground uppercase tracking-widest mt-1 monospace">
              SESSION_STATE: ENCRYPTED // QUERY_MODE: LLM_GROUNDED
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-hidden flex flex-col p-8">
        <Card className="flex-1 bg-black/30 border-white/10 flex flex-col overflow-hidden max-w-5xl w-full mx-auto">
          <ScrollArea ref={scrollRef} className="flex-1 p-6">
            <div className="space-y-6">
              {messages.map((msg, i) => (
                <div key={i} className={cn(
                  "flex gap-4",
                  msg.role === 'user' ? "flex-row-reverse" : "flex-row"
                )}>
                  <div className={cn(
                    "size-8 rounded flex items-center justify-center shrink-0",
                    msg.role === 'user' ? "bg-secondary" : "bg-primary/20"
                  )}>
                    {msg.role === 'user' ? <User className="size-4" /> : <Bot className="size-4 text-primary" />}
                  </div>
                  <div className={cn(
                    "max-w-[80%] rounded-lg p-3 text-sm leading-relaxed",
                    msg.role === 'user' ? "bg-secondary/40 text-foreground" : "bg-white/5 text-foreground/90 border border-white/5"
                  )}>
                    {msg.content}
                  </div>
                </div>
              ))}
              {isLoading && (
                <div className="flex gap-4">
                  <div className="size-8 rounded bg-primary/20 flex items-center justify-center shrink-0">
                    <Loader2 className="size-4 text-primary animate-spin" />
                  </div>
                  <div className="bg-white/5 text-muted-foreground italic text-sm p-3 rounded-lg border border-white/5 flex items-center gap-2">
                    <Sparkles className="size-3 animate-pulse" />
                    Analyzing signals and extracting context...
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="p-4 border-t border-white/10 bg-black/20">
            <form onSubmit={handleSubmit} className="flex gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about your contacts (e.g., 'What is Madi studying?')"
                className="bg-black/40 border-white/10 text-sm h-10"
                disabled={isLoading}
              />
              <Button type="submit" disabled={isLoading} size="icon" className="h-10 w-10 shrink-0">
                <Send className="size-4" />
              </Button>
            </form>
          </div>
        </Card>
      </div>
    </div>
  );
}
