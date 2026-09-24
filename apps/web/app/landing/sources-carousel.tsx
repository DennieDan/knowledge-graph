"use client";

import { Badge } from "@/components/ui/badge";
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "@/components/ui/carousel";
import { sources } from "@/lib/site";
import styles from "./page.module.css";

export default function SourcesCarousel() {
  return (
    <Carousel
      opts={{ align: "start", loop: true }}
      className={`${styles.sourceCarousel} w-full sm:px-14`}
    >
      <CarouselContent className="-ml-4">
        {sources.map((source) => (
          <CarouselItem
            key={source.channel}
            className="pl-4 sm:basis-1/2 lg:basis-1/3"
          >
            <article className="flex h-full flex-col gap-3 rounded-xl border border-border bg-card p-6">
              <Badge className="w-fit bg-secondary text-secondary-foreground">
                {source.channel}
              </Badge>
              <p className="text-[15px] leading-relaxed text-foreground">
                {source.detail}
              </p>
              <p className="mt-auto rounded-lg bg-muted p-3 font-mono text-[13px] text-muted-foreground">
                {source.example}
              </p>
            </article>
          </CarouselItem>
        ))}
      </CarouselContent>
      <CarouselPrevious className="left-0 hidden sm:flex" />
      <CarouselNext className="right-0 hidden sm:flex" />
    </Carousel>
  );
}
