**PATH:** `/apps/admin/Dockerfile`
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json vite.config.ts tsconfig.json index.html ./
COPY src ./src
RUN npm i && npm run build
EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
