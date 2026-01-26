"""
Script to fix all 'api.src' and 'api.bot' imports to use relative imports
"""
import os
import re

def fix_imports_in_file(filepath):
    """Fix imports in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace api.src with src
        content = re.sub(r'from api\.src\.', 'from src.', content)
        content = re.sub(r'import api\.src\.', 'import src.', content)
        
        # Replace api.bot with bot
        content = re.sub(r'from api\.bot\.', 'from bot.', content)
        content = re.sub(r'import api\.bot\.', 'import bot.', content)
        
        # Replace api.config with config
        content = re.sub(r'from api\.config', 'from config', content)
        content = re.sub(r'import api\.config', 'import config', content)
        
        # Replace api.ml with ml
        content = re.sub(r'from api\.ml\.', 'from ml.', content)
        content = re.sub(r'import api\.ml\.', 'import ml.', content)
        
        # Replace api.strategies with strategies
        content = re.sub(r'from api\.strategies\.', 'from strategies.', content)
        content = re.sub(r'import api\.strategies\.', 'import strategies.', content)
        
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
    
    # Process all .py files in src, bot, ml, strategies directories
    for root, dirs, files in os.walk(api_dir):
        # Skip venv and __pycache__
        dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.git', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                if fix_imports_in_file(filepath):
                    print(f"Fixed: {filepath}")
                    fixed_count += 1
    
    print(f"\nTotal files fixed: {fixed_count}")

if __name__ == "__main__":
    main()
