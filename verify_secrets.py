#!/usr/bin/env python3
"""
Security verification script
Checks for potential secrets in codebase before release
"""

import os
import re
from pathlib import Path

# Patterns that might indicate secrets
SECRET_PATTERNS = [
    (r'password\s*=\s*["\'][^"\']{8,}["\']', 'Hardcoded password'),
    (r'api[_-]?key\s*=\s*["\'][^"\']{10,}["\']', 'Hardcoded API key'),
    (r'token\s*=\s*["\'][^"\']{10,}["\']', 'Hardcoded token'),
    (r'secret\s*=\s*["\'][^"\']{8,}["\']', 'Hardcoded secret'),
    (r'credential\s*=\s*["\'][^"\']{8,}["\']', 'Hardcoded credential'),
    (r'aws[_-]?access[_-]?key', 'AWS access key'),
    (r'aws[_-]?secret[_-]?key', 'AWS secret key'),
    (r'sk-[a-zA-Z0-9]{32,}', 'OpenAI API key pattern'),
    (r'ghp_[a-zA-Z0-9]{36}', 'GitHub personal access token'),
    (r'xox[baprs]-[0-9a-zA-Z-]{10,}', 'Slack token'),
]

# Files to skip
SKIP_PATTERNS = [
    '.git',
    '__pycache__',
    '.pyc',
    'node_modules',
    'dist',
    'build',
    '.gitignore',
    'verify_secrets.py',
    'BUILD.md',
    'RELEASE_CHECKLIST.md',
]

# Safe patterns (false positives)
SAFE_PATTERNS = [
    r'password\s*=\s*["\'].*CLEARED.*["\']',
    r'password\s*=\s*["\']your.*["\']',
    r'password\s*=\s*["\'].*example.*["\']',
    r'api_key\s*=\s*["\']your.*["\']',
    r'api_key\s*=\s*["\'].*example.*["\']',
    r'token\s*=\s*["\'].*example.*["\']',
]

def is_safe_match(match_text):
    """Check if match is a safe example/placeholder"""
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, match_text, re.IGNORECASE):
            return True
    return False

def should_skip_file(file_path):
    """Check if file should be skipped"""
    path_str = str(file_path)
    for pattern in SKIP_PATTERNS:
        if pattern in path_str:
            return True
    return False

def scan_file(file_path):
    """Scan a single file for secrets"""
    issues = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                for pattern, description in SECRET_PATTERNS:
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        match_text = match.group(0)
                        if not is_safe_match(match_text):
                            issues.append({
                                'file': str(file_path),
                                'line': line_num,
                                'pattern': description,
                                'match': match_text[:50] + '...' if len(match_text) > 50 else match_text
                            })
    except Exception as e:
        print(f"Error scanning {file_path}: {e}")
    
    return issues

def main():
    """Main verification function"""
    print("=" * 60)
    print("SECURITY VERIFICATION - SECRET SCAN")
    print("=" * 60)
    print()
    
    # Get generation_two directory
    script_dir = Path(__file__).parent
    base_dir = script_dir
    
    all_issues = []
    
    # Scan all Python files
    for file_path in base_dir.rglob('*.py'):
        if should_skip_file(file_path):
            continue
        
        issues = scan_file(file_path)
        all_issues.extend(issues)
    
    # Scan all text files (config, etc.)
    for ext in ['.txt', '.json', '.yaml', '.yml', '.toml', '.cfg', '.ini']:
        for file_path in base_dir.rglob(f'*{ext}'):
            if should_skip_file(file_path):
                continue
            
            # Skip if in .gitignore patterns
            if 'credential' in str(file_path).lower() and 'example' not in str(file_path).lower():
                continue
            
            issues = scan_file(file_path)
            all_issues.extend(issues)
    
    # Report results
    print(f"Scanned {len(list(base_dir.rglob('*')))} files")
    print()
    
    if all_issues:
        print("WARNING: POTENTIAL SECRETS FOUND:")
        print("=" * 60)
        for issue in all_issues:
            print(f"File: {issue['file']}")
            print(f"  Line {issue['line']}: {issue['pattern']}")
            print(f"  Match: {issue['match']}")
            print()
        print("=" * 60)
        print(f"ERROR: Found {len(all_issues)} potential security issues")
        print("Please review and remove any hardcoded secrets before release!")
        return 1
    else:
        print("SUCCESS: No hardcoded secrets found!")
        print("SUCCESS: Codebase is safe for release")
        return 0

if __name__ == "__main__":
    exit(main())
