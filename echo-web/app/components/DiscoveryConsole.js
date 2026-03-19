import React from 'react';
import { Activity, Shield } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export function DiscoveryConsole({ discoveries, setSelectedContactId, setActiveModule }) {
  return (
    <div className="flex-1 flex flex-col min-w-0 bg-background/95">
      <div className="foundry-header border-b px-8 py-8 h-auto flex flex-col items-start gap-4">
        <div className="flex items-center gap-3">
          <div className="size-10 bg-primary rounded flex items-center justify-center">
            <Activity className="size-6 text-primary-foreground" />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Fact Resolver & Discovery Console</h1>
            <div className="text-xs text-muted-foreground uppercase tracking-widest mt-1 monospace">
              ANALYTIC_ENGINE: ACTIVE // DETECTING_HIDDEN_CONNECTIONS
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-5xl space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {discoveries.map((discovery, i) => (
              <Card key={i} className="bg-black/30 border-white/10 hover:border-white/40 transition-all group overflow-hidden">
                <CardContent className="p-0">
                  <div className="p-5 border-b border-border/40 bg-white/5">
                     <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-2">
                          <Badge className="bg-primary text-primary-foreground font-bold text-[9px] uppercase">Connection Discovery</Badge>
                          <span className="text-[10px] text-muted-foreground monospace">LINK_INTENSITY: {discovery.intensity}</span>
                        </div>
                        <Shield className="size-4 text-white/50" />
                     </div>
                     <h3 className="text-lg font-bold text-white flex items-center gap-3">
                        {discovery.value}
                        <Badge variant="outline" className="text-[9px] uppercase border-white/30 text-white">{discovery.category}</Badge>
                     </h3>
                  </div>
                  <div className="p-5 space-y-4">
                     <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Connected Profiles</div>
                     <div className="flex flex-wrap gap-2">
                        {discovery.connected_profiles.map((name, j) => (
                           <div 
                             key={j} 
                             className="px-3 py-1.5 rounded bg-secondary/20 border border-border/40 text-xs font-medium cursor-pointer hover:bg-primary/10 hover:border-primary/30 transition-colors"
                             onClick={() => {
                               const cid = discovery.contact_ids[j];
                               setSelectedContactId(cid);
                               setActiveModule('contacts');
                             }}
                           >
                             {name}
                           </div>
                        ))}
                     </div>
                     <div className="pt-4 border-t border-border/20 flex items-center justify-between">
                        <div className="text-[10px] text-muted-foreground monospace uppercase">Inferred Linkage Probability: 98.4%</div>
                        <Button size="sm" variant="ghost" className="h-7 text-[10px] uppercase tracking-widest hover:text-white">
                          Verify Intelligence
                        </Button>
                     </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            {discoveries.length === 0 && (
               <div className="col-span-2 p-12 text-center border border-dashed border-border rounded-lg bg-black/20">
                  <Activity className="size-12 mx-auto mb-4 opacity-10" />
                  <div className="text-xs font-bold uppercase tracking-widest mb-2">No Hidden Connections Detected</div>
                  <div className="text-[10px] opacity-40">Increase signal ingestion to refine the Fact Resolver model.</div>
               </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
