import os
import glob
import subprocess
import sys

def main():
    # Find all json files in profiles directory
    profiles_dir = "profiles"
    if not os.path.exists(profiles_dir):
        print(f"Directory '{profiles_dir}' not found!")
        return
        
    profile_files = sorted(glob.glob(os.path.join(profiles_dir, "*.json")))
    
    if not profile_files:
        print("No profiles found in the profiles directory.")
        return
        
    print(f"Found {len(profile_files)} profiles to process.")
        
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
            # Run main.py using the current python executable
            subprocess.run([sys.executable, "main.py"], env=env, check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[ ERROR ] Error running pipeline for {profile_name}: {e}")
        except Exception as e:
            print(f"\n[ ERROR ] Unexpected error for {profile_name}: {e}")
            
    print("\n[ SUCCESS ] All profiles processed successfully!")

if __name__ == "__main__":
    main()
