# Imagen ligera oficial de Node.js Alpine
FROM node:20-alpine

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias primero para aprovechar cache de capas Docker
COPY package*.json ./
RUN npm install --omit=dev

# Copiar el código fuente completo
COPY . .

# Crear carpeta de datos con permisos
RUN mkdir -p /app/data/compras

# Exponer puertos para Traefik / Coolify
EXPOSE 80 3000

# Variables de entorno
ENV NODE_ENV=production
ENV PORT=80

# Iniciar servidor Express
CMD ["node", "server.js"]
