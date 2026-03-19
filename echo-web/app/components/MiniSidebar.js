"use client";
import React from 'react';
import { Database, Users, Activity, MessageSquare, Settings } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export function MiniSidebar() {
  const pathname = usePathname();
  
  const modules = [
    { id: 'dashboard', icon: Database, href: '/' },
    { id: 'contactsExplorer', icon: Users, href: '/contactsExplorer' },
    { id: 'discoveries', icon: Activity, href: '/discoveries' },
    { id: 'intelligence', icon: MessageSquare, href: '/intelligence' },
  ];

  return (
    <aside className="w-12 flex flex-col items-center py-4 border-r border-border bg-black/40 shrink-0">
      <div className="size-8 bg-primary rounded flex items-center justify-center mb-8">
        <Database className="text-primary-foreground size-5" />
      </div>
      <div className="flex flex-col gap-4 flex-1">
        {modules.map((m) => (
          <Link key={m.id} href={m.href}>
            <Button 
              variant="ghost" 
              size="icon" 
              className={cn(
                "size-8", 
                pathname.startsWith(m.href) ? "text-primary bg-primary/10" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <m.icon className="size-4" />
            </Button>
          </Link>
        ))}
      </div>
      <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-foreground">
        <Settings className="size-4" />
      </Button>
    </aside>
  );
}
