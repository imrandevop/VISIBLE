from django.core.management.base import BaseCommand
from apps.work_categories.models import WorkCategory, WorkSubCategory

class Command(BaseCommand):
    help = 'Create initial work categories and subcategories'

    def handle(self, *args, **options):
        # Create main categories
        skill_cat = WorkCategory.objects.get_or_create(
            name='skill',
            defaults={
                'display_name': 'Skill',
                'description': 'Skill-based services',
                'sort_order': 1
            }
        )[0]

        vehicle_cat = WorkCategory.objects.get_or_create(
            name='vehicle',
            defaults={
                'display_name': 'Vehicle',
                'description': 'Vehicle-based services',
                'sort_order': 2
            }
        )[0]
        
        business_cat = WorkCategory.objects.get_or_create(
            name='business',
            defaults={
                'display_name': 'Business',
                'description': 'Business services',
                'sort_order': 3
            }
        )[0]
        
        # Create subcategories for Skill
        skill_subcats = [
            ('construction', 'Construction Worker'),
            ('plumber', 'Plumber'),
            ('electrician', 'Electrician'),
            ('painter', 'Painter'),
            ('carpenter', 'Carpenter'),
        ]

        for name, display_name in skill_subcats:
            WorkSubCategory.objects.get_or_create(
                category=skill_cat,
                name=name,
                defaults={'display_name': display_name}
            )
        
        # Create subcategories for Vehicle
        vehicle_subcats = [
            ('taxi', 'Taxi'),
            ('delivery', 'Delivery'),
            ('truck', 'Truck'),
            ('auto', 'Auto Rickshaw'),
        ]

        for name, display_name in vehicle_subcats:
            WorkSubCategory.objects.get_or_create(
                category=vehicle_cat,
                name=name,
                defaults={'display_name': display_name}
            )
        
        # Create subcategories for Business
        business_subcats = [
            ('retail', 'Retail Business'),
            ('food', 'Food Service'),
            ('consulting', 'Consulting'),
            ('online', 'Online Business'),
        ]
        
        for name, display_name in business_subcats:
            WorkSubCategory.objects.get_or_create(
                category=business_cat,
                name=name,
                defaults={'display_name': display_name}
            )
        
        self.stdout.write(
            self.style.SUCCESS('Successfully created work categories and subcategories')
        )