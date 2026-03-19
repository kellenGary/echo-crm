import React from 'react';
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

export function ContactIdentity({ contact }) {
  return (
    <div className="flex items-start justify-between">
      <div className="flex gap-6">
        <Avatar className="size-20 rounded-lg shadow-xl">
          <AvatarFallback className="text-2xl font-bold bg-secondary">
            {contact.display_name.substring(0, 1)}
          </AvatarFallback>
        </Avatar>
        <div className="space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">{contact.display_name}</h1>
          <div className="flex gap-2">
            <Badge variant="secondary" className="bg-primary/10 text-primary text-[10px] font-bold">CONTACT_OBJECT</Badge>
            <Badge variant="outline" className="text-[10px] border-primary/20 text-primary">SYNC_SUCCESS</Badge>
            <Badge variant="outline" className="text-[10px] opacity-50 monospace">v1.2.4</Badge>
          </div>
        </div>
      </div>
      <div className="text-right monospace text-[10px] text-muted-foreground space-y-1 bg-secondary/20 p-3 rounded border border-border">
        <div>OBJECT_UID: {contact.contact_id}</div>
        <div>DATA_SOURCE: iMessage/Beeper</div>
        <div>LAST_OBSERVED: {new Date(contact.last_updated).toLocaleTimeString()}</div>
      </div>
    </div>
  );
}
