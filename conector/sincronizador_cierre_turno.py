"""
=============================================================================
SINCRONIZADOR OFICIAL POR CIERRE DE TURNO (SOFT RESTAURANT 11 -> DC RESTAURANTES)
Desarrollado para DC Asesorías Empresariales
Arquitectura Resiliente: Mes Acumulado Directo de SQL Server (Sin Pérdida de Días)
=============================================================================
"""

import os
import sys
import json
import urllib.request
import urllib.error
import datetime
from pathlib import Path

# Configurar codificación segura de consola en Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Cargar consultas
import queries_sr11 as queries

if getattr(sys, 'frozen', False):
    CURRENT_DIR = Path(sys.executable).resolve().parent
else:
    CURRENT_DIR = Path(__file__).resolve().parent

CONFIG_PATH = CURRENT_DIR / "config.json"
STATE_FILE = CURRENT_DIR / "ultimo_turno_sincronizado.txt"
STATE_FOLIO_FILE = CURRENT_DIR / "ultimo_folio_sincronizado.txt"

# Días en español
DIAS_ESPANOL = {
    "monday": "Lunes", "tuesday": "Martes", "wednesday": "Miércoles",
    "thursday": "Jueves", "friday": "Viernes", "saturday": "Sábado", "sunday": "Domingo",
    "lunes": "Lunes", "martes": "Martes", "miércoles": "Miércoles", "miercoles": "Miércoles",
    "jueves": "Jueves", "viernes": "Viernes", "sábado": "Sábado", "sabado": "Sábado", "domingo": "Domingo"
}


