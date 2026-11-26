"""
DIAGNÓSTICO Y EXPLORADOR DE ALMACÉN, COMIDA DE PERSONAL Y MERMAS
Soft Restaurant 11 -> DC RestoData
"""

import sys
import json
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent

def cargar_config():
    cfg_path = CURRENT_DIR / "config.json"
    if not cfg_path.exists():
        print(f"[ERROR] No se encontró config.json en: {cfg_path}")
        return None
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)

def obtener_conexion(config):
    import pyodbc
    sql = config.get("sql_server", {})
    servidor = sql.get("servidor", "localhost\\SQLEXPRESS")
    bd = sql.get("base_datos", "softrestaurant11")
    usuario = sql.get("usuario", "sa")
    clave = sql.get("clave", "")
    driver = sql.get("driver", "SQL Server")
    usar_win = sql.get("usar_autenticacion_windows", False)

    instancia = servidor.split("\\")[1] if "\\" in servidor else ""
    servidores = [servidor]
    if instancia:
        servidores.extend([f"localhost\\{instancia}", f".\\{instancia}"])

    drivers = [driver, "SQL Server", "SQL Server Native Client 11.0", "ODBC Driver 11 for SQL Server", "ODBC Driver 17 for SQL Server"]

    for srv in servidores:
        for drv in drivers:
            try:
                if usar_win:
                    conn_str = f"DRIVER={{{drv}}};SERVER={srv};DATABASE={bd};Trusted_Connection=yes;"
                else:
                    conn_str = f"DRIVER={{{drv}}};SERVER={srv};DATABASE={bd};UID={usuario};PWD={clave};"
                return pyodbc.connect(conn_str, timeout=6)
            except Exception:
                continue
    raise Exception(f"No se pudo conectar a SQL Server [{servidor}] base de datos [{bd}]")

