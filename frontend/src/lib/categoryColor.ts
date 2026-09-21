// Well-separated hues with similar weight, assigned by category id so the first categories never share a color.
export const PALETTE = [
  '#3f6fb5', // blue
  '#d9822b', // orange
  '#1f9e89', // teal
  '#7b52ab', // purple
  '#c2453d', // red
  '#7a9a2e', // olive
  '#c6478f', // pink
  '#b8942a', // gold
  '#3aa0c9', // sky
  '#8a5a3c', // brown
  '#4e5bc7', // indigo
  '#2e8b57', // green
]

const NEUTRAL = '#9aa3a0'

/** A stable color per category, so rows can be scanned by color. `Other` is neutral grey so it recedes. */
export function categoryColor(id: number, name: string): string {
  if (name.trim().toLowerCase() === 'other') return NEUTRAL
  return PALETTE[(((id - 1) % PALETTE.length) + PALETTE.length) % PALETTE.length]
}
