/** Join class names, dropping falsy values. No merge/dedupe — kept deliberately small. */
export function cn(
  ...values: Array<string | false | null | undefined>
): string {
  return values.filter(Boolean).join(" ");
}
