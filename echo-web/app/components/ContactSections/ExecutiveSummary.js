import React from 'react';
import { Info } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export function ExecutiveSummary({ summary, messageCount, factCount }) {
  return (
    <Card className="col-span-2 bg-black/30 border-border/50">
      <CardContent className="pt-6 space-y-4">
        <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-2">
          <Info className="size-3" /> Executive Summary
        </h3>
        <p className="text-sm leading-relaxed text-foreground/90 italic">
          &quot;{summary}&quot;
        </p>
        <Separator className="opacity-10" />
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-secondary/10 p-4 rounded border border-border/20">
            <div className="text-[10px] uppercase text-muted-foreground mb-1 font-bold">Signal Intensity</div>
            <div className="text-xl font-bold flex items-baseline gap-2">
              {messageCount} <span className="text-[10px] text-muted-foreground font-normal">MESSAGES ANALYZED</span>
            </div>
          </div>
          <div className="bg-secondary/10 p-4 rounded border border-border/20">
            <div className="text-[10px] uppercase text-muted-foreground mb-1 font-bold">Knowledge Density</div>
            <div className="text-xl font-bold flex items-baseline gap-2">
              {factCount} <span className="text-[10px] text-muted-foreground font-normal">DISCRETE FACTS</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
