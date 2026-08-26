"""
Script to replay the 337 synthetic commit records into REAL local Git commit objects
in data/synthetic/acmepay_codebase/.
PRESERVES AUTHOR, EMAIL, TIMESTAMP, CHRONOLOGICAL ORDERING, AND REAL FILE CHANGES.
DOES NOT PUSH TO GITHUB.
"""

import json
import os
import re
import subprocess
from pathlib import Path

# Map author logins/strings to clean full names and emails
AUTHOR_MAP = {
    "Rakshak Shetty": ("Rakshak Shetty", "rakshak@acmepay.io"),
    "Rakshak29": ("Rakshak Shetty", "rakshak@acmepay.io"),
    "Keyuri Sheth": ("Keyuri Sheth", "keyuri@acmepay.io"),
    "keys246": ("Keyuri Sheth", "keyuri@acmepay.io"),
    "Kshitij Naidu": ("Kshitij Naidu", "kshitij@acmepay.io"),
    "kshitijnaidu": ("Kshitij Naidu", "kshitij@acmepay.io"),
    "Krish Trivedi": ("Krish Trivedi", "krish@acmepay.io"),
    "krish-exe": ("Krish Trivedi", "krish@acmepay.io"),
    "Naman Nahar": ("Naman Nahar", "naman@acmepay.io"),
    "NamanN-Creator": ("Naman Nahar", "naman@acmepay.io"),
    "Parth More": ("Parth More", "parth@acmepay.io"),
    "shadecodes10": ("Parth More", "parth@acmepay.io"),
    "Ananya Sharma": ("Ananya Sharma", "ananya@acmepay.io"),
    "ananyas-code": ("Ananya Sharma", "ananya@acmepay.io"),
    "Vikram Malhotra": ("Vikram Malhotra", "vikram@acmepay.io"),
    "vmalhotra-dev": ("Vikram Malhotra", "vikram@acmepay.io"),
    "Deepa Raman": ("Deepa Raman", "deepa@acmepay.io"),
    "deepa-ram": ("Deepa Raman", "deepa@acmepay.io"),
    "Rohan Gupta": ("Rohan Gupta", "rohan.gupta@acmepay.io"),
    "rohan.gupta": ("Rohan Gupta", "rohan.gupta@acmepay.io"),
    "Meera Patel": ("Meera Patel", "meera@acmepay.io"),
    "mpatel-infra": ("Meera Patel", "meera@acmepay.io"),
    "Siddharth Joshi": ("Siddharth Joshi", "siddharth@acmepay.io"),
    "sjoshi-backend": ("Siddharth Joshi", "siddharth@acmepay.io"),
    "Tanvi Deshmukh": ("Tanvi Deshmukh", "tanvi@acmepay.io"),
    "tdeshmukh-qa": ("Tanvi Deshmukh", "tanvi@acmepay.io"),
    "Aditya Verma": ("Aditya Verma", "aditya.verma@acmepay.io"),
    "averma-sec": ("Aditya Verma", "aditya.verma@acmepay.io"),
    "Neha Kapoor": ("Neha Kapoor", "neha@acmepay.io"),
    "nkapoor-dev": ("Neha Kapoor", "neha@acmepay.io"),
    "Arjun Nair": ("Arjun Nair", "arjun@acmepay.io"),
    "anair-backend": ("Arjun Nair", "arjun@acmepay.io"),
    "Pooja Bhatia": ("Pooja Bhatia", "pooja@acmepay.io"),
    "pbhatia-docs": ("Pooja Bhatia", "pooja@acmepay.io"),
    "Varun Saxena": ("Varun Saxena", "varun@acmepay.io"),
    "vsaxena-ops": ("Varun Saxena", "varun@acmepay.io"),
    "Ritu Sengupta": ("Ritu Sengupta", "ritu@acmepay.io"),
    "rsengupta-data": ("Ritu Sengupta", "ritu@acmepay.io"),
    "Kabir Mehta": ("Kabir Mehta", "kabir@acmepay.io"),
    "kmehta-auth": ("Kabir Mehta", "kabir@acmepay.io"),
}

