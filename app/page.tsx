'use client'
// test with "yarn dev"

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useState } from 'react';

export default function Home() {
  
  const [data, setData] = useState(null);
  
  useEffect(() => {
    fetch('/api/apiExample')
      .then(response => response.json())
      .then(json => setData(json))
      .catch(error => console.error(error));
  }, []);

  console.log("data is", data);
  
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      <div className="z-10 w-full max-w-5xl items-center justify-between font-mono text-sm lg:flex">
        In your podcast player, find a setting that says something like "Follow a Show by URL..."
        <br/>
        Enter this link:
        <br/>
        https://storage.googleapis.com/personal-podcasts-2.firebasestorage.app/rss/testUser/podcastId/testRss.xml
        <br/>
        Firebase! version 0.4
      </div>
    </main>
  )
}
