const express = require('express');
const cors = require('cors');
const compression = require('compression');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = parseInt(process.env.PORT, 10) || 80;

// Middleware
app.use(cors());
app.use(compression());
// Aumentar el límite a 100MB para recibir compras e insumos detallados masivos
app.use(express.json({ limit: '100mb' }));
app.use(express.urlencoded({ extended: true, limit: '100mb' }));

// Directorio de persistencia de compras
const DATA_DIR = path.join(__dirname, 'data', 'compras');
if (!fs.existsSync(DATA_DIR)) {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

// Token de seguridad por defecto para el conector (puede configurarse por variable de entorno)
const CONNECTOR_API_TOKEN = process.env.CONNECTOR_API_TOKEN || 'dc_restodata_secure_token_2026';

// -----------------------------------------------------------------------------
// ENDPOINTS DE SALUD Y ESTADO
// -----------------------------------------------------------------------------
app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'DC RestoData API & Web',
    server: 'Netcup VPS',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/status', (req, res) => {
  res.json({
    success: true,
    platform: 'DC RestoData v1.0',
    env: process.env.NODE_ENV || 'production',
    uptime: Math.round(process.uptime()),
    serverTime: new Date().toISOString()
  });
});

// -----------------------------------------------------------------------------
// ENDPOINTS DE COMPRAS (MÓDULOS 5 Y 6)
// -----------------------------------------------------------------------------

// POST /api/compras - Recibe compras de proveedores e insumos desde el conector
app.post('/api/compras', (req, res) => {
  try {
    const { empresa_id, period_key, suppliers, supplies, token } = req.body;

    if (!empresa_id || !period_key) {
      return res.status(400).json({ success: false, message: 'Faltan parámetros empresa_id o period_key' });
    }

    // Validación básica de token (si se envía)
    if (token && token !== CONNECTOR_API_TOKEN) {
      console.warn(`[Seguridad] Intento de sincronización con token no válido para empresa ${empresa_id}`);
      return res.status(401).json({ success: false, message: 'Token de sincronización no autorizado' });
    }

    const safeEmpresa = String(empresa_id).replace(/[^a-zA-Z0-9_-]/g, '');
    const safePeriod = String(period_key).replace(/[^a-zA-Z0-9_-]/g, '');
    const filename = `${safeEmpresa}_${safePeriod}.json`;
    const filePath = path.join(DATA_DIR, filename);

    // Si ya existen datos previos, podemos combinarlos o reemplazarlos con la versión consolidada
    let existingData = { suppliers: [], supplies: [] };
    if (fs.existsSync(filePath)) {
      try {
        existingData = JSON.parse(fs.readFileSync(filePath, 'utf8'));
      } catch (e) {
        existingData = { suppliers: [], supplies: [] };
      }
    }

    const payloadToSave = {
      empresa_id: safeEmpresa,
      period_key: safePeriod,
      suppliers: Array.isArray(suppliers) ? suppliers : (existingData.suppliers || []),
      supplies: Array.isArray(supplies) ? supplies : (existingData.supplies || []),
      _syncedAt: new Date().toISOString(),
      _recordsCount: {
        suppliers: Array.isArray(suppliers) ? suppliers.length : (existingData.suppliers ? existingData.suppliers.length : 0),
        supplies: Array.isArray(supplies) ? supplies.length : (existingData.supplies ? existingData.supplies.length : 0)
      }
    };

    fs.writeFileSync(filePath, JSON.stringify(payloadToSave, null, 2), 'utf8');

    console.log(`[API Netcup] Compras guardadas exitosamente: ${payloadToSave._recordsCount.suppliers} facturas, ${payloadToSave._recordsCount.supplies} insumos para ${safeEmpresa} [${safePeriod}]`);

    return res.json({
      success: true,
      message: 'Compras sincronizadas exitosamente en Netcup VPS',
      recordsCount: payloadToSave._recordsCount,
      timestamp: payloadToSave._syncedAt
    });
  } catch (error) {
    console.error('[API Netcup Error /api/compras POST]:', error);
    return res.status(500).json({ success: false, message: 'Error interno del servidor al guardar compras', error: error.message });
  }
});

