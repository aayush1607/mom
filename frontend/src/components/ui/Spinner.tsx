export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-10 text-ink-3">
      <div className="h-6 w-6 rounded-full border-2 border-ink-3/30 border-t-brand animate-spin" />
      {label ? <span className="text-[13px]">{label}</span> : null}
    </div>
  );
}
