# LabWin Backup Ingestion Pipeline

**Status:** Fase A completa + upload del lab funcionando end-to-end. Falta Fase B (ingesta en VPS) antes de habilitar `LABWIN_USE_MOCK=False`.
**Owner:** Development Team
**Última actualización:** 2026-04-24

---

## 📊 Estado actual (2026-04-25)

| Componente | Estado | Notas |
|---|---|---|
| Usuario `backup_user` + chroot SFTP en VPS | ✅ | Creado 2026-04-24 |
| Par de claves ed25519 | ✅ | Generada en la laptop de Sebastian |
| Clave pública en VPS (`authorized_keys`) | ✅ | Instalada y verificada |
| Clave privada en PC del lab | ✅ | En `C:\labcontrol_backup\keys\labwin_backup` |
| Script `upload_backup.py` (gbak + gzip + SFTP) | ✅ | En producción en PC del lab |
| Primer upload real end-to-end | ✅ | `BASEDAT_20260424_180940.fbk.gz` (69.9 MB) en `/incoming/` |
| Contenedor Firebird en `docker-compose.prod.yml` | ✅ | Desplegado 2026-04-25 — `jacobalberty/firebird:2.5-ss`, accesible en `firebird:3050` desde docker network. Services API verificada desde celery_worker. |
| Permisos de `/srv/labwin_backups/{incoming,processed,failed}` | ✅ | `backup_user:1000 chmod 775` — celery_worker (uid 1000) puede leer y mover archivos |
| `passlib` agregado a `requirements/base.txt` | ✅ | Requerido por `firebirdsql.services` para restore via Services API |
| Task `import_uploaded_backup` | ⏳ | Pendiente (Fase B — siguiente paso) |
| Management command `import_backup` | ⏳ | Pendiente (Fase B) |
| Tests unitarios de `backup_import` | ⏳ | Pendiente (Fase B) |
| `LABWIN_USE_MOCK=False` en prod | ⏳ | Solo después de validar Fase B end-to-end con disparo manual |
| Beat schedule (cron 04:00 AM) | ⏳ | Solo después de soak period con disparos manuales |
| Task Scheduler en la PC del lab | ⏳ | Pendiente — por ahora correrlo manual |
| Limpieza de `.FDB` viejos en `/home/labwin_ftp/results/` | ⏳ | 2 archivos de 2.3 GB cada uno, probablemente corruptos |

**Tiempos reales medidos en el primer upload (DB de 347 MB en caliente):**
- `gbak -b -g`: 67 s
- `gzip`: 17 s
- SFTP upload (69.9 MB a 3.2 MB/s): 22 s
- **Total**: 107 s (~2 min)

El gap de 2h entre upload del lab (02:00) e import en VPS (04:00) del diseño original es holgado — se podría reducir a 30 min si hace falta.

---

## 🎯 Propósito

Este documento describe cómo los datos de LabWin llegan desde la **PC del laboratorio** (offline, sin IP pública) al **VPS de LabControl** en producción, y cómo se ingestan al modelo Django via el sync existente.

Es el puente faltante entre:
- `BACKEND.md` — describe los connectors de LabWin y los modelos de destino
- `DEPLOYMENT.md` — describe la infraestructura del VPS
- `guia_backup_lab.pdf` — describe el push del backup desde la PC del lab

Sin este pipeline, `LABWIN_USE_MOCK=False` no es viable en producción: el VPS no tiene acceso directo al Firebird de la PC del lab.

---

## 🧩 Por qué existe

**Restricción del cliente:**
- La base de LabWin (`C:/sistema/LabWin4/BASEDAT.FDB`, Firebird 2.5) vive **solo en la PC/servidor del laboratorio**
- Esa PC **no está expuesta a Internet** (sin IP pública, detrás de NAT, sin reglas de firewall abiertas)
- El laboratorio **no va a tocar su configuración de red** por razones operativas

**Consecuencia:** el connector Firebird remoto que describe `BACKEND.md`
```env
LABWIN_FDB_HOST=<lab_ip>
LABWIN_FDB_PORT=3050
```
**no puede conectarse** desde el VPS. Tiene que ser al revés: el lab **empuja** el backup al VPS.

---

## 🏗️ Arquitectura end-to-end

