"""
CONSULTAS SQL OFICIALES PARA SOFT RESTAURANT 11 (SR11)
Modo: 100% Solo Lectura (SELECT con WITH (NOLOCK))
Mapeo exacto hacia DC Restaurantes (Módulos 1, 2, 3, 4, 5, 6, 10 y 11)
"""

# =========================================================================
# 1. CONSULTAS PARA CIERRE DE TURNO (CORTE Z / CIERRE DE CAJA EN VIVO)
# =========================================================================

# 1.1 ÚLTIMO TURNO CERRADO
QUERY_ULTIMO_TURNO_CERRADO = """
SELECT TOP 1 
    t.idturno,
    CONVERT(VARCHAR(10), t.apertura, 120) AS fecha_inicio,
    CONVERT(VARCHAR(10), ISNULL(t.cierre, t.apertura), 120) AS fecha_fin,
    CONVERT(VARCHAR(19), t.apertura, 120) AS hora_inicio,
    CONVERT(VARCHAR(19), ISNULL(t.cierre, t.apertura), 120) AS hora_fin,
    CASE WHEN t.cierre IS NOT NULL THEN 1 ELSE 0 END AS cerrado,
    ISNULL(t.cajero, '') AS idusuario
FROM turnos t WITH (NOLOCK)
WHERE t.cierre IS NOT NULL
ORDER BY t.idturnointerno DESC;
"""

# 1.2 VENTAS DEL TURNO (Módulo 1: Renglón del Turno/Día)
QUERY_VENTAS_TURNO = """
SELECT 
    c.idturno,
    CONVERT(VARCHAR(10), MIN(c.fecha), 120) AS fecha,
    DATENAME(WEEKDAY, MIN(c.fecha)) AS dia,
    COUNT(DISTINCT c.folio) AS no_ctas,
    SUM(ISNULL(c.nopersonas, 1)) AS no_pax,
    MIN(c.folio) AS fact_ini,
    MAX(c.folio) AS fact_fin,
    SUM(ISNULL(c.totalalimentos, 0)) AS alimentos,
    SUM(ISNULL(c.totalbebidas, 0)) AS bebidas,
    SUM(ISNULL(c.totalotros, 0)) AS otros,
    SUM(ISNULL(c.subtotal, 0)) AS vta_bruta,
    SUM(ISNULL(c.totaldescuentos, 0)) AS descuentos,
    SUM(ISNULL(c.totalcortesias, 0)) AS cortesias,
    SUM(ISNULL(c.totalimpuesto1, 0)) AS impo,
    SUM(ISNULL(c.propina, 0)) AS propina,
    SUM(ISNULL(c.total, 0)) AS total_vta
FROM cheques c WITH (NOLOCK)
WHERE c.cancelado = 0 AND c.pagado = 1
  AND c.idturno = ?
GROUP BY c.idturno;
"""

# 1.3 FORMAS DE PAGO DEL TURNO (Módulo 2: Desglose por Efectivo, Tarjetas, Nequi, etc.)
QUERY_PAGOS_TURNO = """
SELECT 
    CONVERT(VARCHAR(10), c.fecha, 120) AS fecha,
    DATENAME(WEEKDAY, c.fecha) AS dia,
    ISNULL(fp.descripcion, 'Efectivo') AS forma_pago,
    COUNT(cp.folio) AS transacciones,
    SUM(ISNULL(cp.importe, 0)) AS monto,
    SUM(ISNULL(cp.propina, 0)) AS propina
FROM chequespagos cp WITH (NOLOCK)
INNER JOIN cheques c WITH (NOLOCK) ON cp.folio = c.folio
LEFT JOIN formasdepago fp WITH (NOLOCK) ON cp.idformadepago = fp.idformadepago
WHERE c.cancelado = 0 AND c.pagado = 1
  AND c.idturno = ?
GROUP BY CONVERT(VARCHAR(10), c.fecha, 120), DATENAME(WEEKDAY, c.fecha), fp.descripcion
ORDER BY monto DESC;
"""

