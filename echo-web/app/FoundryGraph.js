"use client";
import React, { useMemo } from 'react';
import dynamic from 'next/dynamic';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), { 
  ssr: false,
  loading: () => <div className="flex-1 flex items-center justify-center bg-black/40 text-[10px] monospace opacity-40 uppercase tracking-widest">Initialising Graph Engine...</div>
});

export default function FoundryGraph({ contacts, onSelect }) {
  // Compute nodes and links from contacts
  const graphData = useMemo(() => {
    const nodes = [];
    const links = [];
    const nodeSet = new Set();

    // 1. Add people nodes
    contacts.forEach(contact => {
      const id = contact.contact_id;
      if (!nodeSet.has(id)) {
        nodes.push({
          id,
          name: contact.display_name,
          type: 'person',
          val: Math.max(5, contact.message_count / 10)
        });
        nodeSet.add(id);
      }

      // 2. Add Place/Interest nodes from facts
      contact.facts?.forEach(fact => {
        if (['Location', 'Interest', 'Work'].includes(fact.category)) {
          const factId = `fact-${fact.category}-${fact.value.toLowerCase()}`;
          if (!nodeSet.has(factId)) {
            nodes.push({
              id: factId,
              name: fact.value,
              type: fact.category.toLowerCase(),
              val: 3
            });
            nodeSet.add(factId);
          }
          links.push({
            source: id,
            target: factId,
            label: fact.category
          });
        }
      });

      // 3. Add Relationship-based links
      contact.relationships?.forEach(rel => {
         // Find target if it exists in our known contacts
         const targetId = contacts.find(c => c.display_name.toLowerCase() === rel.target_name.toLowerCase())?.contact_id;
         if (targetId) {
           links.push({
             source: id,
             target: targetId,
             label: rel.type
           });
         }
      });
    });

    return { nodes, links };
  }, [contacts]);

  return (
    <div className="w-full h-full bg-black/40 border border-border/50 rounded overflow-hidden relative border-none">
      <div className="absolute top-4 left-4 z-10 bg-black/60 p-3 rounded border border-border/50 backdrop-blur-md">
        <div className="text-[10px] font-bold uppercase tracking-widest text-primary mb-2">Graph Schema</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-[8px] uppercase">
            <div className="size-2 rounded-full bg-white" /> Person Object
          </div>
          <div className="flex items-center gap-2 text-[8px] uppercase">
            <div className="size-2 rounded-full bg-gray-400" /> Location Entity
          </div>
          <div className="flex items-center gap-2 text-[8px] uppercase">
            <div className="size-2 rounded-full bg-gray-600" /> Interest/Topic
          </div>
        </div>
      </div>
      
      <ForceGraph2D
        graphData={graphData}
        nodeLabel="name"
        onNodeClick={node => {
          if (node.type === 'person' && onSelect) {
            onSelect(node.id);
          }
        }}
        nodeColor={node => {
          switch(node.type) {
            case 'person': return '#ffffff';
            case 'location': return '#a1a1a1';
            case 'interest': return '#717171';
            case 'work': return '#d1d1d1';
            default: return '#414141';
          }
        }}
        linkColor={() => 'rgba(255, 255, 255, 0.1)'}
        backgroundColor="transparent"
        nodeRelSize={6}
        linkDirectionalParticles={1}
        linkDirectionalParticleSpeed={0.005}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />
    </div>
  );
}
