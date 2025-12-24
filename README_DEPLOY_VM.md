README: Despliegue de Scr4per en VM con TLS
=========================================

Este documento explica, paso a paso, cómo desplegar la API en una VM (por ejemplo 192.168.1.212) y hacer que las peticiones públicas lleguen a ella usando TLS.

Resumen
-------
- Usaremos `docker-compose.vm.yml` (incluido) para ejecutar Uvicorn dentro de la VM en el puerto 8443, montando los certificados ubicados en `/opt/naat`.
- Opciones de exposición pública:
  - Forward/NAT en el host público: PUBLIC_IP:8443 -> VM_IP:8443 (DNAT). (Si el host ya tiene 8443 en uso, usa otro puerto público y/o cambia la configuración previa.)
  - Alternativa recomendada a largo plazo: reverse-proxy en host (nginx/Caddy) que haga `https://naatintelligence.com/redes_sociales/*` -> `http://192.168.1.212:8000`.

Pasos en la VM (192.168.1.212)
------------------------------
1) Copiar el repo a la VM

   Usando rsync desde tu máquina local (ejemplo):
   ```fish
   rsync -avz --exclude='.venv' --exclude='.git' ./ fernando@192.168.1.212:/opt/scr4per
   ssh fernando@192.168.1.212
   cd /opt/scr4per
   ```

2) Asegurar que los certificados estén en `/opt/naat`

   - fullchain.pem y naatapi.key deben estar en `/opt/naat` en la VM.
   - Permisos recomendados:
     ```fish
     sudo chown root:root /opt/naat/naatapi.key /opt/naat/fullchain.pem
     sudo chmod 600 /opt/naat/naatapi.key
     sudo chmod 644 /opt/naat/fullchain.pem
     ```

3) Verificar `db/.env`

   - Asegúrate de que las variables `POSTGRES_*` en `db/.env` sean correctas desde la VM (p.ej. `POSTGRES_HOST=127.0.0.1` si Postgres está en la misma VM).

4) Instalar Docker y Docker Compose (si no están)

   En Debian/Ubuntu (ejemplo):
   ```fish
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo apt install -y docker-compose-plugin
   sudo usermod -aG docker $USER
   ```

5) Levantar el servicio con TLS (en la VM)

   ```fish
   cd /opt/scr4per
   # construir y levantar en background
   docker compose -f docker-compose.vm.yml up -d --build

   # ver estado
   docker compose -f docker-compose.vm.yml ps
   docker compose -f docker-compose.vm.yml logs -f scr4per_api_vm
   ```

6) Probar localmente en la VM

   ```fish
   curl -vk https://127.0.0.1:8443/redes_sociales/docs
   curl -vk https://127.0.0.1:8443/redes_sociales/multi-scrape -X POST -H 'Content-Type: application/json' -d '{"roots":[{"platform":"facebook","username":"SajitVentura"}]}'
   ```

Exponer el servicio públicamente
--------------------------------

Si deseas que la IP pública (PUBLIC_IP) responda en 8443 y reenvíe a la VM:8443 puedes configurar DNAT en el host público. A continuación una receta (hazlo en el host público):

1) Variables (en host público):
```fish
set PUBLIC_IP 1.2.3.4
set VM_IP 192.168.1.212
set IFACE eth0
```

2) Habilitar forwarding y aplicar reglas iptables (host público):
```fish
sudo sysctl -w net.ipv4.ip_forward=1

# PREROUTING: redirigir conexiones entrantes en 8443 a la VM
sudo iptables -t nat -A PREROUTING -p tcp -d $PUBLIC_IP --dport 8443 -j DNAT --to-destination $VM_IP:8443

# POSTROUTING: masquerade para que la VM responda vía host
sudo iptables -t nat -A POSTROUTING -p tcp -d $VM_IP --dport 8443 -o $IFACE -j MASQUERADE

# permitir forwarding
sudo iptables -A FORWARD -p tcp -d $VM_IP --dport 8443 -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT
sudo iptables -A FORWARD -p tcp -s $VM_IP --sport 8443 -m state --state ESTABLISHED,RELATED -j ACCEPT
```

3) Persistencia: guarda las reglas o usa un pequeño systemd unit para re-aplicarlas al boot. Por ejemplo:
```fish
sudo iptables-save | sudo tee /etc/iptables.rules
```
Y restaurar en boot con `/etc/rc.local` o systemd.

4) Comprobar desde fuera:
```fish
curl -vk https://naatintelligence.com:8443/redes_sociales/docs
```

Notas y recomendaciones
----------------------
- DNAT funciona pero tiene inconvenientes: logs de IPs reales, persistencia, complejidad de mantenimiento. Si tienes control del host, la opción más robusta es usar reverse-proxy (nginx/Caddy) en el host y mantener TLS en el host.
- Si el host público ya está usando 443 para otro servicio y no quieres tocarlo, usa otro puerto público (ej. 8443) y reenvía PUBLIC_IP:8443 -> VM:8443.
- Asegúrate de que firewalls (ufw, security groups) permiten 8443 en host y que el host puede enrutar a la VM.
- Verifica que `root_path` sea consistente (`/redes_sociales`) tanto en Uvicorn como en las URLs que uses.

Revertir reglas DNAT (si algo sale mal)
-------------------------------------
```fish
sudo iptables -t nat -D PREROUTING -p tcp -d $PUBLIC_IP --dport 8443 -j DNAT --to-destination $VM_IP:8443
sudo iptables -t nat -D POSTROUTING -p tcp -d $VM_IP --dport 8443 -o $IFACE -j MASQUERADE
sudo iptables -D FORWARD -p tcp -d $VM_IP --dport 8443 -m state --state NEW,ESTABLISHED,RELATED -j ACCEPT
sudo iptables -D FORWARD -p tcp -s $VM_IP --sport 8443 -m state --state ESTABLISHED,RELATED -j ACCEPT
```

Si quieres, puedo generar un pequeño script `deploy_vm.sh` que automatice los pasos 2..6 en la VM (montar permisos, docker compose up, comprobar) o un unit/service para aplicar las reglas iptables en el host en el arranque.