```
┌─────────────── PC LAB (Windows, outbound-only) ──────────────────┐
│                                                                  │
│  LabWin (Firebird 2.5 service)                                   │
│    └─ BASEDAT.FDB  (2–5 GB, lock exclusivo del service)          │
│                                                                  │
│  Task Scheduler 02:00 AM                                         │
│    └─ upload_backup.py                                           │
│         1. gbak -b -g  →  BASEDAT_YYYYMMDD.fbk                   │
│         2. gzip        →  BASEDAT_YYYYMMDD.fbk.gz                │
│         3. paramiko SFTP (key auth) ─────┐                       │
│         4. rotación local (mantener 7)    │                      │
│         5. log a C:\backups\upload.log    │                      │
└───────────────────────────────────────────┼──────────────────────┘
                                            │
                                            │ SFTP :22 outbound
                                            │ backup_user@vps (chroot)
                                            ▼
┌──────────────────────── VPS Hostinger (72.60.137.226) ────────────┐
│                                                                   │
│  /srv/labwin_backups/                                             │
│    ├─ incoming/   BASEDAT_YYYYMMDD.fbk.gz  ← chroot del SFTP      │
│    ├─ processed/  (post-ingest)                                   │
│    └─ failed/     (errores de restore)                            │
│                                                                   │
│  Docker Compose stack (labcontrol_*)                              │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  celery_beat  ─ cron 04:00 AM                              │   │
│  │     └─► apps.labwin_sync.tasks.import_uploaded_backup      │   │
│  │                                                            │   │
│  │  celery_worker                                             │   │
│  │     1. Lee último *.fbk.gz de incoming/                    │   │
│  │     2. gunzip  →  /tmp/backup.fbk                          │   │
│  │     3. docker exec firebird  gbak -r /tmp/backup.fbk ...   │   │
│  │        → restaura a /firebird/data/BASEDAT.FDB             │   │
│  │     4. invoca sync_labwin_results()  (task existente)      │   │
│  │     5. mueve .fbk.gz a processed/ (o failed/)              │   │
│  │     6. rotación: borra processed/ > 30 días                │   │
│  │                                                            │   │
│  │  firebird  (servicio nuevo — jacobalberty/firebird:2.5-ss) │   │
│  │     └─ BASEDAT.FDB restaurado, accesible a la red docker   │   │
│  │                                                            │   │
│  │  web (Django)                                              │   │
│  │     └─ LABWIN_FDB_HOST=firebird  (service name interno)    │   │
│  │        LABWIN_USE_MOCK=False                               │   │
│  └────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

**Ventana horaria (diseño original):**
- 02:00 — Lab genera y sube backup
- 04:00 — VPS dispara `import_uploaded_backup` (holgura de 2h para reintento)
- 04:30 — Sync completo, datos disponibles para el frontend

**Tiempos reales medidos** (primer upload 2026-04-24, DB de 347 MB en caliente):
- `gbak`: 67 s
- `gzip`: 17 s (347 MB → 70 MB, ratio 0.20)
- SFTP upload: 22 s (3.2 MB/s sostenido)
- **Total lab-side: 107 s (~2 min)**

Dada la holgura real, se puede comprimir el schedule a 02:00 upload / 02:30 import sin problema — pero se deja 04:00 para absorber eventuales picos de retry o fallas de red.

---

## 🔧 Componentes nuevos a implementar

### 1. PC del laboratorio

**Archivo:** `C:\labcontrol_backup\upload_backup.py` (en la PC del lab)

Requerimientos no-negociables (mejoras sobre la guía PDF original):
- [ ] Usar `gbak -b -g` para snapshot consistente (no copiar `.fdb` en caliente — Firebird tiene lock exclusivo)
- [ ] Compresión `gzip` antes de subir (reduce ~3 GB a ~500 MB)
- [x] Autenticación **por clave SSH**, no password *(clave instalada 2026-04-24)*
- [ ] Verificación de host key del VPS (evita MITM)
- [ ] Nombre con fecha: `BASEDAT_YYYYMMDD_HHMMSS.fbk.gz`
- [ ] Timeout de transporte configurable (default 3600 s para DBs grandes)
- [ ] Rotación local (retener últimos 7 backups)
- [ ] Log a archivo + código de salida != 0 en fallo (para alertar Task Scheduler)

#### Script completo

Guardar como `C:\labcontrol_backup\upload_backup.py`:

```python
"""
LabControl — Backup nightly uploader
====================================
Genera un backup consistente de la BBDD LabWin (Firebird 2.5) con gbak,
lo comprime con gzip y lo sube al VPS via SFTP usando clave SSH.

Ejecutado por Task Scheduler de Windows a las 02:00 AM.

Uso:
    python upload_backup.py              # Correr normalmente
    python upload_backup.py --dry-run    # No sube, solo valida config y backup

Config:
    Editar las constantes CONFIG abajo si cambia la ruta de LabWin o de la clave.
"""

import argparse
import gzip
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import paramiko

# ============================================================================
# CONFIG — editar aquí si cambian rutas o credenciales
# ============================================================================

# LabWin / Firebird
FBK_DIR = Path(r"C:\labcontrol_backup\work")        # .fbk temporal (local)
LOCAL_ARCHIVE_DIR = Path(r"C:\labcontrol_backup\archive")  # Rotación local
GBAK_EXE = r"C:\Program Files\Firebird\Firebird_2_5\bin\gbak.exe"
LABWIN_DB = r"C:\sistema\LabWin4\Basedat\BASEDAT.FDB"  # Verificado en PC del lab 2026-04-24
FIREBIRD_USER = "SYSDBA"
FIREBIRD_PASSWORD = "REPLACE_WITH_REAL_SYSDBA_PASSWORD"  # See backup_lab_guide.md §"Where to get the password"

# VPS SFTP
VPS_HOST = "72.60.137.226"
VPS_PORT = 22
VPS_USER = "backup_user"
VPS_REMOTE_DIR = "/incoming"
SSH_KEY_PATH = Path(r"C:\labcontrol_backup\keys\labwin_backup")
SSH_KEY_TYPE = "ed25519"  # La clave que generamos

# Host fingerprint del VPS — el script rechaza la conexion si no coincide
EXPECTED_HOST_FINGERPRINT = "SHA256:GTAVmxiXmwQsFNbY5wE2ElowE+GV9ilt64yFdHnT24g"

# Retencion local (cuantos .fbk.gz mantener en C:\labcontrol_backup\archive)
LOCAL_RETENTION_COUNT = 7

# Timeouts
SFTP_BANNER_TIMEOUT = 60
SFTP_TRANSPORT_TIMEOUT = 3600  # 1 hora para subir la DB

# Logging
LOG_FILE = Path(r"C:\labcontrol_backup\upload.log")