# 1.4 PRODUCTOS VENDIDOS EN EL TURNO (Módulos 3 y 4: cheqdet oficial)
QUERY_PRODUCTOS_TURNO = """
SELECT 
    CONVERT(VARCHAR(10), c.fecha, 120) AS fecha,
    DATENAME(WEEKDAY, c.fecha) AS dia,
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')) AS grupo,
    RTRIM(cd.idproducto) AS codigo,
    RTRIM(p.descripcion) AS producto,
    SUM(ISNULL(cd.cantidad, 0)) AS cant,
    CASE 
        WHEN SUM(ISNULL(cd.cantidad, 0)) > 0 
        THEN ROUND(SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) / SUM(ISNULL(cd.cantidad, 0)), 0)
        ELSE AVG(ISNULL(cd.precio, 0))
    END AS precio,
    SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) AS total,
    CAST(ISNULL(rc.costo_receta, 0.0) AS FLOAT) AS costo_unit,
    CAST(ROUND(SUM(ISNULL(cd.cantidad, 0)) * ISNULL(rc.costo_receta, 0.0), 2) AS FLOAT) AS costo_total
FROM cheqdet cd WITH (NOLOCK)
INNER JOIN cheques c WITH (NOLOCK) ON cd.foliodet = c.folio
LEFT JOIN productos p WITH (NOLOCK) ON RTRIM(LTRIM(cd.idproducto)) = RTRIM(LTRIM(p.idproducto))
LEFT JOIN grupos g WITH (NOLOCK) ON RTRIM(LTRIM(p.idgrupo)) = RTRIM(LTRIM(g.idgrupo))
LEFT JOIN subgruposproductos sgp WITH (NOLOCK) ON RTRIM(LTRIM(p.idproducto)) = RTRIM(LTRIM(sgp.idproducto))
LEFT JOIN subgrupos sg WITH (NOLOCK) ON RTRIM(LTRIM(sgp.idsubgrupo)) = RTRIM(LTRIM(sg.idsubgrupo))
LEFT JOIN (
    SELECT 
        RTRIM(LTRIM(cst.idproducto)) AS idprod,
        SUM(ISNULL(cst.cantidad, 0) * ISNULL(NULLIF(id.costopromedio, 0), ISNULL(id.costo, 0))) AS costo_receta
    FROM costos cst WITH (NOLOCK)
    INNER JOIN insumosdetalle id WITH (NOLOCK) ON RTRIM(LTRIM(cst.idinsumo)) = RTRIM(LTRIM(id.idinsumo))
    GROUP BY cst.idproducto
) rc ON RTRIM(LTRIM(cd.idproducto)) = rc.idprod
WHERE c.cancelado = 0 AND c.pagado = 1
  AND c.idturno = ?
GROUP BY CONVERT(VARCHAR(10), c.fecha, 120), DATENAME(WEEKDAY, c.fecha), 
         ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')), 
         cd.idproducto, p.descripcion, rc.costo_receta
ORDER BY total DESC;
"""

# 1.5 COMPRAS POR PROVEEDOR POR FECHA/TURNO (Módulo 5)
QUERY_COMPRAS_PROVEEDORES_FECHA = """
SELECT 
    CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) AS fecha,
    RTRIM(ISNULL(c.folio, '')) AS folio,
    RTRIM(ISNULL(c.foliofactura, ISNULL(c.folio, ''))) AS factura,
    RTRIM(ISNULL(p.razonsocial, ISNULL(p.nombre, 'Proveedor General'))) AS proveedor,
    RTRIM(ISNULL(p.rfc, '')) AS nit,
    CAST(ISNULL(c.subtotal, 0) AS FLOAT) AS subtotal,
    CAST(ISNULL(c.impuesto1, 0) AS FLOAT) AS iva,
    CAST(ISNULL(c.total, 0) AS FLOAT) AS total
FROM compras c WITH (NOLOCK)
LEFT JOIN proveedores p WITH (NOLOCK) ON c.idproveedor = p.idproveedor
WHERE ISNULL(c.cancelado, 0) = 0
  AND CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) = ?
ORDER BY fecha ASC;
"""

