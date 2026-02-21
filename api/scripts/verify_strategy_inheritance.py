"""
Verificación estática de herencia BaseStrategy en estrategias spot.
Busca en el código fuente la declaración de clase sin importar los módulos.
"""
import re
from pathlib import Path

STRATEGIES_DIR = Path(r'J:\openClow\.openclaw\workspace\antigravity\signaalKei_platform\api\src\domain\strategies\spot')

def verify_strategies():
    print("=" * 70)
    print("VERIFICACION DE HERENCIA - BaseStrategy (Analisis Estatico)")
    print("=" * 70)
    
    required_methods = ['def apply', 'def get_features']
    optional_methods = ['def on_price_tick']
    
    results = []
    
    for py_file in sorted(STRATEGIES_DIR.glob('*.py')):
        if py_file.name == '__init__.py':
            continue
        
        try:
            content = py_file.read_text(encoding='utf-8')
            
            # Verificar herencia
            inherits = bool(re.search(r'class\s+\w+\s*\(\s*BaseStrategy\s*\)', content))
            
            # Verificar import
            has_import = 'from api.src.domain.strategies.base import BaseStrategy' in content or \
                        'from ..base import BaseStrategy' in content or \
                        'from ...base import BaseStrategy' in content
            
            # Verificar métodos requeridos
            missing = []
            for method in required_methods:
                if method not in content:
                    missing.append(method.replace('def ', ''))
            
            # Verificar métodos opcionales
            optional_present = []
            for method in optional_methods:
                if method in content:
                    optional_present.append(method.replace('def ', ''))
            
            if not inherits or not has_import:
                print(f"\n[FAIL] {py_file.name}")
                print(f"   Herencia: {inherits}")
                print(f"   Import BaseStrategy: {has_import}")
                results.append((py_file.name, False, "No hereda BaseStrategy"))
            elif missing:
                print(f"\n[FAIL] {py_file.name}")
                print(f"   Faltan metodos: {missing}")
                results.append((py_file.name, False, f"Falta: {missing}"))
            else:
                print(f"\n[OK] {py_file.name}")
                print(f"   Hereda: BaseStrategy OK")
                print(f"   Metodos requeridos: {required_methods} OK")
                print(f"   Metodos opcionales: {optional_present if optional_present else 'Ninguno'}")
                results.append((py_file.name, True, "OK"))
                
        except Exception as e:
            print(f"\n[FAIL] {py_file.name}: Error: {e}")
            results.append((py_file.name, False, f"Error: {e}"))
    
    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    
    print(f"Total: {total}")
    print(f"[OK] Aprobadas: {passed}")
    print(f"[FAIL] Fallidas: {failed}")
    
    if failed > 0:
        print("\nFallidas:")
        for name, ok, reason in results:
            if not ok:
                print(f"  - {name}: {reason}")
    
    print("=" * 70)
    return all(ok for _, ok, _ in results)

if __name__ == '__main__':
    success = verify_strategies()
    exit(0 if success else 1)
