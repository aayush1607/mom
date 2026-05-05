"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "brand" | "ghost" | "outline";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  fullWidth?: boolean;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  brand:
    "bg-brand text-white hover:opacity-95 active:opacity-90 disabled:opacity-50",
  ghost:
    "bg-transparent text-ink-2 hover:text-ink hover:bg-line/40 disabled:opacity-50",
  outline:
    "bg-card text-ink border border-line hover:bg-bg/60 disabled:opacity-50",
};

export function Button({
  variant = "brand",
  fullWidth = false,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      className={`
        inline-flex items-center justify-center
        px-5 py-3 rounded-2xl text-[15px] font-medium
        transition-all duration-150
        focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/60
        ${fullWidth ? "w-full" : ""}
        ${VARIANT_CLASSES[variant]}
        ${className}
      `}
    >
      {children}
    </button>
  );
}