def main():
    print("=" * 70)
    print("  DC RESTODATA - EXPLORADOR DE ALMACÉN, COMIDA Y MERMAS (SR11)")
    print("=" * 70)
    print()

    cfg = cargar_config()
    if not cfg:
        input("Presione Enter para salir...")
        return

    try:
        conn = obtener_conexion(cfg)
        print(" -> [OK] Conectado exitosamente con SQL Server de Soft Restaurant 11.")
    except Exception as e:
        print(f" -> [ERROR] Falló la conexión: {e}")
        input("Presione Enter para salir...")
        return

    cursor = conn.cursor()

    # 1. Explorar tablas existentes en la base de datos
    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
    todas_tablas = [r[0] for r in cursor.fetchall()]

    palabras_clave = ['almacen', 'mov', 'salida', 'merma', 'concepto', 'insumo', 'desperdicio']
    tablas_relevantes = [t for t in todas_tablas if any(k in t.lower() for k in palabras_clave)]

    print(f"\n[1] Tablas de inventarios y almacén detectadas ({len(tablas_relevantes)} tablas):")
    for t in tablas_relevantes:
        print(f"    • {t}")

    # 2. Buscar catálogos de conceptos de movimientos de almacén
    print("\n[2] Buscando catálogo de conceptos de salida / almacén...")
    posibles_tablas_conceptos = [
        'conceptosmovalmacen', 'conceptos_movimientos', 'conceptossalida', 
        'conceptosmov', 'conceptos', 'conceptosinventario', 'conceptos_salida'
    ]
    tabla_conceptos_encontrada = None
    for tc in posibles_tablas_conceptos:
        coincidencias = [t for t in todas_tablas if t.lower() == tc.lower()]
        if coincidencias:
            tabla_conceptos_encontrada = coincidencias[0]
            break

    conceptos_encontrados = []
    if tabla_conceptos_encontrada:
        print(f" -> Tabla de conceptos identificada: [{tabla_conceptos_encontrada}]")
        try:
            cursor.execute(f"SELECT * FROM {tabla_conceptos_encontrada} WITH (NOLOCK)")
            cols = [c[0].lower() for c in cursor.description]
            filas = cursor.fetchall()
            print(f"    Columnas: {', '.join(cols)}")
            print(f"    Total conceptos configurados: {len(filas)}")
            print("-" * 70)
            for f in filas:
                row_dict = dict(zip(cols, f))
                desc = row_dict.get('descripcion') or row_dict.get('nombre') or str(f)
                id_c = row_dict.get('idconcepto') or row_dict.get('idconceptomovimiento') or row_dict.get('id') or ''
                tipo = row_dict.get('tipo') or row_dict.get('naturaleza') or ''
                print(f"    ID: {id_c:<5} | Tipo: {tipo:<3} | Concepto: {desc}")
                conceptos_encontrados.append(row_dict)
        except Exception as e:
            print(f"    Error leyendo {tabla_conceptos_encontrada}: {e}")
    else:
        print(" -> No se encontró una tabla estándar directa de conceptos. Buscando en tablas 'mov'...")

    # 3. Buscar tablas de movimientos de almacén (Cabecera y Detalle)
    print("\n[3] Buscando estructura de movimientos de almacén (Salidas)...")
    candidatos_cabecera = [
        'movalmacen', 'movimientosalmacen', 'movinventario', 'salidasalmacen', 
        'salidas', 'movimientos_inventario', 'encmovalmacen'
    ]
    candidatos_detalle = [
        'movalmacendetalle', 'movimientosalmacendetalle', 'movinventariomovtos', 
        'movinventariodetalle', 'salidasmovtos', 'salidasalmacendetalle', 
        'detalle_movimientos', 'movalmacendet'
    ]

    tabla_cab = None
    for c in candidatos_cabecera:
        matches = [t for t in todas_tablas if t.lower() == c.lower()]
        if matches:
            tabla_cab = matches[0]
            break

    tabla_det = None
    for d in candidatos_detalle:
        matches = [t for t in todas_tablas if t.lower() == d.lower()]
        if matches:
            tabla_det = matches[0]
            break

    print(f" -> Tabla Cabecera de Movimientos : {tabla_cab or '[No detectada automáticamente]'}")
    print(f" -> Tabla Detalle de Insumos     : {tabla_det or '[No detectada automáticamente]'}")

    if tabla_cab and tabla_det:
        try:
            cursor.execute(f"SELECT TOP 1 * FROM {tabla_cab} WITH (NOLOCK)")
            cols_cab = [c[0].lower() for c in cursor.description]
            print(f"\n    Columnas en cabecera ({tabla_cab}):")
            print(f"    {', '.join(cols_cab)}")

            cursor.execute(f"SELECT TOP 1 * FROM {tabla_det} WITH (NOLOCK)")
            cols_det = [c[0].lower() for c in cursor.description]
            print(f"\n    Columnas en detalle ({tabla_det}):")
            print(f"    {', '.join(cols_det)}")
        except Exception as e:
            print(f"    Error inspeccionando columnas: {e}")

    # Guardar reporte en archivo de texto para que el usuario pueda enviárnoslo o revisarlo
    log_path = CURRENT_DIR / "diagnostico_almacen_sr11.txt"
    with open(log_path, "w", encoding="utf-8") as out:
        out.write("REPORTE DE ESTRUCTURA DE ALMACÉN SOFT RESTAURANT 11\n")
        out.write("===================================================\n\n")
        out.write(f"Tablas relevantes: {', '.join(tablas_relevantes)}\n\n")
        out.write(f"Tabla Conceptos: {tabla_conceptos_encontrada}\n")
        for c in conceptos_encontrados:
            out.write(f"  {json.dumps(c, ensure_ascii=False, default=str)}\n")
        out.write(f"\nTabla Cabecera: {tabla_cab}\n")
        out.write(f"Tabla Detalle: {tabla_det}\n")

    print("\n" + "=" * 70)
    print(f"  ¡DIAGNÓSTICO FINALIZADO! Reporte guardado en:")
    print(f"  {log_path}")
    print("=" * 70)
    input("\nPresione Enter para salir...")

if __name__ == "__main__":
    main()