# ============================================================================
# Setup logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("backup")


# ============================================================================
# Helpers
# ============================================================================
def run_gbak(output_fbk: Path) -> None:
    """
    Genera un backup consistente con gbak.

    Flags:
        -b  = backup mode
        -g  = no garbage collection (mas rapido, menos carga en Firebird)
        -v  = verbose (para el log)
    """
    log.info("Running gbak: %s -> %s", LABWIN_DB, output_fbk)
    output_fbk.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        GBAK_EXE,
        "-b", "-g", "-v",
        "-user", FIREBIRD_USER,
        "-password", FIREBIRD_PASSWORD,
        LABWIN_DB,
        str(output_fbk),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=3600
    )
    if result.returncode != 0:
        log.error("gbak failed (rc=%s)", result.returncode)
        log.error("stdout: %s", result.stdout[-2000:])
        log.error("stderr: %s", result.stderr[-2000:])
        raise RuntimeError(f"gbak failed with rc={result.returncode}")

    size_mb = output_fbk.stat().st_size / 1024 / 1024
    log.info("gbak OK — %.1f MB", size_mb)


def gzip_file(fbk_path: Path) -> Path:
    """Comprime .fbk a .fbk.gz (elimina el .fbk original)."""
    gz_path = fbk_path.with_suffix(fbk_path.suffix + ".gz")
    log.info("gzipping: %s -> %s", fbk_path.name, gz_path.name)

    with open(fbk_path, "rb") as src, gzip.open(gz_path, "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)

    fbk_path.unlink()  # Borrar .fbk crudo, ya tenemos el .gz
    ratio = gz_path.stat().st_size / (gz_path.stat().st_size + 1)
    size_mb = gz_path.stat().st_size / 1024 / 1024
    log.info("gzip OK — %.1f MB (ratio %.2f)", size_mb, ratio)
    return gz_path


def verify_host_fingerprint(transport: paramiko.Transport) -> None:
    """Verifica que el host key del VPS coincida con el esperado (proteccion MITM)."""
    import base64
    import hashlib

    host_key = transport.get_remote_server_key()
    digest = hashlib.sha256(host_key.asbytes()).digest()
    actual_fp = "SHA256:" + base64.b64encode(digest).decode().rstrip("=")

    if actual_fp != EXPECTED_HOST_FINGERPRINT:
        log.error("HOST FINGERPRINT MISMATCH!")
        log.error("  Esperado: %s", EXPECTED_HOST_FINGERPRINT)
        log.error("  Recibido: %s", actual_fp)
        raise RuntimeError("VPS host fingerprint no coincide — posible MITM")
    log.info("Host fingerprint OK: %s", actual_fp)


def upload_sftp(local_path: Path, remote_name: str) -> None:
    """Sube archivo via SFTP con verificacion de host key."""
    log.info("Conectando a %s:%s como %s", VPS_HOST, VPS_PORT, VPS_USER)

    if not SSH_KEY_PATH.exists():
        raise RuntimeError(f"Clave SSH no encontrada: {SSH_KEY_PATH}")

    key = paramiko.Ed25519Key.from_private_key_file(str(SSH_KEY_PATH))

    transport = paramiko.Transport((VPS_HOST, VPS_PORT))
    transport.banner_timeout = SFTP_BANNER_TIMEOUT
    transport.default_window_size = 2**27  # 128 MB para transferencias grandes

    try:
        transport.connect(username=VPS_USER, pkey=key)
        verify_host_fingerprint(transport)

        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(SFTP_TRANSPORT_TIMEOUT)

        remote_path = f"{VPS_REMOTE_DIR}/{remote_name}"
        tmp_path = f"{remote_path}.uploading"  # Upload a nombre temporal, renombrar al final

        log.info("Subiendo: %s -> %s", local_path.name, remote_path)
        start = datetime.now()
        sftp.put(str(local_path), tmp_path)
        sftp.rename(tmp_path, remote_path)
        elapsed = (datetime.now() - start).total_seconds()

        size_mb = local_path.stat().st_size / 1024 / 1024
        speed_mbps = size_mb / elapsed if elapsed > 0 else 0
        log.info("Upload OK — %.1f MB en %.0f s (%.1f MB/s)", size_mb, elapsed, speed_mbps)

        sftp.close()
    finally:
        transport.close()


def rotate_local_backups() -> None:
    """Mantiene solo los LOCAL_RETENTION_COUNT backups mas recientes."""
    if not LOCAL_ARCHIVE_DIR.exists():
        return
    backups = sorted(
        LOCAL_ARCHIVE_DIR.glob("BASEDAT_*.fbk.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[LOCAL_RETENTION_COUNT:]:
        log.info("Rotacion: borrando %s", old.name)
        old.unlink()


def main(dry_run: bool = False) -> int:
    start = datetime.now()
    log.info("=" * 60)
    log.info("Backup run iniciado a %s (dry_run=%s)", start.isoformat(), dry_run)

    try:
        # 1. Generar .fbk con gbak
        timestamp = start.strftime("%Y%m%d_%H%M%S")
        fbk_name = f"BASEDAT_{timestamp}.fbk"
        fbk_path = FBK_DIR / fbk_name
        run_gbak(fbk_path)

        # 2. Comprimir
        gz_path = gzip_file(fbk_path)

        # 3. Mover al archivo local para rotacion
        LOCAL_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archived = LOCAL_ARCHIVE_DIR / gz_path.name
        shutil.move(str(gz_path), str(archived))

        # 4. Subir al VPS (salvo dry-run)
        if dry_run:
            log.info("DRY RUN — saltando upload. Archivo listo en: %s", archived)
        else:
            upload_sftp(archived, archived.name)

        # 5. Rotacion local
        rotate_local_backups()

        elapsed = (datetime.now() - start).total_seconds()
        log.info("Backup run OK — duracion total %.0f s", elapsed)
        return 0

    except Exception as e:
        log.exception("Backup FALLO: %s", e)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="No sube al VPS")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
```

#### Instalación en la PC del lab

```powershell
# 1. Crear estructura de carpetas (PowerShell como Administrador)
mkdir C:\labcontrol_backup\keys -Force
mkdir C:\labcontrol_backup\work -Force
mkdir C:\labcontrol_backup\archive -Force

# 2. Verificar Python instalado
python --version   # Debe ser >= 3.11 (en PC actual del lab: 3.12)

# 3. Instalar paramiko
pip install paramiko

# 4. Copiar archivos a las rutas finales:
#    - upload_backup.py      -> C:\labcontrol_backup\upload_backup.py
#    - labwin_backup         -> C:\labcontrol_backup\keys\labwin_backup  (clave privada, 411 bytes)

# 5. Verificar que la clave se lee OK (debe imprimir el fingerprint)
python -c "import paramiko; k = paramiko.Ed25519Key.from_private_key_file(r'C:\labcontrol_backup\keys\labwin_backup'); print('OK:', k.fingerprint)"
# Esperado: OK: SHA256:AztSYVjU5QO5V7PRsjpX5v1X1/gd7sghMnUxSCkc2NA

# 6. Verificar conexion SFTP al VPS
python -c "import paramiko; t=paramiko.Transport(('72.60.137.226',22)); t.connect(username='backup_user', pkey=paramiko.Ed25519Key.from_private_key_file(r'C:\labcontrol_backup\keys\labwin_backup')); s=paramiko.SFTPClient.from_transport(t); print('Conectado:', s.listdir('.')); s.close(); t.close()"
# Esperado: Conectado: ['processed', 'failed', 'incoming']
```

**Gotchas observados al instalar (2026-04-24):**

1. **El archivo de clave se creó como carpeta** — si al copiar la clave con Explorer queda como `Mode: d-----` en vez de `-a----`, significa que Windows creó una carpeta con ese nombre. Fix:
   ```powershell
   Remove-Item C:\labcontrol_backup\keys\labwin_backup -Recurse -Force
   # Volver a copiar el archivo (no la carpeta)
   Get-Item C:\labcontrol_backup\keys\labwin_backup | Format-List Mode, Length
   # Debe decir Mode: -a----, Length: 411
   ```

2. **Ruta de la BBDD en la PC del lab** — el PDF original decía `C:\sistema\LabWin4\BASEDAT.FDB`, pero la ruta real es `C:\sistema\LabWin4\Basedat\BASEDAT.FDB` (con subcarpeta `Basedat\`). Si el script falla con `gbak: ERROR: El sistema no puede encontrar el archivo`, buscar la ruta real:
   ```powershell
   Get-ChildItem -Path C:\ -Filter BASEDAT.FDB -Recurse -ErrorAction SilentlyContinue | Select-Object FullName
   ```
   Y editar `LABWIN_DB` en el script con la ruta devuelta.

#### Test manual antes de programar la tarea

```powershell
# Dry-run: genera backup pero NO sube al VPS
python C:\labcontrol_backup\upload_backup.py --dry-run
```

Salida esperada en el log (`C:\labcontrol_backup\upload.log`):
```
[INFO] Running gbak: C:\sistema\LabWin4\Basedat\BASEDAT.FDB -> ...
[INFO] gbak OK - 347.2 MB
[INFO] gzipping: BASEDAT_*.fbk -> BASEDAT_*.fbk.gz
[INFO] gzip OK - 69.9 MB (ratio 0.20 vs .fbk crudo)
[INFO] DRY RUN - saltando upload. Archivo listo en: C:\labcontrol_backup\archive\BASEDAT_*.fbk.gz
[INFO] Backup run OK - duracion total 153 s
```

Si el dry-run anduvo, upload real:
```powershell
python C:\labcontrol_backup\upload_backup.py
```

Salida esperada adicional en el log:
```
[INFO] Conectando a 72.60.137.226:22 como backup_user
[INFO] Authentication (publickey) successful!
[INFO] Host fingerprint OK: SHA256:GTAVmxiXmwQsFNbY5wE2ElowE+GV9ilt64yFdHnT24g
[INFO] Subiendo: BASEDAT_*.fbk.gz -> /incoming/BASEDAT_*.fbk.gz
[INFO] Upload OK - 69.9 MB en 22 s (3.2 MB/s)
[INFO] Backup run OK - duracion total 107 s
```

Verificar del lado del VPS (desde la laptop de Sebastian):
```bash
sftp -i ~/.ssh/labwin_backup backup_user@72.60.137.226 <<< 'ls -la incoming/'
# Debe mostrar el archivo BASEDAT_YYYYMMDD_HHMMSS.fbk.gz recien subido
```

#### Task Scheduler

- **Trigger:** Diario, 02:00 AM
- **Action:** `C:\Python311\python.exe C:\labcontrol_backup\upload_backup.py`
- **Start in:** `C:\labcontrol_backup\`
- **Run whether user is logged on or not:** ✅
- **Run with highest privileges:** ✅
- Si falla, Task Scheduler registra el exit code (0 = OK, 1 = error) — configurar "Send email on failure" via Event Viewer trigger en el Event ID correspondiente

---

### 2. VPS — usuario SFTP chroot

**Estado:** ✅ Implementado en el VPS el 2026-04-24.

Usuario dedicado que **solo** puede subir a `/srv/labwin_backups/incoming/`:

```bash
# En el VPS (como root) — YA EJECUTADO
sudo useradd -m -s /usr/sbin/nologin backup_user
sudo mkdir -p /srv/labwin_backups/{incoming,processed,failed}
sudo chown root:root /srv/labwin_backups
sudo chmod 755 /srv/labwin_backups
sudo chown backup_user:backup_user /srv/labwin_backups/incoming
sudo chmod 755 /srv/labwin_backups/incoming

# /etc/ssh/sshd_config.d/backup_user.conf — YA CREADO
Match User backup_user
    ChrootDirectory /srv/labwin_backups
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
    PasswordAuthentication no

sudo systemctl reload ssh
```

**Por qué no reutilizar vsftpd:** el stack ya usa `vsftpd` para los PDFs (Phase 13). Se podría reutilizar, pero:
- SFTP (sobre SSH) es más simple de endurecer que FTPS
- Ya tenemos SSH abierto en el VPS; no agregamos superficie de ataque
- Separación de propósito: vsftpd sirve PDFs pull-from-container, SFTP recibe push-from-lab

#### Credenciales SFTP para el laboratorio

| Setting | Value |
|---|---|
| **Host** | `72.60.137.226` |
| **Port** | `22` |
| **Protocolo** | **SFTP** (SSH File Transfer Protocol) |
| **Usuario** | `backup_user` |
| **Autenticación** | Clave SSH (sin password) |
| **Directorio de subida** | `/incoming/` |
| **Fingerprint del host (ed25519)** | `SHA256:GTAVmxiXmwQsFNbY5wE2ElowE+GV9ilt64yFdHnT24g` |

**⚠️ Distinto de las credenciales FTP de PDFs** (`labwin_ftp` :21 `/results`). Son dos pipelines separados:
- **PDFs** → FTP :21, user `labwin_ftp`, `/results/` (Phase 13 — ya en uso)
- **Backups DB** → SFTP :22, user `backup_user`, `/incoming/` (este documento)

#### Par de claves SSH

Clave generada localmente el 2026-04-24 con:
```bash
ssh-keygen -t ed25519 -f ~/.ssh/labwin_backup -C "labwin-backup-lab-pc" -N ""
```

**Clave pública** (ya instalada en `/home/backup_user/.ssh/authorized_keys`):
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAILXoYUFKGjCu7JkPIw0giX8vEAlNt18cSXCFfQXV8QDN labwin-backup-lab-pc
```

**Clave privada** (debe instalarse **solo** en la PC del laboratorio):

> ⚠️ **La clave privada NO se versiona en este documento.** Está guardada en el gestor de secretos del equipo (ver §"Backup de la clave" abajo). Para obtenerla, pedirla al owner del proyecto y transportarla al lab por uno de los canales seguros listados en §"Transporte al lab".
>
> Si sospechás que la clave fue comprometida — o que una versión anterior de este doc con la clave embebida se filtró — **rotala inmediatamente** siguiendo el procedimiento de §"Rotación".

**Fingerprint de la clave (público, OK exponer):** `SHA256:AztSYVjU5QO5V7PRsjpX5v1X1/gd7sghMnUxSCkc2NA`

#### Cómo el laboratorio debe guardar la clave privada

La clave privada otorga acceso de escritura a `/srv/labwin_backups/incoming/` en el VPS. Si se filtra, cualquiera podría subir archivos al VPS haciéndose pasar por el laboratorio. Protocolo de instalación en la PC del lab:

1. **Ubicación** — guardar en una ruta dedicada, no en `Documents` ni en el Desktop:
   ```
   C:\labcontrol_backup\keys\labwin_backup
   ```
   El directorio `C:\labcontrol_backup\` debe ser **solo accesible** por el usuario que ejecuta la tarea programada.

2. **Permisos NTFS** — quitar herencia y dejar permisos solo al usuario de la tarea programada:
   ```powershell
   # PowerShell como Administrador
   icacls C:\labcontrol_backup\keys\labwin_backup /inheritance:r
   icacls C:\labcontrol_backup\keys\labwin_backup /grant:r "%USERNAME%:R"
   icacls C:\labcontrol_backup\keys\labwin_backup /remove "BUILTIN\Users"
   icacls C:\labcontrol_backup\keys\labwin_backup /remove "Everyone"
   ```
   Verificar con `icacls C:\labcontrol_backup\keys\labwin_backup` — solo el usuario de la tarea y `NT AUTHORITY\SYSTEM` deben tener acceso.

3. **Nunca hacer** de esa clave:
   - ❌ No adjuntarla a emails, WhatsApp, Slack, ni mensajes sin cifrar
   - ❌ No subirla a Google Drive / Dropbox / OneDrive sin cifrado previo
   - ❌ No compartirla entre PCs del lab — si hay más de una PC que necesita subir backups, pedir una clave por PC
   - ❌ No commitear a ningún repositorio
   - ❌ No copiarla a memorias USB sin cifrar

4. **Transporte al lab** — compartir la clave **solo** por:
   - ✅ Gestor de contraseñas compartido (1Password, Bitwarden) con acceso revocable
   - ✅ Archivo ZIP con password fuerte enviado en un canal y password en otro canal distinto
   - ✅ Entrega en persona (USB cifrado)

5. **Backup de la clave** — guardar copia cifrada en el gestor de secretos del equipo de desarrollo por si hay que reinstalarla en una PC nueva. Si se pierde, se genera una nueva y se reemplaza la pública en el VPS.

6. **Rotación** — regenerar anualmente, o inmediatamente si se sospecha compromiso. Procedimiento:
   ```bash
   # En el VPS (como deploy, con sudo)
   echo "<NUEVA_CLAVE_PUBLICA>" | sudo tee /home/backup_user/.ssh/authorized_keys
   ```

#### Verificación del fingerprint del VPS

El laboratorio **debe** verificar el fingerprint del VPS en la primera conexión para prevenir MITM:

```
SHA256:GTAVmxiXmwQsFNbY5wE2ElowE+GV9ilt64yFdHnT24g
```

El script `upload_backup.py` debe cargar el host key conocido (`load_host_keys`) y rechazar conexiones a hosts con fingerprint distinto.

---

### 3. VPS — servicio Firebird en Docker

Agregar a `docker-compose.prod.yml`:

```yaml
services:
  firebird:
    image: jacobalberty/firebird:2.5-ss
    container_name: labcontrol_firebird
    restart: unless-stopped
    environment:
      ISC_PASSWORD: ${FIREBIRD_SYSDBA_PASSWORD}
      FIREBIRD_DATABASE: BASEDAT.FDB
    volumes:
      - firebird_data:/firebird/data
      - /srv/labwin_backups/incoming:/backups/incoming:ro
      - /srv/labwin_backups/processed:/backups/processed
    networks:
      - labcontrol_net
    # No exponer puerto al host — solo accesible internamente

volumes:
  firebird_data:
```

Agregar a `.env.production`:
```env
FIREBIRD_SYSDBA_PASSWORD=<random-32-char>
LABWIN_USE_MOCK=False
LABWIN_FDB_HOST=firebird
LABWIN_FDB_PORT=3050
LABWIN_FDB_DATABASE=/firebird/data/BASEDAT.FDB
LABWIN_FDB_USER=SYSDBA
LABWIN_FDB_PASSWORD=${FIREBIRD_SYSDBA_PASSWORD}
```

**Memoria:** Firebird 2.5 Superserver consume ~200–400 MB con la DB del lab. Validar capacidad del VPS antes de activar.

---

### 4. VPS — Celery task nueva

**Archivo:** `apps/labwin_sync/tasks.py` (agregar al existente)

```python
@shared_task(bind=True, max_retries=2)
def import_uploaded_backup(self, lab_client_id=None):
    """
    Restaura el backup más reciente de /backups/incoming/ al contenedor
    Firebird y dispara el sync. Mueve el archivo a processed/ (o failed/).
    """
    from apps.labwin_sync.services.backup_import import BackupImporter

    importer = BackupImporter(lab_client_id=lab_client_id or settings.LABWIN_DEFAULT_LAB_CLIENT_ID)
    return importer.run()
```

**Archivo nuevo:** `apps/labwin_sync/services/backup_import.py`

Responsabilidades:
1. Buscar el `.fbk.gz` más reciente en `/backups/incoming/`
2. Validar integridad (tamaño > 0, gunzip válido)
3. `docker exec labcontrol_firebird gbak -r ...` para restaurar
4. Invocar `sync_labwin_results(lab_client_id=...)` (task existente)
5. Mover archivo procesado a `processed/` con timestamp
6. Rotación: borrar de `processed/` archivos > 30 días
7. Registrar `SyncLog` con status/contadores/errores
8. En error: mover a `failed/`, notificar (email o webhook)

**Registro en Celery Beat** — `config/celery.py`:

```python
CELERY_BEAT_SCHEDULE = {
    'import-labwin-backup': {
        'task': 'apps.labwin_sync.tasks.import_uploaded_backup',
        'schedule': crontab(hour=4, minute=0),  # 04:00 AM diario
    },
    # IMPORTANTE: eliminar el schedule standalone de sync_labwin_results
    # Ahora lo dispara import_uploaded_backup (encadenamiento).
}
```

---

### 5. VPS — management command para disparos manuales

**Archivo:** `apps/labwin_sync/management/commands/import_backup.py`

```bash
# Restaura e ingesta el último backup (uso manual / testing)
python manage.py import_backup

# Fuerza un path específico
python manage.py import_backup --file /srv/labwin_backups/incoming/BASEDAT_20260422.fbk.gz

# Solo restaura, sin disparar sync
python manage.py import_backup --restore-only

# Sync sin restaurar (cuando Firebird ya tiene data reciente)
python manage.py import_backup --sync-only
```

Útil para:
- Testing en staging
- Recuperación si la task de Celery falla
- Ingesta inicial (primer restore del histórico completo)

---

## 📋 Plan de implementación (fases)

### Fase A — Preparación del VPS (~2h)
- [x] Crear usuario `backup_user` + chroot SFTP *(2026-04-24)*
- [x] Generar par de claves SSH ed25519 *(2026-04-24 — ver §2 arriba)*
- [x] Crear directorios `/srv/labwin_backups/{incoming,processed,failed}` *(2026-04-24)*
- [x] Test manual: subir un archivo dummy desde una máquina externa *(2026-04-24 — laptop de Sebastian → `/incoming/labwin_backup_test.txt` OK, luego eliminado)*
- [x] **Deploy del script en PC del lab + primer upload real** *(2026-04-24 — `BASEDAT_20260424_180940.fbk.gz` 69.9 MB en `/incoming/`)*
- [ ] Agregar servicio `firebird` a `docker-compose.prod.yml`
- [ ] Validar que el contenedor inicia y acepta conexiones desde `web`
- [ ] Probar restore del `.fbk.gz` real del lab → validar que es un backup consistente usable

### Fase B — Código del backend (~1–2 días)
- [ ] Implementar `apps/labwin_sync/services/backup_import.py`
- [ ] Implementar `apps/labwin_sync/tasks.py::import_uploaded_backup`
- [ ] Tests unitarios (mock del filesystem + mock del connector Firebird)
- [ ] Management command `import_backup`
- [ ] Actualizar Celery Beat schedule
- [ ] Documentar nuevas env vars en `.env.example`

### Fase C — Script del lab (~0.5 día)
- [x] Implementar `upload_backup.py` *(2026-04-24 — con gbak + gzip + SFTP + host verification + rotación + log)*
- [x] Script de test: `upload_backup.py --dry-run` (valida conexión sin subir) *(2026-04-24)*
- [ ] Configuración de Task Scheduler (XML versionado)
- [ ] Versionar el script en el repo en `deployment/lab_workstation/upload_backup.py` *(actualmente solo en PC del lab)*

### Fase D — Instalación en el lab (~2h in-situ)
- [x] Instalar Python + Paramiko en la PC del lab *(2026-04-24 — Python 3.12 + paramiko ya estaban)*
- [x] Desplegar script + clave privada *(2026-04-24 — via USB, verificado con fingerprint)*
- [x] Verificar con trigger manual *(2026-04-24 — primer upload OK a las 18:11)*
- [x] Confirmar que el archivo llegó al VPS *(2026-04-24 — 69.9 MB en `/incoming/`)*
- [ ] Importar tarea programada (Task Scheduler) para correr automático 02:00 AM

### Fase E — Validación end-to-end (~1 día)
- [ ] Disparar `import_backup` manual → verificar restore OK
- [ ] Verificar que `sync_labwin_results` crea/actualiza registros
- [ ] Validar contadores en Django Admin → `SyncLog`
- [ ] Monitorear la primera ejecución automática 04:00 AM
- [ ] Documentar tiempos reales (upload + restore + sync) para ajustar schedules

### Fase F — Monitoreo y alertas (~0.5 día)
- [ ] Endpoint de health check: "último sync exitoso hace N horas"
- [ ] Email/webhook si no hay backup nuevo en 36h
- [ ] Dashboard en Django Admin con últimos 30 días de `SyncLog`

---

## 🔐 Consideraciones de seguridad

1. **Clave SSH del lab:** generar sin passphrase (para que Task Scheduler corra sin interacción), pero almacenar con permisos `600` y en directorio solo accesible al usuario que corre la tarea
2. **Chroot estricto:** `backup_user` **no puede** ejecutar shell ni ver otros directorios del VPS
3. **No logging de credenciales:** el script debe evitar imprimir la ruta de la clave o credenciales de Firebird
4. **Backup de la clave privada:** si la PC del lab falla, hay que poder reinstalarla. Guardar copia cifrada en el gestor de secretos de YeKo
5. **Cifrado del `.fbk.gz`:** SFTP ya cifra en tránsito. Si el cliente requiere cifrado at-rest adicional, agregar `gpg --encrypt` antes del upload (con clave pública del VPS)
6. **Rotación de claves:** política de rotación anual de la clave SSH del backup
7. **Password de Firebird:** aleatorio, solo conocido por el stack docker, nunca commiteado

---

## 📜 Primer upload exitoso (2026-04-24)

Evidencia del primer upload end-to-end funcional, útil como referencia para debugging futuro.

**Log del script en la PC del lab:**

```
2026-04-24 18:09:40,781 [INFO] ============================================================
2026-04-24 18:09:40,782 [INFO] Backup run iniciado a 2026-04-24T18:09:40.781804 (dry_run=False)
2026-04-24 18:09:40,784 [INFO] Running gbak: C:\sistema\LabWin4\Basedat\BASEDAT.FDB -> C:\labcontrol_backup\work\BASEDAT_20260424_180940.fbk
2026-04-24 18:10:48,246 [INFO] gbak OK - 347.2 MB
2026-04-24 18:10:48,247 [INFO] gzipping: BASEDAT_20260424_180940.fbk -> BASEDAT_20260424_180940.fbk.gz
2026-04-24 18:11:05,073 [INFO] gzip OK - 69.9 MB (ratio 0.20 vs .fbk crudo)
2026-04-24 18:11:05,075 [INFO] Conectando a 72.60.137.226:22 como backup_user
2026-04-24 18:11:05,170 [INFO] Connected (version 2.0, client OpenSSH_9.6p1)
2026-04-24 18:11:05,418 [INFO] Authentication (publickey) successful!
2026-04-24 18:11:05,419 [INFO] Host fingerprint OK: SHA256:GTAVmxiXmwQsFNbY5wE2ElowE+GV9ilt64yFdHnT24g
2026-04-24 18:11:06,373 [INFO] [chan 0] Opened sftp connection (server version 3)
2026-04-24 18:11:06,374 [INFO] Subiendo: BASEDAT_20260424_180940.fbk.gz -> /incoming/BASEDAT_20260424_180940.fbk.gz
2026-04-24 18:11:28,263 [INFO] Upload OK - 69.9 MB en 22 s (3.2 MB/s)
2026-04-24 18:11:28,276 [INFO] Backup run OK - duracion total 107 s
```

**Verificación del lado del VPS** (via `sftp -i ~/.ssh/labwin_backup backup_user@72.60.137.226`):

```
drwxr-xr-x    ? 1003     1003         4096 Apr 24 23:11 incoming/.
drwxr-xr-x    ? root     root         4096 Apr 24 22:02 incoming/..
-rw-rw-r--    ? 1003     1003     73248992 Apr 24 23:11 incoming/BASEDAT_20260424_180940.fbk.gz
```

- Tamaño en VPS: 73,248,992 bytes = 69.9 MB — coincide con el log del lab
- Timestamp en VPS (23:11 UTC) = 18:11 hora local Argentina (UTC-3) — coincide con el log
- Permisos 664, owner `backup_user` (uid 1003) — correcto

**Este archivo queda disponible como dataset real para validar Fase B** (restore + sync) en el VPS.

---

## 🚨 Modos de fallo y recuperación

| Fallo | Detección | Recuperación |
|---|---|---|
| PC del lab apagada | Alerta por falta de backup > 36h | Contactar al lab, disparar manual al volver |
| Upload parcial (conexión cae) | SFTP falla, script retorna != 0 | Task Scheduler reintenta al día siguiente |
| `.fbk.gz` corrupto | `gbak -r` falla en el VPS | Archivo va a `failed/`, se espera el del día siguiente |
| Firebird container OOM | Healthcheck falla | Aumentar memoria del VPS o limitar cache Firebird |
| Sync parcial (error en un record) | `SyncLog.status=partial` | Records problemáticos quedan en `errors` JSON; `SyncedRecord` evita duplicados en el siguiente intento |
| Clave SSH del lab comprometida | Intrusión en el backup_user del VPS | Revocar la clave en `authorized_keys`, generar una nueva, reinstalar |

---

## 📊 Métricas a trackear

- Tamaño del `.fbk.gz` en el tiempo (crecimiento de la DB del lab)
- Duración del upload desde el lab
- Duración del restore en el VPS
- Duración del sync (`sync_labwin_results`)
- % de éxitos en los últimos 30 días
- Gap máximo entre syncs exitosos

### Baseline medido (2026-04-24, primer upload real)

| Métrica | Valor |
|---|---|
| Tamaño BBDD `.FDB` (en la PC del lab) | ~347 MB |
| Tamaño `.fbk` (post-gbak) | 347.2 MB |
| Tamaño `.fbk.gz` (post-gzip) | 69.9 MB |
| Ratio de compresión gzip | 0.20 |
| Duración `gbak -b -g` | 67 s |
| Duración `gzip` | 17 s |
| Duración SFTP upload | 22 s |
| Velocidad sostenida SFTP | 3.2 MB/s |
| **Duración total lab-side** | **107 s** |

La BBDD era más chica de lo estimado originalmente (se asumían 2–5 GB por las docs del diseño). Se recomienda re-medir en 30/60/90 días para estimar tasa de crecimiento.

---

## 🔗 Referencias

- **Guía original del cliente:** `guia_backup_lab.pdf` (SFTP + Paramiko, usaba password y copiaba el `.FDB` en caliente — ya obsoleta, reemplazada por este doc)
- **Backend:** `BACKEND.md` §LabWin Sync
- **Deployment:** `DEPLOYMENT.md` §LabWin Backup Ingestion Pipeline
- **Connectors existentes:** `apps/labwin_sync/connectors/`
- **Sync task existente:** `apps/labwin_sync/tasks.py::sync_labwin_results`
- **Imagen Firebird Docker:** https://hub.docker.com/r/jacobalberty/firebird

---

## ❓ Decisiones pendientes de discutir con el cliente

1. ~~**Horario del backup:** ¿el servicio LabWin sigue activo a las 2 AM? Si sí, validar que `gbak` funcione con el lock del service~~ ✅ **Resuelto 2026-04-24** — `gbak -b -g` corre OK contra la DB en caliente, generó un `.fbk` consistente de 347 MB en 67s sin parar Firebird.
2. ~~**Tamaño real de la DB:**~~ ✅ **Resuelto 2026-04-24** — 347 MB descomprimida, 70 MB `.fbk.gz`. Mucho más chica de lo estimado (2-5 GB). Re-medir en 60 días.
3. ~~**Ancho de banda del lab:**~~ ✅ **Resuelto 2026-04-24** — 70 MB sostiene 3.2 MB/s (22 s total). Impacto mínimo, viable a cualquier hora.
4. **Retención en el VPS:** ¿30 días en `/srv/labwin_backups/processed/` es suficiente? ¿Backup de los backups a S3 / almacenamiento externo?
5. **Multi-sede futura:** si el cliente tiene más de un lab, cada uno necesita su `backup_user` y su `lab_client_id`. El diseño actual asume un único lab.
6. ~~**Password de SYSDBA en el script:**~~ ✅ **Resuelto** — la versión productiva del script (ver `backup_lab_guide.md`) lee el password desde `upload_backup.config.ini` con permisos NTFS restrictivos, no más hardcoding. El snippet inline en este doc usa un placeholder `REPLACE_WITH_REAL_SYSDBA_PASSWORD` para que sea obvio que hay que reemplazarlo. Source of truth del valor: 1Password → "LabControl LabWin SYSDBA".
7. **Task Scheduler:** pendiente de configurar en la PC del lab para automatizar el upload a las 02:00 AM. Por ahora se corre manual.
