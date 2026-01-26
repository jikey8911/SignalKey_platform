"""
Script to restore all imports back to 'api.*' format for running from parent directory
"""
import os
import re

def restore_imports_in_file(filepath):
    """Restore imports in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Restore src to api.src
        content = re.sub(r'from src\.', 'from api.src.', content)
        content = re.sub(r'import src\.', 'import api.src.', content)
        
        # Restore bot to api.bot
        content = re.sub(r'from bot\.', 'from api.bot.', content)
        content = re.sub(r'import bot\.', 'import api.bot.', content)
        
        # Restore config to api.config (but not if it's already api.config)
        content = re.sub(r'from api.config(?!\.)', 'from api.config', content)
        content = re.sub(r'import api.config(?!\.)', 'import api.config', content)
        
        # Restore ml to api.ml
        content = re.sub(r'from ml\.', 'from api.ml.', content)
        content = re.sub(r'import ml\.', 'import api.ml.', content)
        
        # Restore strategies to api.strategies
        content = re.sub(r'from api.strategies(?!\.)', 'from api.strategies', content)
        content = re.sub(r'from api.strategies\.', 'from api.strategies.', content)
        content = re.sub(r'import strategies\.', 'import api.strategies.', content)
        
        # Restore utils to api.utils
        content = re.sub(r'from utils\.', 'from api.utils.', content)
        content = re.sub(r'import utils\.', 'import api.utils.', content)
        
        # Restore main to api.main
        content = re.sub(r'from api.main(?!\.)', 'from api.main', content)
        content = re.sub(r'import api.main(?!\.)', 'import api.main', content)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

def main():
    """Main function to process all Python files"""
    api_dir = r'e:\antigravity\signaalKei_platform\api'
    fixed_count = 0
    
    # Process all .py files
    for root, dirs, files in os.walk(api_dir):
        # Skip venv and __pycache__
        dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.git', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                if restore_imports_in_file(filepath):
                    print(f"Restored: {filepath}")
                    fixed_count += 1
    
    print(f"\nTotal files restored: {fixed_count}")

if __name__ == "__main__":
    main()
