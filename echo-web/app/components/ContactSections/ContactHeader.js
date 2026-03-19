import React from 'react';
import { 
  Users, 
  ChevronRight, 
  PanelLeft, 
  PanelLeftClose, 
  ExternalLink 
} from 'lucide-react';
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export function ContactHeader({ 
  sidebarCollapsed, 
  setSidebarCollapsed, 
  displayName 
}) {
  return (
    <div className="foundry-header justify-between bg-black/20 py-1.5 px-4">
      <div className="flex items-center gap-3">
        <button 
           className="size-6 text-muted-foreground hover:text-foreground flex items-center justify-center"
           onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
           title={sidebarCollapsed ? "Show Sidebar" : "Hide Sidebar"}
        >
          {sidebarCollapsed ? <PanelLeft className="size-3" /> : <PanelLeftClose className="size-3" />}
        </button>
        <Separator orientation="vertical" className="h-4" />
        <div className="flex items-center gap-2 text-xs">
           <Users className="size-3" />
           <span className="text-muted-foreground">Contacts</span>
           <ChevronRight className="size-3 text-muted-foreground/50" />
           <span className="font-semibold">{displayName}</span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="h-7 text-[10px] gap-1.5 border-border">
          <ExternalLink className="size-3" /> OPEN IN GRAPH
        </Button>
        <Button variant="default" size="sm" className="h-7 text-[10px] gap-1.5 font-bold">
          ACTIONS
        </Button>
      </div>
    </div>
  );
}
