export function parseSemver(version: string): [number, number, number, string] {
  if (!version) return [0, 0, 0, ''];
  const match = version.trim().match(/^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z-.]+))?(?:\+([0-9A-Za-z-.]+))?$/);
  if (!match) return [0, 0, 0, ''];
  
  const major = parseInt(match[1], 10);
  const minor = match[2] ? parseInt(match[2], 10) : 0;
  const patch = match[3] ? parseInt(match[3], 10) : 0;
  const preRelease = match[4] || '';
  
  return [major, minor, patch, preRelease];
}

function cmp(a: number | string, b: number | string): number {
  if (a > b) return 1;
  if (a < b) return -1;
  return 0;
}

function comparePreRelease(p1: string, p2: string): number {
  if (p1 === p2) return 0;
  if (!p1) return 1; // No pre-release means it's greater
  if (!p2) return -1;
  
  const parts1 = p1.split('.');
  const parts2 = p2.split('.');
  
  const len = Math.min(parts1.length, parts2.length);
  for (let i = 0; i < len; i++) {
    const pt1 = parts1[i];
    const pt2 = parts2[i];
    
    if (pt1 === pt2) continue;
    
    const pt1IsNum = /^\d+$/.test(pt1);
    const pt2IsNum = /^\d+$/.test(pt2);
    
    if (pt1IsNum && pt2IsNum) {
      return cmp(parseInt(pt1, 10), parseInt(pt2, 10));
    } else if (pt1IsNum) {
      return -1; // Numeric is lower than non-numeric
    } else if (pt2IsNum) {
      return 1;
    } else {
      return cmp(pt1, pt2);
    }
  }
  return cmp(parts1.length, parts2.length);
}

export function compareVersions(v1: string, v2: string): number {
  const [m1, n1, p1, pr1] = parseSemver(v1);
  const [m2, n2, p2, pr2] = parseSemver(v2);
  
  if (m1 !== m2) return cmp(m1, m2);
  if (n1 !== n2) return cmp(n1, n2);
  if (p1 !== p2) return cmp(p1, p2);
  
  return comparePreRelease(pr1, pr2);
}

export function sortVersions(versions: string[], reverse = true): string[] {
  return [...versions].sort((a, b) => {
    const res = compareVersions(a, b);
    return reverse ? -res : res;
  });
}

export function isVersionNewer(v1: string, v2: string): boolean {
  return compareVersions(v1, v2) > 0;
}