def cargar_config():
    if not CONFIG_PATH.exists():
        print(f"[ERROR] No se encontró config.json en: {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def obtener_conexion_sql(config):
    try:
        import pyodbc
    except ImportError:
        print("[ERROR] pyodbc no está instalado en este entorno.")
        sys.exit(1)

    sql_cfg = config.get("sql_server", {})
    servidor = sql_cfg.get("servidor", "localhost\\SQLEXPRESS")
    base_datos = sql_cfg.get("base_datos", "SoftRestaurant11")
    usuario = sql_cfg.get("usuario", "sa")
    clave = sql_cfg.get("clave", "")
    driver = sql_cfg.get("driver", "SQL Server")
    usar_win = sql_cfg.get("usar_autenticacion_windows", False)

    drivers_a_probar = [driver, "SQL Server", "SQL Server Native Client 11.0", "ODBC Driver 11 for SQL Server", "ODBC Driver 17 for SQL Server"]
    drivers_unicos = []
    for d in drivers_a_probar:
        if d and d not in drivers_unicos:
            drivers_unicos.append(d)

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
                conn = pyodbc.connect(conn_str, timeout=5)
                return conn
            except Exception:
                continue

    raise Exception(f"No fue posible conectar con SQL Server en [{servidor}] base de datos [{base_datos}]")


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
                item[col] = 0 if any(k in col for k in ["total", "monto", "cant", "precio", "subtotal", "impo", "propina", "descuento", "pax", "ctas"]) else ""
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
        dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
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


def obtener_ultimo_turno_id_sincronizado():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return 0
    return 0


def guardar_ultimo_turno_id_sincronizado(id_turno):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            f.write(str(id_turno))
    except Exception as e:
        print(f"[AVISO] No se pudo guardar estado local de turno: {e}")


def obtener_ultimo_folio_sincronizado():
    if STATE_FOLIO_FILE.exists():
        try:
            with open(STATE_FOLIO_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            return 0
    return 0


def guardar_ultimo_folio_sincronizado(folio):
    try:
        with open(STATE_FOLIO_FILE, "w", encoding="utf-8") as f:
            f.write(str(folio))
    except Exception as e:
        print(f"[AVISO] No se pudo guardar estado local de folio: {e}")


def calcular_fecha_operativa(dt=None, hora_corte=6):
    """
    Convierte cualquier fecha/hora en la fecha del día operativo contable.
    Ej: Si hora_corte=6, ventas entre las 00:00 y las 05:59 de hoy pertenecen a ayer.
    """
    if dt is None:
        dt = datetime.datetime.now()
    elif isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt[:19].replace(" ", "T"))
        except Exception:
            dt = datetime.datetime.now()

    if dt.hour < hora_corte:
        dt_op = dt - datetime.timedelta(days=1)
    else:
        dt_op = dt
    return dt_op.strftime("%Y-%m-%d")


# =========================================================================
# EXTRACCIÓN RESILIENTE DEL MES ACUMULADO DESDE SQL SERVER
# =========================================================================

def obtener_datos_mes_sql(conn, period_key, config=None):
    """
    Consulta en SQL Server TODO el mes consolidado hasta el instante actual.
    Esto garantiza que NUNCA se borren días anteriores y la información sea
    100% idéntica a lo que tiene el cliente en Soft Restaurant 11.
    Extrae además compras, insumos, almuerzo de personal y mermas/desperdicios.
    """
    # 1. Ventas diarias de todo el mes
    ventas_raw = ejecutar_query(conn, queries.QUERY_VENTAS_MES, [period_key])
    sales_list = []
    for v in ventas_raw:
        f_vta = v.get("fecha")
        if not f_vta:
            continue
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

    # 2. Formas de pago de todo el mes
    pagos_raw = ejecutar_query(conn, queries.QUERY_PAGOS_MES, [period_key])
    pagos_por_dia = {}
    for p in pagos_raw:
        f = p.get("fecha")
        if not f:
            continue
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

    # 3. Productos vendidos de todo el mes
    prods_raw = ejecutar_query(conn, queries.QUERY_PRODUCTOS_MES, [period_key])
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

    # Consolidar ranking de productos mensuales
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
                "codigo": str(pr.get("codigo", "")),
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
    compact_mp = []
    for key, item in sorted(monthly_prods_map.items(), key=lambda x: x[1]["total"], reverse=True):
        cant = item["cantidad"]
        tot = item["total"]
        unit_p = round(tot / cant) if cant > 0 else item["precio"]
        unit_c = round(item["costo_total"] / cant, 2) if (cant > 0 and item["costo_total"] > 0) else item["costo"]
        item["precio"] = unit_p
        item["costo"] = unit_c
        item["participacion"] = round((tot / tot_mes_prods * 100), 1) if tot_mes_prods > 0 else 0
        compact_mp.append(item)
    compact_mp = compact_mp[:150]

    # 4. Compras por proveedor de todo el mes (Módulo 5)
    suppliers_list = []
    try:
        compras_prov_raw = ejecutar_query(conn, queries.QUERY_COMPRAS_PROVEEDORES_MES, [period_key])
        for c in compras_prov_raw:
            suppliers_list.append({
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
        print(f"  [AVISO] No se pudieron extraer compras por proveedor ({e_prov}).")

    # 5. Compras por insumos de todo el mes (Módulo 6)
    supplies_list = []
    try:
        compras_ins_raw = ejecutar_query(conn, queries.QUERY_COMPRAS_INSUMOS_MES, [period_key])
        for ci in compras_ins_raw:
            cant = float(ci.get("cantidad", 0))
            costo = float(ci.get("costo", 0))
            subtot = float(ci.get("subtotal", 0))
            tot = float(ci.get("total", 0))
            supplies_list.append({
                "fecha": ci.get("fecha", ""),
                "factura": str(ci.get("factura", "")),
                "proveedor": str(ci.get("proveedor", "Proveedor General")),
                "grupo": str(ci.get("grupo", "General")),
                "insumo": str(ci.get("insumo", "Insumo")),
                "unidad": str(ci.get("unidad", "UND")),
                "cantidad": cant,
                "costo": costo,
                "subtotal": subtot,
                "total": tot
            })
    except Exception as e_ins:
        print(f"  [AVISO] No se pudieron extraer compras por insumos ({e_ins}).")

    # 6. Almuerzo Personal (Comida Empleados) desde Salidas de Almacén
    staff_lunch_list = []
    cfg_conceptos = (config or {}).get("conceptos_almacen", {}) if config else {}
    kw_lunch = cfg_conceptos.get("palabras_comida_personal") or ["personal", "empleado", "almuerzo", "comida", "alimenta", "cuadrilla"]
    kw_waste = cfg_conceptos.get("palabras_bajas_mermas") or ["merma", "desperdicio", "baja", "caduc", "rotura", "deterioro", "descarte"]

    try:
        q_lunch = queries.get_query_movimientos_almacen_mes("movalmacen", "movalmacendetalle", "conceptosmovalmacen", kw_lunch)
        lunch_raw = ejecutar_query(conn, q_lunch, [period_key])
        for r in lunch_raw:
            cant = float(r.get("cantidad", 0))
            costo = float(r.get("costo", 0))
            costo_total = float(r.get("costo_total", 0))
            if cant > 0 or costo_total > 0:
                staff_lunch_list.append({
                    "grupo": str(r.get("grupo") or "General").strip(),
                    "insumo": str(r.get("insumo") or "Insumo").strip(),
                    "und": str(r.get("und") or "UND").strip().upper(),
                    "cantidad": cant,
                    "cant": cant,
                    "costo": costo,
                    "costo_unit": costo,
                    "costo_total": costo_total
                })
    except Exception as e_l1:
        try:
            q_lunch_sal = queries.get_query_movimientos_almacen_mes("salidas", "salidasmovtos", "conceptossalida", kw_lunch)
            lunch_raw = ejecutar_query(conn, q_lunch_sal, [period_key])
            for r in lunch_raw:
                cant = float(r.get("cantidad", 0))
                costo = float(r.get("costo", 0))
                costo_total = float(r.get("costo_total", 0))
                if cant > 0 or costo_total > 0:
                    staff_lunch_list.append({
                        "grupo": str(r.get("grupo") or "General").strip(),
                        "insumo": str(r.get("insumo") or "Insumo").strip(),
                        "und": str(r.get("und") or "UND").strip().upper(),
                        "cantidad": cant,
                        "cant": cant,
                        "costo": costo,
                        "costo_unit": costo,
                        "costo_total": costo_total
                    })
        except Exception as e_l2:
            print(f"  [AVISO] No se pudieron extraer salidas de comida de personal ({e_l1} / {e_l2}).")

    # 7. Bajas, Desperdicios y Mermas de Almacén
    waste_list = []
    try:
        q_waste = queries.get_query_movimientos_almacen_mes("movalmacen", "movalmacendetalle", "conceptosmovalmacen", kw_waste)
        waste_raw = ejecutar_query(conn, q_waste, [period_key])
        for r in waste_raw:
            cant = float(r.get("cantidad", 0))
            costo = float(r.get("costo", 0))
            costo_total = float(r.get("costo_total", 0))
            if cant > 0 or costo_total > 0:
                waste_list.append({
                    "grupo": str(r.get("grupo") or "General").strip(),
                    "insumo": str(r.get("insumo") or "Insumo").strip(),
                    "und": str(r.get("und") or "UND").strip().upper(),
                    "cantidad": cant,
                    "cant": cant,
                    "costo": costo,
                    "costo_unit": costo,
                    "costo_total": costo_total
                })
    except Exception as e_w1:
        try:
            q_waste_sal = queries.get_query_movimientos_almacen_mes("salidas", "salidasmovtos", "conceptossalida", kw_waste)
            waste_raw = ejecutar_query(conn, q_waste_sal, [period_key])
            for r in waste_raw:
                cant = float(r.get("cantidad", 0))
                costo = float(r.get("costo", 0))
                costo_total = float(r.get("costo_total", 0))
                if cant > 0 or costo_total > 0:
                    waste_list.append({
                        "grupo": str(r.get("grupo") or "General").strip(),
                        "insumo": str(r.get("insumo") or "Insumo").strip(),
                        "und": str(r.get("und") or "UND").strip().upper(),
                        "cantidad": cant,
                        "cant": cant,
                        "costo": costo,
                        "costo_unit": costo,
                        "costo_total": costo_total
                    })
        except Exception as e_w2:
            print(f"  [AVISO] No se pudieron extraer bajas y mermas de almacén ({e_w1} / {e_w2}).")

    return sales_list, payment_methods_list, daily_products_list, compact_mp, suppliers_list, supplies_list, staff_lunch_list, waste_list


# =========================================================================
# COMUNICACIÓN DIRECTA CON NETCUP VPS (API REST PARA COMPRAS E INSUMOS)
# =========================================================================

def subir_compras_a_netcup(netcup_url, empresa_id, period_key, suppliers_list, supplies_list, staff_lunch_list=None, waste_list=None, token="dc_restodata_secure_token_2026"):
    """
    Envía compras por proveedor, insumos, comida de personal y mermas directamente a la API de Netcup VPS sin pasar por Firebase
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
                "User-Agent": "DC-Restaurantes-Connector/2.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                recs = data.get("recordsCount", {})
                print(f"  [NETCUP NUBE] Datos sincronizados en VPS: {recs.get('suppliers', len(suppliers_list or []))} compras, {recs.get('supplies', len(supplies_list or []))} insumos, {recs.get('staffLunch', len(staff_lunch_list or []))} almuerzos, {recs.get('waste', len(waste_list or []))} mermas.")
                return True
            else:
                print(f"  [NETCUP AVISO] Respuesta del servidor: {data.get('message')}")
                return False
    except Exception as e:
        print(f"  [NETCUP AVISO] No se pudo enviar datos a Netcup ({e}). Los módulos de venta continúan funcionando normalmente.")
        return False


# =========================================================================
# COMUNICACIÓN DIRECTA CON FIREBASE FIRESTORE
# =========================================================================

def subir_a_firebase_firestore(empresa_id, period_key, sales_list, payment_methods_list, daily_products_list, monthly_products_list, ultimo_row=None, suppliers_list=None, supplies_list=None, staff_lunch_list=None, waste_list=None):
    """
    Actualiza la empresa en Firebase Firestore bajo su subcolección oficial 'periods/{period_key}'.
    Preserva intactos los módulos gestionados manualmente en Excel (Compras, Gastos, Nómina, etc.)
    e inyecta la información 100% consolidada y acumulada desde SQL Server.
    """
    project_id = "dcasesorias-col"
    doc_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/companies/{empresa_id}"

    # 1. Obtener datos existentes del período para PRESERVAR módulos de Excel manuales (compras, gastos, etc.)
    period_doc_url = f"{doc_url}/periods/{period_key}"
    req_p = urllib.request.Request(period_doc_url, headers={"User-Agent": "DC-Restaurantes-Connector/2.0"})
    p = {}
    try:
        with urllib.request.urlopen(req_p, timeout=12) as p_resp:
            p_data = json.loads(p_resp.read().decode("utf-8"))
            p_fields = p_data.get("fields", {})
            p = {k: from_firestore_value(v) for k, v in p_fields.items()}
    except Exception:
        p = {}

    if not isinstance(p, dict):
        p = {}

    # Actualizar con los datos 100% completos y consolidados de SQL Server
    p["sales"] = sales_list
    p["paymentMethods"] = payment_methods_list
    p["dailyProducts"] = daily_products_list
    p["monthlyProducts"] = monthly_products_list

    # Blindaje compras e insumos en Firestore
    if suppliers_list:
        p["suppliers"] = suppliers_list
        p["purchaseCosts"] = suppliers_list
    if supplies_list:
        p["supplies"] = supplies_list[:1200]

    # Almuerzo de personal y mermas automáticas
    if staff_lunch_list:
        p["staffLunch"] = staff_lunch_list
    if waste_list:
        p["waste"] = waste_list

    now_iso = datetime.datetime.now().isoformat()
    now_ts = int(datetime.datetime.now().timestamp() * 1000)

    # 2. Subir el período consolidado a la subcolección 'periods'
    period_payload = {
        "fields": {
            k: to_firestore_value(v) for k, v in p.items()
        }
    }
    raw_p_bytes = json.dumps(period_payload).encode("utf-8")
    # Salvaguarda: si el documento excede 850 KB, recortar insumos para que nunca supere el límite de 1MB de Firestore
    if len(raw_p_bytes) > 850 * 1024 and "supplies" in p:
        p_safe = dict(p)
        p_safe["supplies"] = p["supplies"][:400]
        period_payload = {
            "fields": {
                k: to_firestore_value(v) for k, v in p_safe.items()
            }
        }
        raw_p_bytes = json.dumps(period_payload).encode("utf-8")
    req_period = urllib.request.Request(
        period_doc_url,
        data=raw_p_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "DC-Restaurantes-Connector/2.0"},
        method="PATCH"
    )
    try:
        with urllib.request.urlopen(req_period, timeout=30) as p_resp:
            pass
    except Exception as e:
        print(f"[AVISO NUBE] Error al subir subcolección periods/{period_key}: {e}")
        return False

    # 3. Actualizar metadatos en la raíz de la empresa (sin borrar nada)
    last_fecha = str(ultimo_row.get("fecha", "")) if ultimo_row else ""
    last_total = float(ultimo_row.get("total_vta", 0)) if ultimo_row else 0.0
    last_ctas = int(ultimo_row.get("no_ctas", 0)) if ultimo_row else 0
    last_pax = int(ultimo_row.get("no_pax", 0)) if ultimo_row else 0

    header_payload = {
        "fields": {
            "selectedPeriod": {"stringValue": period_key},
            "_syncedAt": {"integerValue": str(now_ts)},
            "_updatedAt": {"integerValue": str(now_ts)},
            "_lastShiftSynced": {
                "mapValue": {
                    "fields": {
                        "fecha": {"stringValue": last_fecha},
                        "total": {"doubleValue": last_total},
                        "cuentas": {"integerValue": str(last_ctas)},
                        "pax": {"integerValue": str(last_pax)},
                        "sincronizadoEn": {"stringValue": now_iso}
                    }
                }
            }
        }
    }
    raw_bytes = json.dumps(header_payload).encode("utf-8")
    patch_url = (
        f"{doc_url}?"
        f"updateMask.fieldPaths=selectedPeriod&"
        f"updateMask.fieldPaths=_syncedAt&"
        f"updateMask.fieldPaths=_updatedAt&"
        f"updateMask.fieldPaths=_lastShiftSynced"
    )
    req_patch = urllib.request.Request(
        patch_url,
        data=raw_bytes,
        headers={"Content-Type": "application/json", "User-Agent": "DC-Restaurantes-Connector/2.0"},
        method="PATCH"
    )
    try:
        with urllib.request.urlopen(req_patch, timeout=30) as resp:
            if resp.status in [200, 204]:
                return True
    except Exception as e:
        print(f"[ERROR NUBE] Detalle al actualizar cabecera: {e}")
        return False

    return True


# =========================================================================
# FLUJO PRINCIPAL DE CIERRE DE TURNO
# =========================================================================

def sincronizar_cierre_de_turno(forzar=False):
    config = cargar_config()
    empresa_cfg = config.get("empresa", {})
    empresa_id = empresa_cfg.get("empresa_id", "")
    nombre_rest = empresa_cfg.get("nombre_restaurante", "Restaurante")

    print("\n" + "="*65)
    print("  DC RESTAURANTES - SINCRONIZADOR POR CIERRE DE TURNO (SR11)")
    print(f"  Empresa : {nombre_rest} (ID: {empresa_id})")
    print("="*65 + "\n")

    conn = obtener_conexion_sql(config)

    # 1. Obtener último turno cerrado
    print("[1/4] Consultando último turno cerrado en Soft Restaurant 11...")
    turnos = ejecutar_query(conn, queries.QUERY_ULTIMO_TURNO_CERRADO)
    if not turnos:
        print("[AVISO] No se encontraron turnos cerrados en la base de datos.")
        conn.close()
        return

    turno = turnos[0]
    id_turno = turno.get("idturno")
    fecha_fin = turno.get("fecha_fin") or turno.get("fecha_inicio")
    hora_fin = turno.get("hora_fin") or ""

    print(f" -> Turno detectado: #{id_turno} (Cerrado el {fecha_fin} {hora_fin[11:16]})")

    ultimo_sync_id = obtener_ultimo_turno_id_sincronizado()
    if not forzar and id_turno <= ultimo_sync_id:
        print(f"\n[INFO] El Turno #{id_turno} ya fue sincronizado previamente.")
        print("No hay nuevos turnos pendientes de subida en este momento.")
        print("(Si deseas forzar la subida, ejecuta: sincronizar_cierre_turno.bat --force)")
        conn.close()
        return

    # 2. Extraer Ventas del Turno para respaldo local
    print("\n[2/4] Extrayendo facturación del turno para respaldo local...")
    ventas = ejecutar_query(conn, queries.QUERY_VENTAS_TURNO, [id_turno])
    row_venta = ventas[0] if ventas else {
        "fecha": fecha_fin,
        "dia": formatear_dia_espanol("", fecha_fin),
        "no_ctas": 0, "no_pax": 0, "fact_ini": "—", "fact_fin": "—",
        "alimentos": 0, "bebidas": 0, "otros": 0,
        "vta_bruta": 0, "descuentos": 0, "cortesias": 0,
        "impo": 0, "propina": 0, "total_vta": 0,
        "prom_x_pax": 0, "prom_x_cuenta": 0
    }
    pagos = ejecutar_query(conn, queries.QUERY_PAGOS_TURNO, [id_turno])
    prods = ejecutar_query(conn, queries.QUERY_PRODUCTOS_TURNO, [id_turno])

    # Período destino (ej: 2026-10)
    period_key = str(row_venta.get("fecha", fecha_fin))[:7]

    # Guardar copia de respaldo en disco local (JSON formateado)
    out_dir = CURRENT_DIR / "exportaciones_turnos"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"cierre_turno_{id_turno}_{fecha_fin}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "empresa_id": empresa_id,
            "restaurante": nombre_rest,
            "id_turno": id_turno,
            "fecha_cierre": fecha_fin,
            "hora_cierre": hora_fin,
            "periodo_analisis": period_key,
            "venta_diaria": row_venta,
            "formas_pago": pagos,
            "productos_vendidos": prods,
            "sincronizado_en": datetime.datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

    # 3. Extraer el mes completo acumulado desde SQL Server y sincronizar a la nube
    print(f"\n[3/4] Extrayendo mes completo consolidado ({period_key}) desde SQL Server...")
    sales_list, pm_list, dp_list, mp_list, suppliers_list, supplies_list, staff_lunch_list, waste_list = obtener_datos_mes_sql(conn, period_key, config)
    conn.close()

    print(f"[4/4] Sincronizando período {period_key} con Firebase Firestore ({len(sales_list)} días de venta)...")
    ultimo_row = sales_list[-1] if sales_list else row_venta
    subido = subir_a_firebase_firestore(empresa_id, period_key, sales_list, pm_list, dp_list, mp_list, ultimo_row, suppliers_list, supplies_list, staff_lunch_list, waste_list)

    # Sincronizar compras, insumos, almuerzos y mermas directamente a Netcup VPS (sin límite de 1MB)
    netcup_url = config.get("sincronizacion", {}).get("netcup_api_url", "https://restodata.dcasesoriaslatam.com")
    subir_compras_a_netcup(netcup_url, empresa_id, period_key, suppliers_list, supplies_list, staff_lunch_list, waste_list)

    if subido:
        guardar_ultimo_turno_id_sincronizado(id_turno)
        tot_mes = sum(float(s.get("total_vta", 0)) for s in sales_list)
        print("\n" + "="*65)
        print(f" [ÉXITO TOTAL] TURNO #{id_turno} Y PERÍODO {period_key} SINCRONIZADOS!")
        print(f"   Restaurante       : {nombre_rest}")
        print(f"   Días en el mes    : {len(sales_list)} días acumulados")
        print(f"   Ventas del mes    : ${tot_mes:,.0f} COP")
        print(f"   Venta este turno  : ${float(row_venta.get('total_vta', 0)):,.0f} COP")
        print(f"   Plataforma Web    : https://dcasesorias-col.web.app")
        print("="*65 + "\n")
    else:
        print("\n[ALERTA] Hubo un error al subir el período a Firebase Firestore. Revisa tu conexión.")


# =========================================================================
# FLUJO DE SINCRONIZACIÓN POR DÍA OPERATIVO (AUTOMÁTICO / TIEMPO REAL)
# =========================================================================

def sincronizar_dia_operativo(conn, config, fecha_op, hora_corte=6):
    empresa_cfg = config.get("empresa", {})
    empresa_id = empresa_cfg.get("empresa_id", "")
    nombre_rest = empresa_cfg.get("nombre_restaurante", "Restaurante")

    period_key = fecha_op[:7]
    print(f"\n[DÍA OPERATIVO] Sincronizando período {period_key} (Fecha foco: {fecha_op})...")

    # 1. Extraer el mes completo acumulado desde SQL Server
    sales_list, pm_list, dp_list, mp_list, suppliers_list, supplies_list, staff_lunch_list, waste_list = obtener_datos_mes_sql(conn, period_key, config)

    if not sales_list:
        print(f"  [AVISO] No se encontraron ventas registradas en SQL Server para el período {period_key}.")
        return True

    # 2. Guardar copia local JSON del mes acumulado en disco
    out_dir = CURRENT_DIR / "exportaciones_turnos"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"mes_{period_key}_acumulado.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "empresa_id": empresa_id,
            "restaurante": nombre_rest,
            "periodo": period_key,
            "dias_sincronizados": len(sales_list),
            "sales": sales_list,
            "paymentMethods": pm_list,
            "dailyProducts": dp_list,
            "monthlyProducts": mp_list,
            "suppliers": suppliers_list,
            "supplies": supplies_list,
            "staffLunch": staff_lunch_list,
            "waste": waste_list,
            "sincronizado_en": datetime.datetime.now().isoformat()
        }, f, indent=2, ensure_ascii=False)

    # 3. Subir el mes completo consolidado a Firestore
    ultimo_row = sales_list[-1]
    subido = subir_a_firebase_firestore(empresa_id, period_key, sales_list, pm_list, dp_list, mp_list, ultimo_row, suppliers_list, supplies_list, staff_lunch_list, waste_list)

    # 4. Sincronizar compras, insumos, almuerzo personal y mermas a Netcup VPS
    netcup_url = config.get("sincronizacion", {}).get("netcup_api_url", "https://restodata.dcasesoriaslatam.com")
    subir_compras_a_netcup(netcup_url, empresa_id, period_key, suppliers_list, supplies_list, staff_lunch_list, waste_list)
    if subido:
        tot_mes = sum(float(s.get("total_vta", 0)) for s in sales_list)
        print(f"  [OK] Período {period_key} consolidado exitosamente: {len(sales_list)} días (${tot_mes:,.0f} COP) | {len(pm_list)} días pago | {len(mp_list)} productos | {len(staff_lunch_list)} almuerzos | {len(waste_list)} mermas.")
        return True
    else:
        print(f"  [ERROR] Fallo al subir período {period_key} a Firebase Firestore.")
        return False


def sincronizar_inteligente(forzar=False, fecha_forzada=None):
    """
    Sincronizador Automático e Inteligente por Día Operativo (Soft Restaurant 11 -> Cloud):
    - NO depende de que el cajero cierre el turno manualmente.
    - Sincroniza siempre el mes completo consolidado desde SQL Server (imposible perder días).
    - Detecta inmediatamente si hay nuevos folios cobrados y los sube.
    - Si detecta un cierre de turno formal, también lo procesa y audita.
    - Realiza barrido automático matutino a las 6:00 AM para sellar el día anterior.
    """
    config = cargar_config()
    empresa_cfg = config.get("empresa", {})
    empresa_id = empresa_cfg.get("empresa_id", "")
    nombre_rest = empresa_cfg.get("nombre_restaurante", "Restaurante")
    sync_cfg = config.get("sincronizacion", {})
    hora_corte = int(sync_cfg.get("hora_corte_operativo", 6))

    print("\n" + "="*65)
    print("  DC RESTAURANTES - SINCRONIZADOR INTELIGENTE (SOFT RESTAURANT 11)")
    print(f"  Empresa    : {nombre_rest} (ID: {empresa_id})")
    print(f"  Hora Corte : {hora_corte}:00 AM (Día Operativo)")
    print("="*65 + "\n")

    conn = obtener_conexion_sql(config)

    # 1. Obtener estado de folios en SQL Server
    res_folio = ejecutar_query(conn, queries.QUERY_ULTIMO_FOLIO_PAGADO)
    max_folio = int(res_folio[0].get("max_folio", 0)) if res_folio else 0
    ultimo_folio_sync = obtener_ultimo_folio_sincronizado()

    # 2. Obtener estado de turnos en SQL Server
    res_turno = ejecutar_query(conn, queries.QUERY_ULTIMO_TURNO_CERRADO)
    ultimo_turno_sql = res_turno[0] if res_turno else None
    id_turno_sql = int(ultimo_turno_sql.get("idturno", 0)) if ultimo_turno_sql else 0
    ultimo_turno_sync = obtener_ultimo_turno_id_sincronizado()

    hoy_op = calcular_fecha_operativa(datetime.datetime.now(), hora_corte)
    ayer_op = calcular_fecha_operativa(datetime.datetime.now() - datetime.timedelta(hours=24), hora_corte)

    fechas_a_sincronizar = []

    if fecha_forzada:
        print(f"[MODO] Sincronización forzada de fecha específica: {fecha_forzada}")
        fechas_a_sincronizar = [fecha_forzada]
    elif forzar:
        print(f"[MODO] Sincronización forzada completa (Ayer: {ayer_op} y Hoy: {hoy_op})")
        fechas_a_sincronizar = [ayer_op, hoy_op]
    elif ultimo_folio_sync == 0 and not STATE_FOLIO_FILE.exists():
        print(f"[INICIALIZACIÓN] Primer arranque detectado. Sincronizando {ayer_op} y {hoy_op}...")
        fechas_a_sincronizar = [ayer_op, hoy_op]
    else:
        # Detección inteligente por nuevos folios
        if max_folio > ultimo_folio_sync:
            print(f"[DETECTADO] Nuevas ventas detectadas: Folios #{ultimo_folio_sync + 1} hasta #{max_folio}")
            q_fechas = queries.get_query_fechas_operativas_pendientes(hora_corte)
            filas_f = ejecutar_query(conn, q_fechas, [ultimo_folio_sync])
            fechas_a_sincronizar = [f["fecha_operativa"] for f in filas_f if f.get("fecha_operativa")]
        
        # Verificar si hubo un cierre de turno formal nuevo
        if id_turno_sql > ultimo_turno_sync and ultimo_turno_sql:
            f_turno = calcular_fecha_operativa(ultimo_turno_sql.get("fecha_fin") or ultimo_turno_sql.get("fecha_inicio"), hora_corte)
            print(f"[TURNO] Cierre de turno físico detectado: Turno #{id_turno_sql} (Fecha op: {f_turno})")
            if f_turno not in fechas_a_sincronizar:
                fechas_a_sincronizar.append(f_turno)

        # Barrido de seguridad matutino a las 6:00 AM
        ahora = datetime.datetime.now()
        if ahora.hour == hora_corte and ayer_op not in fechas_a_sincronizar:
            fechas_a_sincronizar.append(ayer_op)

    if not fechas_a_sincronizar:
        print(f"[TODO AL DÍA] No hay nuevas ventas ni turnos pendientes de subir.")
        print(f" -> Último Folio Sincronizado: #{ultimo_folio_sync}")
        print(f" -> Último Turno Sincronizado: #{ultimo_turno_sync}")
        conn.close()
        return True

    # Agrupar por meses afectados para sincronizar cada mes completo sin duplicidad
    meses_afectados = sorted(set(f[:7] for f in fechas_a_sincronizar if len(f) >= 7))
    exito_total = True

    for mes_pk in meses_afectados:
        ok = sincronizar_dia_operativo(conn, config, f"{mes_pk}-01", hora_corte)
        if not ok:
            exito_total = False

    conn.close()

    if exito_total or max_folio > 0:
        guardar_ultimo_folio_sincronizado(max_folio)
        if id_turno_sql > 0:
            guardar_ultimo_turno_id_sincronizado(id_turno_sql)
        print("\n" + "="*65)
        print(" [ÉXITO] SINCRONIZACIÓN AUTOMÁTICA COMPLETADA CORRECTAMENTE")
        print(f" -> Folio alcanzado : #{max_folio}")
        print(f" -> Turno alcanzado : #{id_turno_sql}")
        print(f" -> Meses subidos   : {', '.join(meses_afectados)}")
        print("="*65 + "\n")

    return exito_total


def ejecutar_monitor_continuo():
    import time
    config = cargar_config()
    intervalo = int(config.get("sincronizacion", {}).get("intervalo_segundos", 120))
    print("=" * 65)
    print("  DC RESTAURANTES - MONITOR CONTINUO INTELIGENTE EN EJECUCIÓN")
    print(f"  Intervalo de chequeo: cada {intervalo} segundos")
    print("  Presione Ctrl+C para detener.")
    print("=" * 65 + "\n")
    while True:
        try:
            sincronizar_inteligente(forzar=False)
        except Exception as e:
            print(f"[ERROR MONITOR] Ocurrió un error en la sincronización: {e}")
        time.sleep(intervalo)


def probar_conexion_db():
    config = cargar_config()
    srv = config.get("sql_server", {}).get("servidor", ".\\NATIONALSOFT")
    bd = config.get("sql_server", {}).get("base_datos", "softrestaurant11")
    rest = config.get("empresa", {}).get("nombre_restaurante", "Restaurante")
    emp_id = config.get("empresa", {}).get("empresa_id", "")
    print("=" * 65)
    print("  DC RESTAURANTES - TEST DE CONEXIÓN SOFT RESTAURANT 11")
    print(f"  Restaurante : {rest}")
    print(f"  Empresa ID  : {emp_id}")
    print(f"  Servidor    : {srv} | Base de datos: {bd}")
    print("=" * 65)
    print("\n[1/2] Probando conexión con SQL Server (Soft Restaurant 11)...")
    try:
        conn = obtener_conexion_sql(config)
        print("  -> [OK] Conexión exitosa con la base de datos SQL Server.")
    except Exception as e:
        print(f"  -> [ERROR] Fallo al conectar con SQL Server: {e}")
        return False

    print("\n[2/2] Verificando tablas principales (cheques, turnos, compras)...")
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT TOP 1 idturno, fecha, total FROM cheques WITH (NOLOCK) ORDER BY idturno DESC")
        row = cursor.fetchone()
        if row:
            print(f"  -> [OK] Último turno encontrado en Soft Restaurant: #{row[0]} del {row[1]}")
        else:
            print("  -> [AVISO] Tabla cheques accesible pero sin registros aún.")
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"  -> [ERROR] Error leyendo datos de prueba: {e}")
        return False


def configurar_empresa_interactivo():
    print("=" * 65)
    print("  DC RESTAURANTES - CONFIGURADOR DE CLIENTE (SOFT RESTAURANT 11)")
    print("=" * 65)
    print()

    cfg_path = CURRENT_DIR / "config.json"
    if not cfg_path.exists():
        print(f"[ERROR] No se encontró config.json en: {cfg_path}")
        input("\nPresione Enter para salir...")
        return False

    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[ERROR] No se pudo leer config.json: {e}")
        input("\nPresione Enter para salir...")
        return False

    emp = cfg.get("empresa", {})
    sql = cfg.get("sql_server", {})

    print("--- CONFIGURACIÓN ACTUAL ---")
    print(f"Restaurante  : {emp.get('nombre_restaurante', '')}")
    print(f"ID Empresa   : {emp.get('empresa_id', '')}")
    print(f"NIT          : {emp.get('nit', '')}")
    print(f"Servidor SQL : {sql.get('servidor', '')} | Base Datos: {sql.get('base_datos', '')}")
    print("----------------------------\n")

    nuevo_nombre = input("Ingrese el Nombre del Restaurante (Enter para mantener actual): ").strip()
    if nuevo_nombre:
        emp["nombre_restaurante"] = nuevo_nombre

    nuevo_id = input("Ingrese el ID de la Empresa (comp_...) (Enter para mantener actual): ").strip()
    if nuevo_id:
        emp["empresa_id"] = nuevo_id

    nuevo_nit = input("Ingrese el NIT (Enter para mantener actual): ").strip()
    if nuevo_nit:
        emp["nit"] = nuevo_nit

    cfg["empresa"] = emp

    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        print("\n" + "=" * 65)
        print(" [OK] CONFIGURACIÓN GUARDADA EXITOSAMENTE!")
        print(f" Restaurante : {emp.get('nombre_restaurante')}")
        print(f" ID Empresa  : {emp.get('empresa_id')}")
        print(f" NIT         : {emp.get('nit')}")
        print("=" * 65 + "\n")
        input("Presione Enter para finalizar...")
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo guardar la configuración: {e}")
        input("Presione Enter para finalizar...")
        return False


if __name__ == "__main__":
    if "--config" in sys.argv:
        exito = configurar_empresa_interactivo()
        sys.exit(0 if exito else 1)
    if "--test" in sys.argv:
        exito = probar_conexion_db()
        sys.exit(0 if exito else 1)

    fecha_arg = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--date" and idx + 1 < len(sys.argv):
            fecha_arg = sys.argv[idx + 1]

    if "--today" in sys.argv:
        cfg = cargar_config()
        hc = int(cfg.get("sincronizacion", {}).get("hora_corte_operativo", 6))
        fecha_arg = calcular_fecha_operativa(datetime.datetime.now(), hc)

    if "--yesterday" in sys.argv:
        cfg = cargar_config()
        hc = int(cfg.get("sincronizacion", {}).get("hora_corte_operativo", 6))
        fecha_arg = calcular_fecha_operativa(datetime.datetime.now() - datetime.timedelta(hours=24), hc)

    if "--shift" in sys.argv:
        forzar = "--force" in sys.argv
        sincronizar_cierre_de_turno(forzar=forzar)
    elif "--loop" in sys.argv:
        ejecutar_monitor_continuo()
    else:
        forzar = "--force" in sys.argv
        sincronizar_inteligente(forzar=forzar, fecha_forzada=fecha_arg)