# 1.6 COMPRAS POR INSUMOS POR FECHA/TURNO (Módulo 6)
QUERY_COMPRAS_INSUMOS_FECHA = """
SELECT 
    CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) AS fecha,
    RTRIM(ISNULL(c.foliofactura, ISNULL(c.folio, ''))) AS factura,
    RTRIM(ISNULL(p.razonsocial, ISNULL(p.nombre, 'Proveedor General'))) AS proveedor,
    RTRIM(ISNULL(g.descripcion, 'General')) AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS unidad,
    CAST(ISNULL(cm.cantidad, 0) AS FLOAT) AS cantidad,
    CAST(ISNULL(cm.costo, 0) AS FLOAT) AS costo,
    CAST(ISNULL(cm.importesinimpuestos, ISNULL(cm.cantidad, 0) * ISNULL(cm.costo, 0)) AS FLOAT) AS subtotal,
    CAST(ISNULL(cm.importeconimpuestos, ISNULL(cm.importesinimpuestos, 0)) AS FLOAT) AS total
FROM compras c WITH (NOLOCK)
INNER JOIN comprasmovtos cm WITH (NOLOCK) ON c.idcompra = cm.idcompra
LEFT JOIN proveedores p WITH (NOLOCK) ON c.idproveedor = p.idproveedor
INNER JOIN insumos i WITH (NOLOCK) ON cm.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(c.cancelado, 0) = 0
  AND CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) = ?
ORDER BY fecha ASC;
"""



# =========================================================================
# 1.B CONSULTAS POR DÍA OPERATIVO / TIEMPO REAL (SIN DEPENDER DEL CORTE Z)
# Rango por defecto: 6:00 AM a 5:59 AM del día siguiente (DATEADD(hour, -hora_corte, fecha))
# =========================================================================

# 1.B.1 ÚLTIMO FOLIO PAGADO REGISTRADO EN EL SISTEMA
QUERY_ULTIMO_FOLIO_PAGADO = """
SELECT ISNULL(MAX(c.folio), 0) AS max_folio
FROM cheques c WITH (NOLOCK)
WHERE c.cancelado = 0 AND c.pagado = 1;
"""

def get_query_fechas_operativas_pendientes(hora_corte=6):
    return f"""
    SELECT DISTINCT 
        CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) AS fecha_operativa
    FROM cheques c WITH (NOLOCK)
    WHERE c.cancelado = 0 AND c.pagado = 1
      AND c.folio > ?
    ORDER BY fecha_operativa ASC;
    """

def get_query_ventas_fecha_operativa(hora_corte=6):
    return f"""
    SELECT 
        CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) AS fecha,
        DATENAME(WEEKDAY, MIN(c.fecha)) AS dia,
        COUNT(DISTINCT c.folio) AS no_ctas,
        SUM(ISNULL(c.nopersonas, 1)) AS no_pax,
        MIN(c.folio) AS fact_ini,
        MAX(c.folio) AS fact_fin,
        SUM(ISNULL(c.totalalimentos, 0)) AS alimentos,
        SUM(ISNULL(c.totalbebidas, 0)) AS bebidas,
        SUM(ISNULL(c.totalotros, 0)) AS otros,
        SUM(ISNULL(c.subtotal, 0)) AS vta_bruta,
        SUM(ISNULL(c.totaldescuentos, 0)) AS descuentos,
        SUM(ISNULL(c.totalcortesias, 0)) AS cortesias,
        SUM(ISNULL(c.totalimpuesto1, 0)) AS impo,
        SUM(ISNULL(c.propina, 0)) AS propina,
        SUM(ISNULL(c.total, 0)) AS total_vta
    FROM cheques c WITH (NOLOCK)
    WHERE c.cancelado = 0 AND c.pagado = 1
      AND CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) = ?
    GROUP BY CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120);
    """

def get_query_pagos_fecha_operativa(hora_corte=6):
    return f"""
    SELECT 
        CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) AS fecha,
        DATENAME(WEEKDAY, MIN(c.fecha)) AS dia,
        ISNULL(fp.descripcion, 'Efectivo') AS forma_pago,
        COUNT(cp.folio) AS transacciones,
        SUM(ISNULL(cp.importe, 0)) AS monto,
        SUM(ISNULL(cp.propina, 0)) AS propina
    FROM chequespagos cp WITH (NOLOCK)
    INNER JOIN cheques c WITH (NOLOCK) ON cp.folio = c.folio
    LEFT JOIN formasdepago fp WITH (NOLOCK) ON cp.idformadepago = fp.idformadepago
    WHERE c.cancelado = 0 AND c.pagado = 1
      AND CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) = ?
    GROUP BY CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120), fp.descripcion
    ORDER BY monto DESC;
    """

