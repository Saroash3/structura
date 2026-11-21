"use client";

import dynamic from "next/dynamic";

/*
 * Lazy-loaded client sections. next/dynamic must be called from a Client Component:
 * calling it in a Server Component (app/page.tsx) breaks rendering in Next 16 and gives no code splitting.
 * These still render on the server (ssr is on); only their JavaScript is split into separate chunks.
 */
export const HowItWorks = dynamic(() => import("@/components/landing/how-it-works").then((m) => m.HowItWorks));
export const TopicsBento = dynamic(() => import("@/components/landing/topics-bento").then((m) => m.TopicsBento));
export const CtaBand = dynamic(() => import("@/components/landing/cta-band").then((m) => m.CtaBand));
export const LiveDemo = dynamic(() => import("@/components/landing/live-demo").then((m) => m.LiveDemo));
