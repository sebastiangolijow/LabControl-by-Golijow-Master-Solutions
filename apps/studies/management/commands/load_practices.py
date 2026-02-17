"""
Django Management Command para cargar prácticas desde JSON

INSTALACIÓN:
1. Copiar este archivo a: /Users/cevichesmac/Desktop/labcontrol/apps/studies/management/commands/load_practices.py
2. Copiar practices_data.json a: /Users/cevichesmac/Desktop/labcontrol/data/practices_data.json
3. Ejecutar: docker-compose exec web python manage.py load_practices

O si prefieres, puedes ejecutarlo directamente desde Django shell.
"""

import json
import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.studies.models import Practice


class Command(BaseCommand):
    help = "Carga prácticas desde archivo JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="data/practices_data.json",
            help="Ruta al archivo JSON con las prácticas",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Eliminar todas las prácticas existentes antes de cargar",
        )

    def handle(self, *args, **options):
        file_path = options["file"]
        clear_existing = options["clear"]

        # Verificar que el archivo existe
        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(f"❌ Archivo no encontrado: {file_path}")
            )
            return

        # Leer el JSON
        with open(file_path, "r", encoding="utf-8") as f:
            practices_data = json.load(f)

        self.stdout.write(
            self.style.SUCCESS(
                f"📄 Archivo cargado: {len(practices_data)} prácticas encontradas"
            )
        )

        # Eliminar prácticas existentes si se especificó
        if clear_existing:
            count = Practice.objects.count()
            Practice.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"🗑️  {count} prácticas existentes eliminadas")
            )

        # Cargar prácticas
        created_count = 0
        updated_count = 0
        error_count = 0

        with transaction.atomic():
            for practice_data in practices_data:
                try:
                    # Buscar si ya existe una práctica con ese nombre
                    practice, created = Practice.objects.update_or_create(
                        name=practice_data["name"],
                        defaults={
                            "technique": practice_data.get("technique", ""),
                            "sample_type": practice_data.get("sample_type", ""),
                            "sample_quantity": practice_data.get("sample_quantity", ""),
                            "sample_instructions": practice_data.get(
                                "sample_instructions", ""
                            ),
                            "conservation_transport": practice_data.get(
                                "conservation_transport", ""
                            ),
                            "delay_days": practice_data.get("delay_days", 0),
                            "price": practice_data.get("price", "0.00"),
                            "is_active": practice_data.get("is_active", True),
                        },
                    )

                    if created:
                        created_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  ✅ Creada: {practice.name} (${practice.price})"
                            )
                        )
                    else:
                        updated_count += 1
                        self.stdout.write(
                            self.style.WARNING(
                                f"  🔄 Actualizada: {practice.name} (${practice.price})"
                            )
                        )

                except Exception as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ❌ Error con {practice_data.get("name", "Unknown")}: {str(e)}'
                        )
                    )

        # Resumen final
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("RESUMEN DE CARGA"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"✅ Prácticas creadas:      {created_count}")
        self.stdout.write(f"🔄 Prácticas actualizadas: {updated_count}")
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f"❌ Errores:                {error_count}")
            )
        self.stdout.write(f"📊 Total en BD:            {Practice.objects.count()}")
        self.stdout.write("=" * 80)


# ALTERNATIVA: Script independiente para ejecutar desde Django shell
# Para usar: docker-compose exec web python manage.py shell < load_practices_shell.py

"""
# Script para Django Shell
import json
from apps.studies.models import Practice

# Cargar JSON
with open('data/practices_data.json', 'r', encoding='utf-8') as f:
    practices_data = json.load(f)

# Crear prácticas
for practice_data in practices_data:
    practice, created = Practice.objects.update_or_create(
        name=practice_data['name'],
        defaults={
            'technique': practice_data.get('technique', ''),
            'sample_type': practice_data.get('sample_type', ''),
            'sample_quantity': practice_data.get('sample_quantity', ''),
            'sample_instructions': practice_data.get('sample_instructions', ''),
            'conservation_transport': practice_data.get('conservation_transport', ''),
            'delay_days': practice_data.get('delay_days', 0),
            'price': practice_data.get('price', '0.00'),
            'is_active': practice_data.get('is_active', True),
        }
    )
    status = "CREADA" if created else "ACTUALIZADA"
    print(f"{status}: {practice.name} (${practice.price})")

print(f"\nTotal de prácticas en BD: {Practice.objects.count()}")
"""