def parse_author_info(author_raw):
    if "<" in author_raw and ">" in author_raw:
        name = author_raw.split("<")[0].strip()
        email = author_raw.split("<")[1].split(">")[0].strip()
        return name, email

    clean_raw = author_raw.strip()
    if clean_raw in AUTHOR_MAP:
        return AUTHOR_MAP[clean_raw]
    
    # Fallback heuristic
    return clean_raw, f"{clean_raw.lower().replace(' ', '.')}@acmepay.io"

def replay_commits():
    repo_dir = Path("/Users/rakshak/engineering-comtinuity/data/synthetic/acmepay_codebase")
    commits_json_path = Path("/Users/rakshak/engineering-comtinuity/data/synthetic/commits.json")

    with open(commits_json_path, "r", encoding="utf-8") as f:
        commits = json.load(f)

    # Sort commits strictly chronologically by timestamp
    commits.sort(key=lambda x: x["timestamp"])
    total_count = len(commits)
    print(f"Replaying {total_count} commits in chronological order into {repo_dir}...")

    # First, stage all repository files so the initial structure is tracked
    env_base = os.environ.copy()

    for idx, c in enumerate(commits):
        raw_author = c.get("author_id") or c.get("author")
        name, email = parse_author_info(raw_author)
        timestamp = c["timestamp"]
        message = c["message"]
        files_changed = c.get("files_changed", [])

        # Touch or update file comment to guarantee a real file diff for every commit
        for rel_file in files_changed:
            abs_file = repo_dir / rel_file
            if abs_file.exists():
                # Append/update a subtle commit iteration comment
                with open(abs_file, "a", encoding="utf-8") as f_out:
                    if abs_file.suffix in [".go", ".java"]:
                        f_out.write(f"\n// rev: {idx+1} {timestamp}\n")
                    elif abs_file.suffix in [".py", ".yml", ".yaml"]:
                        f_out.write(f"\n# rev: {idx+1} {timestamp}\n")
                    elif abs_file.suffix in [".json"]:
                        # For json, we stage the file directly
                        pass

        # Stage files
        for rel_file in files_changed:
            abs_file = repo_dir / rel_file
            if abs_file.exists():
                subprocess.run(["git", "add", rel_file], cwd=repo_dir, check=True)

        # Also stage README on first commit
        if idx == 0 and (repo_dir / "README.md").exists():
            subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)

        env = env_base.copy()
        env["GIT_AUTHOR_NAME"] = name
        env["GIT_AUTHOR_EMAIL"] = email
        env["GIT_AUTHOR_DATE"] = timestamp
        env["GIT_COMMITTER_NAME"] = name
        env["GIT_COMMITTER_EMAIL"] = email
        env["GIT_COMMITTER_DATE"] = timestamp

        cmd = ["git", "commit", "--allow-empty", "-m", message]
        subprocess.run(cmd, cwd=repo_dir, env=env, check=True, stdout=subprocess.DEVNULL)

    # Finally, stage any remaining uncommitted files so the working tree is 100% clean
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
    env_final = env_base.copy()
    env_final["GIT_AUTHOR_NAME"] = "Rakshak Shetty"
    env_final["GIT_AUTHOR_EMAIL"] = "rakshak@acmepay.io"
    env_final["GIT_AUTHOR_DATE"] = commits[-1]["timestamp"]
    env_final["GIT_COMMITTER_NAME"] = "Rakshak Shetty"
    env_final["GIT_COMMITTER_EMAIL"] = "rakshak@acmepay.io"
    env_final["GIT_COMMITTER_DATE"] = commits[-1]["timestamp"]
    
    subprocess.run(["git", "commit", "-m", "chore: synchronize acmepay codebase final working tree"], cwd=repo_dir, env=env_final, check=False, stdout=subprocess.DEVNULL)

    print("Replay completed successfully!")

if __name__ == "__main__":
    replay_commits()