def get_query_productos_fecha_operativa(hora_corte=6):
    return f"""
    SELECT 
        CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) AS fecha,
        DATENAME(WEEKDAY, MIN(c.fecha)) AS dia,
        ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')) AS grupo,
        RTRIM(cd.idproducto) AS codigo,
        RTRIM(p.descripcion) AS producto,
        SUM(ISNULL(cd.cantidad, 0)) AS cant,
        CASE 
            WHEN SUM(ISNULL(cd.cantidad, 0)) > 0 
            THEN ROUND(SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) / SUM(ISNULL(cd.cantidad, 0)), 0)
            ELSE AVG(ISNULL(cd.precio, 0))
        END AS precio,
        SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) AS total,
        CAST(ISNULL(rc.costo_receta, 0.0) AS FLOAT) AS costo_unit,
        CAST(ROUND(SUM(ISNULL(cd.cantidad, 0)) * ISNULL(rc.costo_receta, 0.0), 2) AS FLOAT) AS costo_total
    FROM cheqdet cd WITH (NOLOCK)
    INNER JOIN cheques c WITH (NOLOCK) ON cd.foliodet = c.folio
    LEFT JOIN productos p WITH (NOLOCK) ON RTRIM(LTRIM(cd.idproducto)) = RTRIM(LTRIM(p.idproducto))
    LEFT JOIN grupos g WITH (NOLOCK) ON RTRIM(LTRIM(p.idgrupo)) = RTRIM(LTRIM(g.idgrupo))
    LEFT JOIN subgruposproductos sgp WITH (NOLOCK) ON RTRIM(LTRIM(p.idproducto)) = RTRIM(LTRIM(sgp.idproducto))
    LEFT JOIN subgrupos sg WITH (NOLOCK) ON RTRIM(LTRIM(sgp.idsubgrupo)) = RTRIM(LTRIM(sg.idsubgrupo))
    LEFT JOIN (
        SELECT 
            RTRIM(LTRIM(cst.idproducto)) AS idprod,
            SUM(ISNULL(cst.cantidad, 0) * ISNULL(NULLIF(id.costopromedio, 0), ISNULL(id.costo, 0))) AS costo_receta
        FROM costos cst WITH (NOLOCK)
        INNER JOIN insumosdetalle id WITH (NOLOCK) ON RTRIM(LTRIM(cst.idinsumo)) = RTRIM(LTRIM(id.idinsumo))
        GROUP BY cst.idproducto
    ) rc ON RTRIM(LTRIM(cd.idproducto)) = rc.idprod
    WHERE c.cancelado = 0 AND c.pagado = 1
      AND CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120) = ?
    GROUP BY CONVERT(VARCHAR(10), DATEADD(hour, -{int(hora_corte)}, c.fecha), 120),
             ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')), 
             cd.idproducto, p.descripcion, rc.costo_receta
    ORDER BY total DESC;
    """


# =========================================================================
# 2. CONSULTAS PARA SINCRONIZACIÓN HISTÓRICA COMPLETA POR PERÍODOS
# =========================================================================

# 2.1 LISTADO DE PERÍODOS HISTÓRICOS CON VENTAS
QUERY_MESES_HISTORICOS = """
SELECT 
    FORMAT(c.fecha, 'yyyy-MM') AS periodo,
    COUNT(DISTINCT c.folio) AS total_facturas,
    SUM(ISNULL(c.total, 0)) AS total_ventas
FROM cheques c WITH (NOLOCK)
WHERE c.cancelado = 0 AND c.pagado = 1
GROUP BY FORMAT(c.fecha, 'yyyy-MM')
ORDER BY periodo ASC;
"""

# 2.2 VENTAS DEL MES (Módulo 1)
QUERY_VENTAS_MES = """
SELECT 
    CONVERT(VARCHAR(10), c.fecha, 120) AS fecha,
    DATENAME(WEEKDAY, c.fecha) AS dia,
    COUNT(DISTINCT c.folio) AS no_ctas,
    SUM(ISNULL(c.nopersonas, 1)) AS no_pax,
    MIN(c.folio) AS fact_ini,
    MAX(c.folio) AS fact_fin,
    SUM(ISNULL(c.totalbebidas, 0)) AS bebidas,
    SUM(ISNULL(c.totalalimentos, 0)) AS alimentos,
    SUM(ISNULL(c.totalotros, 0)) AS otros,
    SUM(ISNULL(c.subtotal, 0)) AS vta_bruta,
    SUM(ISNULL(c.totaldescuentos, 0)) AS descuentos,
    SUM(ISNULL(c.totalcortesias, 0)) AS cortesias,
    SUM(ISNULL(c.totalimpuesto1, 0)) AS impo,
    SUM(ISNULL(c.propina, 0)) AS propina,
    SUM(ISNULL(c.total, 0)) AS total_vta
FROM cheques c WITH (NOLOCK)
WHERE c.cancelado = 0 AND c.pagado = 1
  AND FORMAT(c.fecha, 'yyyy-MM') = ?
GROUP BY CONVERT(VARCHAR(10), c.fecha, 120), DATENAME(WEEKDAY, c.fecha)
ORDER BY fecha ASC;
"""

