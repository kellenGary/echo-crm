import React from 'react';
import { Card, CardContent } from "@/components/ui/card";

export function StatCard({ label, value, icon: Icon, sub, color }) {
  return (
    <Card className="bg-black/20 border-border/50 backdrop-blur-sm hover:border-border transition-all group">
      <CardContent className="pt-6">
        <div className="flex justify-between items-start">
          <div className="space-y-1">
            <p className="text-xs font-bold text-muted-foreground tracking-widest uppercase">{label}</p>
            <h3 className={`text-4xl font-black ${color} tracking-tighter`}>{value}</h3>
          </div>
          <div className={`p-2 bg-secondary/50 rounded-lg group-hover:scale-110 transition-transform`}>
            <Icon className={`size-5 ${color}`} />
          </div>
        </div>
        <p className="text-xs text-muted-foreground mt-4 font-medium">{sub}</p>
      </CardContent>
    </Card>
  );
}
