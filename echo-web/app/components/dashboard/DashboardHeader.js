import React from 'react';
import { Brain } from 'lucide-react';

export function DashboardHeader() {
  return (
    <header className="flex justify-between items-end">
      <div>
        <h1 className="text-4xl font-black tracking-tight flex items-center gap-3">
          <div className="size-10 bg-primary/20 rounded-xl flex items-center justify-center">
            <Brain className="text-primary size-6" />
          </div>
          ECHO SYSTEM
        </h1>
        <p className="text-muted-foreground mt-2 font-medium">Beeper Intelligence Hub — Personal CRM Analytics & Automation</p>
      </div>
      <div className="text-right">
        <div className="text-xs font-bold tracking-widest text-muted-foreground uppercase">System Status</div>
        <div className="flex gap-2 mt-1">
          <div className="flex items-center gap-1.5 px-2 py-1 bg-emerald-500/10 text-emerald-500 rounded border border-emerald-500/20 text-xs font-bold">
            <div className="size-1.5 bg-emerald-500 rounded-full animate-pulse" />
            API ONLINE
          </div>
        </div>
      </div>
    </header>
  );
}
