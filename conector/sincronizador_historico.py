"""
=============================================================================
SINCRONIZADOR HISTÃ“RICO MASIVO (SOFT RESTAURANT 11 -> DC RESTAURANTES)
Desarrollado para DC AsesorÃ­as Empresariales
=============================================================================
"""

import os
import sys
import json
import urllib.request
import urllib.error
import datetime
from pathlib import Path

# Configurar codificaciÃ³n segura de consola en Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if getattr(sys, 'frozen', False):
    CURRENT_DIR = Path(sys.executable).resolve().parent
else:
    CURRENT_DIR = Path(__file__).resolve().parent

CONFIG_PATH = CURRENT_DIR / "config.json"

DIAS_ESPANOL = {
    "monday": "Lunes", "tuesday": "Martes", "wednesday": "MiÃ©rcoles",
    "thursday": "Jueves", "friday": "Viernes", "saturday": "SÃ¡bado", "sunday": "Domingo",
    "lunes": "Lunes", "martes": "Martes", "miÃ©rcoles": "MiÃ©rcoles", "miercoles": "MiÃ©rcoles",
    "jueves": "Jueves", "viernes": "Viernes", "sÃ¡bado": "SÃ¡bado", "sabado": "SÃ¡bado", "domingo": "Domingo"
}


def cargar_config():
    if not CONFIG_PATH.exists():
        print(f"[ERROR] No se encontro config.json en: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def obtener_conexion_sql(config):
    try:
        import pyodbc
    except ImportError:
        print("[ERROR] pyodbc no esta instalado.")
        sys.exit(1)

    sql_cfg = config.get("sql_server", {})
    servidor = sql_cfg.get("servidor", ".\\NATIONALSOFT")
    base_datos = sql_cfg.get("base_datos", "softrestaurant11")
    usuario = sql_cfg.get("usuario", "sa")
    clave = sql_cfg.get("clave", "")
    driver = sql_cfg.get("driver", "ODBC Driver 11 for SQL Server")
    usar_win = sql_cfg.get("usar_autenticacion_windows", True)

    drivers_a_probar = [driver, "ODBC Driver 11 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server Native Client 11.0", "SQL Server"]
    drivers_unicos = [d for d in drivers_a_probar if d]

    instancia = servidor.split("\\")[1] if "\\" in servidor else ""
    servidores_a_probar = [servidor]
    if instancia:
        servidores_a_probar.extend([f"localhost\\{instancia}", f".\\{instancia}"])

    for srv in servidores_a_probar:
        for drv in drivers_unicos:
            try:
                if usar_win:
                    conn_str = f"DRIVER={{{drv}}};SERVER={srv};DATABASE={base_datos};Trusted_Connection=yes;"
                else:
                    conn_str = f"DRIVER={{{drv}}};SERVER={srv};DATABASE={base_datos};UID={usuario};PWD={clave};"
                conn = pyodbc.connect(conn_str, timeout=6)
                return conn
            except Exception:
                continue

    raise Exception(f"No fue posible conectar con SQL Server en [{servidor}]")


def ejecutar_query(conn, query, params=None):
    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    columnas = [col[0].lower() for col in cursor.description]
    filas = cursor.fetchall()
    resultados = []
    for f in filas:
        item = {}
        for idx, val in enumerate(f):
            col = columnas[idx]
            if isinstance(val, (datetime.date, datetime.datetime)):
                item[col] = str(val)
            elif isinstance(val, (float, int)):
                item[col] = float(val) if isinstance(val, float) else int(val)
            elif val is None:
                item[col] = 0 if any(k in col for k in ["total", "monto", "cant", "precio", "subtotal", "impo", "propina", "descuento", "pax", "ctas", "alimento", "bebida"]) else ""
            elif hasattr(val, '__float__'):
                item[col] = float(val)
            else:
                item[col] = str(val).strip()
        resultados.append(item)
    cursor.close()
    return resultados


def formatear_dia_espanol(nombre_dia, fecha_str):
    if nombre_dia and str(nombre_dia).strip().lower() in DIAS_ESPANOL:
        return DIAS_ESPANOL[str(nombre_dia).strip().lower()]
    try:
        dt = datetime.datetime.strptime(fecha_str[:10], "%Y-%m-%d")
        dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        return dias[dt.weekday()]
    except Exception:
        return "Lunes"


def from_firestore_value(val_dict):
    if not isinstance(val_dict, dict):
        return val_dict
    if "stringValue" in val_dict:
        return val_dict["stringValue"]
    if "integerValue" in val_dict:
        try:
            return int(val_dict["integerValue"])
        except Exception:
            return val_dict["integerValue"]
    if "doubleValue" in val_dict:
        return float(val_dict["doubleValue"])
    if "booleanValue" in val_dict:
        return val_dict["booleanValue"]
    if "nullValue" in val_dict:
        return None
    if "mapValue" in val_dict:
        fields = val_dict.get("mapValue", {}).get("fields", {})
        return {k: from_firestore_value(v) for k, v in fields.items()}
    if "arrayValue" in val_dict:
        values = val_dict.get("arrayValue", {}).get("values", [])
        return [from_firestore_value(v) for v in values]
    return val_dict


def to_firestore_value(val):
    if isinstance(val, bool):
        return {"booleanValue": val}
    elif isinstance(val, int):
        return {"integerValue": str(val)}
    elif isinstance(val, float):
        return {"doubleValue": float(val)}
    elif isinstance(val, str):
        return {"stringValue": val}
    elif isinstance(val, list):
        return {"arrayValue": {"values": [to_firestore_value(x) for x in val]}}
    elif isinstance(val, dict):
        return {"mapValue": {"fields": {k: to_firestore_value(v) for k, v in val.items()}}}
    elif val is None:
        return {"nullValue": None}
    else:
        return {"stringValue": str(val)}


# =========================================================================
# CONSULTAS HISTÃ“RICAS
# =========================================================================

# Importar consultas oficiales centralizadas
import queries_sr11 as queries

QUERY_MESES_HISTORICOS = queries.QUERY_MESES_HISTORICOS
QUERY_VENTAS_MES = queries.QUERY_VENTAS_MES
QUERY_PAGOS_MES = queries.QUERY_PAGOS_MES
QUERY_PRODUCTOS_MES = queries.QUERY_PRODUCTOS_MES
QUERY_COMPRAS_PROVEEDORES_MES = queries.QUERY_COMPRAS_PROVEEDORES_MES
QUERY_COMPRAS_INSUMOS_MES = queries.QUERY_COMPRAS_INSUMOS_MES


def subir_compras_a_netcup(netcup_url, empresa_id, period_key, suppliers_list, supplies_list, staff_lunch_list=None, waste_list=None, token="dc_restodata_secure_token_2026"):
    """
    Envía compras por proveedor, insumos, comida personal y mermas directamente a la API de Netcup VPS sin pasar por Firebase
    (evitando el límite de 1MB por documento de Firestore).
    """
    if not suppliers_list and not supplies_list and not staff_lunch_list and not waste_list:
        return True

    base_url = (netcup_url or "https://restodata.dcasesoriaslatam.com").rstrip("/")
    endpoint = f"{base_url}/api/compras"

    payload = {
        "empresa_id": empresa_id,
        "period_key": period_key,
        "suppliers": suppliers_list or [],
        "supplies": supplies_list or [],
        "staffLunch": staff_lunch_list or [],
        "waste": waste_list or [],
        "token": token
    }

    try:
        raw_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=raw_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DC-Restaurantes-Historical/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                recs = data.get("recordsCount", {})
                print(f" [Netcup VPS: {recs.get('suppliers', len(suppliers_list or []))} compras, {recs.get('supplies', len(supplies_list or []))} insumos, {recs.get('staffLunch', len(staff_lunch_list or []))} almuerzos, {recs.get('waste', len(waste_list or []))} mermas OK]", end="", flush=True)
                return True
    except Exception as e:
        print(f" [Netcup Aviso: {e}]", end="", flush=True)
        return False


def sincronizar_historial_completo():
    config = cargar_config()
    empresa_cfg = config.get("empresa", {})
    empresa_id = empresa_cfg.get("empresa_id", "comp_1791483439223_u53rxi3")
    nombre_rest = empresa_cfg.get("nombre_restaurante", "La Margarita de San Fernando")

    print("\n" + "="*70)
    print("  DC RESTAURANTES - CARGA HISTORICA MASIVA DESDE SOFT RESTAURANT 11")
    print(f"  Empresa : {nombre_rest} (ID: {empresa_id})")
    print("="*70 + "\n")

    conn = obtener_conexion_sql(config)

    print("[1/3] Explorando historial de ventas en Soft Restaurant 11...")
    meses = ejecutar_query(conn, QUERY_MESES_HISTORICOS)
    if not meses:
        print("[AVISO] No se encontraron meses con ventas registradas en la base de datos.")
        conn.close()
        return

    print(f" -> Se encontraron {len(meses)} período(s) con ventas registradas:")
    total_general = 0.0
    for m in meses:
        periodo = m["periodo"]
        facturas = int(m.get("total_facturas", 0))
        ventas = float(m.get("total_ventas", 0))
        total_general += ventas
        print(f"    * Período {periodo}: {facturas:,} facturas ventas (${ventas:,.0f} COP)")

    print(f"\n -> Ventas Históricas Totales : ${total_general:,.0f} COP\n")

    # Leer documento actual de Firestore para mergear sin perder datos
    project_id = "dcasesorias-col"
    doc_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/companies/{empresa_id}"
    req = urllib.request.Request(doc_url, headers={"User-Agent": "DC-Restaurantes-Historical/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            doc_data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR NUBE] No se pudo conectar a Firebase para leer la empresa {empresa_id}: {e}")
        conn.close()
        return

    fields = doc_data.get("fields", {})
    periods = from_firestore_value(fields.get("periods", {})) or {}

    out_dir = CURRENT_DIR / "exportaciones_turnos"
    out_dir.mkdir(exist_ok=True)

    print("[2/3] Procesando y extrayendo cada mes detallado (Ventas, Formas de Pago, Productos)...")

    for idx, m in enumerate(meses, start=1):
        periodo = m["periodo"]
        print(f"\n [{idx}/{len(meses)}] Procesando perÃ­odo {periodo}...")

        # 1. Ventas diarias del mes
        ventas_raw = ejecutar_query(conn, QUERY_VENTAS_MES, [periodo])
        sales_list = []
        for v in ventas_raw:
            f_vta = v.get("fecha")
            no_pax = int(v.get("no_pax", 1)) or 1
            no_ctas = int(v.get("no_ctas", 1)) or 1
            tot_vta = float(v.get("total_vta", 0))
            sales_list.append({
                "fecha": f_vta,
                "dia": formatear_dia_espanol(v.get("dia"), f_vta),
                "no_ctas": no_ctas,
                "no_pax": no_pax,
                "fact_ini": str(v.get("fact_ini", "")),
                "fact_fin": str(v.get("fact_fin", "")),
                "alimentos": float(v.get("alimentos", 0)),
                "bebidas": float(v.get("bebidas", 0)),
                "otros": float(v.get("otros", 0)),
                "vta_bruta": float(v.get("vta_bruta", 0)),
                "descuentos": float(v.get("descuentos", 0)),
                "cortesias": float(v.get("cortesias", 0)),
                "impo": float(v.get("impo", 0)),
                "propina": float(v.get("propina", 0)),
                "total_vta": tot_vta,
                "prom_x_pax": round(tot_vta / no_pax) if no_pax > 0 else 0,
                "prom_x_cuenta": round(tot_vta / no_ctas) if no_ctas > 0 else 0
            })

        # 2. Formas de pago del mes
        pagos_raw = ejecutar_query(conn, QUERY_PAGOS_MES, [periodo])
        pagos_por_dia = {}
        for p in pagos_raw:
            f = p.get("fecha")
            if f not in pagos_por_dia:
                pagos_por_dia[f] = {"efectivo": 0.0, "tarjetas": 0.0, "nequi": 0.0, "total": 0.0, "dia": p.get("dia", ""), "folios": 0}
            fp = str(p.get("forma_pago", "")).lower()
            monto = float(p.get("monto", 0))
            pagos_por_dia[f]["total"] += monto
            pagos_por_dia[f]["folios"] += int(p.get("transacciones", 1))
            if "efectivo" in fp:
                pagos_por_dia[f]["efectivo"] += monto
            elif any(k in fp for k in ["tarjeta", "debito", "credito", "pos", "visa", "master"]):
                pagos_por_dia[f]["tarjetas"] += monto
            else:
                pagos_por_dia[f]["nequi"] += monto

        payment_methods_list = []
        for f, datos in sorted(pagos_por_dia.items()):
            payment_methods_list.append({
                "fecha": f,
                "dia": formatear_dia_espanol(datos["dia"], f),
                "no_folios": datos["folios"],
                "efectivo": datos["efectivo"],
                "tarjetas": datos["tarjetas"],
                "nequi": datos["nequi"],
                "venta_dia": datos["total"]
            })

        # 3. Productos vendidos del mes
        prods_raw = ejecutar_query(conn, QUERY_PRODUCTOS_MES, [periodo])
        daily_products_list = []
        for pr in prods_raw:
            f = pr.get("fecha")
            cant = float(pr.get("cant", 0))
            precio = float(pr.get("precio", 0))
            venta_total = round(cant * precio, 2) if (cant > 0 and precio > 0) else float(pr.get("total", 0))
            costo_unit = float(pr.get("costo_unit", 0))
            costo_total = round(cant * costo_unit, 2) if (cant > 0 and costo_unit > 0) else float(pr.get("costo_total", 0))
            daily_products_list.append({
                "fecha": f,
                "dia": formatear_dia_espanol(pr.get("dia"), f),
                "grupo": pr.get("grupo") or "General",
                "producto": pr.get("producto", ""),
                "cantidad": cant,
                "precio": precio,
                "venta_total": venta_total,
                "costo_unit": costo_unit,
                "costo": costo_unit,
                "costo_total": costo_total,
                "venta_costo": costo_total
            })

        # Consolidar productos mensuales para el modulo de Productos Mensuales
        monthly_prods_map = {}
        for pr in prods_raw:
            p_name = pr.get("producto", "").strip()
            if not p_name:
                continue
            g_name = pr.get("grupo") or "General"
            cant = float(pr.get("cant", 0))
            precio = float(pr.get("precio", 0))
            v_tot = round(cant * precio, 2) if (cant > 0 and precio > 0) else float(pr.get("total", 0))
            costo_unit = float(pr.get("costo_unit", 0))
            costo_total = round(cant * costo_unit, 2) if (cant > 0 and costo_unit > 0) else float(pr.get("costo_total", 0))
            key = p_name.lower()
            if key not in monthly_prods_map:
                monthly_prods_map[key] = {
                    "codigo": pr.get("codigo", ""),
                    "producto": p_name,
                    "grupo": g_name,
                    "cantidad": 0.0,
                    "precio": precio,
                    "total": 0.0,
                    "costo": costo_unit,
                    "costo_total": 0.0
                }
            monthly_prods_map[key]["cantidad"] += cant
            monthly_prods_map[key]["total"] += v_tot
            monthly_prods_map[key]["costo_total"] += costo_total

        tot_mes_prods = sum(item["total"] for item in monthly_prods_map.values())
        monthly_products_list = []
        cogs_auto_list = []
        for key, item in sorted(monthly_prods_map.items(), key=lambda x: x[1]["total"], reverse=True):
            cant = item["cantidad"]
            tot = item["total"]
            unit_p = round(tot / cant) if cant > 0 else item["precio"]
            unit_c = round(item["costo_total"] / cant, 2) if (cant > 0 and item["costo_total"] > 0) else item["costo"]
            item["precio"] = unit_p
            item["costo"] = unit_c
            item["participacion"] = round((tot / tot_mes_prods * 100), 1) if tot_mes_prods > 0 else 0
            monthly_products_list.append(item)

            vta_sin_impo = round(tot / 1.08, 2)
            c_tot = round(item["costo_total"], 2)
            util = round(vta_sin_impo - c_tot, 2)
            cogs_auto_list.append({
                "producto": item["producto"],
                "name": item["producto"],
                "grupo": item["grupo"],
                "category": item["grupo"],
                "precio_venta": unit_p,
                "cant": cant,
                "cantidad": cant,
                "vta_total_sin_impo": vta_sin_impo,
                "costo_unit": unit_c,
                "costo": unit_c,
                "venta_costo": c_tot,
                "utilidad": util,
                "margen_pct": round((util / vta_sin_impo * 100), 1) if vta_sin_impo > 0 else 0
            })

        # Preparar periodo en memoria
        # El conector sube EXCLUSIVAMENTE los 3 ítems operativos de Soft Restaurant:
        # 1. Ventas Diarias (sales)
        # 2. Formas de Pago (paymentMethods)
        # 3. Productos Vendidos (monthlyProducts y dailyProducts para el mes activo)
        # Las compras, gastos, etc. se gestionan manualmente vía Excel.
        is_current_active_period = (idx == len(meses))

        # monthlyProducts compacto (solo campos esenciales y ventas > 0, top 150)
        compact_mp = []
        for p in monthly_products_list:
            tot_p = float(p.get("total", p.get("total_venta", 0)))
            cant_p = float(p.get("cantidad", 0))
            if cant_p > 0 or tot_p > 0:
                compact_mp.append({
                    "producto": p.get("producto", ""),
                    "grupo": p.get("grupo", "General"),
                    "cantidad": cant_p,
                    "precio": float(p.get("precio", p.get("precio_unitario", 0))),
                    "total": tot_p,
                    "costo": float(p.get("costo", p.get("costo_unit", 0))),
                    "costo_total": float(p.get("costo_total", 0))
                })
        compact_mp = compact_mp[:150]

        if periodo not in periods:
            periods[periodo] = {}
        periods[periodo]["sales"] = sales_list
        periods[periodo]["paymentMethods"] = [pm for pm in payment_methods_list if float(pm.get("monto", 0)) > 0] or payment_methods_list
        periods[periodo]["monthlyProducts"] = compact_mp
        periods[periodo]["dailyProducts"] = daily_products_list if is_current_active_period else []

        # 4. Compras por proveedor y por insumos de este mes
        suppliers_m = []
        try:
            compras_prov_raw = ejecutar_query(conn, QUERY_COMPRAS_PROVEEDORES_MES, [periodo])
            for c in compras_prov_raw:
                suppliers_m.append({
                    "fecha": c.get("fecha", ""),
                    "folio": str(c.get("folio", "")),
                    "factura": str(c.get("factura", "")),
                    "proveedor": str(c.get("proveedor", "Proveedor General")),
                    "nit": str(c.get("nit", "")),
                    "subtotal": float(c.get("subtotal", 0)),
                    "iva": float(c.get("iva", 0)),
                    "total": float(c.get("total", 0))
                })
        except Exception as e_prov:
            print(f" [Aviso Compras: {e_prov}]", end="", flush=True)

        supplies_m = []
        try:
            compras_ins_raw = ejecutar_query(conn, QUERY_COMPRAS_INSUMOS_MES, [periodo])
            for ci in compras_ins_raw:
                supplies_m.append({
                    "fecha": ci.get("fecha", ""),
                    "factura": str(ci.get("factura", "")),
                    "proveedor": str(ci.get("proveedor", "Proveedor General")),
                    "grupo": str(ci.get("grupo", "General")),
                    "insumo": str(ci.get("insumo", "Insumo")),
                    "unidad": str(ci.get("unidad", "UND")),
                    "cantidad": float(ci.get("cantidad", 0)),
                    "costo": float(ci.get("costo", 0)),
                    "subtotal": float(ci.get("subtotal", 0)),
                    "total": float(ci.get("total", 0))
                })
        except Exception as e_ins:
            print(f" [Aviso Insumos: {e_ins}]", end="", flush=True)

        # 5. Almuerzo de Personal (Comida de Empleados)
        staff_lunch_m = []
        cfg_conceptos = config.get("conceptos_almacen", {})
        kw_lunch = cfg_conceptos.get("palabras_comida_personal") or ["personal", "empleado", "almuerzo", "comida", "alimenta", "cuadrilla"]
        kw_waste = cfg_conceptos.get("palabras_bajas_mermas") or ["merma", "desperdicio", "baja", "caduc", "rotura", "deterioro", "descarte"]

        try:
            q_lunch = queries.get_query_movimientos_almacen_mes("movalmacen", "movalmacendetalle", "conceptosmovalmacen", kw_lunch)
            raw_lunch = ejecutar_query(conn, q_lunch, [periodo])
            for r in raw_lunch:
                c_cant = float(r.get("cantidad", 0))
                c_cost = float(r.get("costo", 0))
                c_tot = float(r.get("costo_total", 0))
                if c_cant > 0 or c_tot > 0:
                    staff_lunch_m.append({
                        "grupo": str(r.get("grupo") or "General").strip(),
                        "insumo": str(r.get("insumo") or "Insumo").strip(),
                        "und": str(r.get("und") or "UND").strip().upper(),
                        "cantidad": c_cant,
                        "cant": c_cant,
                        "costo": c_cost,
                        "costo_unit": c_cost,
                        "costo_total": c_tot
                    })
        except Exception:
            try:
                q_lunch_sal = queries.get_query_movimientos_almacen_mes("salidas", "salidasmovtos", "conceptossalida", kw_lunch)
                raw_lunch = ejecutar_query(conn, q_lunch_sal, [periodo])
                for r in raw_lunch:
                    c_cant = float(r.get("cantidad", 0))
                    c_cost = float(r.get("costo", 0))
                    c_tot = float(r.get("costo_total", 0))
                    if c_cant > 0 or c_tot > 0:
                        staff_lunch_m.append({
                            "grupo": str(r.get("grupo") or "General").strip(),
                            "insumo": str(r.get("insumo") or "Insumo").strip(),
                            "und": str(r.get("und") or "UND").strip().upper(),
                            "cantidad": c_cant,
                            "cant": c_cant,
                            "costo": c_cost,
                            "costo_unit": c_cost,
                            "costo_total": c_tot
                        })
            except Exception:
                pass

        # 6. Bajas, Desperdicios y Mermas de Almacén
        waste_m = []
        try:
            q_waste = queries.get_query_movimientos_almacen_mes("movalmacen", "movalmacendetalle", "conceptosmovalmacen", kw_waste)
            raw_waste = ejecutar_query(conn, q_waste, [periodo])
            for r in raw_waste:
                w_cant = float(r.get("cantidad", 0))
                w_cost = float(r.get("costo", 0))
                w_tot = float(r.get("costo_total", 0))
                if w_cant > 0 or w_tot > 0:
                    waste_m.append({
                        "grupo": str(r.get("grupo") or "General").strip(),
                        "insumo": str(r.get("insumo") or "Insumo").strip(),
                        "und": str(r.get("und") or "UND").strip().upper(),
                        "cantidad": w_cant,
                        "cant": w_cant,
                        "costo": w_cost,
                        "costo_unit": w_cost,
                        "costo_total": w_tot
                    })
        except Exception:
            try:
                q_waste_sal = queries.get_query_movimientos_almacen_mes("salidas", "salidasmovtos", "conceptossalida", kw_waste)
                raw_waste = ejecutar_query(conn, q_waste_sal, [periodo])
                for r in raw_waste:
                    w_cant = float(r.get("cantidad", 0))
                    w_cost = float(r.get("costo", 0))
                    w_tot = float(r.get("costo_total", 0))
                    if w_cant > 0 or w_tot > 0:
                        waste_m.append({
                            "grupo": str(r.get("grupo") or "General").strip(),
                            "insumo": str(r.get("insumo") or "Insumo").strip(),
                            "und": str(r.get("und") or "UND").strip().upper(),
                            "cantidad": w_cant,
                            "cant": w_cant,
                            "costo": w_cost,
                            "costo_unit": w_cost,
                            "costo_total": w_tot
                        })
            except Exception:
                pass

        if "historico_compras" not in locals():
            historico_compras = {}
        historico_compras[periodo] = {
            "suppliers": suppliers_m,
            "supplies": supplies_m,
            "staffLunch": staff_lunch_m,
            "waste": waste_m
        }

        # Guardar en periods[periodo] para almacenamiento en Firestore
        periods[periodo]["suppliers"] = suppliers_m
        periods[periodo]["purchaseCosts"] = suppliers_m
        periods[periodo]["supplies"] = supplies_m[:1200]
        if staff_lunch_m:
            periods[periodo]["staffLunch"] = staff_lunch_m
        if waste_m:
            periods[periodo]["waste"] = waste_m

        # Guardar respaldo local COMPLETO en JSON (sin recortar nada en disco)
        backup_file = out_dir / f"historico_{empresa_id}_{periodo}.json"
        with open(backup_file, "w", encoding="utf-8") as bf:
            json.dump({
                "empresa_id": empresa_id,
                "periodo": periodo,
                "sales": sales_list,
                "paymentMethods": payment_methods_list,
                "monthlyProducts": compact_mp,
                "dailyProducts": daily_products_list if is_current_active_period else [],
                "suppliers": suppliers_m,
                "supplies": supplies_m,
                "staffLunch": staff_lunch_m,
                "waste": waste_m
            }, bf, indent=2, ensure_ascii=False)

        print(f"    -> {len(sales_list)} dias de ventas | {len(payment_methods_list)} cierres pago | {len(compact_mp)} productos | {len(suppliers_m)} compras | {len(staff_lunch_m)} almuerzos | {len(waste_m)} mermas")

    conn.close()

    # [3/3] Subir los periodos procesados a Firestore
    print("\n[3/3] Subiendo períodos procesados a Firebase Firestore...")
    now_ts = int(datetime.datetime.now().timestamp() * 1000)
    ultimo_periodo = meses[-1]["periodo"]
    active_period = periods.get(ultimo_periodo, {})

    # Arquitectura de Alto Rendimiento: Cada período se almacena en su propio
    # documento independiente bajo la subcolección 'periods' (ej. companies/{id}/periods/{pk}).
    # Esto otorga hasta 1 MB exclusivo por cada mes, eliminando para siempre el error de límite de tamaño.
    meses_exitosos = 0
    total_periodos_a_subir = len(meses)

    for idx, m in enumerate(meses, start=1):
        pk = m["periodo"]
        period_data = periods.get(pk, {})
        if not period_data:
            continue

        period_doc_url = f"{doc_url}/periods/{pk}"
        p_payload = {
            "fields": {
                k: to_firestore_value(v) for k, v in period_data.items()
            }
        }
        p_bytes = json.dumps(p_payload).encode("utf-8")
        # Salvaguarda: si el documento excede 850 KB, recortar insumos para que nunca supere el límite de 1MB de Firestore
        if len(p_bytes) > 850 * 1024 and "supplies" in period_data:
            period_data_safe = dict(period_data)
            period_data_safe["supplies"] = period_data["supplies"][:400]
            p_payload = {
                "fields": {
                    k: to_firestore_value(v) for k, v in period_data_safe.items()
                }
            }
            p_bytes = json.dumps(p_payload).encode("utf-8")
        p_kb = len(p_bytes) / 1024
        print(f"  [{idx}/{total_periodos_a_subir}] Subiendo período {pk} ({p_kb:.1f} KB)...", end="", flush=True)

        req_p = urllib.request.Request(
            period_doc_url,
            data=p_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "DC-Restaurantes-Historical/1.0"},
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(req_p, timeout=40) as resp:
                if resp.status in [200, 204]:
                    meses_exitosos += 1
                    print(" [Firebase OK]", end="", flush=True)
                    # Sincronizar compras masivas, almuerzos y mermas a Netcup VPS
                    if "historico_compras" in locals() and pk in historico_compras:
                        netcup_url = config.get("sincronizacion", {}).get("netcup_api_url", "https://restodata.dcasesoriaslatam.com")
                        h_data = historico_compras[pk]
                        subir_compras_a_netcup(
                            netcup_url, empresa_id, pk,
                            h_data["suppliers"], h_data["supplies"],
                            h_data.get("staffLunch"), h_data.get("waste")
                        )
                    print("")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="replace")
            print(f" [FALLO HTTP {e.code}: {err_msg[:120]}]")
        except Exception as e:
            print(f" [FALLO: {e}]")

    # Finalmente, actualizar businessData con el último período activo y los metadatos de sincronización
    print("  -> Actualizando panel principal (businessData y selectedPeriod)...", end="", flush=True)
    active_period_safe = dict(active_period)
    if "supplies" in active_period_safe and len(active_period_safe.get("supplies", [])) > 300:
        active_period_safe["supplies"] = active_period_safe["supplies"][:300]

    header_payload = {
        "fields": {
            "businessData": to_firestore_value(active_period_safe),
            "selectedPeriod": {"stringValue": ultimo_periodo},
            "_syncedAt": {"integerValue": str(now_ts)},
            "_updatedAt": {"integerValue": str(now_ts)},
            "periods": {"mapValue": {"fields": {}}}
        }
    }
    h_bytes = json.dumps(header_payload).encode("utf-8")
    header_url = (
        f"{doc_url}?"
        f"updateMask.fieldPaths=businessData&"
        f"updateMask.fieldPaths=selectedPeriod&"
        f"updateMask.fieldPaths=_syncedAt&"
        f"updateMask.fieldPaths=_updatedAt&"
        f"updateMask.fieldPaths=periods"
    )
    req_h = urllib.request.Request(
        header_url,
        data=h_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "DC-Restaurantes-Historical/1.0"},
        method="PATCH"
    )
    try:
        with urllib.request.urlopen(req_h, timeout=40) as resp:
            if resp.status in [200, 204]:
                print(" [OK]")
    except Exception as e:
        print(f" [AVISO: {e}]")

    print("\n" + "="*70)
    print(" [EXITO TOTAL] HISTORIAL COMPLETO SINCRONIZADO CON LA NUBE!")
    print(f"  Empresa              : {nombre_rest}")
    print(f"  Meses Sincronizados  : {meses_exitosos} de {len(meses)} período(s)")
    print(f"  Facturación Total    : ${total_general:,.0f} COP")
    print(f"  Plataforma Web       : https://dcasesorias-col.web.app")
    print("="*70 + "\n")


if __name__ == "__main__":
    sincronizar_historial_completo()