# 2.3 FORMAS DE PAGO DEL MES (Módulo 2)
QUERY_PAGOS_MES = """
SELECT 
    CONVERT(VARCHAR(10), c.fecha, 120) AS fecha,
    DATENAME(WEEKDAY, c.fecha) AS dia,
    ISNULL(fp.descripcion, 'Efectivo') AS forma_pago,
    COUNT(cp.folio) AS transacciones,
    SUM(ISNULL(cp.importe, 0)) AS monto,
    SUM(ISNULL(cp.propina, 0)) AS propina
FROM chequespagos cp WITH (NOLOCK)
INNER JOIN cheques c WITH (NOLOCK) ON cp.folio = c.folio
LEFT JOIN formasdepago fp WITH (NOLOCK) ON cp.idformadepago = fp.idformadepago
WHERE c.cancelado = 0 AND c.pagado = 1
  AND FORMAT(c.fecha, 'yyyy-MM') = ?
GROUP BY CONVERT(VARCHAR(10), c.fecha, 120), DATENAME(WEEKDAY, c.fecha), fp.descripcion
ORDER BY fecha ASC, monto DESC;
"""

# 2.4 PRODUCTOS DEL MES (Módulos 3 y 4: cheqdet)
QUERY_PRODUCTOS_MES = """
SELECT 
    CONVERT(VARCHAR(10), c.fecha, 120) AS fecha,
    DATENAME(WEEKDAY, c.fecha) AS dia,
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')) AS grupo,
    RTRIM(cd.idproducto) AS codigo,
    RTRIM(p.descripcion) AS producto,
    SUM(ISNULL(cd.cantidad, 0)) AS cant,
    CASE 
        WHEN SUM(ISNULL(cd.cantidad, 0)) > 0 
        THEN ROUND(SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) / SUM(ISNULL(cd.cantidad, 0)), 0)
        ELSE AVG(ISNULL(cd.precio, 0))
    END AS precio,
    SUM(ISNULL(cd.cantidad, 0) * ISNULL(cd.precio, 0)) AS total,
    CAST(ISNULL(rc.costo_receta, 0.0) AS FLOAT) AS costo_unit,
    CAST(ROUND(SUM(ISNULL(cd.cantidad, 0)) * ISNULL(rc.costo_receta, 0.0), 2) AS FLOAT) AS costo_total
FROM cheqdet cd WITH (NOLOCK)
INNER JOIN cheques c WITH (NOLOCK) ON cd.foliodet = c.folio
LEFT JOIN productos p WITH (NOLOCK) ON RTRIM(LTRIM(cd.idproducto)) = RTRIM(LTRIM(p.idproducto))
LEFT JOIN grupos g WITH (NOLOCK) ON RTRIM(LTRIM(p.idgrupo)) = RTRIM(LTRIM(g.idgrupo))
LEFT JOIN subgruposproductos sgp WITH (NOLOCK) ON RTRIM(LTRIM(p.idproducto)) = RTRIM(LTRIM(sgp.idproducto))
LEFT JOIN subgrupos sg WITH (NOLOCK) ON RTRIM(LTRIM(sgp.idsubgrupo)) = RTRIM(LTRIM(sg.idsubgrupo))
LEFT JOIN (
    SELECT 
        RTRIM(LTRIM(cst.idproducto)) AS idprod,
        SUM(ISNULL(cst.cantidad, 0) * ISNULL(NULLIF(id.costopromedio, 0), ISNULL(id.costo, 0))) AS costo_receta
    FROM costos cst WITH (NOLOCK)
    INNER JOIN insumosdetalle id WITH (NOLOCK) ON RTRIM(LTRIM(cst.idinsumo)) = RTRIM(LTRIM(id.idinsumo))
    GROUP BY cst.idproducto
) rc ON RTRIM(LTRIM(cd.idproducto)) = rc.idprod
WHERE c.cancelado = 0 AND c.pagado = 1
  AND FORMAT(c.fecha, 'yyyy-MM') = ?
GROUP BY CONVERT(VARCHAR(10), c.fecha, 120), DATENAME(WEEKDAY, c.fecha), 
         ISNULL(NULLIF(RTRIM(g.descripcion), ''), ISNULL(NULLIF(RTRIM(sg.descripcion), ''), 'General')), 
         cd.idproducto, p.descripcion, rc.costo_receta
ORDER BY fecha ASC, total DESC;
"""

