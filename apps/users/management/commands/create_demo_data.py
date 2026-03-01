"""
Management command to create demo data for LabControl.

Creates:
- 3 admin users (Carlos, Franco, Lucia)
- 3 patients
- 2 doctors
- Multiple studies with realistic data
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.studies.models import Practice, Study

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo data for LabControl demonstration"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Creating demo data..."))

        # Create admin users
        self.create_admins()

        # Create patients
        self.create_patients()

        # Create doctors
        self.create_doctors()

        # Create practices if they don't exist
        self.create_practices()

        # Create studies
        self.create_studies()

        self.stdout.write(self.style.SUCCESS("\n✅ Demo data created successfully!"))
        self.stdout.write(self.style.SUCCESS("\nCredentials:"))
        self.stdout.write("  All users password: test1234")
        self.stdout.write("\nAdmin users:")
        self.stdout.write("  - carlos@labcontrol.com")
        self.stdout.write("  - franco@labcontrol.com")
        self.stdout.write("  - lucia@labcontrol.com")
        self.stdout.write("\nPatients:")
        self.stdout.write("  - patient+0@labcontrol.com")
        self.stdout.write("  - patient+1@labcontrol.com")
        self.stdout.write("  - patient+2@labcontrol.com")
        self.stdout.write("\nDoctors:")
        self.stdout.write("  - doctor+0@labcontrol.com")
        self.stdout.write("  - doctor+1@labcontrol.com")

    def create_admins(self):
        """Create 3 admin users"""
        admins = [
            {
                "email": "carlos@labcontrol.com",
                "first_name": "Carlos",
                "last_name": "Golijow",
                "phone_number": "+54 11 5555-0001",
                "dni": "35123456",
            },
            {
                "email": "franco@labcontrol.com",
                "first_name": "Franco",
                "last_name": "Siri",
                "phone_number": "+54 11 5555-0002",
                "dni": "36234567",
            },
            {
                "email": "lucia@labcontrol.com",
                "first_name": "Lucia",
                "last_name": "LDM",
                "phone_number": "+54 11 5555-0003",
                "dni": "37345678",
            },
        ]

        for admin_data in admins:
            user, created = User.objects.get_or_create(
                email=admin_data["email"],
                defaults={
                    "first_name": admin_data["first_name"],
                    "last_name": admin_data["last_name"],
                    "phone_number": admin_data["phone_number"],
                    "dni": admin_data["dni"],
                    "role": "admin",
                    "is_staff": True,
                    "is_superuser": True,
                    "is_active": True,
                    "is_verified": True,
                    "lab_client_id": 1,
                },
            )
            if created:
                user.set_password("test1234")
                user.save()
                self.stdout.write(
                    f"  ✓ Created admin: {admin_data['first_name']} {admin_data['last_name']}"
                )
            else:
                self.stdout.write(f"  - Admin already exists: {admin_data['email']}")

    def create_patients(self):
        """Create 3 patient users"""
        patients_data = [
            {
                "email": "patient+0@labcontrol.com",
                "first_name": "María",
                "last_name": "González",
                "phone_number": "+54 11 4444-0001",
                "dni": "40123456",
                "gender": "F",
                "birthday": "1990-05-15",
                "location": "Buenos Aires",
                "direction": "Av. Corrientes 1234",
                "mutual_name": "OSDE",
                "mutual_code": "210",
                "carnet": "12345678901234",
            },
            {
                "email": "patient+1@labcontrol.com",
                "first_name": "Juan",
                "last_name": "Pérez",
                "phone_number": "+54 11 4444-0002",
                "dni": "41234567",
                "gender": "M",
                "birthday": "1985-08-22",
                "location": "Buenos Aires",
                "direction": "Av. Santa Fe 5678",
                "mutual_name": "Swiss Medical",
                "mutual_code": "101",
                "carnet": "23456789012345",
            },
            {
                "email": "patient+2@labcontrol.com",
                "first_name": "Ana",
                "last_name": "Martínez",
                "phone_number": "+54 11 4444-0003",
                "dni": "42345678",
                "gender": "F",
                "birthday": "1995-12-03",
                "location": "Buenos Aires",
                "direction": "Av. Callao 9012",
                "mutual_name": "Galeno",
                "mutual_code": "305",
                "carnet": "34567890123456",
            },
        ]

        for patient_data in patients_data:
            user, created = User.objects.get_or_create(
                email=patient_data["email"],
                defaults={
                    **patient_data,
                    "role": "patient",
                    "is_active": True,
                    "is_verified": True,
                    "lab_client_id": 1,
                },
            )
            if created:
                user.set_password("test1234")
                user.save()
                self.stdout.write(
                    f"  ✓ Created patient: {patient_data['first_name']} {patient_data['last_name']}"
                )
            else:
                self.stdout.write(
                    f"  - Patient already exists: {patient_data['email']}"
                )

    def create_doctors(self):
        """Create 2 doctor users"""
        doctors_data = [
            {
                "email": "doctor+0@labcontrol.com",
                "first_name": "Roberto",
                "last_name": "Fernández",
                "phone_number": "+54 11 3333-0001",
                "dni": "30123456",
                "location": "Buenos Aires",
            },
            {
                "email": "doctor+1@labcontrol.com",
                "first_name": "Laura",
                "last_name": "Rodríguez",
                "phone_number": "+54 11 3333-0002",
                "dni": "31234567",
                "location": "Buenos Aires",
            },
        ]

        for doctor_data in doctors_data:
            user, created = User.objects.get_or_create(
                email=doctor_data["email"],
                defaults={
                    **doctor_data,
                    "role": "doctor",
                    "is_active": True,
                    "is_verified": True,
                    "lab_client_id": 1,
                },
            )
            if created:
                user.set_password("test1234")
                user.save()
                self.stdout.write(
                    f"  ✓ Created doctor: Dr. {doctor_data['first_name']} {doctor_data['last_name']}"
                )
            else:
                self.stdout.write(f"  - Doctor already exists: {doctor_data['email']}")

    def create_practices(self):
        """Create sample practices if they don't exist"""
        practices_data = [
            {
                "name": "Hemograma Completo",
                "technique": "Citometría de flujo",
                "sample_type": "Sangre",
                "sample_quantity": "5 ml",
                "price": 2500.00,
                "delay_days": 1,
            },
            {
                "name": "Perfil Bioquímico",
                "technique": "Espectrofotometría",
                "sample_type": "Sangre",
                "sample_quantity": "10 ml",
                "price": 3500.00,
                "delay_days": 2,
            },
            {
                "name": "Orina Completa",
                "technique": "Examen físico-químico y microscópico",
                "sample_type": "Orina",
                "sample_quantity": "50 ml",
                "price": 1500.00,
                "delay_days": 1,
            },
            {
                "name": "Perfil Tiroideo",
                "technique": "Electroquimioluminiscencia",
                "sample_type": "Sangre",
                "sample_quantity": "5 ml",
                "price": 4500.00,
                "delay_days": 3,
            },
            {
                "name": "Vitamina D",
                "technique": "HPLC",
                "sample_type": "Sangre",
                "sample_quantity": "5 ml",
                "price": 5000.00,
                "delay_days": 5,
            },
        ]

        for practice_data in practices_data:
            practice, created = Practice.objects.get_or_create(
                name=practice_data["name"], defaults=practice_data
            )
            if created:
                self.stdout.write(f"  ✓ Created practice: {practice_data['name']}")

    def create_studies(self):
        """Create sample studies for patients"""
        patients = User.objects.filter(role="patient")
        doctors = User.objects.filter(role="doctor")
        practices = Practice.objects.filter(is_active=True)

        if not patients.exists():
            self.stdout.write(
                self.style.WARNING("  - No patients found, skipping studies")
            )
            return

        if not practices.exists():
            self.stdout.write(
                self.style.WARNING("  - No practices found, skipping studies")
            )
            return

        # Create studies with different statuses
        statuses = ["completed", "in_progress", "pending"]

        study_count = 0
        for patient in patients:
            # Create 3-5 studies per patient
            num_studies = random.randint(3, 5)

            for i in range(num_studies):
                practice = random.choice(practices)
                doctor = random.choice(doctors) if doctors.exists() else None
                status = random.choice(statuses)

                # Generate protocol number
                protocol_number = (
                    f"LDM{timezone.now().year}{random.randint(1000, 9999)}"
                )

                # Create study
                study = Study.objects.create(
                    patient=patient,
                    practice=practice,
                    protocol_number=protocol_number,
                    ordered_by=doctor,
                    status=status,
                    lab_client_id=1,
                    created_at=timezone.now() - timedelta(days=random.randint(1, 30)),
                )

                # Add results for completed studies
                if status == "completed":
                    study.completed_at = timezone.now() - timedelta(
                        days=random.randint(0, 5)
                    )
                    study.results = f"Resultados normales para {practice.name}. Todos los valores dentro de rangos de referencia."
                    # Note: In production, you would upload a PDF file here
                    # study.results_file = 'path/to/pdf'
                    study.save()

                study_count += 1

        self.stdout.write(f"  ✓ Created {study_count} studies")
