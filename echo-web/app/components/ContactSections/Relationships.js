import React from 'react';
import { Trash2 } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function Relationships({ relationships, onUpdateRelationships }) {
  return (
    <Card className="bg-black/30 border-border/50">
      <CardContent className="pt-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Relationships</h3>
          <Badge variant="outline" className="text-[8px] opacity-70">AUTO_SYNCED</Badge>
        </div>
        <div className="space-y-3">
          {relationships?.length > 0 ? (
            relationships.map((rel, i) => (
              <div key={i} className="flex items-center justify-between group">
                <div className="space-y-0.5">
                  <div className="text-xs font-medium text-primary flex items-center gap-1.5">
                    {rel.target_name} 
                    <Badge className="text-[8px] h-3.5 px-1 bg-primary/20 text-primary border-none">{rel.type.toUpperCase()}</Badge>
                  </div>
                  {rel.context && <div className="text-[9px] text-muted-foreground italic truncate max-w-[150px]">{rel.context}</div>}
                </div>
                <button 
                  className="size-6 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-destructive hover:bg-destructive/10 rounded"
                  onClick={() => {
                      const newRels = relationships.filter((_, idx) => idx !== i);
                      onUpdateRelationships(newRels);
                  }}
                >
                  <Trash2 className="size-3" />
                </button>
              </div>
            ))
          ) : (
            <div className="text-[10px] text-muted-foreground italic py-2">No active intelligence mappings</div>
          )}
          <Button variant="outline" size="sm" className="w-full h-7 text-[9px] mt-2 border-dashed opacity-50 hover:opacity-100">
            + ADD RELATIONSHIP
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
