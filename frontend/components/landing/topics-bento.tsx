"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BentoGrid } from "@/components/ui/bento-grid";
import { MagicCard } from "@/components/ui/magic-card";
import { ScrollReveal, SectionHeading } from "@/components/landing/scroll-reveal";
import { BfsMini, LinkedListMini, QueueMini, StackMini, TreeMini } from "@/components/landing/topic-minis";
import { cn } from "@/lib/utils";

type Mini = (props: { active: boolean }) => React.ReactNode;

const TOPICS: { name: string; topic: string; text: string; Mini: Mini; span: string }[] = [
  { name: "Queue", topic: "how does a queue work", text: "First in, first out. Enqueue at the back, dequeue from the front, and watch the front label follow.", Mini: QueueMini, span: "md:col-span-2" },
  { name: "Stack", topic: "how does a stack work", text: "Last in, first out. Push and pop on the top of the pile.", Mini: StackMini, span: "md:row-span-2" },
  { name: "Linked list", topic: "how does a linked list insert and delete", text: "Nodes joined by pointers. Walk the chain to search or delete.", Mini: LinkedListMini, span: "" },
  { name: "Binary search tree", topic: "how does a binary search tree insert and search", text: "Smaller goes left, larger goes right. Searches follow one path down.", Mini: TreeMini, span: "" },
  { name: "Breadth first search", topic: "show breadth first search on a graph", text: "Explore a graph level by level, driven by a real queue of nodes to visit.", Mini: BfsMini, span: "md:col-span-3" },
];

function TopicCard({ name, topic, text, Mini, span, index }: (typeof TOPICS)[number] & { index: number }) {
  const [active, setActive] = useState(false);
  const on = () => setActive(true), off = () => setActive(false);
  return (
    <ScrollReveal delay={index * 0.07} className={cn("h-full", span)}>
      <Link href={`/app?topic=${encodeURIComponent(topic)}`}
        onPointerEnter={on} onPointerLeave={off} onFocus={on} onBlur={off}
        className="group block h-full rounded-2xl transition-transform duration-300 hover:-translate-y-1 focus-visible:-translate-y-1">
        <MagicCard className="h-full rounded-2xl" gradientColor="#2A2A2A" gradientOpacity={0.6} gradientSize={260}
          gradientFrom="#FF7A1A" gradientTo="#4CC9F0">
          <div className="flex h-full flex-col gap-5 p-5 sm:p-6">
            <div className="grid min-h-44 flex-1 place-items-center overflow-hidden rounded-xl border border-border/60 bg-stage px-3 py-6">
              <Mini active={active} />
            </div>
            <div className="flex items-end justify-between gap-4">
              <div>
                <h3 className="text-xl font-semibold">{name}</h3>
                <p className="mt-1.5 max-w-md text-[15px] leading-relaxed text-muted">{text}</p>
              </div>
              <span className="grid size-10 shrink-0 place-items-center rounded-full border border-border text-muted transition-[color,border-color,transform] duration-300 group-hover:translate-x-0.5 group-hover:border-accent2 group-hover:text-accent2"
                aria-hidden>
                <ArrowRight className="size-4" />
              </span>
            </div>
          </div>
        </MagicCard>
        <span className="sr-only">Start a lesson about {name.toLowerCase()}</span>
      </Link>
    </ScrollReveal>
  );
}

export function TopicsBento() {
  return (
    <section id="topics" aria-labelledby="topics-title" className="section-y scroll-mt-20 border-t border-border">
      <div className="container-page">
        <SectionHeading id="topics-title" eyebrow="Topics" title="Pick a structure. Hover to see it move."
          lead="Each card opens a fresh lesson. Arrays and bubble sort are supported too, just ask." />
        <BentoGrid className="mt-14 max-w-none gap-4 md:auto-rows-[minmax(19rem,auto)] md:grid-cols-3">
          {TOPICS.map((t, i) => <TopicCard key={t.name} {...t} index={i} />)}
        </BentoGrid>
      </div>
    </section>
  );
}
