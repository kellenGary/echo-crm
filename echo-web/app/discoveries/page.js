"use client";
import React, { useState, useEffect } from 'react';
import { DiscoveryConsole } from '../components/DiscoveryConsole';

export default function DiscoveriesPage() {
  const [discoveries, setDiscoveries] = useState([]);

  useEffect(() => {
    const fetchDiscoveries = async () => {
      try {
        const res = await fetch(`/api/discoveries`);
        if (res.ok) {
          const data = await res.json();
          setDiscoveries(data);
        }
      } catch (err) {
        console.error("Failed to fetch discoveries:", err);
      }
    };
    fetchDiscoveries();
  }, []);

  return (
    <DiscoveryConsole discoveries={discoveries} />
  );
}
