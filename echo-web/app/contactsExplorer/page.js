"use client";
import React from 'react';

export default function ContactsExplorerEmpty() {
  return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground bg-black/40 h-full min-h-0">
      <div className="text-center space-y-4">
        <div className="text-xs font-bold tracking-widest uppercase opacity-40">
          SELECT A CONTACT TO BEGIN
        </div>
      </div>
    </div>
  );
}
