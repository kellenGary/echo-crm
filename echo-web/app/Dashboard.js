"use client";
import React, { useState, useEffect, useMemo } from 'react';
import { 
  Users, 
  Brain, 
  MessageSquare,
  Sparkles
} from 'lucide-react';

// Refactored Dashboard Components
import { DashboardHeader } from './components/dashboard/DashboardHeader';
import { StatCard } from './components/dashboard/StatCard';
import { ControlCenter } from './components/dashboard/ControlCenter';
import { IntelligenceAnalytics } from './components/dashboard/IntelligenceAnalytics';
import { DiscoveryFeed } from './components/dashboard/DiscoveryFeed';
import { StatusBadge } from './components/dashboard/StatusBadge';

export default function Dashboard({ initialContacts = [], discoveries = [] }) {
  const [taskStatus, setTaskStatus] = useState({
    sync: { status: "idle", last_run: null, error: null },
    extract: { status: "idle", last_run: null, error: null },
    obsidian: { status: "idle", last_run: null, error: null }
  });

  // Memoize analytics calculations
  const analytics = useMemo(() => {
    const totalContacts = initialContacts.length;
    const totalFacts = initialContacts.reduce((acc, c) => acc + (c.facts?.length || 0), 0);
    const totalMessages = initialContacts.reduce((acc, c) => acc + (c.message_count || 0), 0);
    const topContacts = [...initialContacts]
      .sort((a, b) => (b.message_count || 0) - (a.message_count || 0))
      .slice(0, 5);
    
    const topCategories = {};
    initialContacts.forEach(c => {
      c.facts?.forEach(f => {
        const cat = f.category || 'General';
        topCategories[cat] = (topCategories[cat] || 0) + 1;
      });
    });

    return { totalContacts, totalFacts, totalMessages, topContacts, topCategories };
  }, [initialContacts]);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/tasks/status');
        if (res.ok) {
          const data = await res.json();
          setTaskStatus(data);
        }
      } catch (err) {
        console.error("Failed to fetch task status:", err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const runTask = async (task) => {
    try {
      const res = await fetch(`/api/run/${task}`, { method: 'POST' });
      if (res.ok) {
        setTaskStatus(prev => ({
          ...prev,
          [task]: { ...prev[task], status: "running" }
        }));
      }
    } catch (err) {
      console.error(`Failed to run ${task}:`, err);
    }
  };

  const getStatusBadge = (status) => <StatusBadge status={status} />;

  return (
    <div className="bg-background p-8 pb-16">
      <div className="max-w-7xl mx-auto space-y-8">
        <DashboardHeader />
        {/* Stats Grid */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard 
            label="Total Intelligence" 
            value={analytics.totalFacts} 
            icon={Brain} 
            sub="Extracted facts & insights" 
            color="text-primary"
          />
          <StatCard 
            label="Network Depth" 
            value={analytics.totalContacts} 
            icon={Users} 
            sub="Active contact profiles" 
            color="text-blue-500"
          />
          <StatCard 
            label="Conversations" 
            value={(analytics.totalMessages / 1000).toFixed(1) + "k"} 
            icon={MessageSquare} 
            sub="Processed messages" 
            color="text-amber-500"
          />
          <StatCard 
            label="Knowledge Pool" 
            value={discoveries.length} 
            icon={Sparkles} 
            sub="Recent discoveries" 
            color="text-purple-500"
          />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          <div className="lg:col-span-2 space-y-8">
            <ControlCenter 
              taskStatus={taskStatus} 
              runTask={runTask} 
              getStatusBadge={getStatusBadge} 
            />
            
            <IntelligenceAnalytics analytics={analytics} />
          </div>

          <div className="lg:h-[700px]">
            <DiscoveryFeed discoveries={discoveries} />
          </div>
        </div>

      </div>
    </div>
  );
}
