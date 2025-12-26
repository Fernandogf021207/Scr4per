import os
import sys
from ftplib import FTP
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env vars
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db', '.env')
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

def get_ftp_connection():
    host = os.getenv('FTP_HOST').replace('ftp://', '').replace('ftps://', '')
    port = int(os.getenv('FTP_PORT', 21))
    user = os.getenv('FTP_USER_RO')
    password = os.getenv('FTP_PASS_RO')
    
    print(f"Connecting to {host}:{port} as {user}...")
    ftp = FTP()
    ftp.connect(host, port)
    ftp.login(user, password)
    return ftp

def list_recursive(ftp, path, level=0):
    indent = "  " * level
    print(f"{indent}[DIR] {path}")
    
    try:
        items = []
        ftp.dir(path, items.append)
        
        for item in items:
            # Parse typical ls -l output
            # drwxr-xr-x    2 ftp      ftp          4096 Nov 27 10:00 foldername
            parts = item.split()
            name = " ".join(parts[8:]) # Handle spaces in filenames if possible, though simple split might fail on dates.
            # Better parsing:
            # The last part is usually the name, but date can be tricky.
            # Let's assume standard format for now.
            
            # Try to be robust about name extraction
            # If we assume the format is consistent: permissions links owner group size month day time/year name
            # That's 8 fields before name.
            if len(parts) >= 9:
                name = " ".join(parts[8:])
            else:
                name = parts[-1]

            if name in ['.', '..']:
                continue
                
            full_path = f"{path}/{name}"
            
            is_dir = item.startswith('d')
            
            if is_dir:
                list_recursive(ftp, full_path, level + 1)
            else:
                print(f"{indent}  - {name}")
                
    except Exception as e:
        print(f"{indent}Error listing {path}: {e}")

def main():
    base_path = os.getenv('FTP_BASE_PATH', 'redes_sociales')
    abs_path = os.getenv('FTP_ABSOLUTE_PATH', 'ftp/upload')
    
    # Ensure paths don't have leading/trailing slashes that might confuse concatenation
    abs_path = abs_path.strip('/')
    base_path = base_path.strip('/')
    
    target_path = f"{abs_path}/{base_path}"
    
    print(f"Target path: {target_path}")
    
    try:
        ftp = get_ftp_connection()
        list_recursive(ftp, target_path)
        ftp.quit()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
