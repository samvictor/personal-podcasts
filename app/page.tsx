'use client'
// test with "yarn dev"
// push to github to deploy

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useState } from 'react';

export default function Home() {
  
  

  
  return (
    <main className="p-24">
      <h1 className='text-xl mb-6'>Personal Podcasts</h1>
      In your podcast player, find a setting that says something like "Follow a Show by URL..."
      <br/>
      Enter this link:
      https://storage.googleapis.com/personal-podcasts-2.firebasestorage.app/rss/testUser/podcastId/testRss.xml
      <br/><br/>
      <a className='underline' href="https://storage.googleapis.com/personal-podcasts-2.firebasestorage.app/audio/testUser/podcastId/daily_update_January%2007%2C%202025_04%3A00.wav"
        >Listen to an Example Here</a>
      <br/><br/>
      Version 0.5
    </main>
  )
}
