# Practices Data

This directory contains JSON data files for loading practices into the database.

## Files

- **practices_data.json** - 13 practices from Infectología Molecular area

## Usage

### Load practices using Make command

```bash
# Load practices (keeps existing)
make load_practices

# Load practices (clear existing first)
make load_practices_clear
```

### Load practices using Django management command

```bash
# Default usage
docker-compose exec web python manage.py load_practices

# Clear existing practices first
docker-compose exec web python manage.py load_practices --clear

# Use custom file
docker-compose exec web python manage.py load_practices --file=/path/to/file.json
```

## Practices Included (13 total)

All from **ÁREA BIOLOGÍA MOLECULAR - Infectología Molecular**:

1. Detección Sars-CoV-2 - $21,920.92
2. Detección Chlamydia trachomatis - $14,831.18
3. Detección Ureaplasma urealiticum - $9,269.47
4. Detección Mycoplasma hominis - $9,269.47
5. Papilomavirus humano - Detección + tipificación - $23,835.77
6. Herpes Simplex Virus - Detección y tipificación (I, II) - $15,890.52
7. Detección Epstein Barr Virus - $13,242.10
8. Detección Mycobacterium tuberculosis - $13,242.10
9. Detección Citomegalovirus - $13,242.10
10. Detección Neisseria gonorrhoeae - $10,483.33
11. Detección Mycoplasma genitalium - $13,242.10
12. Detección DENV (Dengue) - $21,201.35
13. Panel ginecológico (5 en 1) - $27,337.22

## JSON Structure

Each practice has the following fields:

```json
{
  "name": "Practice name",
  "technique": "Technique used",
  "sample_type": "Types of samples accepted",
  "sample_quantity": "Sample quantity required",
  "sample_instructions": "Instructions for sample collection",
  "conservation_transport": "Conservation and transport conditions",
  "delay_days": 7,
  "price": "13242.10",
  "is_active": true
}
```

## Source

- **File**: Reg-114_ARANCELES_DERIVACIÓN_LDM_AGOSTO2024.csv
- **Date**: August 2024
- **Area**: Biología Molecular - Infectología Molecular
- **Pages extracted**: 2-5 (out of 23)

## Notes

- This is a partial extraction (only Infectología Molecular area)
- The source CSV has 23 pages with many more practices
- To add more practices, extract them from the source CSV and append to this JSON file
