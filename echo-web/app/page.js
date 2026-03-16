'use client';

import { useState, useEffect } from 'react';

export default function Home() {
  const [contacts, setContacts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch('/api/contacts');
        const data = await response.json();
        setContacts(data);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  return (
    <main className="main-container">
      <header className="header">
        <div>
          <h1 className="title">Echo CRM</h1>
          <p style={{ color: 'var(--muted-foreground)' }}>Next.js + Python Hybrid System</p>
        </div>
        <div style={{ padding: '0.5rem 1rem', background: 'var(--muted)', borderRadius: 'var(--radius)', fontSize: '0.875rem' }}>
          {contacts.length} Profiles Synced
        </div>
      </header>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '4rem' }}>Loading intelligence...</div>
      ) : (
        <div className="grid">
          {contacts.map((contact) => (
            <div key={contact.contact_id} className="card">
              <h2 className="card-title">{contact.display_name}</h2>
              <div style={{ marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--muted-foreground)' }}>
                {contact.message_count} messages analyzed
              </div>
              
              <div style={{ display: 'flex', flexWrap: 'wrap', margin: '-0.25rem' }}>
                {contact.facts?.map((fact, i) => (
                  <span key={i} className="fact-badge">
                    {fact.category}: {fact.value}
                  </span>
                ))}
              </div>
              
              <div style={{ marginTop: '1.5rem', paddingTop: '1rem', borderTop: '1px solid var(--border)', fontSize: '0.75rem', color: 'var(--muted-foreground)' }}>
                Last activity: {new Date(contact.last_updated).toLocaleDateString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
