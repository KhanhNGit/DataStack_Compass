import re
from typing import List, Tuple
from pyspark.sql.functions import udf
from pyspark.sql.types import IntegerType

SEMVER_REGEX = re.compile(
    r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:-([0-9A-Za-z-.]+))?(?:\+([0-9A-Za-z-.]+))?$'
)

def parse_semver(version: str) -> Tuple[int, int, int, str]:
    if not version:
        return (0, 0, 0, "")
    match = SEMVER_REGEX.match(version.strip())
    if not match:
        return (0, 0, 0, "")
    
    major = int(match.group(1))
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    pre_release = match.group(4) if match.group(4) else ""
    
    return (major, minor, patch, pre_release)

def _cmp(a, b):
    return (a > b) - (a < b)

def compare_pre_release(p1: str, p2: str) -> int:
    if p1 == p2:
        return 0
    if not p1:
        return 1  # No pre-release means it's greater
    if not p2:
        return -1
    
    parts1 = p1.split('.')
    parts2 = p2.split('.')
    
    for pt1, pt2 in zip(parts1, parts2):
        if pt1 == pt2:
            continue
        pt1_is_num = pt1.isdigit()
        pt2_is_num = pt2.isdigit()
        
        if pt1_is_num and pt2_is_num:
            return _cmp(int(pt1), int(pt2))
        elif pt1_is_num:
            return -1 # Numeric is lower than non-numeric
        elif pt2_is_num:
            return 1
        else:
            return _cmp(pt1, pt2)
            
    return _cmp(len(parts1), len(parts2))

def compare_semver(v1: str, v2: str) -> int:
    m1, n1, p1, pr1 = parse_semver(v1)
    m2, n2, p2, pr2 = parse_semver(v2)
    
    if m1 != m2:
        return _cmp(m1, m2)
    if n1 != n2:
        return _cmp(n1, n2)
    if p1 != p2:
        return _cmp(p1, p2)
        
    return compare_pre_release(pr1, pr2)

def sort_versions(versions: List[str], reverse: bool = True) -> List[str]:
    import functools
    return sorted(versions, key=functools.cmp_to_key(compare_semver), reverse=reverse)

def is_version_affected(version: str, range_spec: str) -> bool:
    if not range_spec or range_spec.strip() == "*" or range_spec.strip() == "":
        return True
    
    conditions = [cond.strip() for cond in range_spec.split(',')]
    
    for cond in conditions:
        match = re.match(r'^(>=|<=|>|<|=)?\s*(.*)$', cond)
        if not match:
            continue
        op = match.group(1) or '='
        target = match.group(2).strip()
        
        if 'x' in target.lower() or '*' in target:
            prefix = target.lower().replace('.x', '').replace('.*', '').replace('x', '').replace('*', '')
            clean_ver = version.lstrip('v')
            prefix = prefix.rstrip('.')
            if not (clean_ver == prefix or clean_ver.startswith(prefix + '.')):
                 return False
            continue
            
        cmp_res = compare_semver(version, target)
        
        if op == '>=' and cmp_res < 0:
            return False
        elif op == '<=' and cmp_res > 0:
            return False
        elif op == '>' and cmp_res <= 0:
            return False
        elif op == '<' and cmp_res >= 0:
            return False
        elif op == '=' and cmp_res != 0:
            return False
            
    return True

semver_udf = udf(compare_semver, IntegerType())
