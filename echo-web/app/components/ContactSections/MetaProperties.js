import React from 'react';
import { Shield } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";

export function MetaProperties() {
  return (
    <Card className="bg-black/30 border-border/50">
      <CardContent className="pt-6">
        <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4">Meta Properties</h3>
        <div className="space-y-3">
          <div className="flex justify-between items-center text-[10px]">
            <span className="text-muted-foreground uppercase tracking-wider">Object Class</span>
            <span className="monospace">PERSON</span>
          </div>
          <div className="flex justify-between items-center text-[10px]">
            <span className="text-muted-foreground uppercase tracking-wider">Consistency Score</span>
            <span className="text-primary">0.982</span>
          </div>
          <div className="flex justify-between items-center text-[10px]">
            <span className="text-muted-foreground uppercase tracking-wider">Security Context</span>
            <span className="flex items-center gap-1"><Shield className="size-2 text-primary" /> ENCRYPTED</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
