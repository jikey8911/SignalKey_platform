import os
import glob

def convert_to_utf8(filepath):
    try:
        # Try reading with utf-8 first
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        # If successful, it's already utf-8 (or close enough), but we write back to be sure (e.g. valid utf-8 with BOM)
    except UnicodeDecodeError:
        try:
            # Try cp1252 (common on Windows)
            with open(filepath, 'r', encoding='cp1252') as f:
                content = f.read()
            print(f"Converted {filepath} from cp1252 to utf-8")
        except UnicodeDecodeError:
            try:
                # Try latin-1
                with open(filepath, 'r', encoding='latin-1') as f:
                    content = f.read()
                print(f"Converted {filepath} from latin-1 to utf-8")
            except Exception as e:
                try:
                    # Try utf-16
                    with open(filepath, 'r', encoding='utf-16') as f:
                        content = f.read()
                    print(f"Converted {filepath} from utf-16 to utf-8")
                except Exception as e:
                    print(f"Failed to read {filepath}: {e}")
                    return

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Saved {filepath} as utf-8")
    except Exception as e:
        print(f"Failed to write {filepath}: {e}")

def main():
    base_dir = r"E:\antigravity\signaalKei_platform"
    
    files_to_fix = [
        "api/tests/test_exchanges.py",
        "api/tests/test_strategies.py",
        "api/tests/test_position_aware.py",
        "api/tests/test_sprint1_fixes.py",
        "api/tests/test_sprint1_ml.py",
        "api/tests/test_strategy_loading.py",
        "api/tests/test_strategy_trainer.py",
        "api/tests/test_strategy_trainer_logic.py"
    ]
    
    # Add manual verification tests
    manual_tests = glob.glob(os.path.join(base_dir, "tests/manual_verification/*.py"))
    
    all_files = [os.path.join(base_dir, f) for f in files_to_fix] + manual_tests
    
    for filepath in all_files:
        if os.path.exists(filepath):
            convert_to_utf8(filepath)
        else:
            print(f"File not found: {filepath}")

if __name__ == "__main__":
    main()