// GET /api/compras - Consulta compras para RestoData frontend
app.get('/api/compras', (req, res) => {
  try {
    const { empresa_id, period_key } = req.query;

    if (!empresa_id || !period_key) {
      return res.status(400).json({ success: false, message: 'Parámetros empresa_id y period_key son requeridos' });
    }

    const safeEmpresa = String(empresa_id).replace(/[^a-zA-Z0-9_-]/g, '');
    const safePeriod = String(period_key).replace(/[^a-zA-Z0-9_-]/g, '');
    const filename = `${safeEmpresa}_${safePeriod}.json`;
    const filePath = path.join(DATA_DIR, filename);

    if (!fs.existsSync(filePath)) {
      return res.json({
        success: true,
        empresa_id: safeEmpresa,
        period_key: safePeriod,
        suppliers: [],
        supplies: [],
        message: 'Sin compras sincronizadas en Netcup para este período'
      });
    }

    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    return res.json({
      success: true,
      empresa_id: safeEmpresa,
      period_key: safePeriod,
      suppliers: data.suppliers || [],
      supplies: data.supplies || [],
      syncedAt: data._syncedAt || null,
      recordsCount: data._recordsCount || { suppliers: 0, supplies: 0 }
    });
  } catch (error) {
    console.error('[API Netcup Error /api/compras GET]:', error);
    return res.status(500).json({ success: false, message: 'Error al consultar compras', error: error.message });
  }
});

// GET /api/compras/summary - Resumen de compras almacenadas en el servidor
app.get('/api/compras/summary', (req, res) => {
  try {
    if (!fs.existsSync(DATA_DIR)) {
      return res.json({ success: true, count: 0, files: [] });
    }
    const files = fs.readdirSync(DATA_DIR).filter(f => f.endsWith('.json'));
    const summary = files.map(f => {
      try {
        const full = path.join(DATA_DIR, f);
        const stat = fs.statSync(full);
        const content = JSON.parse(fs.readFileSync(full, 'utf8'));
        return {
          filename: f,
          empresa_id: content.empresa_id,
          period_key: content.period_key,
          suppliersCount: content._recordsCount ? content._recordsCount.suppliers : (content.suppliers || []).length,
          suppliesCount: content._recordsCount ? content._recordsCount.supplies : (content.supplies || []).length,
          sizeKB: Math.round(stat.size / 1024),
          syncedAt: content._syncedAt
        };
      } catch (err) {
        return { filename: f, error: err.message };
      }
    });
    return res.json({ success: true, count: summary.length, files: summary });
  } catch (e) {
    return res.status(500).json({ success: false, error: e.message });
  }
});

// -----------------------------------------------------------------------------
// SERVIR ARCHIVOS ESTÁTICOS DEL FRONTEND
// -----------------------------------------------------------------------------
app.use(express.static(path.join(__dirname), {
  etag: true,
  maxAge: '1h',
  setHeaders: (res, pathHeader) => {
    // Para archivos críticos no cachear de forma agresiva
    if (pathHeader.endsWith('index.html') || pathHeader.endsWith('sw.js')) {
      res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate');
    }
  }
}));

// Fallback SPA
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Iniciar servidor en el puerto configurado (y opcionalmente en el puerto 3000 como fallback)
const mainServer = app.listen(PORT, '0.0.0.0', () => {
  console.log(`🚀 DC RestoData Server ejecutándose en puerto principal ${PORT}`);
});

// Si el puerto principal no es 3000, escuchar también en 3000 para compatibilidad universal con Traefik
if (PORT !== 3000) {
  try {
    app.listen(3000, '0.0.0.0', () => {
      console.log(`🚀 DC RestoData Server escuchando adicionalmente en puerto 3000 (puerto Traefik fallback)`);
    }).on('error', (err) => {
      // Si el puerto 3000 está ocupado, no pasa nada, el puerto principal sigue activo
      console.log('Nota puerto 3000:', err.message);
    });
  } catch (e) {}
}