# 2.5 COMPRAS POR PROVEEDOR MENSUAL (Módulo 5)
QUERY_COMPRAS_PROVEEDORES_MES = """
SELECT 
    CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) AS fecha,
    RTRIM(ISNULL(c.folio, '')) AS folio,
    RTRIM(ISNULL(c.foliofactura, ISNULL(c.folio, ''))) AS factura,
    RTRIM(ISNULL(p.razonsocial, ISNULL(p.nombre, 'Proveedor General'))) AS proveedor,
    RTRIM(ISNULL(p.rfc, '')) AS nit,
    CAST(ISNULL(c.subtotal, 0) AS FLOAT) AS subtotal,
    CAST(ISNULL(c.impuesto1, 0) AS FLOAT) AS iva,
    CAST(ISNULL(c.total, 0) AS FLOAT) AS total
FROM compras c WITH (NOLOCK)
LEFT JOIN proveedores p WITH (NOLOCK) ON c.idproveedor = p.idproveedor
WHERE ISNULL(c.cancelado, 0) = 0
  AND FORMAT(ISNULL(c.fechaaplicacion, c.fechafactura), 'yyyy-MM') = ?
ORDER BY fecha ASC;
"""


# 2.6 COMPRAS POR INSUMOS MENSUAL (Módulo 6)
QUERY_COMPRAS_INSUMOS_MES = """
SELECT 
    CONVERT(VARCHAR(10), ISNULL(c.fechaaplicacion, c.fechafactura), 120) AS fecha,
    RTRIM(ISNULL(c.foliofactura, ISNULL(c.folio, ''))) AS factura,
    RTRIM(ISNULL(p.razonsocial, ISNULL(p.nombre, 'Proveedor General'))) AS proveedor,
    RTRIM(ISNULL(g.descripcion, 'General')) AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS unidad,
    CAST(ISNULL(cm.cantidad, 0) AS FLOAT) AS cantidad,
    CAST(ISNULL(cm.costo, 0) AS FLOAT) AS costo,
    CAST(ISNULL(cm.importesinimpuestos, ISNULL(cm.cantidad, 0) * ISNULL(cm.costo, 0)) AS FLOAT) AS subtotal,
    CAST(ISNULL(cm.importeconimpuestos, ISNULL(cm.importesinimpuestos, 0)) AS FLOAT) AS total
FROM compras c WITH (NOLOCK)
INNER JOIN comprasmovtos cm WITH (NOLOCK) ON c.idcompra = cm.idcompra
LEFT JOIN proveedores p WITH (NOLOCK) ON c.idproveedor = p.idproveedor
INNER JOIN insumos i WITH (NOLOCK) ON cm.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(c.cancelado, 0) = 0
  AND FORMAT(ISNULL(c.fechaaplicacion, c.fechafactura), 'yyyy-MM') = ?
ORDER BY fecha ASC;
"""


# =========================================================================
# 2.7 ALMUERZO DE PERSONAL / COMIDA EMPLEADOS (Salidas de Almacén)
# =========================================================================
QUERY_ALMUERZO_PERSONAL_MES = """
SELECT 
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), 'General') AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS und,
    CAST(SUM(ISNULL(md.cantidad, 0)) AS FLOAT) AS cantidad,
    CAST(CASE WHEN SUM(ISNULL(md.cantidad, 0)) > 0 
              THEN SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) / SUM(ISNULL(md.cantidad, 0))
              ELSE AVG(ISNULL(md.costo, 0)) 
         END AS FLOAT) AS costo,
    CAST(SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) AS FLOAT) AS costo_total
FROM movalmacen m WITH (NOLOCK)
INNER JOIN movalmacendetalle md WITH (NOLOCK) ON m.idmovalmacen = md.idmovalmacen
INNER JOIN conceptosmovalmacen c WITH (NOLOCK) ON m.idconcepto = c.idconcepto
INNER JOIN insumos i WITH (NOLOCK) ON md.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(m.cancelado, 0) = 0
  AND (
      LOWER(c.descripcion) LIKE '%personal%' 
   OR LOWER(c.descripcion) LIKE '%empleado%' 
   OR LOWER(c.descripcion) LIKE '%almuerzo%' 
   OR LOWER(c.descripcion) LIKE '%comida%'
   OR LOWER(c.descripcion) LIKE '%alimenta%'
  )
  AND FORMAT(m.fecha, 'yyyy-MM') = ?
GROUP BY g.descripcion, i.descripcion, i.unidad
ORDER BY costo_total DESC;
"""

