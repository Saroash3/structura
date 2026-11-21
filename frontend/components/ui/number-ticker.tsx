"use client"

import { useEffect, useRef, type ComponentPropsWithoutRef } from "react"
import { useMotionValue, useReducedMotion, useSpring } from "motion/react"

import { useReached } from "@/lib/use-reached"

import { cn } from "@/lib/utils"

interface NumberTickerProps extends ComponentPropsWithoutRef<"span"> {
  value: number
  startValue?: number
  direction?: "up" | "down"
  delay?: number
  decimalPlaces?: number
}

export function NumberTicker({
  value,
  startValue = 0,
  direction = "up",
  delay = 0,
  className,
  decimalPlaces = 0,
  ...props
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const motionValue = useMotionValue(direction === "down" ? value : startValue)
  const springValue = useSpring(motionValue, {
    damping: 60,
    stiffness: 100,
  })
  // Structura: useReached instead of useInView, so a skipped-over ticker still counts up
  const isInView = useReached(ref)
  const reduce = useReducedMotion()

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null

    if (isInView) {
      timer = setTimeout(() => {
        motionValue.set(direction === "down" ? startValue : value)
      }, delay * 1000)
    }

    return () => {
      if (timer !== null) {
        clearTimeout(timer)
      }
    }
  }, [motionValue, isInView, delay, value, direction, startValue])

  useEffect(
    () =>
      springValue.on("change", (latest) => {
        if (ref.current) {
          ref.current.textContent = Intl.NumberFormat("en-US", {
            minimumFractionDigits: decimalPlaces,
            maximumFractionDigits: decimalPlaces,
          }).format(Number(latest.toFixed(decimalPlaces)))
        }
      }),
    [springValue, decimalPlaces]
  )

  const format = (n: number) =>
    Intl.NumberFormat("en-US", { minimumFractionDigits: decimalPlaces, maximumFractionDigits: decimalPlaces }).format(n)
  // Structura: screen readers get the real value; reduced motion shows it without counting
  if (reduce) {
    return <span className={cn("inline-block tabular-nums", className)} {...props}>{format(value)}</span>
  }
  return (
    <span className="relative inline-block">
    <span className="sr-only">{format(value)}</span>
    <span
      aria-hidden
      ref={ref}
      className={cn(
        "inline-block tabular-nums",
        className
      )}
      {...props}
    >
      {startValue}
    </span>
    </span>
  )
}
