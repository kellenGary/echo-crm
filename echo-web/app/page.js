import fs from 'fs';
import path from 'path';
import Dashboard from './Dashboard';

export const dynamic = 'force-dynamic';

export default async function Home() {
  let contacts = [];
  let discoveries = [];

  try {
    // Fetch from our local FastAPI backend
    const apiHost = process.env.BACKEND_URL || 'http://localhost:8000';
    console.log(`[Next.js] Fetching data from ${apiHost}...`);
    
    const [contactsRes, discoveriesRes] = await Promise.all([
      fetch(`${apiHost}/api/contacts`, { cache: 'no-store' }),
      fetch(`${apiHost}/api/discoveries`, { cache: 'no-store' })
    ]);
    
    if (contactsRes.ok) contacts = await contactsRes.json();
    if (discoveriesRes.ok) discoveries = await discoveriesRes.json();
    
    console.log(`[Next.js] Successfully loaded ${contacts.length} contacts and ${discoveries.length} discoveries.`);
  } catch (err) {
    console.error('❌ [Next.js] Error connecting to API:', err.message);
    console.error('   Make sure the FastAPI backend is running on http://localhost:8000');
  }

  return (
    <main className="flex-1 min-h-0 overflow-y-auto">
      <Dashboard initialContacts={contacts} discoveries={discoveries} />
    </main>
  );
}