QUERY_ALMUERZO_PERSONAL_MES_SALIDAS = """
SELECT 
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), 'General') AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS und,
    CAST(SUM(ISNULL(sm.cantidad, 0)) AS FLOAT) AS cantidad,
    CAST(CASE WHEN SUM(ISNULL(sm.cantidad, 0)) > 0 
              THEN SUM(ISNULL(sm.importe, ISNULL(sm.cantidad, 0) * ISNULL(sm.costo, 0))) / SUM(ISNULL(sm.cantidad, 0))
              ELSE AVG(ISNULL(sm.costo, 0)) 
         END AS FLOAT) AS costo,
    CAST(SUM(ISNULL(sm.importe, ISNULL(sm.cantidad, 0) * ISNULL(sm.costo, 0))) AS FLOAT) AS costo_total
FROM salidas s WITH (NOLOCK)
INNER JOIN salidasmovtos sm WITH (NOLOCK) ON s.idsalida = sm.idsalida
LEFT JOIN conceptossalida c WITH (NOLOCK) ON s.idconcepto = c.idconcepto
INNER JOIN insumos i WITH (NOLOCK) ON sm.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(s.cancelado, 0) = 0
  AND (
      LOWER(c.descripcion) LIKE '%personal%' 
   OR LOWER(c.descripcion) LIKE '%empleado%' 
   OR LOWER(c.descripcion) LIKE '%almuerzo%' 
   OR LOWER(c.descripcion) LIKE '%comida%'
   OR LOWER(c.descripcion) LIKE '%alimenta%'
  )
  AND FORMAT(s.fecha, 'yyyy-MM') = ?
GROUP BY g.descripcion, i.descripcion, i.unidad
ORDER BY costo_total DESC;
"""

# =========================================================================
# 2.8 BAJAS, MERMAS Y DESPERDICIOS DE ALMACÉN
# =========================================================================
QUERY_BAJAS_MERMAS_MES = """
SELECT 
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), 'General') AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS und,
    CAST(SUM(ISNULL(md.cantidad, 0)) AS FLOAT) AS cantidad,
    CAST(CASE WHEN SUM(ISNULL(md.cantidad, 0)) > 0 
              THEN SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) / SUM(ISNULL(md.cantidad, 0))
              ELSE AVG(ISNULL(md.costo, 0)) 
         END AS FLOAT) AS costo,
    CAST(SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) AS FLOAT) AS costo_total
FROM movalmacen m WITH (NOLOCK)
INNER JOIN movalmacendetalle md WITH (NOLOCK) ON m.idmovalmacen = md.idmovalmacen
INNER JOIN conceptosmovalmacen c WITH (NOLOCK) ON m.idconcepto = c.idconcepto
INNER JOIN insumos i WITH (NOLOCK) ON md.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(m.cancelado, 0) = 0
  AND (
      LOWER(c.descripcion) LIKE '%merma%' 
   OR LOWER(c.descripcion) LIKE '%desperdicio%' 
   OR LOWER(c.descripcion) LIKE '%baja%' 
   OR LOWER(c.descripcion) LIKE '%caduc%' 
   OR LOWER(c.descripcion) LIKE '%rotura%' 
   OR LOWER(c.descripcion) LIKE '%deterioro%'
  )
  AND FORMAT(m.fecha, 'yyyy-MM') = ?
GROUP BY g.descripcion, i.descripcion, i.unidad
ORDER BY costo_total DESC;
"""

