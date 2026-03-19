import React from 'react';
import { Zap, RefreshCw, Brain, BookOpen } from 'lucide-react';
import { CommandCard } from './CommandCard';

export function ControlCenter({ taskStatus, runTask, getStatusBadge }) {
  return (
    <section>
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <Zap className="size-5 text-primary" />
        Control Center
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <CommandCard 
          title="Message Sync" 
          desc="Pull latest messages from Beeper" 
          icon={RefreshCw} 
          onRun={() => runTask('sync')}
          status={taskStatus.sync}
          badge={getStatusBadge(taskStatus.sync.status)}
        />
        <CommandCard 
          title="LLM Extraction" 
          desc="Run Ollama profile enrichment" 
          icon={Brain} 
          onRun={() => runTask('extract')}
          status={taskStatus.extract}
          badge={getStatusBadge(taskStatus.extract.status)}
        />
        <CommandCard 
          title="Obsidian Sync" 
          desc="Sync neural vault to Obsidian" 
          icon={BookOpen} 
          onRun={() => runTask('obsidian')}
          status={taskStatus.obsidian}
          badge={getStatusBadge(taskStatus.obsidian.status)}
        />
      </div>
    </section>
  );
}
