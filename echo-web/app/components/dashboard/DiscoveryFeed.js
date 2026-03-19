import React from 'react';
import { Sparkles, Clock, Users, Activity } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

export function DiscoveryFeed({ discoveries }) {
  return (
    <div className="space-y-8 h-full">
      <Card className="bg-black/20 border-border/50 backdrop-blur-sm h-full flex flex-col">
        <CardHeader>
          <CardTitle className="text-sm font-bold flex items-center gap-2 uppercase tracking-widest text-primary">
            <Sparkles className="size-4" />
            Recent Discoveries
          </CardTitle>
          <CardDescription>
            Insights found across your network
          </CardDescription>
        </CardHeader>
        <CardContent className="flex-1 overflow-hidden p-0">
          <ScrollArea className="h-full px-6">
            <div className="space-y-4 pb-6">
              {discoveries.length > 0 ? discoveries.map((d, i) => (
                <div key={i} className="p-3 bg-secondary/30 rounded-lg border border-border/50 space-y-2 group hover:bg-secondary/50 transition-colors">
                  <div className="flex justify-between items-start">
                    <Badge variant="secondary" className="text-[10px] font-bold px-1.5 py-0 h-4 bg-primary/10 text-primary border-primary/20">
                      {d.type || 'Insight'}
                    </Badge>
                    <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                      <Clock className="size-2.5" />
                      {d.timestamp ? new Date(d.timestamp).toLocaleDateString() : 'Recent'}
                    </span>
                  </div>
                  <p className="text-sm font-medium leading-relaxed">
                    {d.value || d.text}
                  </p>
                  {d.contact_name && (
                    <div className="text-[10px] text-muted-foreground flex items-center gap-1 mt-1">
                      <Users className="size-2.5" />
                      {d.contact_name}
                    </div>
                  )}
                </div>
              )) : (
                <div className="flex flex-col items-center justify-center py-12 text-center opacity-30">
                  <Activity className="size-8 mb-4 lg:mb-2" />
                  <p className="text-xs font-bold uppercase tracking-tighter">No discoveries yet</p>
                </div>
              )}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
