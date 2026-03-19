import React from 'react';
import { Badge } from "@/components/ui/badge";
import { RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';

export function StatusBadge({ status }) {
  switch (status) {
    case 'running':
      return <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20 animate-pulse"><RefreshCw className="size-3 mr-1 animate-spin" /> RUNNING</Badge>;
    case 'success':
      return <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20"><CheckCircle2 className="size-3 mr-1" /> SUCCESS</Badge>;
    case 'error':
      return <Badge className="bg-red-500/10 text-red-500 border-red-500/20"><AlertCircle className="size-3 mr-1" /> ERROR</Badge>;
    default:
      return <Badge variant="outline" className="opacity-50">IDLE</Badge>;
  }
}
