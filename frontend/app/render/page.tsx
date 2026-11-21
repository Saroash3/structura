import { Suspense } from "react";
import type { Metadata } from "next";
import { RenderView } from "@/components/render-view";

export const metadata: Metadata = { title: "Render | Structura", robots: { index: false } };

/** Used only by the backend's headless browser to record the lesson video (see backend/video.py). */
export default function RenderPage() {
  return (
    <Suspense fallback={<div className="fixed inset-0 bg-white" />}>
      <RenderView />
    </Suspense>
  );
}
