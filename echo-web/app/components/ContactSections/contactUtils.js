import React from 'react';
import { Briefcase, MapPin, Heart, Shield, Info } from 'lucide-react';

export const getCategoryIcon = (category) => {
  switch (category?.toLowerCase()) {
    case 'professional': case 'work': return <Briefcase className="size-3" />;
    case 'biographical': case 'location': return <MapPin className="size-3" />;
    case 'interest': case 'hobby': return <Heart className="size-3" />;
    case 'identity': return <Shield className="size-3" />;
    default: return <Info className="size-3" />;
  }
};
