import React from 'react';
import { Activity, MessageSquare } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getCategoryIcon } from './contactUtils';

export function KnowledgeGrid({ facts, onSelectFact }) {
  return (
    <div className="space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
        <Activity className="size-3" /> Extracted Properties & Inference
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {facts?.map((fact, i) => (
          <Card key={i} 
            className="bg-secondary/10 border-border/30 hover:border-primary/30 transition-all cursor-default group overflow-hidden"
            onClick={() => onSelectFact(fact)}
          >
            <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-100 transition-opacity">
              <Badge variant="outline" className="text-[8px] monospace">{fact.confidence?.toUpperCase()}</Badge>
            </div>
            <CardContent className="p-4 pt-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-primary/70">{getCategoryIcon(fact.category)}</span>
                <span className="text-[10px] font-bold uppercase tracking-tighter text-muted-foreground">{fact.category}</span>
              </div>
              <div className="text-sm font-medium mb-3 min-h-[2.5rem] leading-snug">
                {fact.value}
              </div>
              <div className="flex border-t border-border/20 pt-3 mt-auto">
                <div className="flex-1">
                  <div className="text-[9px] uppercase text-muted-foreground tracking-tight flex items-center gap-1">
                    <MessageSquare className="size-2" /> Source Quote
                  </div>
                  <div className="text-[10px] text-muted-foreground italic truncate max-w-[200px]">
                    {fact.source_quote}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
