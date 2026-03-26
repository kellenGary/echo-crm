"use client";
import React, { useState, useMemo, useEffect, createContext, useContext } from 'react';
import { ContactExplorer } from '../components/ContactExplorer';
import { useParams, usePathname } from 'next/navigation';

const ContactsContext = createContext(null);

export const useContacts = () => useContext(ContactsContext);

export default function ContactsLayout({ children }) {
  const [contacts, setContacts] = useState([]);
  const [search, setSearch] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const params = useParams();
  const selectedContactId = params?.id ? decodeURIComponent(params.id) : null;

  useEffect(() => {
    const fetchContacts = async () => {
      try {
        const res = await fetch(`/api/contacts`);
        if (res.ok) {
          const data = await res.json();
          setContacts(data);
        }
      } catch (err) {
        console.error("Failed to fetch contacts in layout:", err);
      }
    };
    fetchContacts();
  }, []);

  const filteredContacts = useMemo(() => {
    return contacts.filter((c) => 
      c.display_name.toLowerCase().includes(search.toLowerCase())
    );
  }, [contacts, search]);

  return (
    <ContactsContext.Provider value={{ contacts, filteredContacts, selectedContactId }}>
      <div className="flex flex-1 overflow-hidden h-full">
        <ContactExplorer 
          search={search}
          setSearch={setSearch}
          filteredContacts={filteredContacts}
          selectedContactId={selectedContactId}
          sidebarCollapsed={sidebarCollapsed}
          setSidebarCollapsed={setSidebarCollapsed}
        />
        
        <div className="flex-1 relative min-w-0 flex flex-col h-full">
          {children}
        </div>
      </div>
    </ContactsContext.Provider>
  );
}