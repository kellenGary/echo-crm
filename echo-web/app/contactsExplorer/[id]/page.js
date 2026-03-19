"use client";
import React from 'react';
import { ContactWorkspace } from '../../components/ContactWorkspace';
import { useParams, useRouter } from 'next/navigation';
import { useContacts } from '../layout';

export default function ContactPage() {
  const { contacts } = useContacts();
  const params = useParams();
  const selectedContactId = params?.id ? decodeURIComponent(params.id) : null;
  const router = useRouter();

  if (!selectedContactId) return null;

  return (
    <ContactWorkspace 
      selectedContactId={selectedContactId}
      initialContacts={contacts}
      setSelectedContactId={(newId) => router.push(`/contactsExplorer/${encodeURIComponent(newId)}`)}
      setActiveModule={(module) => router.push(`/${module === 'contacts' ? 'contactsExplorer' : module}`)}
    />
  );
}
