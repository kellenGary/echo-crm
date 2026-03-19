import React from 'react';
import { Activity, Users, Database } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Link from 'next/link';

export function IntelligenceAnalytics({ analytics }) {
  return (
    <section>
      <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
        <Activity className="size-5 text-primary" />
        Intelligence Analytics
      </h2>
      <Card className="bg-black/20 border-border/50 backdrop-blur-sm">
        <CardContent className="pt-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Top Contacts Chart */}
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="text-xs font-bold tracking-widest text-muted-foreground uppercase flex items-center gap-2">
                  <Users className="size-3" />
                  Engagement by Contact
                </h3>
                <Link href="/contactsExplorer">
                  <Button variant="link" size="sm" className="h-auto p-0 text-[10px] font-bold text-primary hover:underline uppercase tracking-widest">View Explorer</Button>
                </Link>
              </div>
              <div className="space-y-3">
                {analytics.topContacts.map((c, i) => (
                  <div key={c.contact_id || i} className="space-y-1">
                    <div className="flex justify-between text-sm font-medium">
                      <span>{c.display_name}</span>
                      <span className="text-muted-foreground">{c.message_count} msgs</span>
                    </div>
                    <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-primary" 
                        style={{ width: `${(c.message_count / (analytics.topContacts[0]?.message_count || 1)) * 100}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Category Distribution */}
            <div className="space-y-4">
              <h3 className="text-xs font-bold tracking-widest text-muted-foreground uppercase flex items-center gap-2">
                <Database className="size-3" />
                Fact Distribution
              </h3>
              <div className="space-y-3">
                {Object.entries(analytics.topCategories)
                  .sort((a,b) => b[1] - a[1])
                  .slice(0, 5)
                  .map(([cat, count], i) => (
                  <div key={cat} className="space-y-1">
                    <div className="flex justify-between text-sm font-medium">
                      <span>{cat}</span>
                      <span className="text-muted-foreground">{count} facts</span>
                    </div>
                    <div className="h-1.5 w-full bg-secondary rounded-full overflow-hidden">
                      <div 
                        className={`h-full bg-blue-500`} 
                        style={{ width: `${(count / Math.max(1, ...Object.values(analytics.topCategories))) * 100}%`, opacity: 1 - i*0.15 }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
