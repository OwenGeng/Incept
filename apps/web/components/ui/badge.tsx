import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:     "border-transparent bg-primary text-primary-foreground",
        secondary:   "border-border bg-muted text-muted-foreground",
        accent:      "border-accent/20 bg-soft-accent text-accent",
        success:     "border-[rgba(45,138,100,0.2)] bg-success-soft text-success",
        warning:     "border-[rgba(216,146,22,0.2)] bg-warning-soft text-warning",
        destructive: "border-[rgba(208,68,68,0.18)] bg-danger-soft text-destructive",
        outline:     "border-border text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
