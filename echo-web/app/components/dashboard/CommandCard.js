import React from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Clock } from 'lucide-react';

export function CommandCard({ title, desc, icon: Icon, onRun, status, badge }) {
  const isRunning = status.status === 'running';

  return (
    <Card className="bg-black/20 border-border/50 backdrop-blur-sm flex flex-col hover:border-primary/50 transition-colors group">
      <CardHeader className="pb-2">
        <div className="flex justify-between items-start mb-2">
          <div className="p-2 bg-primary/10 rounded-lg text-primary">
            <Icon className="size-5" />
          </div>
          {badge}
        </div>
        <CardTitle className="text-base font-bold">{title}</CardTitle>
        <CardDescription className="text-xs">{desc}</CardDescription>
      </CardHeader>
      <CardFooter className="pt-4 mt-auto">
        <Button 
          onClick={onRun} 
          disabled={isRunning} 
          className="w-full font-bold h-9 bg-primary hover:bg-primary/90 text-primary-foreground shadow-[0_0_15px_-5px_var(--primary)]"
        >
          {isRunning ? "PROCESSING..." : "RUN COMMAND"}
        </Button>
      </CardFooter>
      {status.last_run && (
        <div className="px-6 pb-4 text-[10px] text-muted-foreground/60 flex items-center gap-1 italic">
          <Clock className="size-2.5" />
          Last: {new Date(status.last_run).toLocaleTimeString()}
        </div>
      )}
    </Card>
  );
}
