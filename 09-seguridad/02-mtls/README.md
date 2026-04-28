# Generacion certificados CA, server y client

Correr todo dentro de la carpeta `./certs`

## Generar CA

```bash
openssl req -x509 -newkey rsa:4096 -keyout ca.key -out ca.crt -days 365 -nodes -subj "/CN=MyCA"
```

## Generar Server

```bash
openssl req -newkey rsa:4096 -keyout server.key -out server.csr -nodes -subj "/CN=server"
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365
```

## Generar Client

```bash
openssl req -newkey rsa:4096 -keyout client.key -out client.csr -nodes -subj "/CN=client"
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out client.crt -days 365
```

## Pruebas con cURL

```bash
# este falla porque no tiene el client certificate
curl -kvv https://localhost

# aqui si mandamos el client certificate
curl -kvv --cacert ./certs/ca.crt --cert ./certs/client.crt --key ./certs/client.key https://localhost

```
