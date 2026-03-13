import shutil
from pathlib import Path

def cleanup_domain_skills(skills_dir="data/skills"):
    skills_path = Path(skills_dir)
    if not skills_path.exists():
        print(f"Directory {skills_dir} does not exist.")
        return

    print(f"Scanning {skills_dir} for domain skills cleanup...")
    count = 0
    for item in skills_path.iterdir():
        if item.is_dir() and item.name.startswith("domain-"):
            print(f"Deleting domain skill: {item.name}")
            shutil.rmtree(item)
            count += 1
    
    print(f"\nCleanup finished. Deleted {count} domain skill(s).")
    print("Core skills (web-search, arxiv-research, etc.) have been preserved.")

if __name__ == "__main__":
    # Ensure we are in the project root or provide absolute path
    # For this project, 'data/skills' is relative to the root.
    cleanup_domain_skills()
