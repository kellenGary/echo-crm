import Link from "next/link";
import { Search, PanelLeftClose, ChevronRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function ContactExplorer({
  search,
  setSearch,
  filteredContacts,
  selectedContactId,
  sidebarCollapsed,
  setSidebarCollapsed,
}) {
  const imsgContacts = filteredContacts.filter((c) =>
    c.contact_id?.startsWith("imsg"),
  );

  return (
    <div
      className={cn(
        "foundry-panel transition-all duration-300 ease-in-out border-r border-border shrink-0",
        sidebarCollapsed ? "w-0 overflow-hidden border-none" : "w-80",
      )}
    >
      <div className="foundry-header justify-between py-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="icon"
            className="size-6 text-muted-foreground hover:text-foreground"
            onClick={() => setSidebarCollapsed(true)}
            title="Hide Sidebar"
          >
            <PanelLeftClose className="size-4" />
          </Button>
          <span className="font-bold text-xs uppercase tracking-widest flex items-center gap-2">
            Contacts Explorer
          </span>
        </div>
        <Badge variant="outline" className="text-[10px] monospace">
          {imsgContacts.length}
        </Badge>
      </div>
      {/* Search bar */}
      <div className="p-3 border-b border-border bg-secondary/20">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
          <Input
            placeholder="Search..."
            className="pl-8 h-8 text-xs bg-black/20 font-medium"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <ScrollArea className="flex-1 min-h-0 ">
        {imsgContacts.map((contact) => (
          <Link
            key={contact.contact_id}
            href={`/contactsExplorer/${encodeURIComponent(contact.contact_id)}`}
            className={cn(
              "foundry-list-item block",
              selectedContactId === contact.contact_id && "active bg-primary/10 border-l-2 border-primary",
            )}
          >
            <div className="flex items-center gap-3">
              <Avatar className="size-6 border border-border">
                <AvatarFallback className="text-[10px] bg-secondary font-bold">
                  {contact.display_name.substring(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-semibold truncate leading-none mb-1">
                  {contact.display_name}
                </div>
              </div>
              <ChevronRight className="size-3 text-muted-foreground/30" />
            </div>
          </Link>
        ))}
      </ScrollArea>
    </div>
  );
}
