# Frontend Notulis (Expo web) dibangun menjadi berkas statis, lalu disajikan nginx.
# EXPO_PUBLIC_API_URL dibaca saat build dan ikut tertanam di hasilnya, jadi mengubah alamat API berarti build ulang
# (isi lewat Build Args di Dokploy).
FROM node:22-alpine AS build
WORKDIR /app
ARG EXPO_PUBLIC_API_URL
ENV EXPO_PUBLIC_API_URL=$EXPO_PUBLIC_API_URL
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY . .
RUN npx expo export --platform web --output-dir dist

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
