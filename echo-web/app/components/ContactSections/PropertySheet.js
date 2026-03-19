import React from 'react';
import { MapPin as MapPinIcon, Cake, Briefcase as BriefcaseIcon, GraduationCap } from 'lucide-react';
import { Card, CardContent } from "@/components/ui/card";

export function PropertySheet({ location, birthday, occupation, education }) {
  const hasProperties = location || birthday || occupation || education;
  
  if (!hasProperties) return null;

  return (
    <Card className="bg-black/30 border-border/50">
      <CardContent className="pt-6">
        <h3 className="text-xs font-bold uppercase tracking-widest text-muted-foreground mb-4">Property Sheet</h3>
        <div className="space-y-4">
          {location && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
                <MapPinIcon className="size-3 text-primary/70" /> Location
              </div>
              <div className="text-xs font-medium pl-5">{location}</div>
            </div>
          )}
          {birthday && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
                <Cake className="size-3 text-primary/70" /> Birthday
              </div>
              <div className="text-xs font-medium pl-5">{birthday}</div>
            </div>
          )}
          {occupation && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
                <BriefcaseIcon className="size-3 text-primary/70" /> Professional
              </div>
              <div className="text-xs font-medium pl-5">{occupation}</div>
            </div>
          )}
          {education && (
            <div className="space-y-1">
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground uppercase tracking-wider">
                <GraduationCap className="size-3 text-primary/70" /> Education
              </div>
              <div className="text-xs font-medium pl-5">{education}</div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
