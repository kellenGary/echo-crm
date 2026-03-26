import React, { useState, useEffect } from "react";
import { Activity, Loader2 } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import FoundryGraph from "../FoundryGraph";
import FactPopup from "./MessagePopup";

// Import refactored components
import {
  ContactHeader,
  ContactIdentity,
  ExecutiveSummary,
  MetaProperties,
  PropertySheet,
  Relationships,
  KnowledgeGrid,
} from "./ContactSections";

export function ContactWorkspace({
  selectedContactId,
  sidebarCollapsed,
  setSidebarCollapsed,
  initialContacts,
  setActiveModule,
  setSelectedContactId,
}) {
  const [selectedContact, setSelectedContact] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedFact, setSelectedFact] = useState(null);

  useEffect(() => {
    if (!selectedContactId) return;

    const fetchContact = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`/api/contacts/${selectedContactId}`);
        if (!response.ok) throw new Error("Failed to fetch contact");
        const data = await response.json();
        setSelectedContact(data);
      } catch (err) {
        console.error("Error fetching contact:", err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchContact();
  }, [selectedContactId]);

  const handleUpdateFact = async (updatedFact) => {
    if (!selectedContact) return;

    // Optimistic update
    const updatedFacts = selectedContact.facts.map((f) =>
      f.value === selectedFact.value && f.category === selectedFact.category
        ? updatedFact
        : f,
    );

    try {
      const response = await fetch(
        `/api/contacts/${selectedContact.contact_id}/update`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...selectedContact, facts: updatedFacts }),
        },
      );

      if (response.ok) {
        setSelectedFact(null);
        window.location.reload();
      }
    } catch (err) {
      console.error("Failed to update fact:", err);
    }
  };

  const handleDeleteFact = async (factToDelete) => {
    if (!selectedContact) return;
    const factIndex = selectedContact.facts.findIndex(
      (f) => f.value === factToDelete.value,
    );
    if (factIndex === -1) return;

    try {
      const response = await fetch(
        `/api/contacts/${selectedContact.contact_id}/facts/${factIndex}`,
        {
          method: "DELETE",
        },
      );

      if (response.ok) {
        setSelectedFact(null);
        window.location.reload();
      }
    } catch (err) {
      console.error("Failed to delete fact:", err);
    }
  };

  const handleUpdateRelationship = async (updatedRels) => {
    try {
      await fetch(`/api/contacts/${selectedContact.contact_id}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...selectedContact,
          relationships: updatedRels,
        }),
      });
      window.location.reload();
    } catch (err) {
      console.error("Failed to update relationships:", err);
    }
  };

  const findKeyFact = (keywords, categories = []) => {
    return selectedContact?.facts?.find(
      (f) =>
        (categories.length === 0 || categories.includes(f.category)) &&
        keywords.some((k) => f.value.toLowerCase().includes(k.toLowerCase())),
    )?.value;
  };

  const birthday = findKeyFact(
    ["birthday", "born on", "born in"],
    ["Biographical", "Social", "Identity"],
  );
  const location = findKeyFact(
    ["lives in", "located in", "address", "based in", "currently in"],
    ["Biographical", "Location"],
  );
  const education = findKeyFact(
    ["studied", "university", "college", "school", "major"],
    ["Biographical", "Professional"],
  );
  const occupation = findKeyFact(
    ["works at", "job", "position", "employed", "career"],
    ["Professional"],
  );

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground bg-black/40">
        <div className="text-center space-y-4">
          <Loader2 className="size-12 mx-auto animate-spin text-primary opacity-20" />
          <div className="text-xs font-bold tracking-widest uppercase opacity-40">
            Fetching Intelligence Data
          </div>
        </div>
      </div>
    );
  }

  if (!selectedContact) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted-foreground bg-black/40">
        <div className="text-center space-y-4">
          <Activity className="size-12 mx-auto opacity-10" />
          <div className="text-xs font-bold tracking-widest uppercase">
            Select an object to explore properties
          </div>
          <div className="text-[10px] opacity-40 monospace">
            FOUNDRY_INSTANCE_023 // WAITING_FOR_INPUT
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col h-full min-h-0 bg-black/10">
      <ContactHeader
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
        displayName={selectedContact.display_name}
      />

      <div className="flex-1 overflow-y-auto min-h-0 p-6">
        <div className="max-w-5xl mx-auto space-y-6">
          <ContactIdentity contact={selectedContact} />

          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="bg-transparent border-b border-border rounded-none p-0 h-auto gap-6">
              <TabsTrigger
                value="overview"
                className="bg-transparent data-[state=active]:bg-primary/10 rounded-none px-0 py-2 text-xs font-bold uppercase tracking-wider"
              >
                Overview
              </TabsTrigger>
              <TabsTrigger
                value="lineage"
                className="bg-transparent data-[state=active]:bg-primary/10 rounded-none px-0 py-2 text-xs font-bold uppercase tracking-wider"
              >
                Intelligence Lineage
              </TabsTrigger>
              <TabsTrigger
                value="raw"
                className="bg-transparent data-[state=active]:bg-primary/10 rounded-none px-0 py-2 text-xs font-bold uppercase tracking-wider"
              >
                Raw Signals
              </TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="flex flex-col gap-4 md:col-span-2">
                  <ExecutiveSummary
                    summary={selectedContact.summary}
                    messageCount={selectedContact.message_count}
                    factCount={selectedContact.facts?.length || 0}
                  />

                  <KnowledgeGrid
                    facts={selectedContact.facts}
                    onSelectFact={setSelectedFact}
                  />
                </div>

                <div className="space-y-6">
                  <MetaProperties />

                  <PropertySheet
                    location={location}
                    birthday={birthday}
                    occupation={occupation}
                    education={education}
                  />

                  <Relationships
                    relationships={selectedContact.relationships}
                    onUpdateRelationships={handleUpdateRelationship}
                  />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="lineage" className="mt-6 h-[600px]">
              <FoundryGraph
                contacts={initialContacts}
                onSelect={(id) => {
                  if (setSelectedContactId) setSelectedContactId(id);
                  setActiveModule("contacts");
                }}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <FactPopup
        fact={selectedFact}
        onClose={() => setSelectedFact(null)}
        onUpdate={handleUpdateFact}
        onDelete={handleDeleteFact}
      />
    </div>
  );
}
