import { levelClasses } from "@/lib/api";
import { cn } from "@/lib/utils";

export function LevelBadge({ level }: { level: string | null | undefined }) {
  if (!level) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide",
        levelClasses(level),
      )}
    >
      {level}
    </span>
  );
}