QUERY_BAJAS_MERMAS_MES_SALIDAS = """
SELECT 
    ISNULL(NULLIF(RTRIM(g.descripcion), ''), 'General') AS grupo,
    RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
    RTRIM(ISNULL(i.unidad, 'UND')) AS und,
    CAST(SUM(ISNULL(sm.cantidad, 0)) AS FLOAT) AS cantidad,
    CAST(CASE WHEN SUM(ISNULL(sm.cantidad, 0)) > 0 
              THEN SUM(ISNULL(sm.importe, ISNULL(sm.cantidad, 0) * ISNULL(sm.costo, 0))) / SUM(ISNULL(sm.cantidad, 0))
              ELSE AVG(ISNULL(sm.costo, 0)) 
         END AS FLOAT) AS costo,
    CAST(SUM(ISNULL(sm.importe, ISNULL(sm.cantidad, 0) * ISNULL(sm.costo, 0))) AS FLOAT) AS costo_total
FROM salidas s WITH (NOLOCK)
INNER JOIN salidasmovtos sm WITH (NOLOCK) ON s.idsalida = sm.idsalida
LEFT JOIN conceptossalida c WITH (NOLOCK) ON s.idconcepto = c.idconcepto
INNER JOIN insumos i WITH (NOLOCK) ON sm.idinsumo = i.idinsumo
LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
WHERE ISNULL(s.cancelado, 0) = 0
  AND (
      LOWER(c.descripcion) LIKE '%merma%' 
   OR LOWER(c.descripcion) LIKE '%desperdicio%' 
   OR LOWER(c.descripcion) LIKE '%baja%' 
   OR LOWER(c.descripcion) LIKE '%caduc%' 
   OR LOWER(c.descripcion) LIKE '%rotura%' 
   OR LOWER(c.descripcion) LIKE '%deterioro%'
  )
  AND FORMAT(s.fecha, 'yyyy-MM') = ?
GROUP BY g.descripcion, i.descripcion, i.unidad
ORDER BY costo_total DESC;
"""

# =========================================================================
# 2.9 GENERADOR DINÁMICO CON PALABRAS CLAVE PERSONALIZADAS
# =========================================================================
def construir_clausula_like(columna, palabras):
    if not palabras:
        return "1=1"
    condiciones = [f"LOWER({columna}) LIKE '%{p.lower().strip()}%'" for p in palabras if p.strip()]
    if not condiciones:
        return "1=1"
    return "(" + " OR ".join(condiciones) + ")"

def get_query_movimientos_almacen_mes(tabla_cab="movalmacen", tabla_det="movalmacendetalle", tabla_con="conceptosmovalmacen", palabras_clave=None):
    clausula = construir_clausula_like("c.descripcion", palabras_clave or ["personal", "empleado", "almuerzo", "comida"])
    id_cab = "idmovalmacen" if "movalmacen" in tabla_cab.lower() else "idsalida"
    return f"""
    SELECT 
        ISNULL(NULLIF(RTRIM(g.descripcion), ''), 'General') AS grupo,
        RTRIM(ISNULL(i.descripcion, 'Insumo')) AS insumo,
        RTRIM(ISNULL(i.unidad, 'UND')) AS und,
        CAST(SUM(ISNULL(md.cantidad, 0)) AS FLOAT) AS cantidad,
        CAST(CASE WHEN SUM(ISNULL(md.cantidad, 0)) > 0 
                  THEN SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) / SUM(ISNULL(md.cantidad, 0))
                  ELSE AVG(ISNULL(md.costo, 0)) 
             END AS FLOAT) AS costo,
        CAST(SUM(ISNULL(md.importe, ISNULL(md.cantidad, 0) * ISNULL(md.costo, 0))) AS FLOAT) AS costo_total
    FROM {tabla_cab} m WITH (NOLOCK)
    INNER JOIN {tabla_det} md WITH (NOLOCK) ON m.{id_cab} = md.{id_cab}
    LEFT JOIN {tabla_con} c WITH (NOLOCK) ON m.idconcepto = c.idconcepto
    INNER JOIN insumos i WITH (NOLOCK) ON md.idinsumo = i.idinsumo
    LEFT JOIN gruposi g WITH (NOLOCK) ON i.idgruposi = g.idgruposi
    WHERE ISNULL(m.cancelado, 0) = 0
      AND {clausula}
      AND FORMAT(m.fecha, 'yyyy-MM') = ?
    GROUP BY g.descripcion, i.descripcion, i.unidad
    ORDER BY costo_total DESC;
    """
