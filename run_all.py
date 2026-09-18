import os
import glob
import subprocess
import sys
from core.config import is_profile_enabled

# Hard cap per profile. A scraper thread that never returns keeps main.py alive even after the
# scraping deadline (Python joins worker threads at exit), which would starve the remaining
# profiles until the 6h GitHub Actions limit. Normal runs take ~30 min per profile.
PROFILE_TIMEOUT_SECONDS = 90 * 60

def main():
    # Resolve project root from this script's location (not CWD)
    project_root = os.path.dirname(os.path.abspath(__file__))
    profiles_dir = os.path.join(project_root, "profiles")
    main_script = os.path.join(project_root, "main.py")

    if not os.path.exists(profiles_dir):
        print(f"Directory '{profiles_dir}' not found!")
        return
        
    all_profile_files = sorted(glob.glob(os.path.join(profiles_dir, "*.json")))
    profile_files = [p for p in all_profile_files if is_profile_enabled(p)]
    paused = [os.path.splitext(os.path.basename(p))[0] for p in all_profile_files if p not in profile_files]
    if paused:
        print(f"Skipping paused profiles (\"enabled\": false): {', '.join(paused)}")

    if not profile_files:
        print("No active profiles found in the profiles directory.")
        return

    print(f"Found {len(profile_files)} profiles to process.")
        
    failed_profiles = []
    
    for profile_file in profile_files:
        # Extract profile name (filename without extension)
        profile_name = os.path.splitext(os.path.basename(profile_file))[0]
        
        print("\n" + "="*60)
        print(f"[ STARTING ] PIPELINE FOR PROFILE: {profile_name}")
        print("="*60 + "\n")
        
        # Set environment variable and run main.py
        env = os.environ.copy()
        env["ACTIVE_PROFILE"] = profile_name
        
        try:
            # Run main.py using the current python executable, forwarding CLI arguments
            subprocess.run([sys.executable, main_script, *sys.argv[1:]], env=env, cwd=project_root, check=True, timeout=PROFILE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            print(f"\n[ ERROR ] Pipeline for {profile_name} exceeded {PROFILE_TIMEOUT_SECONDS // 60} min and was killed.")
            failed_profiles.append(profile_name)
        except subprocess.CalledProcessError as e:
            print(f"\n[ ERROR ] Error running pipeline for {profile_name}: {e}")
            failed_profiles.append(profile_name)
        except Exception as e:
            print(f"\n[ ERROR ] Unexpected error for {profile_name}: {e}")
            failed_profiles.append(profile_name)
            
    if failed_profiles:
        print(f"\n[ FAILED ] Pipeline finished with errors in {len(failed_profiles)}/{len(profile_files)} profiles: {', '.join(failed_profiles)}")
        sys.exit(1)
    else:
        print(f"\n[ SUCCESS ] All {len(profile_files)} profiles processed successfully!")

if __name__ == "__main__":
    main()
