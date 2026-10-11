import { cn } from '@/lib/utils'

export function Input({ className, type = 'text', ...props }) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'w-full min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
