from django.core.management.base import BaseCommand
from apps.work_categories.models import WorkCategory, WorkSubCategory

class Command(BaseCommand):
    help = 'Create initial work categories and subcategories'

    def handle(self, *args, **options):
        # Create main categories
        worker_cat = WorkCategory.objects.get_or_create(
            name='worker',
            defaults={
                'display_name': 'Worker',
                'description': 'General workers and laborers',
                'sort_order': 1
            }
        )[0]
        
        driver_cat = WorkCategory.objects.get_or_create(
            name='driver',
            defaults={
                'display_name': 'Driver',
                'description': 'Professional drivers',
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
        
        # Create subcategories for Worker
        worker_subcats = [
            ('construction', 'Construction Worker'),
            ('plumber', 'Plumber'),
            ('electrician', 'Electrician'),
            ('painter', 'Painter'),
            ('carpenter', 'Carpenter'),
        ]
        
        for name, display_name in worker_subcats:
            WorkSubCategory.objects.get_or_create(
                category=worker_cat,
                name=name,
                defaults={'display_name': display_name}
            )
        
        # Create subcategories for Driver
        driver_subcats = [
            ('taxi', 'Taxi Driver'),
            ('delivery', 'Delivery Driver'),
            ('truck', 'Truck Driver'),
            ('auto', 'Auto Rickshaw Driver'),
        ]
        
        for name, display_name in driver_subcats:
            WorkSubCategory.objects.get_or_create(
                category=driver_cat,
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